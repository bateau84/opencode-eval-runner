"""Generic comparison contract for completed baseline/candidate outcomes.

The generic engine owns only comparison input readiness and output-contract
validation. Projects own what a comparison means, including any score, delta,
improvement, regression, or value classification.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeAlias

from runner.eval_types import EvalClassification, JsonValue


COMPARISON_RESULT_SCHEMA = "opencode-eval-runner/eval-comparison/v1"
ComparisonStatus: TypeAlias = Literal["compared", "non-evidence", "invalid"]


class CompletedEvaluationOutcome(Protocol):
    """Minimum completed-side surface needed by generic comparison mechanics."""

    classification: EvalClassification


@dataclass(frozen=True)
class ComparisonDecision:
    """Project-owned meaning for a valid baseline/candidate comparison."""

    classification: str
    summary: str
    data: JsonValue


@dataclass(frozen=True)
class ComparisonFailure:
    """Explicit generic failure to obtain a valid comparison decision."""

    code: str
    message: str


@dataclass(frozen=True)
class ComparisonResult:
    """Generic structured envelope around a project-owned comparison decision."""

    status: ComparisonStatus
    baseline_classification: EvalClassification | None
    candidate_classification: EvalClassification | None
    decision: ComparisonDecision | None
    failure: ComparisonFailure | None


class EvalComparisonExtension(Protocol):
    """Optional project/profile extension for paired evaluation comparison."""

    def compare_pair(
        self,
        baseline: CompletedEvaluationOutcome,
        candidate: CompletedEvaluationOutcome,
    ) -> ComparisonDecision: ...


def _strict_json_value(value: Any, where: str) -> None:
    if value is None or type(value) in {bool, int, str}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{where} must not contain non-finite numbers")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _strict_json_value(item, f"{where}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{where} object keys must be strings")
            _strict_json_value(item, f"{where}.{key}")
        return
    raise TypeError(f"{where} must contain only strict JSON-compatible values")


def _side_classification(
    side: str,
    outcome: CompletedEvaluationOutcome,
) -> EvalClassification:
    classification = getattr(outcome, "classification", None)
    if classification not in {"pass", "fail", "non-evidence"}:
        raise ValueError(
            f"{side} outcome must have classification pass, fail, or non-evidence"
        )
    return classification


def _validated_decision(value: object) -> ComparisonDecision:
    if not isinstance(value, ComparisonDecision):
        raise TypeError("comparison callback must return ComparisonDecision")
    if type(value.classification) is not str or not value.classification.strip():
        raise ValueError("comparison classification must be a non-empty string")
    if type(value.summary) is not str:
        raise TypeError("comparison summary must be a string")
    _strict_json_value(value.data, "comparison data")
    return value


def _invalid(
    *,
    baseline: EvalClassification | None,
    candidate: EvalClassification | None,
    code: str,
    message: str,
) -> ComparisonResult:
    return ComparisonResult(
        status="invalid",
        baseline_classification=baseline,
        candidate_classification=candidate,
        decision=None,
        failure=ComparisonFailure(code=code, message=message),
    )


def compare_completed_outcomes(
    extension: EvalComparisonExtension,
    *,
    baseline: CompletedEvaluationOutcome,
    candidate: CompletedEvaluationOutcome,
) -> ComparisonResult:
    """Compare completed paired outcomes without inventing project semantics.

    A side classified as ``non-evidence`` blocks comparison before the project
    callback runs. The generic layer never substitutes a score or numeric zero
    for an unusable side.
    """

    baseline_classification: EvalClassification | None = None
    candidate_classification: EvalClassification | None = None
    try:
        baseline_classification = _side_classification("baseline", baseline)
        candidate_classification = _side_classification("candidate", candidate)
    except Exception as exc:
        return _invalid(
            baseline=baseline_classification,
            candidate=candidate_classification,
            code="comparison_input_invalid",
            message=f"{type(exc).__name__}: {exc}",
        )

    if (
        baseline_classification == "non-evidence"
        or candidate_classification == "non-evidence"
    ):
        sides = []
        if baseline_classification == "non-evidence":
            sides.append("baseline")
        if candidate_classification == "non-evidence":
            sides.append("candidate")
        return ComparisonResult(
            status="non-evidence",
            baseline_classification=baseline_classification,
            candidate_classification=candidate_classification,
            decision=None,
            failure=ComparisonFailure(
                code="comparison_side_non_evidence",
                message=f"comparison unavailable: {', '.join(sides)} side is non-evidence",
            ),
        )

    callback = getattr(extension, "compare_pair", None)
    if not callable(callback):
        return _invalid(
            baseline=baseline_classification,
            candidate=candidate_classification,
            code="comparison_callback_missing",
            message="paired comparison extension must define compare_pair",
        )

    try:
        decision = _validated_decision(callback(baseline, candidate))
    except Exception as exc:
        return _invalid(
            baseline=baseline_classification,
            candidate=candidate_classification,
            code="comparison_output_invalid",
            message=f"{type(exc).__name__}: {exc}",
        )

    return ComparisonResult(
        status="compared",
        baseline_classification=baseline_classification,
        candidate_classification=candidate_classification,
        decision=decision,
        failure=None,
    )


def comparison_result_envelope(result: ComparisonResult) -> dict[str, JsonValue]:
    """Serialize a comparison result for durable paired artifacts."""

    if not isinstance(result, ComparisonResult):
        raise TypeError("comparison result must be ComparisonResult")

    decision: dict[str, JsonValue] | None = None
    if result.decision is not None:
        decision = {
            "classification": result.decision.classification,
            "summary": result.decision.summary,
            "data": result.decision.data,
        }

    failure: dict[str, JsonValue] | None = None
    if result.failure is not None:
        failure = {
            "code": result.failure.code,
            "message": result.failure.message,
        }

    envelope: dict[str, JsonValue] = {
        "schema": COMPARISON_RESULT_SCHEMA,
        "status": result.status,
        "baseline_classification": result.baseline_classification,
        "candidate_classification": result.candidate_classification,
        "decision": decision,
        "failure": failure,
    }
    _strict_json_value(envelope, "comparison result")
    return envelope


__all__ = [
    "COMPARISON_RESULT_SCHEMA",
    "ComparisonDecision",
    "ComparisonFailure",
    "ComparisonResult",
    "ComparisonStatus",
    "CompletedEvaluationOutcome",
    "EvalComparisonExtension",
    "compare_completed_outcomes",
    "comparison_result_envelope",
]
