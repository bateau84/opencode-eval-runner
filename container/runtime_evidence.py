from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

RUNTIME_EVIDENCE_SCHEMA = "opencode-eval-runner/runtime-evidence/v1"

STATUSES = {"complete", "incomplete", "unsupported", "invalid"}
FIELD_STATES = {"available", "redacted", "omitted", "unsupported"}
MODES = {"native", "code_mode"}
OUTCOMES = {"success", "error", "missing"}
PROCESS_STATES = {"completed", "timeout", "interrupted", "unsupported"}

BOUNDARY_NATIVE = "native"
BOUNDARY_CODE_MODE_EXECUTION = "code_mode_execution"
BOUNDARY_CODE_MODE_FINALITY = "code_mode_finality"
CODE_MODE_FINALITY_REASON = "stock_codemode_final_boundary_not_exposed"

TOP_LEVEL_KEYS = {"schema", "status", "evidence_eligible", "observations", "coverage"}
OBSERVATION_KEYS = {
    "invocation_id",
    "tool",
    "mode",
    "actor",
    "session_id",
    "message_id",
    "call_id",
    "parent",
    "input",
    "outcome",
    "result",
    "error",
    "start_sequence",
    "terminal_sequence",
}
COVERAGE_KEYS = {
    "observation_closed",
    "process_state",
    "starts",
    "terminals",
    "missing_terminals",
    "observer_failures",
    "callback_failures",
    "losses",
    "unsupported",
    "boundaries",
}
BOUNDARY_KEYS = {
    "status",
    "evidence_eligible",
    "starts",
    "terminals",
    "missing_terminals",
    "issues",
}


