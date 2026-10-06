"""Fail-closed completeness accounting for normalized runtime observations.

The capture adapters for native and Code Mode calls may differ. This module only
accounts for a small normalized stream and explicit capture-health signals. It
does not infer missing work from product output, stdout, or absent JSON fields.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

STATUSES = ("complete", "incomplete", "unsupported", "invalid")
FIELD_STATES = frozenset({"available", "redacted", "omitted", "truncated", "unsupported"})
PROCESS_STATES = frozenset({"completed", "timeout", "interrupted"})
EVENT_KINDS = frozenset({"start", "terminal"})

_GLOBAL_INVALID = frozenset({
    "invalid_accounting_input",
    "malformed_observation",
    "duplicate_sequence",
    "duplicate_invocation",
    "ambiguous_invocation",
})
_GLOBAL_INCOMPLETE = frozenset({
    "observation_not_closed",
    "observer_failure",
    "callback_failure",
    "observation_loss",
    "runtime_timeout",
    "process_interrupted",
})


def _counter(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _name(value: Any) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= 256:
        return value
    return None


def _new_boundary(*, declared_supported: bool = False, declared_unsupported: bool = False) -> dict[str, Any]:
    return {
        "status": "unsupported" if declared_unsupported else "complete",
        "evidence_eligible": not declared_unsupported,
        "declared_supported": declared_supported,
        "declared_unsupported": declared_unsupported,
        "starts": 0,
        "terminals": 0,
        "missing_terminals": 0,
        "required_fields_omitted": 0,
        "required_fields_truncated": 0,
        "required_fields_unsupported": 0,
        "issues": ["unsupported_boundary"] if declared_unsupported else [],
    }


def _add_issue(target: list[str], code: str) -> None:
    if code not in target:
        target.append(code)


def _set_boundary_status(boundary: dict[str, Any], status: str, issue: str) -> None:
    priority = {"complete": 0, "unsupported": 1, "incomplete": 2, "invalid": 3}
    if priority[status] > priority[boundary["status"]]:
        boundary["status"] = status
    boundary["evidence_eligible"] = boundary["status"] == "complete"
    _add_issue(boundary["issues"], issue)


def _invalid_result(issues: list[str], coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "invalid",
        "evidence_eligible": False,
        "issues": issues or ["invalid_accounting_input"],
        "coverage": coverage,
    }


def account_runtime_evidence(
    observations: Iterable[Mapping[str, Any]],
    *,
    observation_closed: bool,
    supported_boundaries: Iterable[str] = (),
    unsupported_boundaries: Iterable[str] = (),
    observer_failures: int = 0,
    callback_failures: int = 0,
    losses: int = 0,
    process_state: str = "completed",
) -> dict[str, Any]:
    """Account for normalized runtime observation starts and terminals.

    Each observation must contain kind, sequence, invocation_id,
    boundary, and required_fields. required_fields maps semantic
    field names to available, redacted, omitted, truncated, or
    unsupported. Adapters decide which fields are required; this layer only
    accounts for their explicit states.

    observation_closed is an ordinary correctness signal from the capture
    adapter that no more in-scope observations are expected. It is not a
    cryptographic seal. Without it, absence is never complete evidence.
    """
    coverage: dict[str, Any] = {
        "observation_closed": observation_closed if type(observation_closed) is bool else False,
        "starts": 0,
        "terminals": 0,
        "missing_terminals": 0,
        "observer_failures": 0,
        "callback_failures": 0,
        "losses": 0,
        "malformed_observations": 0,
        "duplicate_invocations": 0,
        "ambiguous_invocations": 0,
        "duplicate_sequences": 0,
        "required_fields_omitted": 0,
        "required_fields_truncated": 0,
        "required_fields_unsupported": 0,
        "process_state": process_state if process_state in PROCESS_STATES else "invalid",
        "supported_boundaries": [],
        "unsupported_boundaries": [],
        "by_boundary": {},
    }
    issues: list[str] = []

    failures = _counter(observer_failures)
    callback_failure_count = _counter(callback_failures)
    loss_count = _counter(losses)
    if (
        type(observation_closed) is not bool
        or failures is None
        or callback_failure_count is None
        or loss_count is None
        or process_state not in PROCESS_STATES
    ):
        _add_issue(issues, "invalid_accounting_input")
        return _invalid_result(issues, coverage)
    coverage["observer_failures"] = failures
    coverage["callback_failures"] = callback_failure_count
    coverage["losses"] = loss_count

    supported: set[str] = set()
    unsupported: set[str] = set()
    for raw, target in ((supported_boundaries, supported), (unsupported_boundaries, unsupported)):
        try:
            values = list(raw)
        except TypeError:
            _add_issue(issues, "invalid_accounting_input")
            return _invalid_result(issues, coverage)
        for value in values:
            name = _name(value)
            if name is None:
                _add_issue(issues, "invalid_accounting_input")
                return _invalid_result(issues, coverage)
            target.add(name)
    if supported & unsupported:
        _add_issue(issues, "invalid_accounting_input")
        return _invalid_result(issues, coverage)

    coverage["supported_boundaries"] = sorted(supported)
    coverage["unsupported_boundaries"] = sorted(unsupported)
    boundaries: dict[str, dict[str, Any]] = {
        name: _new_boundary(declared_supported=True) for name in sorted(supported)
    }
    for name in sorted(unsupported):
        boundaries[name] = _new_boundary(declared_unsupported=True)

    calls: dict[str, dict[str, Any]] = {}
    seen_sequences: set[int] = set()

    try:
        stream = list(observations)
    except TypeError:
        _add_issue(issues, "invalid_accounting_input")
        return _invalid_result(issues, coverage)

    for item in stream:
        if not isinstance(item, Mapping):
            coverage["malformed_observations"] += 1
            _add_issue(issues, "malformed_observation")
            continue

        kind = item.get("kind")
        sequence = item.get("sequence")
        invocation_id = _name(item.get("invocation_id"))
        boundary_name = _name(item.get("boundary"))
        fields = item.get("required_fields")
        valid_sequence = type(sequence) is int and sequence >= 0
        valid_fields = isinstance(fields, Mapping)
        if (
            kind not in EVENT_KINDS
            or not valid_sequence
            or invocation_id is None
            or boundary_name is None
            or not valid_fields
        ):
            coverage["malformed_observations"] += 1
            _add_issue(issues, "malformed_observation")
            continue

        field_states: dict[str, str] = {}
        malformed_field = False
        for field_name, state in fields.items():
            safe_name = _name(field_name)
            if safe_name is None or state not in FIELD_STATES:
                malformed_field = True
                break
            field_states[safe_name] = state
        if malformed_field:
            coverage["malformed_observations"] += 1
            _add_issue(issues, "malformed_observation")
            continue

        boundary = boundaries.setdefault(boundary_name, _new_boundary())
        if boundary_name not in supported and boundary_name not in unsupported:
            _set_boundary_status(boundary, "unsupported", "undeclared_boundary")

        if sequence in seen_sequences:
            coverage["duplicate_sequences"] += 1
            _add_issue(issues, "duplicate_sequence")
            _set_boundary_status(boundary, "invalid", "duplicate_sequence")
            continue
        seen_sequences.add(sequence)

        for state in field_states.values():
            if state == "omitted":
                coverage["required_fields_omitted"] += 1
                boundary["required_fields_omitted"] += 1
                _set_boundary_status(boundary, "incomplete", "required_field_omitted")
            elif state == "truncated":
                coverage["required_fields_truncated"] += 1
                boundary["required_fields_truncated"] += 1
                _set_boundary_status(boundary, "incomplete", "required_field_truncated")
            elif state == "unsupported":
                coverage["required_fields_unsupported"] += 1
                boundary["required_fields_unsupported"] += 1
                _set_boundary_status(boundary, "unsupported", "required_field_unsupported")

        if kind == "start":
            if invocation_id in calls:
                coverage["duplicate_invocations"] += 1
                _add_issue(issues, "duplicate_invocation")
                _set_boundary_status(boundary, "invalid", "duplicate_invocation")
                continue
            calls[invocation_id] = {
                "boundary": boundary_name,
                "start_sequence": sequence,
                "terminal_sequence": None,
            }
            coverage["starts"] += 1
            boundary["starts"] += 1
            continue

        call = calls.get(invocation_id)
        if call is None:
            coverage["ambiguous_invocations"] += 1
            _add_issue(issues, "ambiguous_invocation")
            _set_boundary_status(boundary, "invalid", "terminal_without_start")
            continue
        start_boundary = boundaries[call["boundary"]]
        if call["boundary"] != boundary_name or call["terminal_sequence"] is not None or sequence <= call["start_sequence"]:
            coverage["ambiguous_invocations"] += 1
            _add_issue(issues, "ambiguous_invocation")
            _set_boundary_status(boundary, "invalid", "ambiguous_terminal")
            _set_boundary_status(start_boundary, "invalid", "ambiguous_terminal")
            continue
        call["terminal_sequence"] = sequence
        coverage["terminals"] += 1
        boundary["terminals"] += 1

    for call in calls.values():
        if call["terminal_sequence"] is None:
            coverage["missing_terminals"] += 1
            boundary = boundaries[call["boundary"]]
            boundary["missing_terminals"] += 1
            _set_boundary_status(boundary, "incomplete", "missing_terminal")

    if not observation_closed:
        _add_issue(issues, "observation_not_closed")
    if failures:
        _add_issue(issues, "observer_failure")
    if callback_failure_count:
        _add_issue(issues, "callback_failure")
    if loss_count:
        _add_issue(issues, "observation_loss")
    if process_state == "timeout":
        _add_issue(issues, "runtime_timeout")
    elif process_state == "interrupted":
        _add_issue(issues, "process_interrupted")

    if coverage["missing_terminals"]:
        _add_issue(issues, "missing_terminal")
    if coverage["required_fields_omitted"]:
        _add_issue(issues, "required_field_omitted")
    if coverage["required_fields_truncated"]:
        _add_issue(issues, "required_field_truncated")
    if coverage["required_fields_unsupported"]:
        _add_issue(issues, "required_field_unsupported")
    if unsupported:
        _add_issue(issues, "unsupported_boundary")
    undeclared = sorted(name for name in boundaries if name not in supported and name not in unsupported)
    if undeclared:
        _add_issue(issues, "undeclared_boundary")

    global_invalid = any(code in _GLOBAL_INVALID for code in issues)
    global_incomplete = any(code in _GLOBAL_INCOMPLETE for code in issues)
    for boundary in boundaries.values():
        if global_invalid:
            _set_boundary_status(boundary, "invalid", "global_invalid_capture")
        elif global_incomplete:
            _set_boundary_status(boundary, "incomplete", "global_incomplete_capture")

    coverage["by_boundary"] = {name: boundaries[name] for name in sorted(boundaries)}

    if global_invalid or any(boundary["status"] == "invalid" for boundary in boundaries.values()):
        status = "invalid"
    elif global_incomplete or any(boundary["status"] == "incomplete" for boundary in boundaries.values()):
        status = "incomplete"
    elif any(boundary["status"] == "unsupported" for boundary in boundaries.values()):
        status = "unsupported"
    else:
        status = "complete"

    return {
        "status": status,
        "evidence_eligible": status == "complete",
        "issues": issues,
        "coverage": coverage,
    }


def assertion_status(accounting: Mapping[str, Any], required_boundaries: Iterable[str]) -> str:
    """Return the fail-closed status for one assertion's required boundaries.

    This lets an unsupported Code Mode boundary avoid poisoning an unrelated
    native-only assertion while global loss/invalidity still fails every scope.
    """
    try:
        coverage = accounting["coverage"]
        boundaries = coverage["by_boundary"]
        issues = accounting["issues"]
    except (KeyError, TypeError):
        return "invalid"
    if not isinstance(coverage, Mapping) or not isinstance(boundaries, Mapping) or not isinstance(issues, list):
        return "invalid"
    if any(code in _GLOBAL_INVALID for code in issues):
        return "invalid"
    if any(code in _GLOBAL_INCOMPLETE for code in issues):
        return "incomplete"

    try:
        names = list(required_boundaries)
    except TypeError:
        return "invalid"
    statuses: list[str] = []
    for raw_name in names:
        name = _name(raw_name)
        if name is None:
            return "invalid"
        boundary = boundaries.get(name)
        if not isinstance(boundary, Mapping):
            return "unsupported"
        status = boundary.get("status")
        if status not in STATUSES:
            return "invalid"
        statuses.append(status)
    if "invalid" in statuses:
        return "invalid"
    if "incomplete" in statuses:
        return "incomplete"
    if "unsupported" in statuses:
        return "unsupported"
    return "complete"
