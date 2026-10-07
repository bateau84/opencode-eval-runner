"""Minimal Task-5 composition for one generic evaluation case.

This module composes already-normalized target execution, project-owned checks and
judge callbacks, generic judge execution, classification, and Task-3 artifacts.
It deliberately does not discover cases, expose a public eval CLI, define a
semantic assertion language, or own project-specific behavior.
"""
from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from runner.eval_artifacts import (
    EVAL_ARTIFACT_SCHEMA,
    attach_artifact_evidence_id,
    canonical_json_bytes,
)
from runner.eval_classification import EvalProfileCallbacks, classify_evaluation
from runner.eval_evidence import EvidenceRequirement
from runner.eval_execute import (
    InvokeAdapter,
    JudgeExecutionOutcome,
    SleepFn,
    TargetExecutionOutcome,
    invoke_once,
    run_judge_attempts,
    run_target_attempts,
)
from runner.eval_types import (
    AttemptFailure,
    AttemptRecord,
    CheckOutcome,
    EvalClassification,
    InvocationSpec,
    JsonValue,
    NormalizedCase,
    RetryDecision,
    RetryPolicy,
    SemanticDecision,
)


@dataclass(frozen=True)
class EvaluationResult:
    """Normalized one-case result before durable run/case identity is attached."""

    case: NormalizedCase
    classification: EvalClassification
    target: TargetExecutionOutcome
    deterministic_checks: tuple[CheckOutcome, ...]
    judge_required: bool
    judge: JudgeExecutionOutcome | None
    judge_contract_failure: AttemptFailure | None
    semantic: SemanticDecision | None
    project_metadata: dict[str, JsonValue]


def _contract_failure(code: str, message: str) -> AttemptFailure:
    return AttemptFailure(
        plane="infrastructure",
        code=code,
        message=message,
        retry_safe=False,
    )


def _non_evidence_check(code: str, message: str) -> CheckOutcome:
    return CheckOutcome(
        name=code,
        status="non-evidence",
        reason=message,
        metadata={},
    )


def _validated_semantic(value: object) -> SemanticDecision:
    if not isinstance(value, SemanticDecision):
        raise TypeError("profile parse_judge must return SemanticDecision")
    if value.status not in {"pass", "fail"}:
        raise ValueError(f"unsupported semantic status: {value.status!r}")
    if not isinstance(value.summary, str):
        raise TypeError("semantic summary must be a string")
    canonical_json_bytes(value.data)
    return value


