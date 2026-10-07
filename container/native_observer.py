from __future__ import annotations

import json
import os
import socket
import stat
import threading
from pathlib import Path
from typing import Any

OBSERVER_STREAM_ENV = "OPENCODE_EVAL_OBSERVER_STREAM"
SCHEMA = "opencode-eval-runner/runtime-observer-event/v1"
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 20001


class InvalidObservation(ValueError):
    pass


def _constant(_: str) -> Any:
    raise InvalidObservation("malformed_capture")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidObservation("malformed_capture")
        result[key] = value
    return result


def _read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise InvalidObservation("malformed_capture")
        if info.st_size > MAX_CAPTURE_BYTES:
            raise InvalidObservation("malformed_capture")
        raw = os.read(fd, MAX_CAPTURE_BYTES + 1)
        if len(raw) > MAX_CAPTURE_BYTES:
            raise InvalidObservation("malformed_capture")
        return raw
    finally:
        os.close(fd)


class RuntimeObservationTransport:
    """One-connection runner-owned loopback stream for observer records."""

    def __init__(self) -> None:
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        host, port = self._listener.getsockname()
        self.endpoint = f"{host}:{port}"
        self._data = bytearray()
        self._issue: str | None = None
        self._closing = False
        self._thread = threading.Thread(target=self._receive, name="runtime-observer-capture", daemon=True)
        self._thread.start()

    def _receive(self) -> None:
        try:
            connection, _ = self._listener.accept()
            self._listener.close()
            with connection:
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    if len(self._data) + len(chunk) > MAX_CAPTURE_BYTES:
                        self._issue = "malformed_capture"
                        continue
                    self._data.extend(chunk)
        except OSError:
            if not self._closing:
                self._issue = "capture_io_error"

    def finish(self) -> dict[str, Any]:
        self._closing = True
        try:
            self._listener.close()
        except OSError:
            pass
        self._thread.join(timeout=2)
        if self._thread.is_alive():
            self._issue = "capture_io_error"
        capture = load_runtime_observations(bytes(self._data))
        if self._issue and self._issue not in capture["issues"]:
            capture["issues"].append(self._issue)
        return capture


def _counter(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def empty_capture(reason: str) -> dict[str, Any]:
    return {
        "capture_started": False,
        "capture_ended": False,
        "records": [],
        "observer_failures": None,
        "callback_failures": None,
        "issues": [reason],
    }


def load_runtime_observations(source: bytes | Path) -> dict[str, Any]:
    """Parse internal observer input without assigning evidence status.

    Production passes bytes received from the runner-owned one-connection stream.
    Path input remains only for parser/unit-test coverage; it is not an
    authoritative runtime transport.

    The runtime_evidence builder is the only owner of completeness, status,
    eligibility, and the public wire representation.
    """
    try:
        raw = source if isinstance(source, bytes) else _read(source)
    except FileNotFoundError:
        return empty_capture("missing_capture")
    except (OSError, InvalidObservation):
        return empty_capture("malformed_capture")

    if not raw:
        return empty_capture("empty_capture")

    issues: list[str] = []
    if not raw.endswith(b"\n"):
        issues.append("unterminated_capture")
    lines = raw.splitlines()
    if len(lines) > MAX_RECORDS:
        return empty_capture("malformed_capture")

    records: list[dict[str, Any]] = []
    capture_started = False
    capture_ended = False
    end_event: dict[str, Any] | None = None
    seen_sequences: set[int] = set()

    for line_index, line in enumerate(lines):
        try:
            event = json.loads(
                line.decode("utf-8"),
                object_pairs_hook=_object,
                parse_constant=_constant,
            )
        except (json.JSONDecodeError, UnicodeDecodeError, InvalidObservation):
            if "malformed_capture" not in issues:
                issues.append("malformed_capture")
            continue

        if not isinstance(event, dict) or event.get("schema") != SCHEMA:
            if "wrong_schema" not in issues:
                issues.append("wrong_schema")
            continue

        sequence = event.get("sequence")
        if (
            type(sequence) is not int
            or sequence < 0
            or sequence in seen_sequences
            or sequence != line_index
        ):
            if "ambiguous_order" not in issues:
                issues.append("ambiguous_order")
            continue
        seen_sequences.add(sequence)

        if (
            _counter(event.get("observer_failures")) is None
            or _counter(event.get("callback_failures")) is None
        ):
            if "malformed_capture" not in issues:
                issues.append("malformed_capture")
            continue

        kind = event.get("kind")
        if line_index == 0:
            expected = {
                "kind": "capture_start",
                "version": 1,
                "source": "stock-opencode-2.0.23-plugin",
                "native_input_boundary": "decoded-tool-execute+outer-execute-before",
                "native_terminal_boundary": "session.tool.success+session.tool.failed",
                "code_input_boundary": "decoded-code-tool-handler",
                "code_terminal_boundary": "tool-handler-return+tool-handler-throw",
                "code_finality": "unsupported",
                "code_finality_reason": "stock_codemode_final_boundary_not_exposed",
                "correlation": "identity-not-input-or-fifo",
                "ordering": "observer-monotonic-sequence",
            }
            if any(event.get(key) != value for key, value in expected.items()):
                issues.append("invalid_capture_start")
            else:
                capture_started = True
            continue

        if capture_ended:
            issues.append("records_after_capture_end")
            continue

        if kind == "capture_end":
            required = (
                "native_starts",
                "native_terminals",
                "code_starts",
                "code_terminals",
                "observer_failures",
                "callback_failures",
                "unavailable_fields",
            )
            if any(_counter(event.get(name)) is None for name in required):
                issues.append("invalid_capture_end")
                continue
            capture_ended = True
            end_event = event
            continue

        if kind not in {
            "native_start",
            "native_terminal",
            "code_start",
            "code_terminal",
        }:
            issues.append("invalid_record")
            continue
        records.append(event)

    if not capture_started and "invalid_capture_start" not in issues:
        issues.append("invalid_capture_start")
    if not capture_ended:
        issues.append("missing_capture_end")

    native_starts = sum(item.get("kind") == "native_start" for item in records)
    native_terminals = sum(item.get("kind") == "native_terminal" for item in records)
    code_starts = sum(item.get("kind") == "code_start" for item in records)
    code_terminals = sum(item.get("kind") == "code_terminal" for item in records)

    observer_failures: int | None = None
    callback_failures: int | None = None
    if end_event is not None:
        observer_failures = end_event["observer_failures"]
        callback_failures = end_event["callback_failures"]
        if (
            end_event["native_starts"] != native_starts
            or end_event["native_terminals"] != native_terminals
            or end_event["code_starts"] != code_starts
            or end_event["code_terminals"] != code_terminals
        ):
            issues.append("count_mismatch")

    return {
        "capture_started": capture_started,
        "capture_ended": capture_ended,
        "records": records,
        "observer_failures": observer_failures,
        "callback_failures": callback_failures,
        "issues": list(dict.fromkeys(issues)),
    }
