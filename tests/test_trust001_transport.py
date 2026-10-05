from __future__ import annotations

import socket
import threading
import unittest

from runner.trust001.protocol import ProtocolError, WIRE_VERSION, encode
from runner.trust001.transport import CapabilityRelay, EvidenceCollector, FramedSocket


GEN = "a" * 64
REQ = "b" * 32


class TransportTests(unittest.TestCase):
    def test_capability_relay_admits_roles_and_round_trips_callback(self):
        bridge_client, bridge_server = socket.socketpair()
        loom_client, loom_server = socket.socketpair()
        try:
            FramedSocket(bridge_client, channel="capability").send({
                "version": WIRE_VERSION,
                "kind": "capability.hello",
                "generation": GEN,
                "role": "bridge",
            })
            FramedSocket(loom_client, channel="capability").send({
                "version": WIRE_VERSION,
                "kind": "capability.hello",
                "generation": GEN,
                "role": "loom",
            })
            relay = CapabilityRelay.admit(GEN, bridge_server, loom_server)

            bridge = FramedSocket(bridge_client, channel="capability")
            loom = FramedSocket(loom_client, channel="capability")
            request = {
                "version": WIRE_VERSION,
                "kind": "capability.callback.request",
                "generation": GEN,
                "request_id": REQ,
                "operation": "trust001.preflight.ping",
                "payload": {"value": "ping"},
            }
            bridge.send(request)
            self.assertEqual(relay.relay_bridge_once(), request)
            self.assertEqual(loom.recv(), request)

            response = {
                "version": WIRE_VERSION,
                "kind": "capability.callback.response",
                "generation": GEN,
                "request_id": REQ,
                "ok": True,
                "payload": {"value": "pong"},
            }
            loom.send(response)
            self.assertEqual(relay.relay_loom_once(), response)
            self.assertEqual(bridge.recv(), response)
        finally:
            for sock in (bridge_client, bridge_server, loom_client, loom_server):
                sock.close()

    def test_evidence_collector_requires_contiguous_seal(self):
        client, server = socket.socketpair()
        try:
            wire = FramedSocket(client, channel="evidence")
            wire.send({
                "version": WIRE_VERSION,
                "kind": "evidence.hello",
                "generation": GEN,
                "role": "bridge",
            })
            collector = EvidenceCollector.admit(GEN, server)
            wire.send({
                "version": WIRE_VERSION,
                "kind": "evidence.observation",
                "generation": GEN,
                "sequence": 1,
                "payload": {"type": "bridge.activated"},
            })
            collector.receive_once()
            wire.send({
                "version": WIRE_VERSION,
                "kind": "evidence.seal",
                "generation": GEN,
                "final_sequence": 1,
            })
            collector.receive_once()
            self.assertTrue(collector.ledger.complete)
        finally:
            client.close()
            server.close()

    def test_evidence_post_seal_is_rejected(self):
        client, server = socket.socketpair()
        try:
            wire = FramedSocket(client, channel="evidence")
            wire.send({
                "version": WIRE_VERSION,
                "kind": "evidence.hello",
                "generation": GEN,
                "role": "bridge",
            })
            collector = EvidenceCollector.admit(GEN, server)
            wire.send({
                "version": WIRE_VERSION,
                "kind": "evidence.seal",
                "generation": GEN,
                "final_sequence": 0,
            })
            collector.receive_once()
            wire.send({
                "version": WIRE_VERSION,
                "kind": "evidence.observation",
                "generation": GEN,
                "sequence": 1,
                "payload": {"late": True},
            })
            with self.assertRaises(ProtocolError):
                collector.receive_once()
        finally:
            client.close()
            server.close()


if __name__ == "__main__":
    unittest.main()
