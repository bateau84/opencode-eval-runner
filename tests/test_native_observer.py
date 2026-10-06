from __future__ import annotations

import json
import socket
from pathlib import Path
import tempfile
import unittest

from container.native_observer import (
    SCHEMA,
    RuntimeObservationTransport,
    load_runtime_observations,
)


def available(value):
    return {"state": "available", "value": value}


HEADER = {
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


def event(sequence, kind, **extra):
    return {
        "schema": SCHEMA,
        "sequence": sequence,
        "observer_failures": 0,
        "callback_failures": 0,
        "kind": kind,
        **extra,
    }


def native_start(sequence=1):
    return event(
        sequence,
        "native_start",
        invocation_id="native-1",
        tool=available("fixture_native"),
        session_id=available("ses-1"),
        agent=available("general"),
        message_id=available("msg-1"),
        call_id=available("call-1"),
        parent_session_id=available(None),
        input=available({"value": "accepted"}),
        boundary="decoded-tool-execute",
    )


def native_terminal(sequence=2):
    return event(
        sequence,
        "native_terminal",
        invocation_id="native-1",
        tool=available("fixture_native"),
        session_id=available("ses-1"),
        agent=available("general"),
        message_id=available("msg-1"),
        call_id=available("call-1"),
        outcome="success",
        result=available({"content": "ok"}),
        boundary="session.tool.success",
    )


def capture_end(sequence=3, *, native_starts=1, native_terminals=1, code_starts=0, code_terminals=0):
    return event(
        sequence,
        "capture_end",
        native_starts=native_starts,
        native_terminals=native_terminals,
        code_starts=code_starts,
        code_terminals=code_terminals,
        unavailable_fields=0,
    )


class RuntimeObserverAdapterTests(unittest.TestCase):
    def load(self, records, *, final_newline=True):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            text = "\n".join(json.dumps(item) for item in records)
            if final_newline:
                text += "\n"
            path.write_text(text, encoding="utf-8")
            return load_runtime_observations(path)

    def test_valid_capture_is_raw_adapter_input_only(self):
        result = self.load([
            event(0, **HEADER),
            native_start(),
            native_terminal(),
            capture_end(),
        ])
        self.assertTrue(result["capture_started"])
        self.assertTrue(result["capture_ended"])
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["observer_failures"], 0)
        self.assertEqual(result["callback_failures"], 0)
        self.assertEqual(result["issues"], [])
        self.assertNotIn("status", result)
        self.assertNotIn("evidence_eligible", result)

    def test_runner_owned_stream_capture_round_trip(self):
        records = [
            event(0, **HEADER),
            native_start(),
            native_terminal(),
            capture_end(),
        ]
        payload = ("\n".join(json.dumps(item) for item in records) + "\n").encode()
        transport = RuntimeObservationTransport()
        host, raw_port = transport.endpoint.rsplit(":", 1)
        with socket.create_connection((host, int(raw_port)), timeout=1) as client:
            client.sendall(payload)
        result = transport.finish()
        self.assertTrue(result["capture_started"])
        self.assertTrue(result["capture_ended"])
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["issues"], [])

    def test_missing_capture_does_not_report_zero_coverage(self):
        result = load_runtime_observations(Path("/definitely/missing/runtime-observer.jsonl"))
        self.assertFalse(result["capture_started"])
        self.assertFalse(result["capture_ended"])
        self.assertIsNone(result["observer_failures"])
        self.assertIn("missing_capture", result["issues"])

    def test_sequence_gap_is_invalid_input(self):
        result = self.load([
            event(0, **HEADER),
            native_start(sequence=2),
        ])
        self.assertIn("ambiguous_order", result["issues"])

    def test_missing_capture_end_is_explicit(self):
        result = self.load([
            event(0, **HEADER),
            native_start(),
        ])
        self.assertFalse(result["capture_ended"])
        self.assertIn("missing_capture_end", result["issues"])

    def test_count_mismatch_is_explicit(self):
        result = self.load([
            event(0, **HEADER),
            native_start(),
            native_terminal(),
            capture_end(native_starts=2),
        ])
        self.assertIn("count_mismatch", result["issues"])

    def test_unterminated_capture_is_explicit(self):
        result = self.load([
            event(0, **HEADER),
            native_start(),
        ], final_newline=False)
        self.assertIn("unterminated_capture", result["issues"])

    def test_records_after_end_are_rejected(self):
        result = self.load([
            event(0, **HEADER),
            capture_end(sequence=1, native_starts=0, native_terminals=0),
            native_start(sequence=2),
        ])
        self.assertIn("records_after_capture_end", result["issues"])


if __name__ == "__main__":
    unittest.main()
