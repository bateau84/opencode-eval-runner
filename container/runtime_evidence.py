from __future__ import annotations

import json
from typing import Any

RUNTIME_EVIDENCE_SCHEMA = "opencode-eval-runner/runtime-evidence/v1"

STATUSES = {"complete", "incomplete", "unsupported", "invalid"}
FIELD_STATES = {"available", "redacted", "omitted", "unsupported"}
MODES = {"native", "code_mode"}
OUTCOMES = {"success", "error", "missing"}

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
COVERAGE_KEYS = {"starts", "terminals", "missing_terminals", "losses", "unsupported"}


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
    _require(state in {"available", "unsupported"}, f"{where} must be available or unsupported")
    if state == "available":
        _require(value >= 0, f"{where}.value must be >= 0")
    return state, value


def _codes(raw: Any, where: str) -> list[str]:
    _require(type(raw) is list, f"{where} must be a list")
    values = [_string(item, f"{where}[{index}]") for index, item in enumerate(raw)]
    _require(len(values) == len(set(values)), f"{where} must not contain duplicates")
    return values


def unsupported_runtime_evidence(reason: str) -> dict[str, Any]:
    """Explicit non-evidence used until a reviewed observer can populate the contract."""
    _string(reason, "reason")
    return {
        "schema": RUNTIME_EVIDENCE_SCHEMA,
        "status": "unsupported",
        "evidence_eligible": False,
        "observations": [],
        "coverage": {
            "starts": field_unavailable("unsupported", reason),
            "terminals": field_unavailable("unsupported", reason),
            "missing_terminals": field_unavailable("unsupported", reason),
            "losses": [],
            "unsupported": [reason],
        },
    }


