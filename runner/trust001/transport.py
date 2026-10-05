from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any

from .broker import CapabilityRouter
from .protocol import FrameReader, ProtocolError, encode, require, validate_evidence
from .state import EvidenceLedger


class FramedSocket:
    def __init__(self, sock: socket.socket, *, channel: str) -> None:
        require(channel in {"capability", "evidence"}, "invalid_channel")
        self.sock = sock
        self.channel = channel
        self.reader = FrameReader()
        self.pending: list[dict[str, Any]] = []

    def send(self, value: dict[str, Any]) -> None:
        self.sock.sendall(encode(value))

    def recv(self) -> dict[str, Any]:
        if self.pending:
            return self.pending.pop(0)
        while True:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ProtocolError("channel_closed")
            frames = self.reader.feed(chunk, channel=self.channel)
            if frames:
                self.pending.extend(frames[1:])
                return frames[0]


@dataclass
class CapabilityRelay:
    generation: str
    bridge: FramedSocket
    loom: FramedSocket
    router: CapabilityRouter

    @classmethod
    def admit(
        cls,
        generation: str,
        bridge_sock: socket.socket,
        loom_sock: socket.socket,
    ) -> "CapabilityRelay":
        bridge = FramedSocket(bridge_sock, channel="capability")
        loom = FramedSocket(loom_sock, channel="capability")
        bridge_hello = bridge.recv()
        loom_hello = loom.recv()
        require(
            bridge_hello == {
                "version": bridge_hello["version"],
                "kind": "capability.hello",
                "generation": generation,
                "role": "bridge",
            },
            "invalid_bridge_hello",
        )
        require(
            loom_hello == {
                "version": loom_hello["version"],
                "kind": "capability.hello",
                "generation": generation,
                "role": "loom",
            },
            "invalid_loom_hello",
        )
        return cls(
            generation=generation,
            bridge=bridge,
            loom=loom,
            router=CapabilityRouter(generation),
        )

    def relay_bridge_once(self) -> dict[str, Any]:
        message = self.bridge.recv()
        target, routed = self.router.route("bridge", message)
        require(target == "loom", "invalid_route")
        self.loom.send(routed)
        return routed

    def relay_loom_once(self) -> dict[str, Any]:
        message = self.loom.recv()
        target, routed = self.router.route("loom", message)
        require(target == "bridge", "invalid_route")
        self.bridge.send(routed)
        return routed


@dataclass
class EvidenceCollector:
    generation: str
    channel: FramedSocket
    ledger: EvidenceLedger

    @classmethod
    def admit(cls, generation: str, sock: socket.socket) -> "EvidenceCollector":
        channel = FramedSocket(sock, channel="evidence")
        hello = channel.recv()
        require(
            hello == {
                "version": hello["version"],
                "kind": "evidence.hello",
                "generation": generation,
                "role": "bridge",
            },
            "invalid_evidence_hello",
        )
        return cls(
            generation=generation,
            channel=channel,
            ledger=EvidenceLedger(generation),
        )

    def receive_once(self) -> dict[str, Any]:
        message = validate_evidence(self.channel.recv())
        require(message["generation"] == self.generation, "stale_generation")
        if message["kind"] == "evidence.observation":
            self.ledger.observe(message["sequence"], message["payload"])
        elif message["kind"] == "evidence.seal":
            self.ledger.seal(message["final_sequence"])
        else:
            raise ProtocolError("unexpected_evidence_hello")
        return message
