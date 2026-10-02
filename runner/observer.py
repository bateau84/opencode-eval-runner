"""Fail-closed importer for an independently trusted execution-hook observer.

This module never observes tools or signs records. The producer must implement
and attest the boundary described in docs/execution-observer.md. In particular,
a signing key in the evaluated container is NOT a trusted observer deployment.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any

PROTOCOL = b"opencode-eval-observer/v1\0"
MOUNT = "/eval-observer"
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_FRAME_BYTES = 256 * 1024
MAX_FRAMES = 10001
MAX_FIELD_BYTES = 16384
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:/@-]{1,256}\Z")
SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token|authorization|credential|api[-_]?key|private[-_]?key",
    re.IGNORECASE,
)


class InvalidCapture(ValueError):
    """A constant, non-sensitive reason code; never includes producer text."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidCapture("duplicate_json_key")
        result[key] = value
    return result


def _invalid_number(_: str) -> None:
    raise InvalidCapture("nonfinite_number")


def _json(raw: bytes) -> Any:
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_invalid_number)
    # Also reject overflowed floats and unpaired UTF-16 surrogates.
    json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return value


def projection(run_id: str | None = None) -> dict[str, Any]:
    return {
        "kind": "execution-observer-projection", "version": 1,
        "run_id": run_id, "status": "unavailable", "evidence_eligible": False,
        "records": [], "issues": [],
        "coverage": {
            "capture_started": False, "capture_ended": False,
            "observed_starts": 0, "observed_terminals": 0,
            "missing_terminals": 0, "omitted_records": None,
            "truncated": False, "unsupported": [],
        },
    }


def unavailable(reason: str, run_id: str | None = None) -> dict[str, Any]:
    result = projection(run_id)
    result["issues"].append(reason)
    return result


