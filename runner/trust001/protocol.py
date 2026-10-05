from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass
from typing import Any

WIRE_VERSION = "opencode-eval-runner/trust001-wire/v1"
MAX_FRAME_BYTES = 256 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 20_000

GENERATION_RE = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_RE = re.compile(r"[0-9a-f]{32}\Z")

HOST_OPERATIONS = frozenset({
    "storage.get", "storage.set", "storage.scan",
    "rpc.register",
    "agent.transform.register", "agent.list",
    "tool.transform.register", "tool.list", "tool.hook.register",
    "permission.hook.register",
    "session.hook.register", "session.get", "session.context", "session.synthetic",
})

CALLBACK_OPERATIONS = frozenset({
    "rpc.call",
    "tool.execute",
    "tool.execute.before",
    "tool.execute.after",
    "permission.evaluate",
    "session.context",
    "session.retry",
    "trust001.preflight.ping",
})

CAPABILITY_KINDS = frozenset({
    "capability.hello",
    "capability.host.request",
    "capability.host.response",
    "capability.callback.request",
    "capability.callback.response",
    "capability.cancel",
})
EVIDENCE_KINDS = frozenset({
    "evidence.hello",
    "evidence.observation",
    "evidence.seal",
})


class ProtocolError(ValueError):
    pass


def require(ok: bool, message: str = "invalid_protocol") -> None:
    if not ok:
        raise ProtocolError(message)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def _bad_number(_: str) -> None:
    raise ProtocolError("nonfinite_number")


def _bounded_json(value: Any) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        require(nodes <= MAX_JSON_NODES and depth <= MAX_JSON_DEPTH, "json_shape_limit")
        if current is None or type(current) in (bool, int, str):
            if type(current) is str:
                current.encode("utf-8", errors="strict")
            continue
        if type(current) is float:
            require(math.isfinite(current), "nonfinite_number")
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in current)
            continue
        if type(current) is dict:
            require(all(type(key) is str for key in current), "non_string_key")
            pending.extend((item, depth + 1) for item in current.values())
            continue
        raise ProtocolError("non_json_value")


def strict_loads(raw: bytes) -> dict[str, Any]:
    require(len(raw) <= MAX_FRAME_BYTES, "frame_limit")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_bad_number,
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ProtocolError("invalid_json") from exc
    require(type(value) is dict, "frame_not_object")
    _bounded_json(value)
    return value


def encode(value: dict[str, Any]) -> bytes:
    _bounded_json(value)
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ProtocolError("invalid_json") from exc
    require(len(raw) <= MAX_FRAME_BYTES, "frame_limit")
    return struct.pack("!I", len(raw)) + raw


def _exact(value: dict[str, Any], required: set[str], optional: set[str] = frozenset()) -> None:
    require(required <= value.keys(), "missing_field")
    require(not (set(value) - required - optional), "unknown_field")


def _common(value: dict[str, Any], kinds: frozenset[str]) -> tuple[str, str]:
    _exact(value, {"version", "kind", "generation"}, {
        "role", "request_id", "operation", "payload", "ok", "error",
        "reason", "sequence", "final_sequence",
    })
    require(value.get("version") == WIRE_VERSION, "wrong_version")
    kind = value.get("kind")
    generation = value.get("generation")
    require(type(kind) is str and kind in kinds, "wrong_channel_kind")
    require(type(generation) is str and GENERATION_RE.fullmatch(generation) is not None, "invalid_generation")
    return kind, generation


def validate_capability(value: dict[str, Any]) -> dict[str, Any]:
    kind, _ = _common(value, CAPABILITY_KINDS)
    if kind == "capability.hello":
        _exact(value, {"version", "kind", "generation", "role"})
        require(value["role"] in {"bridge", "loom"}, "invalid_role")
        return value

    if kind in {"capability.host.request", "capability.callback.request"}:
        _exact(value, {"version", "kind", "generation", "request_id", "operation", "payload"})
        require(type(value["request_id"]) is str and REQUEST_RE.fullmatch(value["request_id"]) is not None,
                "invalid_request_id")
        require(type(value["operation"]) is str, "invalid_operation")
        allowed = HOST_OPERATIONS if kind == "capability.host.request" else CALLBACK_OPERATIONS
        require(value["operation"] in allowed, "operation_not_admitted")
        _bounded_json(value["payload"])
        return value

    if kind in {"capability.host.response", "capability.callback.response"}:
        _exact(value, {"version", "kind", "generation", "request_id", "ok"}, {"payload", "error"})
        require(type(value["request_id"]) is str and REQUEST_RE.fullmatch(value["request_id"]) is not None,
                "invalid_request_id")
        require(type(value["ok"]) is bool, "invalid_response")
        require(("payload" in value) != ("error" in value), "invalid_response")
        if "error" in value:
            require(type(value["error"]) is str and 0 < len(value["error"]) <= 256, "invalid_error")
        elif "payload" in value:
            _bounded_json(value["payload"])
        return value

    _exact(value, {"version", "kind", "generation", "request_id", "reason"})
    require(type(value["request_id"]) is str and REQUEST_RE.fullmatch(value["request_id"]) is not None,
            "invalid_request_id")
    require(type(value["reason"]) is str and 0 < len(value["reason"]) <= 128, "invalid_reason")
    return value


def validate_evidence(value: dict[str, Any]) -> dict[str, Any]:
    kind, _ = _common(value, EVIDENCE_KINDS)
    if kind == "evidence.hello":
        _exact(value, {"version", "kind", "generation", "role"})
        require(value["role"] == "bridge", "invalid_role")
    elif kind == "evidence.observation":
        _exact(value, {"version", "kind", "generation", "sequence", "payload"})
        require(type(value["sequence"]) is int and 1 <= value["sequence"] <= 2**53 - 1, "invalid_sequence")
        _bounded_json(value["payload"])
    elif kind == "evidence.seal":
        _exact(value, {"version", "kind", "generation", "final_sequence"})
        require(type(value["final_sequence"]) is int and 0 <= value["final_sequence"] <= 2**53 - 1,
                "invalid_final_sequence")
    return value


@dataclass
class FrameReader:
    buffer: bytearray

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes, *, channel: str) -> list[dict[str, Any]]:
        require(channel in {"capability", "evidence"}, "invalid_channel")
        self.buffer.extend(data)
        frames: list[dict[str, Any]] = []
        while len(self.buffer) >= 4:
            size = struct.unpack("!I", self.buffer[:4])[0]
            require(0 < size <= MAX_FRAME_BYTES, "frame_limit")
            if len(self.buffer) < 4 + size:
                break
            raw = bytes(self.buffer[4:4 + size])
            del self.buffer[:4 + size]
            value = strict_loads(raw)
            frames.append(validate_capability(value) if channel == "capability" else validate_evidence(value))
        require(len(self.buffer) <= MAX_FRAME_BYTES + 4, "frame_buffer_limit")
        return frames
