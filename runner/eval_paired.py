"""Generic baseline/candidate execution over the normal eval lifecycle.

This module owns pairing mechanics only. Project code decides what baseline and
candidate mean and, in the comparison extension, how their outcomes are compared.
No score, delta, trap, skill-loading, or aggregate verdict semantics live here.
"""
from __future__ import annotations

import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from runner.eval_artifacts import (
    EVAL_PAIRED_ARTIFACT_SCHEMA,
    attach_paired_artifact_evidence_id,
    calculate_pair_id,
)
from runner.eval_classification import EvalProfileCallbacks
from runner.eval_engine import (
    EvaluationResult,
    build_eval_artifact,
    run_evaluation_phase,
)
from runner.eval_evidence import EvidenceRequirement
from runner.eval_execute import InvokeAdapter, SleepFn, invoke_once
from runner.eval_types import InvocationSpec, JsonValue, NormalizedCase, RetryPolicy


PairedSideName: TypeAlias = Literal["baseline", "candidate"]
PairedExecutionMode: TypeAlias = Literal["sequential", "parallel"]


@dataclass(frozen=True)
class PairedExecutionPolicy:
    """Explicit side scheduling policy.

    order is meaningful for sequential execution and is also the deterministic
    submission/artifact order for parallel execution.
    """

    mode: PairedExecutionMode = "sequential"
    order: tuple[PairedSideName, PairedSideName] = ("baseline", "candidate")

    def __post_init__(self) -> None:
        if self.mode not in {"sequential", "parallel"}:
            raise ValueError(f"unsupported paired execution mode: {self.mode!r}")
        if (
            not isinstance(self.order, tuple)
            or len(self.order) != 2
            or set(self.order) != {"baseline", "candidate"}
        ):
            raise ValueError(
                "paired execution order must contain baseline and candidate exactly once"
            )


@dataclass(frozen=True)
class PairedSideExecution:
    """Inputs for one normal evaluation phase inside a pair."""

    case: NormalizedCase
    prepared: Any
    target_spec: InvocationSpec
    evidence_requirement: EvidenceRequirement
    profile: EvalProfileCallbacks
    project_metadata: Mapping[str, JsonValue] | None = None
    target_retry_policy: RetryPolicy | None = None
    target_max_attempts: int = 1
    judge_retry_policy: RetryPolicy | None = None
    judge_max_attempts: int = 1


@dataclass(frozen=True)
class PairedEvaluationResult:
    """Completed baseline and candidate phases with one shared identity."""

    run_id: str
    case_id: str
    iteration: int
    policy: PairedExecutionPolicy
    baseline: EvaluationResult
    candidate: EvaluationResult

    @property
    def pair_id(self) -> str:
        return calculate_pair_id(self.run_id, self.case_id, self.iteration)


def _validate_pair_inputs(
    *,
    run_id: str,
    iteration: int,
    baseline: PairedSideExecution,
    candidate: PairedSideExecution,
) -> str:
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 1:
        raise ValueError("iteration must be an integer >= 1")

    if not isinstance(baseline.case, NormalizedCase) or not isinstance(
        candidate.case, NormalizedCase
    ):
        raise TypeError("paired side case must be a NormalizedCase")
    baseline_case = baseline.case.id
    candidate_case = candidate.case.id
    if not baseline_case:
        raise ValueError("baseline case must have a non-empty id")
    if candidate_case != baseline_case:
        raise ValueError(
            "baseline and candidate must share one normalized case identity"
        )
    return baseline_case


def _run_side(
    side: PairedSideExecution,
    *,
    target_invoker: InvokeAdapter,
    judge_invoker: InvokeAdapter,
    sleep: SleepFn,
) -> EvaluationResult:
    return run_evaluation_phase(
        case=side.case,
        prepared=side.prepared,
        target_spec=side.target_spec,
        evidence_requirement=side.evidence_requirement,
        profile=side.profile,
        project_metadata=side.project_metadata,
        target_retry_policy=side.target_retry_policy,
        target_max_attempts=side.target_max_attempts,
        target_invoker=target_invoker,
        target_sleep=sleep,
        judge_retry_policy=side.judge_retry_policy,
        judge_max_attempts=side.judge_max_attempts,
        judge_invoker=judge_invoker,
        judge_sleep=sleep,
    )


def run_paired_evaluation(
    *,
    run_id: str,
    iteration: int,
    baseline: PairedSideExecution,
    candidate: PairedSideExecution,
    policy: PairedExecutionPolicy = PairedExecutionPolicy(),
    target_invoker: InvokeAdapter = invoke_once,
    judge_invoker: InvokeAdapter = invoke_once,
    sleep: SleepFn = time.sleep,
) -> PairedEvaluationResult:
    """Run both sides using the same normal evaluation phase primitive."""

    case_id = _validate_pair_inputs(
        run_id=run_id,
        iteration=iteration,
        baseline=baseline,
        candidate=candidate,
    )
    sides = {"baseline": baseline, "candidate": candidate}
    outcomes: dict[str, EvaluationResult] = {}

    if policy.mode == "sequential":
        for side_name in policy.order:
            outcomes[side_name] = _run_side(
                sides[side_name],
                target_invoker=target_invoker,
                judge_invoker=judge_invoker,
                sleep=sleep,
            )
    else:
        with ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="eval-pair",
        ) as pool:
            futures = {
                side_name: pool.submit(
                    _run_side,
                    sides[side_name],
                    target_invoker=target_invoker,
                    judge_invoker=judge_invoker,
                    sleep=sleep,
                )
                for side_name in policy.order
            }
            for side_name in policy.order:
                outcomes[side_name] = futures[side_name].result()

    return PairedEvaluationResult(
        run_id=run_id,
        case_id=case_id,
        iteration=iteration,
        policy=policy,
        baseline=outcomes["baseline"],
        candidate=outcomes["candidate"],
    )


def build_paired_eval_artifact(result: PairedEvaluationResult) -> dict[str, Any]:
    """Build a paired artifact without inventing comparison semantics."""

    for side_name, side in (
        ("baseline", result.baseline),
        ("candidate", result.candidate),
    ):
        if side.case.id != result.case_id:
            raise ValueError(
                f"{side_name} result case id does not match paired identity"
            )

    artifact = {
        "schema": EVAL_PAIRED_ARTIFACT_SCHEMA,
        "run_id": result.run_id,
        "case": result.case_id,
        "iteration": result.iteration,
        "pair_id": result.pair_id,
        "execution_policy": {
            "mode": result.policy.mode,
            "order": list(result.policy.order),
        },
        "sides": {
            "baseline": build_eval_artifact(
                result.baseline,
                run_id=result.run_id,
                iteration=result.iteration,
            ),
            "candidate": build_eval_artifact(
                result.candidate,
                run_id=result.run_id,
                iteration=result.iteration,
            ),
        },
    }
    return attach_paired_artifact_evidence_id(artifact)