def evaluate_target_outcome(
    *,
    case: NormalizedCase,
    prepared: Any,
    target: TargetExecutionOutcome,
    profile: EvalProfileCallbacks,
    project_metadata: Mapping[str, JsonValue] | None = None,
    judge_retry_policy: RetryPolicy | None = None,
    judge_max_attempts: int = 1,
    judge_invoker: InvokeAdapter = invoke_once,
    judge_sleep: SleepFn = time.sleep,
) -> EvaluationResult:
    """Complete deterministic/judge/classification phases for one target outcome.

    The function consumes the canonical Task-4 TargetExecutionOutcome and, when
    the profile requests a judge, calls run_judge_attempts so the canonical
    Task-5 JudgeExecutionOutcome is the only judge execution representation.

    Project callback/contract failures fail closed as non-evidence. A successful
    judge execution remains preserved as such even when project parsing rejects
    its output; the parse/contract failure is recorded separately.
    """

    target_attempt = target.final_attempt
    readiness = target.readiness
    target_usable = (
        target_attempt.failure is None
        and readiness is not None
        and readiness.status == "ready"
    )

    checks: tuple[CheckOutcome, ...] = ()
    judge_required = False
    judge: JudgeExecutionOutcome | None = None
    judge_contract_failure: AttemptFailure | None = None
    semantic: SemanticDecision | None = None

    if target_usable:
        try:
            raw_checks = tuple(
                profile.deterministic_checks(
                    case,
                    prepared,
                    target_attempt,
                    readiness,
                )
            )
            if not all(isinstance(check, CheckOutcome) for check in raw_checks):
                raise TypeError(
                    "profile deterministic_checks must return CheckOutcome values"
                )
            checks = raw_checks
        except Exception as exc:
            checks = (
                _non_evidence_check(
                    "deterministic_checks_invalid",
                    f"{type(exc).__name__}: {exc}",
                ),
            )

        judge_spec: InvocationSpec | None
        try:
            judge_spec = profile.judge_spec(
                case,
                prepared,
                target_attempt,
                checks,
            )
            if judge_spec is not None and not isinstance(judge_spec, InvocationSpec):
                raise TypeError("profile judge_spec must return InvocationSpec or None")
        except Exception as exc:
            judge_required = True
            judge_spec = None
            judge_contract_failure = _contract_failure(
                "judge_spec_invalid",
                f"{type(exc).__name__}: {exc}",
            )

        if judge_spec is not None:
            judge_required = True
            judge = run_judge_attempts(
                judge_spec,
                retry_policy=judge_retry_policy,
                max_attempts=judge_max_attempts,
                invoker=judge_invoker,
                sleep=judge_sleep,
            )
            if judge.final_attempt.failure is None:
                try:
                    semantic = _validated_semantic(
                        profile.parse_judge(
                            case,
                            prepared,
                            judge.final_attempt,
                        )
                    )
                except Exception as exc:
                    judge_contract_failure = _contract_failure(
                        "judge_contract_invalid",
                        f"{type(exc).__name__}: {exc}",
                    )

    judge_failure = judge_contract_failure
    if judge is not None and judge.final_attempt.failure is not None:
        judge_failure = judge.final_attempt.failure

    classification = classify_evaluation(
        target_failure=target_attempt.failure,
        target_readiness=readiness,
        deterministic_checks=checks,
        judge_required=judge_required,
        judge_failure=judge_failure,
        semantic=semantic,
    )

    metadata = dict(case.metadata) if project_metadata is None else dict(project_metadata)
    return EvaluationResult(
        case=case,
        classification=classification,
        target=target,
        deterministic_checks=checks,
        judge_required=judge_required,
        judge=judge,
        judge_contract_failure=judge_contract_failure,
        semantic=semantic,
        project_metadata=metadata,
    )


def run_evaluation_phase(
    *,
    case: NormalizedCase,
    prepared: Any,
    target_spec: InvocationSpec,
    evidence_requirement: EvidenceRequirement,
    profile: EvalProfileCallbacks,
    project_metadata: Mapping[str, JsonValue] | None = None,
    target_retry_policy: RetryPolicy | None = None,
    target_max_attempts: int = 1,
    target_invoker: InvokeAdapter = invoke_once,
    target_sleep: SleepFn = time.sleep,
    judge_retry_policy: RetryPolicy | None = None,
    judge_max_attempts: int = 1,
    judge_invoker: InvokeAdapter = invoke_once,
    judge_sleep: SleepFn = time.sleep,
) -> EvaluationResult:
    """Run the reusable target/readiness/checks/judge/classification phase.

    Normal eval mode and paired eval mode share this primitive so paired
    orchestration cannot silently diverge from the proven single-case lifecycle.
    Project preparation and invocation construction stay outside this helper.
    """

    if not isinstance(target_spec, InvocationSpec):
        raise TypeError("target_spec must be an InvocationSpec")
    if not isinstance(evidence_requirement, EvidenceRequirement):
        raise TypeError("evidence_requirement must be an EvidenceRequirement")

    target = run_target_attempts(
        target_spec,
        retry_policy=target_retry_policy,
        max_attempts=target_max_attempts,
        invoker=target_invoker,
        evidence_requirement=evidence_requirement,
        sleep=target_sleep,
    )
    return evaluate_target_outcome(
        case=case,
        prepared=prepared,
        target=target,
        profile=profile,
        project_metadata=project_metadata,
        judge_retry_policy=judge_retry_policy,
        judge_max_attempts=judge_max_attempts,
        judge_invoker=judge_invoker,
        judge_sleep=judge_sleep,
    )


