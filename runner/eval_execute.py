"""Target attempt execution and explicit retry orchestration.

This module deliberately stays above the existing host ``invoke`` boundary:
one attempt calls ``runner.cli.invoke`` exactly once.  It does not construct
OCI commands and it does not implement runtime-evidence readiness semantics.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, TypeAlias, cast

from runner.cli import RunnerError, invoke, validate_container_result
from runner.eval_types import (
    AttemptFailure,
    AttemptRecord,
    FailurePlane,
    InvocationSpec,
    JsonValue,
    RetryDecision,
    RetryPolicy,
)


RESULT_SCHEMA = "opencode-eval-runner/v1"

InvokeAdapter: TypeAlias = Callable[[InvocationSpec], tuple[int, object]]
SleepFn: TypeAlias = Callable[[float], None]


class EvidenceReadinessResult(Protocol):
    """Narrow bridge for the sibling canonical evidence-readiness API.

    Reconciliation can pass the sibling ``EvidenceReadiness`` result directly;
    this worker intentionally does not duplicate boundary/field semantics.
    """

    status: str
    reasons: tuple[str, ...]


EvidenceReadinessEvaluator: TypeAlias = Callable[
    [Mapping[str, object]], EvidenceReadinessResult
]


@dataclass(frozen=True)
class TargetExecutionOutcome:
    """Target attempt history plus explicit retry decisions and provenance."""

    spec: InvocationSpec
    attempts: tuple[AttemptRecord, ...]
    retry_decisions: tuple[RetryDecision, ...]
    readiness: EvidenceReadinessResult | None

    @property
    def final_attempt(self) -> AttemptRecord:
        if not self.attempts:
            raise RuntimeError("target execution has no attempts")
        return self.attempts[-1]

    @property
    def succeeded(self) -> bool:
        return self.final_attempt.failure is None


@dataclass(frozen=True)
class NoRetryPolicy:
    """Explicit policy that never retries."""

    def decide(
        self,
        attempts: tuple[AttemptRecord, ...],
        latest: AttemptRecord,
    ) -> RetryDecision:
        return RetryDecision(False, "retry disabled by policy", 0.0)


@dataclass(frozen=True)
class TransientProviderRetryPolicy:
    """Opt-in retry policy for the architecture-approved narrow provider case.

    The classifier recognizes only the exact ``provider.no-route`` +
    ``Model unavailable`` infrastructure class. Replay is still permitted only
    when authoritative runtime evidence proves that no invocation was observed.
    This policy cannot override that safety check.
    """

    delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        _validate_delay(self.delay_seconds)

    def decide(
        self,
        attempts: tuple[AttemptRecord, ...],
        latest: AttemptRecord,
    ) -> RetryDecision:
        failure = latest.failure
        if (
            failure is not None
            and failure.plane == "infrastructure"
            and failure.code == "provider_transient_unavailable"
            and failure.retry_safe
        ):
            return RetryDecision(
                True,
                "explicit transient-provider retry",
                self.delay_seconds,
            )
        return RetryDecision(False, "failure is not a transient provider outage", 0.0)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _path_arg(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def invoke_once(spec: InvocationSpec) -> tuple[int, object]:
    """Execute exactly one existing host invoke call for ``spec``.

    Prompt/system materialization is orchestration glue only. OCI construction,
    transport execution, timeout mechanics, result parsing, and runtime-evidence
    validation remain owned by ``runner.cli.invoke``.
    """

    with tempfile.TemporaryDirectory(prefix="opencode-eval-engine-") as temp:
        root = Path(temp)
        prompt_file = root / "prompt.txt"
        system_file = root / "system.txt"
        output_file = root / "result.json"
        prompt_file.write_text(spec.prompt, encoding="utf-8")
        if spec.system is not None:
            system_file.write_text(spec.system, encoding="utf-8")

        args = argparse.Namespace(
            transport=spec.transport,
            engine=spec.engine,
            network=spec.network,
            image=spec.image,
            workspace=str(spec.workspace),
            workspace_mode=spec.workspace_mode,
            mount=[],
            model=spec.model,
            reasoning=spec.reasoning,
            agent=spec.agent,
            skill=spec.skill,
            expected_plugin=spec.expected_plugin,
            prompt_file=str(prompt_file),
            system_file=str(system_file) if spec.system is not None else None,
            output=str(output_file),
            auth=_path_arg(spec.auth),
            config=_path_arg(spec.config),
            models_catalog=_path_arg(spec.models_catalog),
            database=_path_arg(spec.database),
            config_root=_path_arg(spec.config_root),
            env=list(spec.env_names),
            timeout_seconds=spec.timeout_seconds,
            container_timeout=spec.container_timeout,
            print_result=False,
        )

        host_exit_code = invoke(args)
        if not output_file.is_file():
            raise RunnerError("invoke completed without a result file")
        try:
            result = json.loads(output_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RunnerError(f"invoke result file is invalid JSON: {exc}") from exc
        return host_exit_code, result


def _failure(
    plane: FailurePlane,
    code: str,
    message: str,
    *,
    retry_safe: bool,
) -> AttemptFailure:
    return AttemptFailure(
        plane=plane,
        code=code,
        message=message,
        retry_safe=retry_safe,
    )


def _short_result_message(result: Mapping[str, object], fallback: str) -> str:
    stderr = result.get("stderr")
    if isinstance(stderr, str) and stderr.strip():
        return stderr.strip()[:1000]
    return fallback


def _runtime_evidence_proves_no_invocation(result: Mapping[str, object]) -> bool:
    """Use authoritative runtime evidence to prove no invocation was observed."""

    evidence = result.get("runtime_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("status") != "complete":
        return False
    if evidence.get("observations") != []:
        return False
    coverage = evidence.get("coverage")
    if not isinstance(coverage, Mapping) or coverage.get("process_state") != "completed":
        return False
    closed = coverage.get("observation_closed")
    starts = coverage.get("starts")
    return (
        isinstance(closed, Mapping)
        and closed.get("state") == "available"
        and closed.get("value") is True
        and isinstance(starts, Mapping)
        and starts.get("state") == "available"
        and starts.get("value") == 0
    )


def _is_transient_provider_unavailable(result: Mapping[str, object]) -> bool:
    stderr = result.get("stderr")
    exit_code = result.get("exit_code")
    return (
        type(exit_code) is int
        and exit_code != 0
        and isinstance(stderr, str)
        and "provider.no-route" in stderr
        and "Model unavailable" in stderr
    )


def _validate_result_v1(
    raw: object,
    spec: InvocationSpec,
) -> tuple[dict[str, JsonValue] | None, AttemptFailure | None]:
    try:
        result = validate_container_result(raw)
    except RunnerError as exc:
        return None, _failure(
            "infrastructure",
            "invoke_invalid_result",
            str(exc),
            retry_safe=False,
        )

    invalid: str | None = None
    if result.get("schema") != RESULT_SCHEMA:
        invalid = f"result schema must be {RESULT_SCHEMA!r}"
    elif result.get("transport") != spec.transport:
        invalid = "result transport does not match InvocationSpec"
    elif result.get("model") != spec.model:
        invalid = "result model does not match InvocationSpec"
    elif not isinstance(result.get("reasoning"), str) or not result.get("reasoning"):
        invalid = "result reasoning provenance must be a non-empty string"
    elif spec.reasoning is not None and result.get("reasoning") != spec.reasoning:
        invalid = "result reasoning does not match explicit InvocationSpec reasoning"
    elif not isinstance(result.get("reasoning_source"), str) or not result.get(
        "reasoning_source"
    ):
        invalid = "result reasoning_source provenance must be a non-empty string"
    elif type(result.get("exit_code")) is not int:
        invalid = "result exit_code must be an integer"
    elif "timed_out" in result and type(result.get("timed_out")) is not bool:
        invalid = "result timed_out must be a boolean when present"
    elif "infrastructure_error" in result and type(
        result.get("infrastructure_error")
    ) is not bool:
        invalid = "result infrastructure_error must be a boolean when present"

    if invalid is not None:
        return None, _failure(
            "infrastructure",
            "invoke_invalid_result",
            invalid,
            retry_safe=False,
        )

    return cast(dict[str, JsonValue], result), None


def _classify_result(
    result: dict[str, JsonValue],
    host_exit_code: int,
) -> AttemptFailure | None:
    # The narrow provider.no-route signature is a transport availability
    # failure even when the low-level result represents it as a non-zero model
    # process exit. No other product failure is promoted to infrastructure.
    if _is_transient_provider_unavailable(cast(Mapping[str, object], result)):
        return _failure(
            "infrastructure",
            "provider_transient_unavailable",
            _short_result_message(
                cast(Mapping[str, object], result),
                "provider route is temporarily unavailable",
            ),
            retry_safe=_runtime_evidence_proves_no_invocation(
                cast(Mapping[str, object], result)
            ),
        )

    # The container wrapper uses a non-zero host exit for failures that occur
    # outside a normal product result. Product failures remain inside result/v1.
    if result.get("infrastructure_error") is True:
        return _failure(
            "infrastructure",
            "invoke_preflight_failed",
            _short_result_message(
                cast(Mapping[str, object], result),
                "invoke reported an infrastructure error",
            ),
            retry_safe=False,
        )

    if host_exit_code != 0:
        return _failure(
            "infrastructure",
            "invoke_host_error",
            f"invoke host process exited with code {host_exit_code}",
            retry_safe=False,
        )

    exit_code = cast(int, result["exit_code"])
    timed_out = result.get("timed_out") is True or exit_code == 124
    if timed_out:
        return _failure(
            "product",
            "product_timeout",
            _short_result_message(
                cast(Mapping[str, object], result),
                "target invocation reached its inner timeout",
            ),
            retry_safe=False,
        )
    if exit_code != 0:
        return _failure(
            "product",
            "product_error",
            _short_result_message(
                cast(Mapping[str, object], result),
                f"target invocation exited with code {exit_code}",
            ),
            retry_safe=False,
        )
    return None


def _classify_readiness(
    readiness: EvidenceReadinessResult,
) -> AttemptFailure | None:
    status = readiness.status
    if status == "ready":
        return None
    code = {
        "incomplete": "evidence_incomplete",
        "unsupported": "evidence_unsupported",
        "invalid": "evidence_invalid",
    }.get(status)
    if code is None:
        raise ValueError(f"evidence readiness returned unknown status: {status!r}")
    message = "; ".join(readiness.reasons) or f"runtime evidence is {status}"
    # A non-ready result follows actual target execution. Without a separate,
    # authoritative replay-safety proof it is not safe to repeat the target.
    return _failure("evidence", code, message, retry_safe=False)


def _validate_delay(delay: float) -> None:
    if isinstance(delay, bool) or not isinstance(delay, (int, float)):
        raise ValueError("retry delay_seconds must be a number")
    if not math.isfinite(float(delay)) or delay < 0:
        raise ValueError("retry delay_seconds must be finite and >= 0")


def _validate_max_attempts(max_attempts: int) -> None:
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise ValueError("max_attempts must be an integer")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")


def _safe_policy_decision(
    policy: RetryPolicy,
    attempts: tuple[AttemptRecord, ...],
    latest: AttemptRecord,
) -> RetryDecision:
    try:
        decision = policy.decide(attempts, latest)
    except Exception as exc:
        return RetryDecision(
            False,
            f"retry policy failed: {type(exc).__name__}: {exc}",
            0.0,
        )
    if not isinstance(decision, RetryDecision):
        return RetryDecision(False, "retry policy returned an invalid decision", 0.0)
    try:
        _validate_delay(decision.delay_seconds)
    except ValueError as exc:
        return RetryDecision(False, f"retry policy rejected: {exc}", 0.0)
    if not isinstance(decision.reason, str) or not decision.reason.strip():
        return RetryDecision(False, "retry policy returned an empty reason", 0.0)
    return decision


def run_target_attempts(
    spec: InvocationSpec,
    *,
    retry_policy: RetryPolicy | None = None,
    max_attempts: int = 1,
    invoker: InvokeAdapter = invoke_once,
    evidence_readiness: EvidenceReadinessEvaluator | None = None,
    sleep: SleepFn = time.sleep,
) -> TargetExecutionOutcome:
    """Run a target with explicit, bounded, replay-safe retry orchestration."""

    _validate_max_attempts(max_attempts)
    attempts: list[AttemptRecord] = []
    retry_decisions: list[RetryDecision] = []
    final_readiness: EvidenceReadinessResult | None = None

    for attempt_number in range(1, max_attempts + 1):
        started_at = _utc_now()
        started = time.monotonic()
        host_exit_code: int | None = None
        result: dict[str, JsonValue] | None = None
        failure: AttemptFailure | None = None
        readiness: EvidenceReadinessResult | None = None

        try:
            host_exit_code, raw_result = invoker(spec)
            if isinstance(host_exit_code, bool) or not isinstance(host_exit_code, int):
                failure = _failure(
                    "infrastructure",
                    "invoke_host_error",
                    "invoke adapter returned a non-integer host exit code",
                    retry_safe=False,
                )
            else:
                result, failure = _validate_result_v1(raw_result, spec)
            if result is not None and failure is None:
                failure = _classify_result(result, host_exit_code)
            if (
                result is not None
                and failure is None
                and evidence_readiness is not None
            ):
                runtime_evidence = result.get("runtime_evidence")
                if not isinstance(runtime_evidence, Mapping):
                    failure = _failure(
                        "infrastructure",
                        "invoke_invalid_result",
                        "validated result has no runtime_evidence mapping",
                        retry_safe=False,
                    )
                else:
                    try:
                        readiness = evidence_readiness(
                            cast(Mapping[str, object], runtime_evidence)
                        )
                        failure = _classify_readiness(readiness)
                    except Exception as exc:
                        failure = _failure(
                            "infrastructure",
                            "evidence_readiness_check_failed",
                            f"evidence readiness evaluation failed: {exc}",
                            retry_safe=False,
                        )
        except subprocess.TimeoutExpired as exc:
            failure = _failure(
                "infrastructure",
                "invoke_outer_timeout",
                f"invoke exceeded outer container timeout: {exc}",
                retry_safe=False,
            )
        except RunnerError as exc:
            message = str(exc)
            code = (
                "invoke_invalid_result"
                if "result" in message.lower()
                else "invoke_preflight_failed"
            )
            failure = _failure(
                "infrastructure",
                code,
                message,
                retry_safe=False,
            )
        except (OSError, ValueError, TypeError) as exc:
            failure = _failure(
                "infrastructure",
                "invoke_host_error",
                f"{type(exc).__name__}: {exc}",
                retry_safe=False,
            )

        duration_seconds = max(0.0, time.monotonic() - started)
        record = AttemptRecord(
            attempt=attempt_number,
            started_at=started_at,
            duration_seconds=duration_seconds,
            host_exit_code=host_exit_code,
            result=result,
            failure=failure,
        )
        attempts.append(record)
        if readiness is not None:
            final_readiness = readiness

        if failure is None:
            break

        if attempt_number >= max_attempts:
            retry_decisions.append(
                RetryDecision(False, "maximum attempts reached", 0.0)
            )
            break

        # Replay safety is a fact from classification, not policy permission.
        # Policy never gets a chance to override a fail-closed safety result.
        if not failure.retry_safe:
            retry_decisions.append(
                RetryDecision(
                    False,
                    f"retry blocked: {failure.code} is not replay-safe",
                    0.0,
                )
            )
            break

        if retry_policy is None:
            retry_decisions.append(
                RetryDecision(False, "no retry policy configured", 0.0)
            )
            break

        decision = _safe_policy_decision(retry_policy, tuple(attempts), record)
        retry_decisions.append(decision)
        if not decision.retry:
            break
        if decision.delay_seconds:
            sleep(decision.delay_seconds)

    return TargetExecutionOutcome(
        spec=spec,
        attempts=tuple(attempts),
        retry_decisions=tuple(retry_decisions),
        readiness=final_readiness,
    )