def _keys(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
        raise InvalidCapture("invalid_record_shape")


def _integer(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 2**53 - 1


def _identity(value: Any, known_secrets: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise InvalidCapture("invalid_identity")
    if any(secret in value for secret in known_secrets):
        raise InvalidCapture("unsafe_identity")
    return value


def _scrub(value: Any, known_secrets: tuple[str, ...]) -> tuple[Any, bool]:
    """Defense in depth AFTER the producer's authenticated safe-redaction claim."""
    changed = False
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            safe_key, key_changed = _scrub(key, known_secrets)
            if safe_key in result:
                # Redaction must not merge two distinct input keys.
                raise InvalidCapture("redaction_key_collision")
            if SENSITIVE_KEY.search(key):
                result[safe_key] = "[REDACTED]"
                changed = True
            else:
                result[safe_key], item_changed = _scrub(item, known_secrets)
                changed |= item_changed
            changed |= key_changed
        return result, changed
    if isinstance(value, list):
        items = [_scrub(item, known_secrets) for item in value]
        return [item for item, _ in items], any(flag for _, flag in items)
    if isinstance(value, str):
        safe = value
        for secret in known_secrets:
            safe = safe.replace(secret, "[REDACTED]")
        return safe, safe != value
    return value, False


def _field(value: Any, known_secrets: tuple[str, ...], limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"state": "omitted", "reason": "unsafe_redaction"}
    state = value.get("state")
    if state not in {"available", "redacted", "omitted", "truncated"}:
        raise InvalidCapture("invalid_field_state")
    if state in {"omitted", "truncated"}:
        # Reasons and previews from the producer might themselves contain secrets.
        return {"state": state, "reason": "producer_" + state}
    if value.get("redaction") != "safe" or "value" not in value:
        return {"state": "omitted", "reason": "unsafe_redaction"}
    safe, changed = _scrub(value["value"], known_secrets)
    # Redaction happens BEFORE any clipping/size decision. Oversized fields are
    # omitted, never returned as a deceptively complete prefix or parsed JSON.
    size = len(json.dumps(safe, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    if size > limit:
        return {"state": "truncated", "reason": "field_limit"}
    return {"state": "redacted" if changed or state == "redacted" else "available", "value": safe}


def _read_regular(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise InvalidCapture("unsafe_capture_file")
        if info.st_size > limit:
            raise InvalidCapture("capture_limit")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise InvalidCapture("capture_limit")
        return raw
    finally:
        os.close(fd)


def load_capture(
    path: Path, *, key: bytes, run_id: str, known_secrets: tuple[str, ...] = (),
    field_limit: int = MAX_FIELD_BYTES, transport_ok: bool = True,
) -> dict[str, Any]:
    """Return a sanitized projection. No malformed/partial capture can be eligible.

    Authentication is relative to a trusted producer with an isolated key. It
    does not prove that an arbitrary hook implementation sees the final result.
    """
    result = projection(run_id)
    coverage = result["coverage"]
    calls: dict[str, dict[str, Any]] = {}
    known_secrets = tuple(sorted({s for s in known_secrets if s}, key=len, reverse=True))
    try:
        raw = _read_regular(path, MAX_CAPTURE_BYTES)
        if not raw:
            return unavailable("empty_capture", run_id)
        if not raw.endswith(b"\n"):
            coverage["truncated"] = True
            raise InvalidCapture("unterminated_capture")
        lines = raw.splitlines()
        if len(lines) > MAX_FRAMES:
            raise InvalidCapture("record_limit")
        previous = bytes(32)
        ended = False
        for sequence, line in enumerate(lines):
            if ended:
                raise InvalidCapture("records_after_capture_end")
            if len(line) > MAX_FRAME_BYTES:
                raise InvalidCapture("frame_limit")
            envelope = _json(line)
            _keys(envelope, {"payload", "mac"})
            if not isinstance(envelope["payload"], str) or not isinstance(envelope["mac"], str):
                raise InvalidCapture("invalid_envelope")
            payload = base64.b64decode(envelope["payload"], validate=True)
            mac = hmac.new(key, PROTOCOL + run_id.encode("ascii") + b"\0" + previous + payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, envelope["mac"]):
                raise InvalidCapture("authentication_failed")
            previous = bytes.fromhex(mac)
            event = _json(payload)
            if not isinstance(event, dict) or event.get("run_id") != run_id:
                raise InvalidCapture("wrong_run")
            if type(event.get("seq")) is not int or event["seq"] != sequence:
                raise InvalidCapture("ambiguous_order")
            kind = event.get("kind")
            common = {"kind", "run_id", "seq"}
            if sequence == 0:
                _keys(event, common | {"version", "source", "boundary", "correlation", "ordering"})
                if kind != "capture_start" or type(event["version"]) is not int or event["version"] != 1:
                    raise InvalidCapture("unsupported_version")
                expected = {
                    "source": "loom-execution-hook", "boundary": "tool-return-to-caller",
                    "correlation": "execution-invocation-id", "ordering": "monotonic-sequence",
                }
                if any(event[name] != value for name, value in expected.items()):
                    raise InvalidCapture("unsupported_capture_boundary")
                coverage["capture_started"] = True
            elif kind == "call_start":
                _keys(event, common | {"invocation_id", "tool", "input", "actor", "parent", "mode"})
                invocation = _identity(event["invocation_id"], known_secrets)
                if invocation in calls:
                    raise InvalidCapture("duplicate_invocation")
                _keys(event["actor"], {"agent", "session_id"})
                actor = {name: _identity(value, known_secrets) for name, value in event["actor"].items()}
                if event["mode"] not in {"native", "code_mode"}:
                    raise InvalidCapture("unsupported_call_mode")
                parent = event["parent"]
                if parent is not None:
                    _keys(parent, {"session_id", "call_id"})
                    parent = {name: _identity(value, known_secrets) for name, value in parent.items()}
                elif event["mode"] == "code_mode":
                    raise InvalidCapture("missing_parent")
                calls[invocation] = {
                    "invocation_id": invocation, "tool": _identity(event["tool"], known_secrets),
                    "actor": actor, "parent": parent, "mode": event["mode"],
                    "input": _field(event["input"], known_secrets, field_limit),
                    "start_sequence": sequence, "terminal_sequence": None,
                    "outcome": "missing", "evidence_eligible": False,
                }
                coverage["observed_starts"] += 1
            elif kind == "call_end":
                _keys(event, common | {"invocation_id", "outcome"}, {"result", "error"})
                invocation = _identity(event["invocation_id"], known_secrets)
                call = calls.get(invocation)
                if call is None or call["terminal_sequence"] is not None:
                    raise InvalidCapture("ambiguous_terminal")
                outcome = event["outcome"]
                field = {"returned": "result", "threw": "error"}.get(outcome)
                if field is None or field not in event or ("error" if field == "result" else "result") in event:
                    raise InvalidCapture("invalid_terminal")
                call.update(outcome=outcome, terminal_sequence=sequence)
                call[field] = _field(event[field], known_secrets, field_limit)
                coverage["observed_terminals"] += 1
            elif kind == "capture_end":
                _keys(event, common | {"calls_started", "calls_ended", "omitted_records", "truncated", "unsupported"})
                for name in ("calls_started", "calls_ended", "omitted_records"):
                    if not _integer(event[name]):
                        raise InvalidCapture("invalid_completeness")
                if event["calls_started"] != len(calls) or event["calls_ended"] != coverage["observed_terminals"]:
                    raise InvalidCapture("count_mismatch")
                if type(event["truncated"]) is not bool or not isinstance(event["unsupported"], list):
                    raise InvalidCapture("invalid_completeness")
                coverage.update(
                    capture_ended=True, omitted_records=event["omitted_records"],
                    truncated=event["truncated"],
                    unsupported=[_identity(item, known_secrets) for item in event["unsupported"]],
                )
                ended = True
            else:
                raise InvalidCapture("unknown_record_kind")
        result["records"] = list(calls.values())  # start order, NEVER completion order
        coverage["missing_terminals"] = sum(call["outcome"] == "missing" for call in calls.values())
        if not ended:
            result["issues"].append("missing_capture_end")
        if coverage["missing_terminals"]:
            result["issues"].append("missing_terminals")
        if coverage["omitted_records"]:
            result["issues"].append("omitted_records")
        if coverage["unsupported"]:
            result["issues"].append("unsupported_capture")
        if coverage["truncated"]:
            result["issues"].append("truncated_capture")
        for call in calls.values():
            fields = [call[name] for name in ("input", "result", "error") if name in call]
            if any(field["state"] != "available" for field in fields):
                if "incomplete_fields" not in result["issues"]:
                    result["issues"].append("incomplete_fields")
            if any(field["state"] == "truncated" for field in fields):
                coverage["truncated"] = True
        if not transport_ok:
            result["issues"].append("transport_failed")
        result["evidence_eligible"] = not result["issues"]
        result["status"] = "complete" if result["evidence_eligible"] else "incomplete"
        for call in calls.values():
            call["evidence_eligible"] = result["evidence_eligible"]
    except FileNotFoundError:
        return unavailable("missing_capture", run_id)
    except InvalidCapture as exc:
        code = str(exc)
        result["status"] = "unsupported" if code.startswith("unsupported_") else "invalid"
        result["issues"] = [code]
        result["records"] = []
        if code in {"capture_limit", "record_limit", "frame_limit", "unterminated_capture"}:
            coverage["truncated"] = True
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, binascii.Error):
        result["status"] = "invalid"
        result["issues"] = ["malformed_capture"]
        result["records"] = []
    coverage["missing_terminals"] = coverage["observed_starts"] - coverage["observed_terminals"]
    return result


class ObserverCapture:
    """Fresh per-invoke transport. Only the public nonce/path reach the target."""

    def __init__(self, key_path: Path, root: Path, command: list[str], host_env: dict[str, str]):
        self.key = _read_regular(key_path, 4096)
        if len(self.key) < 32:
            raise ValueError("observer key must contain at least 32 bytes")
        resolved = key_path.resolve()
        if resolved.stat().st_mode & 0o077:
            raise ValueError("observer key file must be private (mode 0600)")
        key_encodings = {self.key, self.key.hex().encode(), base64.b64encode(self.key)}
        for index, argument in enumerate(command[:-1]):
            if argument not in {"--volume", "--env"}:
                continue
            specification = command[index + 1]
            if argument == "--volume":
                source = Path(specification.rsplit(":", 2)[0]).resolve()
                if resolved == source or source in resolved.parents:
                    raise ValueError("observer key must be outside all container mounts")
                if source.is_file() and os.path.samefile(source, resolved):
                    raise ValueError("observer key must not be mounted")
                target = specification.rsplit(":", 2)[1]
                if target == "/" or target == MOUNT or target.startswith(MOUNT + "/"):
                    raise ValueError("observer mount target is reserved")
            else:
                name, _, inline = specification.partition("=")
                value = inline if "=" in specification else host_env.get(name, "")
                if value.encode("utf-8") in key_encodings:
                    raise ValueError("observer key must not be forwarded in the environment")
                if name.startswith("EVAL_OBSERVER_"):
                    raise ValueError("observer environment names are reserved")
        self.run_id = secrets.token_hex(32)
        capture_dir = root / "observer"
        capture_dir.mkdir(mode=0o777)
        capture_dir.chmod(0o777)  # writable by the image's non-root UID under Docker
        self.path = capture_dir / "records.jsonl"
        command[-1:-1] = [
            "--volume", f"{capture_dir}:{MOUNT}:rw",
            "--env", "EVAL_OBSERVER_PROTOCOL=1",
            "--env", f"EVAL_OBSERVER_RUN_ID={self.run_id}",
            "--env", f"EVAL_OBSERVER_PATH={MOUNT}/records.jsonl",
        ]
        # No automatic forwarding of credentials/signing material. Redact known
        # host secrets as a second layer; the producer must sanitize unknown ones.
        self.known_secrets = tuple(value for name, value in host_env.items() if value and SENSITIVE_KEY.search(name))
        try:
            self.known_secrets += (self.key.decode("utf-8"),)
        except UnicodeError:
            pass
        self.known_secrets += (self.key.hex(), base64.b64encode(self.key).decode("ascii"))

    def finish(self, *, transport_ok: bool) -> dict[str, Any]:
        return load_capture(self.path, key=self.key, run_id=self.run_id,
                            known_secrets=self.known_secrets, transport_ok=transport_ok)