class RuntimeEvidenceError(ValueError):
    """The runtime-evidence object is not safe to consume as contracted evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeEvidenceError(message)


def _exact_object(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    _require(type(value) is dict, f"{where} must be an object")
    _require(set(value) == keys, f"{where} keys must be exactly {sorted(keys)}")
    return value


def _string(value: Any, where: str) -> str:
    _require(type(value) is str and bool(value.strip()), f"{where} must be a non-empty string")
    return value


def _json_value(value: Any, where: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeEvidenceError(f"{where} must be a finite JSON value") from exc


def field_available(value: Any) -> dict[str, Any]:
    """Represent an exact projected runtime value. JSON null remains a real value."""
    _json_value(value, "field value")
    return {"state": "available", "value": value}


def field_unavailable(state: str, reason: str) -> dict[str, str]:
    """Represent a value that must not be replaced by an empty/default value."""
    _require(state in {"redacted", "omitted", "unsupported"}, "invalid unavailable field state")
    _string(reason, "field reason")
    return {"state": state, "reason": reason}


def _field(
    raw: Any,
    where: str,
    *,
    value_type: type | None = None,
) -> tuple[str, Any | None]:
    _require(type(raw) is dict, f"{where} must be a field-state object")
    state = raw.get("state")
    _require(state in FIELD_STATES, f"{where}.state is invalid")

    if state == "available":
        _require(set(raw) == {"state", "value"}, f"{where} available state requires state/value")
        value = raw["value"]
        _json_value(value, f"{where}.value")
        if value_type is int:
            _require(type(value) is int, f"{where}.value must be an integer")
        elif value_type is str:
            _string(value, f"{where}.value")
        return state, value

    _require(set(raw) == {"state", "reason"}, f"{where} unavailable state requires state/reason")
    _string(raw["reason"], f"{where}.reason")
    return state, None


def _count(raw: Any, where: str) -> tuple[str, int | None]:
    state, value = _field(raw, where, value_type=int)
    _require(state in {"available", "omitted", "unsupported"}, f"{where} count state is invalid")
    if state == "available":
        _require(value >= 0, f"{where}.value must be >= 0")
    return state, value


def _codes(raw: Any, where: str) -> list[str]:
    _require(type(raw) is list, f"{where} must be a list")
    values = [_string(item, f"{where}[{index}]") for index, item in enumerate(raw)]
    _require(len(values) == len(set(values)), f"{where} must not contain duplicates")
    return values


STATUSES = ("complete", "incomplete", "unsupported", "invalid")
FIELD_STATES = frozenset({"available", "redacted", "omitted", "unsupported"})
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
    elif any(boundary["status"] == "complete" for boundary in boundaries.values()):
        status = "complete"
    else:
        status = "unsupported"

    return {
        "status": status,
        "evidence_eligible": status == "complete",
        "issues": issues,
        "coverage": coverage,
    }



def _public_count(value: int | None, reason: str = "unknown_coverage") -> dict[str, Any]:
    return field_available(value) if type(value) is int and value >= 0 else field_unavailable("omitted", reason)


def _unsupported_boundary(reason: str) -> dict[str, Any]:
    return {
        "status": "unsupported",
        "evidence_eligible": False,
        "starts": field_unavailable("unsupported", reason),
        "terminals": field_unavailable("unsupported", reason),
        "missing_terminals": field_unavailable("unsupported", reason),
        "issues": [reason],
    }


def unsupported_runtime_evidence(reason: str) -> dict[str, Any]:
    _string(reason, "reason")
    evidence = {
        "schema": RUNTIME_EVIDENCE_SCHEMA,
        "status": "unsupported",
        "evidence_eligible": False,
        "observations": [],
        "coverage": {
            "observation_closed": field_unavailable("unsupported", reason),
            "process_state": "unsupported",
            "starts": field_unavailable("unsupported", reason),
            "terminals": field_unavailable("unsupported", reason),
            "missing_terminals": field_unavailable("unsupported", reason),
            "observer_failures": field_unavailable("unsupported", reason),
            "callback_failures": field_unavailable("unsupported", reason),
            "losses": [],
            "unsupported": [reason],
            "boundaries": {
                BOUNDARY_NATIVE: _unsupported_boundary(reason),
                BOUNDARY_CODE_MODE_EXECUTION: _unsupported_boundary(reason),
                BOUNDARY_CODE_MODE_FINALITY: _unsupported_boundary(reason),
            },
        },
    }
    return validate_runtime_evidence(evidence)


def _state(raw: Any) -> str:
    return raw.get("state") if isinstance(raw, dict) and raw.get("state") in FIELD_STATES else "omitted"


def _project(raw: Any, sanitizer: Any | None, *, limit: int = 256 * 1024) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return field_unavailable("omitted", "missing")
    state = raw.get("state")
    if state in {"redacted", "omitted"} and isinstance(raw.get("reason"), str) and raw["reason"]:
        return field_unavailable(state, raw["reason"])
    if state != "available" or set(raw) != {"state", "value"}:
        return field_unavailable("omitted", "unsupported_representation")
    value = raw["value"]
    try:
        if sanitizer is not None:
            value, changed = sanitizer.evidence_value(value)
            if changed:
                return field_unavailable("redacted", "credential_match")
        _json_value(value, "runtime evidence field")
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) > limit:
            return field_unavailable("omitted", "size_limit")
        return field_available(value)
    except Exception as exc:
        reason = getattr(exc, "reason", "unsupported_representation")
        return field_unavailable("omitted", reason if isinstance(reason, str) and reason else "unsupported_representation")


def _identity(value: Any, reason: str) -> dict[str, Any]:
    if isinstance(value, dict):
        state = value.get("state")
        if state == "available" and set(value) == {"state", "value"}:
            raw = value.get("value")
            if type(raw) is str and raw and "\x00" not in raw:
                return field_available(raw)
            return field_unavailable("omitted", reason)
        if state in {"redacted", "omitted"} and set(value) == {"state", "reason"}:
            raw_reason = value.get("reason")
            if isinstance(raw_reason, str) and raw_reason:
                return field_unavailable(state, raw_reason)
        return field_unavailable("omitted", reason)
    if type(value) is str and value and "\x00" not in value:
        return field_available(value)
    return field_unavailable("omitted", reason)


def _parent(start: Mapping[str, Any]) -> dict[str, Any]:
    if start.get("kind") == "code_start":
        value = start.get("parent_invocation_id")
        if type(value) is str and value:
            return field_available({"kind": "invocation", "id": value})
        return field_unavailable("omitted", "parent_invocation_unavailable")
    raw = start.get("parent_session_id")
    if isinstance(raw, dict) and raw.get("state") == "available" and set(raw) == {"state", "value"}:
        value = raw.get("value")
        if value is None:
            return field_available(None)
        if type(value) is str and value:
            return field_available({"kind": "session", "id": value})
    if isinstance(raw, dict) and raw.get("state") in {"redacted", "omitted"} and isinstance(raw.get("reason"), str):
        return field_unavailable(raw["state"], raw["reason"])
    return field_unavailable("omitted", "session_parent_unavailable")


def _capture_issue_kind(code: str) -> str:
    if code in {
        "malformed_capture",
        "wrong_schema",
        "ambiguous_order",
        "records_after_capture_end",
        "invalid_capture_start",
        "invalid_capture_end",
        "invalid_record",
        "count_mismatch",
        "unterminated_capture",
    }:
        return "invalid"
    return "incomplete"


def build_runtime_evidence(
    capture: Mapping[str, Any],
    sanitizer: Any | None = None,
    *,
    process_state: str = "completed",
) -> dict[str, Any]:
    if process_state not in {"completed", "timeout", "interrupted"}:
        process_state = "interrupted"
    if not isinstance(capture, Mapping):
        capture = {
            "capture_started": False,
            "capture_ended": False,
            "records": [],
            "observer_failures": None,
            "callback_failures": None,
            "issues": ["missing_capture"],
        }

    records = capture.get("records") if isinstance(capture.get("records"), list) else []
    starts: dict[str, Mapping[str, Any]] = {}
    terminals: dict[str, Mapping[str, Any]] = {}
    adapter_invalid = False
    loss_codes: list[str] = []

    for raw_code in capture.get("issues", []):
        if not isinstance(raw_code, str) or not raw_code:
            adapter_invalid = True
            raw_code = "malformed_capture"
        if raw_code not in loss_codes:
            loss_codes.append(raw_code)
        adapter_invalid = adapter_invalid or _capture_issue_kind(raw_code) == "invalid"

    for record in records:
        if not isinstance(record, Mapping):
            adapter_invalid = True
            continue
        kind = record.get("kind")
        invocation_id = record.get("invocation_id")
        sequence = record.get("sequence")
        if type(invocation_id) is not str or not invocation_id or type(sequence) is not int or sequence < 0:
            adapter_invalid = True
            continue
        target = starts if kind in {"native_start", "code_start"} else terminals if kind in {"native_terminal", "code_terminal"} else None
        if target is None or invocation_id in target:
            adapter_invalid = True
            continue
        target[invocation_id] = record

    observations: list[dict[str, Any]] = []
    accounting_events: list[dict[str, Any]] = []
    if adapter_invalid:
        accounting_events.append({})

    for invocation_id, start in sorted(starts.items(), key=lambda item: item[1]["sequence"]):
        mode = "native" if start.get("kind") == "native_start" else "code_mode"
        boundary = BOUNDARY_NATIVE if mode == "native" else BOUNDARY_CODE_MODE_EXECUTION
        terminal = terminals.get(invocation_id)
        expected_terminal = "native_terminal" if mode == "native" else "code_terminal"
        if terminal is not None and terminal.get("kind") != expected_terminal:
            terminal = None
            accounting_events.append({})
        if terminal is not None:
            expected_identity = {
                "tool": start.get("tool"),
                "session_id": start.get("session_id"),
                "agent": start.get("agent"),
                "message_id": start.get("message_id"),
                "call_id": start.get("call_id"),
            }
            if any(terminal.get(name) != value for name, value in expected_identity.items()):
                terminal = None
                accounting_events.append({})
            elif mode == "native":
                expected_boundary = {
                    "success": "session.tool.success",
                    "error": "session.tool.failed",
                }.get(terminal.get("outcome"))
                if terminal.get("boundary") != expected_boundary:
                    terminal = None
                    accounting_events.append({})
            else:
                expected_boundary = {
                    "success": "tool-handler-return",
                    "error": "tool-handler-throw",
                }.get(terminal.get("outcome"))
                if terminal.get("boundary") != expected_boundary:
                    terminal = None
                    accounting_events.append({})

        tool = _identity(start.get("tool"), "tool_unavailable")
        actor = _identity(start.get("agent"), "actor_unavailable")
        session_id = _identity(start.get("session_id"), "session_unavailable")
        message_id = _identity(start.get("message_id"), "message_unavailable")
        call_id = _identity(start.get("call_id"), "call_unavailable")
        parent = _parent(start)
        input_field = _project(start.get("input"), sanitizer)
        start_sequence = start["sequence"]
        required = {
            "tool": _state(tool),
            "actor": _state(actor),
            "session_id": _state(session_id),
            "message_id": _state(message_id),
            "call_id": _state(call_id),
            "input": _state(input_field),
        }
        if mode == "code_mode":
            required["parent"] = _state(parent)
        accounting_events.append({
            "kind": "start",
            "sequence": start_sequence,
            "invocation_id": invocation_id,
            "boundary": boundary,
            "required_fields": required,
        })

        outcome = "missing"
        result = field_unavailable("omitted", "terminal_missing")
        error = field_unavailable("omitted", "terminal_missing")
        terminal_sequence = field_unavailable("omitted", "terminal_missing")

        if terminal is not None and type(terminal.get("sequence")) is int and terminal["sequence"] > start_sequence:
            sequence = terminal["sequence"]
            raw_outcome = terminal.get("outcome")
            if raw_outcome in {"success", "error"}:
                outcome = raw_outcome
                terminal_sequence = field_available(sequence)
                if mode == "code_mode":
                    if outcome == "success":
                        result = field_unavailable("unsupported", CODE_MODE_FINALITY_REASON)
                        error = field_unavailable("omitted", "not_applicable")
                    else:
                        result = field_unavailable("omitted", "not_applicable")
                        error = field_unavailable("unsupported", CODE_MODE_FINALITY_REASON)
                    terminal_required = {"outcome": "available"}
                elif outcome == "success":
                    result = _project(terminal.get("result"), sanitizer)
                    error = field_unavailable("omitted", "not_applicable")
                    terminal_required = {"outcome": "available", "result_or_error": _state(result)}
                else:
                    result = field_unavailable("omitted", "not_applicable")
                    error = _project(terminal.get("error"), sanitizer)
                    terminal_required = {"outcome": "available", "result_or_error": _state(error)}
                accounting_events.append({
                    "kind": "terminal",
                    "sequence": sequence,
                    "invocation_id": invocation_id,
                    "boundary": boundary,
                    "required_fields": terminal_required,
                })
            else:
                accounting_events.append({})

        observations.append({
            "invocation_id": invocation_id,
            "tool": tool,
            "mode": mode,
            "actor": actor,
            "session_id": session_id,
            "message_id": message_id,
            "call_id": call_id,
            "parent": parent,
            "input": input_field,
            "outcome": outcome,
            "result": result,
            "error": error,
            "start_sequence": start_sequence,
            "terminal_sequence": terminal_sequence,
        })

    if any(invocation_id not in starts for invocation_id in terminals):
        accounting_events.append({})

    capture_started = capture.get("capture_started") is True
    capture_ended = capture.get("capture_ended") is True
    observer_failures = capture.get("observer_failures") if capture_ended else None
    callback_failures = capture.get("callback_failures") if capture_ended else None
    if type(observer_failures) is not int or observer_failures < 0:
        observer_failures = None
    if type(callback_failures) is not int or callback_failures < 0:
        callback_failures = None

    accounting = account_runtime_evidence(
        accounting_events,
        observation_closed=capture_ended,
        supported_boundaries=(BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_EXECUTION),
        unsupported_boundaries=(BOUNDARY_CODE_MODE_FINALITY,),
        observer_failures=observer_failures or 0,
        callback_failures=callback_failures or 0,
        losses=sum(_capture_issue_kind(code) == "incomplete" for code in loss_codes),
        process_state=process_state,
    )

    boundary_output: dict[str, Any] = {}
    for name in (BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_EXECUTION):
        raw_boundary = accounting["coverage"]["by_boundary"].get(name, {})
        count_reason = "missing_capture"
        counts_known = capture_started
        boundary_output[name] = {
            "status": raw_boundary.get("status", "invalid"),
            "evidence_eligible": raw_boundary.get("status") == "complete",
            "starts": _public_count(raw_boundary.get("starts") if counts_known else None, count_reason),
            "terminals": _public_count(raw_boundary.get("terminals") if counts_known else None, count_reason),
            "missing_terminals": _public_count(raw_boundary.get("missing_terminals") if counts_known else None, count_reason),
            "issues": list(dict.fromkeys(raw_boundary.get("issues", []))),
        }
    boundary_output[BOUNDARY_CODE_MODE_FINALITY] = _unsupported_boundary(CODE_MODE_FINALITY_REASON)

    totals_known = capture_started
    starts_total = len(observations)
    terminals_total = sum(item["outcome"] != "missing" for item in observations)
    missing_total = starts_total - terminals_total

    actual_losses = list(dict.fromkeys(
        loss_codes
        + [
            code for code in accounting.get("issues", [])
            if code not in {"unsupported_boundary", "required_field_unsupported"}
        ]
    ))
    unsupported = [CODE_MODE_FINALITY_REASON]
    for name in (BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_EXECUTION):
        boundary = boundary_output[name]
        if boundary["status"] == "unsupported":
            for issue in boundary["issues"]:
                if issue not in unsupported:
                    unsupported.append(issue)

    evidence = {
        "schema": RUNTIME_EVIDENCE_SCHEMA,
        "status": accounting["status"],
        "evidence_eligible": accounting["status"] == "complete",
        "observations": observations,
        "coverage": {
            "observation_closed": field_available(capture_ended),
            "process_state": process_state,
            "starts": _public_count(starts_total if totals_known else None, "missing_capture"),
            "terminals": _public_count(terminals_total if totals_known else None, "missing_capture"),
            "missing_terminals": _public_count(missing_total if totals_known else None, "missing_capture"),
            "observer_failures": _public_count(observer_failures, "observation_not_closed"),
            "callback_failures": _public_count(callback_failures, "observation_not_closed"),
            "losses": actual_losses,
            "unsupported": unsupported,
            "boundaries": boundary_output,
        },
    }
    return validate_runtime_evidence(evidence)


def _validate_boundary(raw: Any, where: str) -> tuple[str, dict[str, Any]]:
    boundary = _exact_object(raw, BOUNDARY_KEYS, where)
    status = boundary["status"]
    _require(status in STATUSES, f"{where}.status is invalid")
    _require(type(boundary["evidence_eligible"]) is bool, f"{where}.evidence_eligible must be boolean")
    _require(boundary["evidence_eligible"] == (status == "complete"), f"{where}.evidence_eligible is inconsistent")
    for key in ("starts", "terminals", "missing_terminals"):
        _count(boundary[key], f"{where}.{key}")
    _codes(boundary["issues"], f"{where}.issues")
    return status, boundary


def validate_runtime_evidence(raw: Any) -> dict[str, Any]:
    evidence = _exact_object(raw, TOP_LEVEL_KEYS, "runtime_evidence")
    _require(evidence["schema"] == RUNTIME_EVIDENCE_SCHEMA, "unsupported runtime_evidence schema")
    status = evidence["status"]
    _require(status in STATUSES, "runtime_evidence.status is invalid")
    _require(type(evidence["evidence_eligible"]) is bool, "runtime_evidence.evidence_eligible must be boolean")
    _require(evidence["evidence_eligible"] == (status == "complete"), "runtime_evidence.evidence_eligible is inconsistent")
    _require(type(evidence["observations"]) is list, "runtime_evidence.observations must be a list")
    coverage = _exact_object(evidence["coverage"], COVERAGE_KEYS, "runtime_evidence.coverage")
    process_state = coverage["process_state"]
    _require(process_state in PROCESS_STATES, "runtime_evidence.coverage.process_state is invalid")
    closed_state, closed = _field(coverage["observation_closed"], "runtime_evidence.coverage.observation_closed")
    starts_state, starts = _count(coverage["starts"], "runtime_evidence.coverage.starts")
    terminals_state, terminals = _count(coverage["terminals"], "runtime_evidence.coverage.terminals")
    missing_state, missing = _count(coverage["missing_terminals"], "runtime_evidence.coverage.missing_terminals")
    observer_state, observer_failures = _count(coverage["observer_failures"], "runtime_evidence.coverage.observer_failures")
    callback_state, callback_failures = _count(coverage["callback_failures"], "runtime_evidence.coverage.callback_failures")
    losses = _codes(coverage["losses"], "runtime_evidence.coverage.losses")
    unsupported = _codes(coverage["unsupported"], "runtime_evidence.coverage.unsupported")
    boundaries = coverage["boundaries"]
    _require(type(boundaries) is dict, "runtime_evidence.coverage.boundaries must be an object")

    expected_names = {BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_EXECUTION, BOUNDARY_CODE_MODE_FINALITY}
    _require(set(boundaries) == expected_names, "runtime_evidence.coverage.boundaries has unexpected names")
    boundary_status: dict[str, str] = {}
    for name in expected_names:
        boundary_status[name], _ = _validate_boundary(
            boundaries[name], f"runtime_evidence.coverage.boundaries.{name}"
        )

    if process_state == "unsupported":
        _require(status == "unsupported" and not evidence["observations"], "unsupported transport cannot carry observations")
        _require(closed_state == "unsupported", "unsupported transport requires unsupported closure")
        _require(starts_state == terminals_state == missing_state == "unsupported", "unsupported transport requires unknown counts")
        _require(observer_state == callback_state == "unsupported", "unsupported transport requires unknown failure counts")
        _require(bool(unsupported), "unsupported transport requires a reason")
        return evidence

    _require(closed_state == "available" and type(closed) is bool, "observed capture requires explicit closure")
    aggregate_available = starts_state == terminals_state == missing_state == "available"
    aggregate_unknown = starts_state == terminals_state == missing_state == "omitted"
    _require(aggregate_available or aggregate_unknown, "coverage counts must be uniformly available or omitted")
    if aggregate_available:
        _require(starts >= terminals and missing == starts - terminals, "aggregate coverage counts are inconsistent")
    else:
        _require(status in {"incomplete", "invalid"}, "complete evidence cannot have unknown coverage")
        _require(bool(losses), "unknown coverage requires an explicit loss")

    seen_ids: set[str] = set()
    seen_sequences: set[int] = set()
    previous_start = -1
    terminal_count = 0
    reconstructed: list[dict[str, Any]] = []

    for index, observation in enumerate(evidence["observations"]):
        where = f"runtime_evidence.observations[{index}]"
        observation = _exact_object(observation, OBSERVATION_KEYS, where)
        invocation_id = _string(observation["invocation_id"], f"{where}.invocation_id")
        _require(invocation_id not in seen_ids, f"{where}.invocation_id must be unique")
        seen_ids.add(invocation_id)
        mode = observation["mode"]
        _require(mode in MODES, f"{where}.mode is invalid")
        required = {}
        for key in ("tool", "actor", "session_id", "message_id", "call_id", "input"):
            state, _ = _field(observation[key], f"{where}.{key}")
            required[key] = state
        parent_state, parent = _field(observation["parent"], f"{where}.parent")
        if parent_state == "available" and parent is not None:
            parent = _exact_object(parent, {"kind", "id"}, f"{where}.parent.value")
            _require(parent["kind"] in {"invocation", "session"}, f"{where}.parent.value.kind is invalid")
            _string(parent["id"], f"{where}.parent.value.id")
        if mode == "code_mode":
            required["parent"] = parent_state

        start_sequence = observation["start_sequence"]
        _require(type(start_sequence) is int and start_sequence >= 0, f"{where}.start_sequence must be >= 0")
        _require(start_sequence > previous_start and start_sequence not in seen_sequences, "start sequences must be unique and ordered")
        previous_start = start_sequence
        seen_sequences.add(start_sequence)
        boundary = BOUNDARY_NATIVE if mode == "native" else BOUNDARY_CODE_MODE_EXECUTION
        reconstructed.append({
            "kind": "start",
            "sequence": start_sequence,
            "invocation_id": invocation_id,
            "boundary": boundary,
            "required_fields": required,
        })

        outcome = observation["outcome"]
        _require(outcome in OUTCOMES, f"{where}.outcome is invalid")
        result_state, _ = _field(observation["result"], f"{where}.result")
        error_state, _ = _field(observation["error"], f"{where}.error")
        terminal_state, terminal_sequence = _field(
            observation["terminal_sequence"], f"{where}.terminal_sequence", value_type=int
        )
        if outcome == "missing":
            _require(terminal_state == result_state == error_state == "omitted", f"{where} missing terminal must be explicit")
            continue
        _require(terminal_state == "available" and terminal_sequence > start_sequence, f"{where}.terminal_sequence must follow start")
        _require(terminal_sequence not in seen_sequences, f"{where}.terminal_sequence must be unique")
        seen_sequences.add(terminal_sequence)
        terminal_count += 1
        if mode == "code_mode":
            if outcome == "success":
                _require(result_state == "unsupported" and error_state == "omitted", f"{where} final result must be unsupported")
            else:
                _require(error_state == "unsupported" and result_state == "omitted", f"{where} final error must be unsupported")
            terminal_required = {"outcome": "available"}
        elif outcome == "success":
            _require(error_state == "omitted", f"{where}.error must be omitted on success")
            terminal_required = {"outcome": "available", "result_or_error": result_state}
        else:
            _require(result_state == "omitted", f"{where}.result must be omitted on error")
            terminal_required = {"outcome": "available", "result_or_error": error_state}
        reconstructed.append({
            "kind": "terminal",
            "sequence": terminal_sequence,
            "invocation_id": invocation_id,
            "boundary": boundary,
            "required_fields": terminal_required,
        })

    if aggregate_available:
        _require(starts == len(evidence["observations"]), "coverage starts does not match observations")
        _require(terminals == terminal_count, "coverage terminals does not match observations")

    _require(boundary_status[BOUNDARY_CODE_MODE_FINALITY] == "unsupported", "code_mode_finality must be unsupported")
    _require(CODE_MODE_FINALITY_REASON in unsupported, "Code Mode finality limitation must be explicit")

    if any(_capture_issue_kind(code) == "invalid" for code in losses):
        reconstructed.append({})

    accounting = account_runtime_evidence(
        reconstructed,
        observation_closed=closed,
        supported_boundaries=(BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_EXECUTION),
        unsupported_boundaries=(BOUNDARY_CODE_MODE_FINALITY,),
        observer_failures=observer_failures if observer_state == "available" else 0,
        callback_failures=callback_failures if callback_state == "available" else 0,
        losses=sum(_capture_issue_kind(code) == "incomplete" for code in losses),
        process_state=process_state,
    )
    _require(status == accounting["status"], "runtime_evidence.status does not match canonical accounting")
    _require(evidence["evidence_eligible"] == accounting["evidence_eligible"], "runtime_evidence eligibility does not match canonical accounting")
    for name in (BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_EXECUTION):
        _require(boundary_status[name] == accounting["coverage"]["by_boundary"][name]["status"], f"{name} status does not match canonical accounting")
    return evidence


def assertion_status(
    evidence: Mapping[str, Any],
    required_boundaries: Iterable[str],
    required_fields: Iterable[tuple[str, str]] = (),
) -> str:
    try:
        coverage = evidence["coverage"]
        boundaries = coverage["boundaries"]
        process_state = coverage["process_state"]
    except (KeyError, TypeError):
        return "invalid"
    if evidence.get("status") == "invalid":
        return "invalid"
    if evidence.get("status") == "incomplete" or process_state in {"timeout", "interrupted"}:
        return "incomplete"
    try:
        names = list(required_boundaries)
    except TypeError:
        return "invalid"
    statuses = []
    for name in names:
        if not isinstance(name, str) or not name:
            return "invalid"
        boundary = boundaries.get(name) if isinstance(boundaries, Mapping) else None
        if not isinstance(boundary, Mapping):
            return "unsupported"
        boundary_status = boundary.get("status")
        if boundary_status not in STATUSES:
            return "invalid"
        statuses.append(boundary_status)
    if "invalid" in statuses:
        return "invalid"
    if "incomplete" in statuses:
        return "incomplete"
    if "unsupported" in statuses:
        return "unsupported"

    observations = evidence.get("observations")
    if not isinstance(observations, list):
        return "invalid"
    by_id = {
        item.get("invocation_id"): item
        for item in observations
        if isinstance(item, Mapping) and isinstance(item.get("invocation_id"), str)
    }
    try:
        field_requirements = list(required_fields)
    except TypeError:
        return "invalid"
    for requirement in field_requirements:
        if (
            not isinstance(requirement, tuple)
            or len(requirement) != 2
            or not all(isinstance(value, str) and value for value in requirement)
        ):
            return "invalid"
        invocation_id, field_name = requirement
        item = by_id.get(invocation_id)
        if not isinstance(item, Mapping) or field_name not in OBSERVATION_KEYS:
            return "unsupported"
        raw = item.get(field_name)
        if field_name in {"mode", "outcome", "start_sequence"}:
            continue
        state = raw.get("state") if isinstance(raw, Mapping) else None
        if state == "unsupported":
            return "unsupported"
        if state in {"redacted", "omitted"}:
            return "incomplete"
        if state != "available":
            return "invalid"
    return "complete"


def assertion_evidence_eligible(
    evidence: Mapping[str, Any],
    required_boundaries: Iterable[str],
    required_fields: Iterable[tuple[str, str]] = (),
) -> bool:
    return assertion_status(evidence, required_boundaries, required_fields) == "complete"