def validate_runtime_evidence(raw: Any) -> dict[str, Any]:
    """Validate shape, sequencing, coverage, and fail-closed eligibility."""
    evidence = _exact_object(raw, TOP_LEVEL_KEYS, "runtime_evidence")
    _require(evidence["schema"] == RUNTIME_EVIDENCE_SCHEMA, "unsupported runtime_evidence schema")
    status = evidence["status"]
    _require(status in STATUSES, "runtime_evidence.status is invalid")
    _require(type(evidence["evidence_eligible"]) is bool, "runtime_evidence.evidence_eligible must be boolean")
    _require(type(evidence["observations"]) is list, "runtime_evidence.observations must be a list")

    coverage = _exact_object(evidence["coverage"], COVERAGE_KEYS, "runtime_evidence.coverage")
    starts_state, starts = _count(coverage["starts"], "runtime_evidence.coverage.starts")
    terminals_state, terminals = _count(coverage["terminals"], "runtime_evidence.coverage.terminals")
    missing_state, missing = _count(coverage["missing_terminals"], "runtime_evidence.coverage.missing_terminals")
    losses = _codes(coverage["losses"], "runtime_evidence.coverage.losses")
    unsupported = _codes(coverage["unsupported"], "runtime_evidence.coverage.unsupported")

    seen_invocations: set[str] = set()
    seen_sequences: set[int] = set()
    previous_start = -1
    terminal_observations = 0
    has_unsupported_field = False

    for index, raw_observation in enumerate(evidence["observations"]):
        where = f"runtime_evidence.observations[{index}]"
        observation = _exact_object(raw_observation, OBSERVATION_KEYS, where)

        invocation_id = _string(observation["invocation_id"], f"{where}.invocation_id")
        _require(invocation_id not in seen_invocations, f"{where}.invocation_id must be unique")
        seen_invocations.add(invocation_id)

        for name in ("tool", "actor", "session_id", "message_id", "call_id"):
            state, _ = _field(observation[name], f"{where}.{name}", value_type=str)
            has_unsupported_field |= state == "unsupported"

        _require(observation["mode"] in MODES, f"{where}.mode is invalid")

        parent_state, parent = _field(observation["parent"], f"{where}.parent")
        has_unsupported_field |= parent_state == "unsupported"
        if parent_state == "available":
            parent = _exact_object(parent, {"kind", "id"}, f"{where}.parent.value")
            _require(parent["kind"] in {"invocation", "session"}, f"{where}.parent.value.kind is invalid")
            _string(parent["id"], f"{where}.parent.value.id")

        input_state, _ = _field(observation["input"], f"{where}.input")
        has_unsupported_field |= input_state == "unsupported"

        outcome = observation["outcome"]
        _require(outcome in OUTCOMES, f"{where}.outcome is invalid")

        result_state, _ = _field(observation["result"], f"{where}.result")
        error_state, _ = _field(observation["error"], f"{where}.error")
        has_unsupported_field |= result_state == "unsupported" or error_state == "unsupported"

        start_sequence = observation["start_sequence"]
        _require(type(start_sequence) is int and start_sequence >= 0, f"{where}.start_sequence must be >= 0")
        _require(start_sequence > previous_start, "observations must be ordered by increasing start_sequence")
        _require(start_sequence not in seen_sequences, f"{where}.start_sequence must be unique")
        previous_start = start_sequence
        seen_sequences.add(start_sequence)

        terminal_state, terminal_sequence = _field(
            observation["terminal_sequence"], f"{where}.terminal_sequence", value_type=int
        )
        has_unsupported_field |= terminal_state == "unsupported"

        if outcome == "success":
            _require(result_state in {"available", "redacted", "unsupported"}, f"{where}.result is invalid for success")
            _require(error_state == "omitted", f"{where}.error must be omitted on success")
            _require(terminal_state == "available", f"{where}.terminal_sequence must be available on success")
            terminal_observations += 1
        elif outcome == "error":
            _require(error_state in {"available", "redacted", "unsupported"}, f"{where}.error is invalid for error")
            _require(result_state == "omitted", f"{where}.result must be omitted on error")
            _require(terminal_state == "available", f"{where}.terminal_sequence must be available on error")
            terminal_observations += 1
        else:
            _require(result_state == error_state == "omitted", f"{where} missing outcome cannot carry result/error")
            _require(terminal_state == "omitted", f"{where}.terminal_sequence must be omitted when terminal is missing")

        if terminal_state == "available":
            _require(terminal_sequence >= 0, f"{where}.terminal_sequence must be >= 0")
            _require(terminal_sequence > start_sequence, f"{where}.terminal_sequence must follow start_sequence")
            _require(terminal_sequence not in seen_sequences, f"{where}.terminal_sequence must be unique")
            seen_sequences.add(terminal_sequence)

    counts_available = starts_state == terminals_state == missing_state == "available"
    coverage_complete = False
    if counts_available:
        _require(starts >= terminals, "coverage starts must be >= terminals")
        _require(missing == starts - terminals, "coverage missing_terminals must equal starts - terminals")
        _require(starts == len(evidence["observations"]), "coverage starts must equal observation count")
        _require(terminals == terminal_observations, "coverage terminals must equal terminal observation count")
        coverage_complete = missing == 0 and not losses and not unsupported

    if has_unsupported_field:
        _require(unsupported, "unsupported observation fields must be reflected in coverage.unsupported")

    if status == "complete":
        _require(counts_available and coverage_complete, "complete runtime evidence cannot contain coverage gaps")
        _require(not has_unsupported_field, "complete runtime evidence cannot contain unsupported observation fields")
    elif status == "unsupported":
        _require(not evidence["observations"], "unsupported runtime evidence cannot contain observations")
        _require(unsupported, "unsupported runtime evidence requires an unsupported reason")
        _require(
            starts_state == terminals_state == missing_state == "unsupported",
            "unsupported runtime evidence requires unsupported coverage counts",
        )
    elif status == "incomplete":
        _require(
            bool(losses or unsupported or not counts_available or not coverage_complete),
            "incomplete runtime evidence must identify an incomplete condition",
        )
    else:
        _require(bool(losses or unsupported), "invalid runtime evidence must identify why capture was invalid")

    expected_eligible = status == "complete" and coverage_complete and not has_unsupported_field
    _require(
        evidence["evidence_eligible"] == expected_eligible,
        "runtime_evidence.evidence_eligible does not match contract eligibility",
    )
    return evidence
