from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .protocol import ProtocolError, require, validate_capability
from .state import CapabilityLedger

Peer = Literal["bridge", "loom"]


@dataclass
class CapabilityRouter:
    generation: str
    host_calls: CapabilityLedger = field(init=False)
    callbacks: CapabilityLedger = field(init=False)
    failed: bool = False
    failure: str | None = None

    def __post_init__(self) -> None:
        self.host_calls = CapabilityLedger(self.generation)
        self.callbacks = CapabilityLedger(self.generation)

    def _reject(self, reason: str) -> None:
        self.failed = True
        self.failure = self.failure or reason
        raise ProtocolError(reason)

    def route(self, origin: Peer, raw: dict[str, Any]) -> tuple[Peer, dict[str, Any]]:
        if self.failed:
            raise ProtocolError(self.failure or "capability_router_failed")
        message = validate_capability(raw)
        if message["generation"] != self.generation:
            self._reject("stale_generation")

        kind = message["kind"]
        if kind == "capability.hello":
            self._reject("unexpected_hello_after_admission")

        try:
            if origin == "loom":
                if kind == "capability.host.request":
                    self.host_calls.admit(message["request_id"], message["operation"])
                    return "bridge", message
                if kind == "capability.callback.response":
                    self.callbacks.settle(message["request_id"])
                    return "bridge", message
                if kind == "capability.host.cancel":
                    self.host_calls.cancel(message["request_id"])
                    return "bridge", message
                self._reject("loom_direction_violation")

            if origin == "bridge":
                if kind == "capability.callback.request":
                    self.callbacks.admit(message["request_id"], message["operation"])
                    return "loom", message
                if kind == "capability.host.response":
                    self.host_calls.settle(message["request_id"])
                    return "loom", message
                if kind == "capability.callback.cancel":
                    self.callbacks.cancel(message["request_id"])
                    return "loom", message
                self._reject("bridge_direction_violation")
        except ProtocolError as exc:
            self._reject(str(exc))

        self._reject("invalid_origin")

    def close_admission(self) -> None:
        self.host_calls.close_admission()
        self.callbacks.close_admission()

    @property
    def settled(self) -> bool:
        return self.host_calls.settled and self.callbacks.settled
