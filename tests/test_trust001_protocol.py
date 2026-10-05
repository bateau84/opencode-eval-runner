from __future__ import annotations

import json
import unittest

from runner.trust001.protocol import (
    EVIDENCE_KINDS,
    FrameReader,
    ProtocolError,
    WIRE_VERSION,
    encode,
    validate_capability,
    validate_evidence,
)
from runner.trust001.state import CapabilityLedger, EvidenceLedger


GEN = "a" * 64
REQ = "b" * 32


class ProtocolTests(unittest.TestCase):
    def test_channel_message_kinds_do_not_overlap(self):
        from runner.trust001.protocol import CAPABILITY_KINDS
        self.assertFalse(CAPABILITY_KINDS & EVIDENCE_KINDS)

    def test_capability_rejects_evidence_frame(self):
        value = {
            "version": WIRE_VERSION,
            "kind": "evidence.observation",
            "generation": GEN,
            "sequence": 1,
            "payload": {"safe": True},
        }
        with self.assertRaises(ProtocolError):
            validate_capability(value)

    def test_evidence_rejects_capability_frame(self):
        value = {
            "version": WIRE_VERSION,
            "kind": "capability.response",
            "generation": GEN,
            "request_id": REQ,
            "ok": True,
            "payload": {"safe": True},
        }
        with self.assertRaises(ProtocolError):
            validate_evidence(value)

    def test_frame_reader_handles_fragmented_input(self):
        message = {
            "version": WIRE_VERSION,
            "kind": "evidence.observation",
            "generation": GEN,
            "sequence": 1,
            "payload": {"value": "public"},
        }
        raw = encode(message)
        reader = FrameReader()
        self.assertEqual(reader.feed(raw[:3], channel="evidence"), [])
        self.assertEqual(reader.feed(raw[3:9], channel="evidence"), [])
        self.assertEqual(reader.feed(raw[9:], channel="evidence"), [message])

    def test_duplicate_json_keys_rejected(self):
        raw = (
            '{"version":"' + WIRE_VERSION + '","kind":"evidence.hello",'
            '"generation":"' + GEN + '","role":"bridge","role":"bridge"}'
        ).encode()
        framed = len(raw).to_bytes(4, "big") + raw
        with self.assertRaises(ProtocolError):
            FrameReader().feed(framed, channel="evidence")

    def test_capability_response_shape_is_strict(self):
        good = {
            "version": WIRE_VERSION,
            "kind": "capability.response",
            "generation": GEN,
            "request_id": REQ,
            "ok": True,
            "payload": {"value": 1},
        }
        self.assertEqual(validate_capability(good), good)
        for bad in (
            {**good, "error": "also present"},
            {**good, "unknown": 1},
            {**good, "request_id": "caller-picked prose"},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ProtocolError):
                    validate_capability(bad)


class LifecycleTests(unittest.TestCase):
    def test_capability_response_is_at_most_once(self):
        ledger = CapabilityLedger(GEN)
        ledger.admit(REQ, "session.get")
        self.assertEqual(ledger.settle(REQ), "session.get")
        with self.assertRaises(ProtocolError):
            ledger.settle(REQ)

    def test_cancel_closes_request_to_late_response(self):
        ledger = CapabilityLedger(GEN)
        ledger.admit(REQ, "tool.execute")
        self.assertEqual(ledger.cancel(REQ), "tool.execute")
        with self.assertRaises(ProtocolError):
            ledger.settle(REQ)

    def test_generation_close_blocks_new_requests(self):
        ledger = CapabilityLedger(GEN)
        ledger.close_admission()
        with self.assertRaises(ProtocolError):
            ledger.admit(REQ, "session.get")

    def test_seal_requires_contiguous_final_sequence(self):
        ledger = EvidenceLedger(GEN)
        ledger.observe(1, {"kind": "first"})
        ledger.observe(2, {"kind": "second"})
        ledger.seal(2)
        self.assertTrue(ledger.complete)

    def test_sequence_gap_rejects_checkpoint(self):
        ledger = EvidenceLedger(GEN)
        with self.assertRaises(ProtocolError):
            ledger.observe(2, {"kind": "gap"})
        self.assertTrue(ledger.invalid)
        self.assertFalse(ledger.complete)

    def test_post_seal_observation_rejects_checkpoint(self):
        ledger = EvidenceLedger(GEN)
        ledger.observe(1, {"kind": "first"})
        ledger.seal(1)
        with self.assertRaises(ProtocolError):
            ledger.observe(2, {"kind": "late"})
        self.assertTrue(ledger.invalid)
        self.assertFalse(ledger.complete)

    def test_empty_generation_can_seal_at_zero(self):
        ledger = EvidenceLedger(GEN)
        ledger.seal(0)
        self.assertTrue(ledger.complete)


if __name__ == "__main__":
    unittest.main()
