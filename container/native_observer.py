from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

OBSERVATION_PATH = Path("/tmp/runtime/native-tool-observer.jsonl")
SCHEMA = "opencode-eval-runner/native-tool-observer-event/v1"
RESULT_SCHEMA = "opencode-eval-runner/native-tool-observations/v1"
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10001


class InvalidObservation(ValueError):
    pass


def projection() -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "status": "unavailable",
        "evidence_eligible": False,
        "records": [],
        "issues": [],
        "coverage": {
            "capture_started": False,
            "capture_ended": False,
            "observed_starts": 0,
            "observed_terminals": 0,
            "missing_terminals": 0,
            "observer_failures": None,
            "unavailable_fields": None,
        },
    }


def unavailable(reason: str) -> dict[str, Any]:
    result = projection()
    result["issues"] = [reason]
    return result


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidObservation("duplicate_json_key")
        result[key] = value
    return result


def _read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise InvalidObservation("unsafe_capture_file")
        if info.st_size > MAX_CAPTURE_BYTES:
            raise InvalidObservation("capture_limit")
        raw = os.read(fd, MAX_CAPTURE_BYTES + 1)
        if len(raw) > MAX_CAPTURE_BYTES:
            raise InvalidObservation("capture_limit")
        return raw
    finally:
        os.close(fd)


def _identity(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024 or "\x00" in value:
        raise InvalidObservation("invalid_identity")
    return value


def _field(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) not in ({"state", "value"}, {"state", "reason"}):
        raise InvalidObservation("invalid_field")
    if value.get("state") == "available":
        return {"state": "available", "value": value["value"]}
    if value.get("state") == "omitted" and isinstance(value.get("reason"), str):
        return {"state": "omitted", "reason": value["reason"]}
    raise InvalidObservation("invalid_field")


def load_native_observations(path: Path = OBSERVATION_PATH) -> dict[str, Any]:
    result = projection()
    coverage = result["coverage"]
    calls: dict[tuple[str, str, str], dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    ended = False
    try:
        raw = _read(path)
        if not raw:
            return unavailable("empty_capture")
        if not raw.endswith(b"\n"):
            raise InvalidObservation("unterminated_capture")
        lines = raw.splitlines()
        if len(lines) > MAX_RECORDS:
            raise InvalidObservation("record_limit")

        for expected_sequence, line in enumerate(lines):
            if ended:
                raise InvalidObservation("records_after_capture_end")
            try:
                event = json.loads(line.decode("utf-8"), object_pairs_hook=_object)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise InvalidObservation("malformed_capture") from exc
            if not isinstance(event, dict) or event.get("schema") != SCHEMA:
                raise InvalidObservation("wrong_schema")
            if event.get("sequence") != expected_sequence:
                raise InvalidObservation("ambiguous_order")
            if not isinstance(event.get("observer_failures"), int) or event["observer_failures"] < 0:
                raise InvalidObservation("invalid_failure_count")

            kind = event.get("kind")
            if expected_sequence == 0:
                if kind != "capture_start" or event.get("version") != 1:
                    raise InvalidObservation("missing_capture_start")
                expected = {
                    "source": "stock-opencode-2.0.23-plugin",
                    "input_boundary": "decoded-tool-execute",
                    "terminal_boundary": "tool.execute.after",
                    "correlation": "session-message-call-id",
                    "ordering": "observer-monotonic-sequence",
                }
                if any(event.get(key) != value for key, value in expected.items()):
                    raise InvalidObservation("unsupported_capture_boundary")
                coverage["capture_started"] = True
                continue

            if kind == "call_start":
                if event.get("boundary") != "decoded-tool-execute":
                    raise InvalidObservation("unsupported_start_boundary")
                identity = {
                    "tool": _identity(event.get("tool")),
                    "session_id": _identity(event.get("session_id")),
                    "agent": _identity(event.get("agent")),
                    "message_id": _identity(event.get("message_id")),
                    "call_id": _identity(event.get("call_id")),
                }
                key = (identity["session_id"], identity["message_id"], identity["call_id"])
                if key in calls:
                    raise InvalidObservation("duplicate_call_start")
                record = {
                    **identity,
                    "input": _field(event.get("input")),
                    "start_sequence": expected_sequence,
                    "terminal_sequence": None,
                    "outcome": "missing",
                }
                calls[key] = record
                ordered.append(record)
                coverage["observed_starts"] += 1
                continue

            if kind == "call_terminal":
                if event.get("boundary") != "tool.execute.after":
                    raise InvalidObservation("unsupported_terminal_boundary")
                session_id = _identity(event.get("session_id"))
                message_id = _identity(event.get("message_id"))
                call_id = _identity(event.get("call_id"))
                key = (session_id, message_id, call_id)
                record = calls.get(key)
                if record is None or record["terminal_sequence"] is not None:
                    raise InvalidObservation("ambiguous_terminal")
                if record["tool"] != _identity(event.get("tool")) or record["agent"] != _identity(event.get("agent")):
                    raise InvalidObservation("identity_changed")
                outcome = event.get("outcome")
                if outcome == "success" and "result" in event and "error" not in event:
                    record["result"] = _field(event["result"])
                elif outcome == "failure" and "error" in event and "result" not in event:
                    record["error"] = _field(event["error"])
                else:
                    raise InvalidObservation("invalid_terminal")
                record["outcome"] = outcome
                record["terminal_sequence"] = expected_sequence
                coverage["observed_terminals"] += 1
                continue

            if kind == "capture_end":
                for field in ("calls_started", "calls_terminal", "outstanding_calls", "observer_failures", "unavailable_fields"):
                    if not isinstance(event.get(field), int) or event[field] < 0:
                        raise InvalidObservation("invalid_completeness")
                if event["calls_started"] != coverage["observed_starts"]:
                    raise InvalidObservation("start_count_mismatch")
                if event["calls_terminal"] != coverage["observed_terminals"]:
                    raise InvalidObservation("terminal_count_mismatch")
                missing = sum(record["outcome"] == "missing" for record in ordered)
                if event["outstanding_calls"] != missing:
                    raise InvalidObservation("outstanding_count_mismatch")
                coverage["capture_ended"] = True
                coverage["observer_failures"] = event["observer_failures"]
                coverage["unavailable_fields"] = event["unavailable_fields"]
                ended = True
                continue

            raise InvalidObservation("unknown_record_kind")

        result["records"] = ordered
        coverage["missing_terminals"] = sum(record["outcome"] == "missing" for record in ordered)
        if not ended:
            result["issues"].append("missing_capture_end")
        if coverage["missing_terminals"]:
            result["issues"].append("missing_terminals")
        if coverage["observer_failures"]:
            result["issues"].append("observer_failures")
        if coverage["unavailable_fields"]:
            result["issues"].append("unavailable_fields")
        if any(
            value.get("state") != "available"
            for record in ordered
            for value in (record.get("input"), record.get("result"), record.get("error"))
            if isinstance(value, dict)
        ) and "unavailable_fields" not in result["issues"]:
            result["issues"].append("unavailable_fields")
        result["evidence_eligible"] = not result["issues"]
        result["status"] = "complete" if result["evidence_eligible"] else "incomplete"
        return result
    except FileNotFoundError:
        return unavailable("missing_capture")
    except InvalidObservation as exc:
        result["status"] = "invalid"
        result["issues"] = [str(exc)]
        result["records"] = []
        return result
    except OSError:
        result["status"] = "invalid"
        result["issues"] = ["capture_io_error"]
        result["records"] = []
        return result
