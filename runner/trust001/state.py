from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

from .protocol import ProtocolError, REQUEST_RE, require


@dataclass
class CapabilityLedger:
    generation: str
    outstanding: dict[str, str] = field(default_factory=dict)
    terminal: set[str] = field(default_factory=set)
    closed: bool = False

    def allocate(self, operation: str) -> str:
        require(not self.closed, "generation_closed")
        request_id = secrets.token_hex(16)
        while request_id in self.outstanding or request_id in self.terminal:
            request_id = secrets.token_hex(16)
        self.outstanding[request_id] = operation
        return request_id

    def admit(self, request_id: str, operation: str) -> None:
        """Deterministic helper for provider-free fixtures; production should allocate()."""
        require(not self.closed, "generation_closed")
        require(REQUEST_RE.fullmatch(request_id) is not None, "invalid_request_id")
        require(request_id not in self.outstanding and request_id not in self.terminal, "duplicate_request")
        self.outstanding[request_id] = operation

    def settle(self, request_id: str) -> str:
        require(request_id in self.outstanding, "unknown_or_late_response")
        operation = self.outstanding.pop(request_id)
        self.terminal.add(request_id)
        return operation

    def cancel(self, request_id: str) -> str:
        return self.settle(request_id)

    def close_admission(self) -> None:
        self.closed = True

    @property
    def settled(self) -> bool:
        return self.closed and not self.outstanding


@dataclass
class EvidenceLedger:
    generation: str
    sequence: int = 0
    observations: list[Any] = field(default_factory=list)
    sealed: bool = False
    invalid: bool = False
    failure: str | None = None

    def _fail(self, reason: str) -> None:
        self.invalid = True
        self.failure = self.failure or reason
        raise ProtocolError(reason)

    def observe(self, sequence: int, payload: Any) -> None:
        if self.sealed:
            self._fail("post_seal_observation")
        expected = self.sequence + 1
        if sequence != expected:
            self._fail("non_contiguous_sequence")
        self.sequence = sequence
        self.observations.append(payload)

    def seal(self, final_sequence: int) -> None:
        if self.sealed:
            self._fail("duplicate_seal")
        if final_sequence != self.sequence:
            self._fail("seal_sequence_mismatch")
        self.sealed = True

    @property
    def complete(self) -> bool:
        return self.sealed and not self.invalid
