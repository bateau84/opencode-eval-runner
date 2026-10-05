from __future__ import annotations

import secrets
import socket
from dataclasses import dataclass
from pathlib import Path

from .channel import OneShotUnixListener, PeerCredentials
from .protocol import require
from .transport import CapabilityRelay, EvidenceCollector


@dataclass
class AdmittedChannels:
    generation: str
    capability: CapabilityRelay
    evidence: EvidenceCollector
    bridge_capability_peer: PeerCredentials | None
    loom_capability_peer: PeerCredentials | None
    evidence_peer: PeerCredentials | None


class ChannelSet:
    """Three physically distinct one-shot endpoints.

    - evidence: visible only to stock OpenCode/bridge
    - capability_bridge: visible only to stock OpenCode/bridge
    - capability_loom: visible only to isolated Loom

    The two capability sockets are joined only by the trusted host relay.
    """

    def __init__(self, root: Path | None = None, generation: str | None = None) -> None:
        self.generation = generation or secrets.token_hex(32)
        require(len(self.generation) == 64, "invalid_generation")
        self.evidence = OneShotUnixListener(root, name="evidence.sock")
        self.capability_bridge = OneShotUnixListener(root, name="bridge.sock")
        self.capability_loom = OneShotUnixListener(root, name="loom.sock")

    def paths(self) -> dict[str, Path]:
        return {
            "evidence": self.evidence.path,
            "capability_bridge": self.capability_bridge.path,
            "capability_loom": self.capability_loom.path,
        }

    def mount_roots(self) -> dict[str, Path]:
        return {
            "evidence": self.evidence.root,
            "capability_bridge": self.capability_bridge.root,
            "capability_loom": self.capability_loom.root,
        }

    def admit(
        self,
        *,
        bridge_uid: int | None = None,
        bridge_gid: int | None = None,
        loom_uid: int | None = None,
        loom_gid: int | None = None,
        timeout: float = 10.0,
    ) -> AdmittedChannels:
        evidence_sock, evidence_peer = self.evidence.accept_once(
            expected_uid=bridge_uid,
            expected_gid=bridge_gid,
            timeout=timeout,
        )
        bridge_sock, bridge_peer = self.capability_bridge.accept_once(
            expected_uid=bridge_uid,
            expected_gid=bridge_gid,
            timeout=timeout,
        )
        loom_sock, loom_peer = self.capability_loom.accept_once(
            expected_uid=loom_uid,
            expected_gid=loom_gid,
            timeout=timeout,
        )
        try:
            capability = CapabilityRelay.admit(self.generation, bridge_sock, loom_sock)
            evidence = EvidenceCollector.admit(self.generation, evidence_sock)
        except Exception:
            evidence_sock.close()
            bridge_sock.close()
            loom_sock.close()
            raise
        return AdmittedChannels(
            generation=self.generation,
            capability=capability,
            evidence=evidence,
            bridge_capability_peer=bridge_peer,
            loom_capability_peer=loom_peer,
            evidence_peer=evidence_peer,
        )

    def cleanup(self) -> None:
        for listener in (self.evidence, self.capability_bridge, self.capability_loom):
            listener.cleanup()

    def __enter__(self) -> "ChannelSet":
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()