def _failure_json(failure: AttemptFailure) -> dict[str, JsonValue]:
    return {
        "plane": failure.plane,
        "code": failure.code,
        "message": failure.message,
        "retry_safe": failure.retry_safe,
    }


def _retry_json(decision: RetryDecision) -> dict[str, JsonValue]:
    return {
        "retry": decision.retry,
        "reason": decision.reason,
        "delay_seconds": decision.delay_seconds,
    }


def _attempts_json(
    attempts: tuple[AttemptRecord, ...],
    retry_decisions: tuple[RetryDecision, ...],
) -> list[JsonValue]:
    values: list[JsonValue] = []
    retry_index = 0
    for attempt in attempts:
        value: dict[str, JsonValue] = {
            "attempt": attempt.attempt,
            "started_at": attempt.started_at,
            "duration_seconds": attempt.duration_seconds,
            "host_exit_code": attempt.host_exit_code,
            "result": attempt.result,
            "failure": (
                _failure_json(attempt.failure)
                if attempt.failure is not None
                else None
            ),
        }
        if attempt.failure is not None and retry_index < len(retry_decisions):
            value["retry_decision"] = _retry_json(retry_decisions[retry_index])
            retry_index += 1
        values.append(value)

    if retry_index != len(retry_decisions):
        raise ValueError("retry decisions do not match failed attempt history")
    return values


def _readiness_json(result: EvaluationResult) -> dict[str, JsonValue]:
    readiness = result.target.readiness
    if readiness is None:
        return {}
    return {
        "status": readiness.status,
        "reasons": list(readiness.reasons),
        "required_boundaries": list(readiness.required_boundaries),
    }


def _check_json(check: CheckOutcome) -> dict[str, JsonValue]:
    return {
        "name": check.name,
        "status": check.status,
        "reason": check.reason,
        "metadata": check.metadata,
    }


def _semantic_json(semantic: SemanticDecision | None) -> dict[str, JsonValue] | None:
    if semantic is None:
        return None
    return {
        "status": semantic.status,
        "summary": semantic.summary,
        "data": semantic.data,
    }


def build_eval_artifact(
    result: EvaluationResult,
    *,
    run_id: str,
    iteration: int,
) -> dict[str, Any]:
    """Build and integrity-seal a Task-3 eval-artifact/v1 envelope."""

    target_seconds = sum(attempt.duration_seconds for attempt in result.target.attempts)
    judge_attempts = result.judge.attempts if result.judge is not None else ()
    judge_retries = (
        result.judge.retry_decisions if result.judge is not None else ()
    )
    judge_seconds = sum(attempt.duration_seconds for attempt in judge_attempts)

    artifact: dict[str, Any] = {
        "schema": EVAL_ARTIFACT_SCHEMA,
        "run_id": run_id,
        "case": result.case.id,
        "iteration": iteration,
        "lane": result.case.lane,
        "classification": result.classification,
        "timing": {
            "started_at": result.target.attempts[0].started_at,
            "duration_seconds": target_seconds + judge_seconds,
            "target_seconds": target_seconds,
            "judge_seconds": judge_seconds,
        },
        "target": {
            "attempts": _attempts_json(
                result.target.attempts,
                result.target.retry_decisions,
            ),
            "evidence_readiness": _readiness_json(result),
        },
        "deterministic_checks": [
            _check_json(check) for check in result.deterministic_checks
        ],
        "judge": {
            "attempts": _attempts_json(judge_attempts, judge_retries),
            "semantic": _semantic_json(result.semantic),
        },
        "project_metadata": result.project_metadata,
    }
    if result.judge_contract_failure is not None:
        artifact["judge"]["contract_failure"] = _failure_json(
            result.judge_contract_failure
        )

    return attach_artifact_evidence_id(artifact)
