"""Canonical runtime-evidence readiness checks for the generic eval engine.

This module decides only whether already-validated runtime evidence is usable for
an explicitly declared assertion scope. Project code still owns observation
selection and behavioral meaning.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from container.runtime_evidence import (
    BOUNDARY_CODE_MODE_EXECUTION,
    BOUNDARY_CODE_MODE_FINALITY,
    BOUNDARY_NATIVE,
    RuntimeEvidenceError,
    validate_runtime_evidence,
)

EvidenceBoundary: TypeAlias = Literal[
    "native",
    "code_mode_execution",
    "code_mode_finality",
]
EvidenceReadinessStatus: TypeAlias = Literal[
    "ready",
    "incomplete",
    "unsupported",
    "invalid",
]

KNOWN_BOUNDARIES: tuple[EvidenceBoundary, ...] = (
    BOUNDARY_NATIVE,
    BOUNDARY_CODE_MODE_EXECUTION,
    BOUNDARY_CODE_MODE_FINALITY,
)


@dataclass(frozen=True)
class EvidenceRequirement:
    """Runtime boundaries required by one project assertion/check."""

    boundaries: tuple[EvidenceBoundary, ...] = ()


@dataclass(frozen=True)
class EvidenceReadiness:
    """Structured evidence-readiness result for an assertion scope."""

    status: EvidenceReadinessStatus
    reasons: tuple[str, ...]
    required_boundaries: tuple[str, ...]


def _readiness(
    status: EvidenceReadinessStatus,
    reasons: tuple[str, ...],
    required_boundaries: tuple[str, ...],
) -> EvidenceReadiness:
    return EvidenceReadiness(
        status=status,
        reasons=reasons,
        required_boundaries=required_boundaries,
    )


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _declared_boundaries(requirement: object) -> tuple[str, ...]:
    if not isinstance(requirement, EvidenceRequirement):
        return ()
    raw = requirement.boundaries
    if not isinstance(raw, tuple):
        return ()
    return _dedupe([value for value in raw if isinstance(value, str) and value])


def _normalize_requirement(
    requirement: object,
) -> tuple[tuple[str, ...] | None, tuple[str, ...]]:
    if not isinstance(requirement, EvidenceRequirement):
        return None, ("requirement_invalid_type",)
    if not isinstance(requirement.boundaries, tuple):
        return None, ("requirement_boundaries_must_be_tuple",)

    normalized: list[str] = []
    reasons: list[str] = []
    for boundary in requirement.boundaries:
        if not isinstance(boundary, str) or not boundary:
            reasons.append("requirement_invalid_boundary")
            continue
        if boundary not in KNOWN_BOUNDARIES:
            reasons.append(f"requirement_invalid_boundary:{boundary}")
            continue
        if boundary not in normalized:
            normalized.append(boundary)

    if reasons:
        return None, _dedupe(reasons)
    return tuple(normalized), ()


def _boundary_reasons(
    boundary_name: str,
    boundary: Mapping[str, Any],
) -> tuple[str, ...]:
    status = boundary.get("status")
    reasons = [f"boundary_{status}:{boundary_name}"]
    issues = boundary.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, str) and issue:
                reasons.append(f"boundary_issue:{boundary_name}:{issue}")
    return _dedupe(reasons)


def _capture_reasons(
    evidence: Mapping[str, Any],
    required_boundaries: tuple[str, ...],
) -> tuple[str, ...]:
    status = evidence.get("status")
    reasons: list[str] = [f"runtime_evidence_{status}"]
    coverage = evidence.get("coverage")
    if not isinstance(coverage, Mapping):
        return tuple(reasons)

    process_state = coverage.get("process_state")
    if isinstance(process_state, str) and process_state != "completed":
        reasons.append(f"process_state:{process_state}")

    losses = coverage.get("losses")
    if isinstance(losses, list):
        for loss in losses:
            if isinstance(loss, str) and loss:
                reasons.append(f"capture_loss:{loss}")

    boundaries = coverage.get("boundaries")
    if isinstance(boundaries, Mapping):
        for name in required_boundaries:
            boundary = boundaries.get(name)
            if isinstance(boundary, Mapping) and boundary.get("status") != "complete":
                reasons.extend(_boundary_reasons(name, boundary))

    return _dedupe(reasons)


def check_evidence_readiness(
    runtime_evidence: Mapping[str, Any],
    requirement: EvidenceRequirement,
) -> EvidenceReadiness:
    """Evaluate capture/boundary readiness for one declared assertion scope.

    The canonical runtime-evidence validator remains the sole schema/accounting
    authority. This function never consults diagnostic/convenience fields and
    therefore cannot backfill missing authoritative runtime facts.
    """

    try:
        evidence = validate_runtime_evidence(runtime_evidence)
    except (RuntimeEvidenceError, TypeError, ValueError) as exc:
        return _readiness(
            "invalid",
            ("runtime_evidence_invalid", f"validation_error:{exc}"),
            _declared_boundaries(requirement),
        )

    required_boundaries, requirement_errors = _normalize_requirement(requirement)
    if required_boundaries is None:
        return _readiness(
            "invalid",
            requirement_errors,
            _declared_boundaries(requirement),
        )

    # No runtime assertion is being made. The evidence object must still be a
    # valid v1 object, but capture health is irrelevant to this check.
    if not required_boundaries:
        return _readiness("ready", (), ())

    overall_status = evidence["status"]
    if overall_status == "invalid":
        return _readiness(
            "invalid",
            _capture_reasons(evidence, required_boundaries),
            required_boundaries,
        )
    if overall_status == "incomplete":
        return _readiness(
            "incomplete",
            _capture_reasons(evidence, required_boundaries),
            required_boundaries,
        )

    boundaries = evidence["coverage"]["boundaries"]
    reasons: list[str] = []
    statuses: list[str] = []
    for name in required_boundaries:
        boundary = boundaries[name]
        status = boundary["status"]
        if status != "complete":
            statuses.append(status)
            reasons.extend(_boundary_reasons(name, boundary))

    if "invalid" in statuses:
        status: EvidenceReadinessStatus = "invalid"
    elif "incomplete" in statuses:
        status = "incomplete"
    elif "unsupported" in statuses:
        status = "unsupported"
    else:
        status = "ready"

    return _readiness(status, _dedupe(reasons), required_boundaries)


def check_field_readiness(field: Mapping[str, Any]) -> EvidenceReadiness:
    """Evaluate readiness of one exact authoritative observation field.

    Project code is responsible for locating the field inside validated
    ``runtime_evidence``. Diagnostic values are intentionally not accepted as
    fallback input.
    """

    if not isinstance(field, Mapping):
        return _readiness("invalid", ("field_invalid:not_object",), ())

    state = field.get("state")
    if state == "available":
        if set(field) != {"state", "value"}:
            return _readiness("invalid", ("field_invalid:available_shape",), ())
        try:
            json.dumps(field["value"], ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            return _readiness("invalid", ("field_invalid:non_json_value",), ())
        return _readiness("ready", (), ())

    if state in {"redacted", "omitted", "unsupported"}:
        if set(field) != {"state", "reason"}:
            return _readiness("invalid", (f"field_invalid:{state}_shape",), ())
        reason = field.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return _readiness("invalid", (f"field_invalid:{state}_reason",), ())
        if state == "unsupported":
            return _readiness("unsupported", (f"field_unsupported:{reason}",), ())
        return _readiness("incomplete", (f"field_{state}:{reason}",), ())

    return _readiness("invalid", ("field_invalid:state",), ())
