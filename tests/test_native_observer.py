import json
from pathlib import Path
import tempfile
import unittest

from container.native_observer import load_native_observations, SCHEMA


def available(value):
    return {"state": "available", "value": value}


def frames(*events):
    output = []
    for sequence, event in enumerate(events):
        output.append(json.dumps({"schema": SCHEMA, "sequence": sequence, "observer_failures": 0, **event}))
    return "\n".join(output) + "\n"


def start(call="call-1", input_value=None, message="msg-1", tool="native_one"):
    return {
        "kind": "call_start", "tool": tool, "session_id": "ses-1", "agent": "build",
        "message_id": message, "call_id": call, "input": available(input_value or {"tag": "accepted"}),
        "boundary": "decoded-tool-execute",
    }


def terminal(call="call-1", message="msg-1", tool="native_one", outcome="success"):
    base = {
        "kind": "call_terminal", "tool": tool, "session_id": "ses-1", "agent": "build",
        "message_id": message, "call_id": call,
        "boundary": "session.tool.success" if outcome == "success" else "session.tool.failed",
        "outcome": outcome,
    }
    if outcome == "success":
        base["result"] = available({"content": "ok"})
    else:
        base["error"] = available({"type": "Tool.Error", "message": "failed"})
    return base


HEADER = {
    "kind": "capture_start", "version": 1, "source": "stock-opencode-2.0.23-plugin",
    "input_boundary": "decoded-tool-execute",
    "terminal_boundary": "session.tool.success+session.tool.failed",
    "correlation": "session-message-call-id", "ordering": "observer-monotonic-sequence",
}


def end(starts=1, terminals=1, outstanding=0, failures=0, unavailable=0):
    return {
        "kind": "capture_end", "calls_started": starts, "calls_terminal": terminals,
        "outstanding_calls": outstanding, "observer_failures": failures, "unavailable_fields": unavailable,
    }


class NativeObserverTests(unittest.TestCase):
    def load(self, *events):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            path.write_text(frames(*events), encoding="utf-8")
            return load_native_observations(path)

    def test_success_preserves_input_identity_terminal_and_order(self):
        result = self.load(HEADER, start(input_value={"tag": "accepted"}), terminal(), end())
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["records"], [{
            "tool": "native_one", "session_id": "ses-1", "agent": "build", "message_id": "msg-1",
            "call_id": "call-1", "input": available({"tag": "accepted"}), "start_sequence": 1,
            "terminal_sequence": 2, "outcome": "success", "result": available({"content": "ok"}),
        }])

    def test_failure_is_a_real_correlated_terminal(self):
        result = self.load(HEADER, start(), terminal(outcome="failure"), end())
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual(result["records"][0]["outcome"], "failure")
        self.assertEqual(result["records"][0]["error"]["value"]["message"], "failed")

    def test_two_calls_use_ids_not_equal_inputs_and_keep_observed_order(self):
        same = {"tag": "same"}
        result = self.load(
            HEADER,
            start(call="call-a", message="msg-a", input_value=same),
            terminal(call="call-a", message="msg-a"),
            start(call="call-b", message="msg-b", input_value=same),
            terminal(call="call-b", message="msg-b"),
            end(starts=2, terminals=2),
        )
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual([record["call_id"] for record in result["records"]], ["call-a", "call-b"])
        self.assertEqual([(r["start_sequence"], r["terminal_sequence"]) for r in result["records"]], [(1, 2), (3, 4)])

    def test_terminal_without_start_is_rejected_not_invented(self):
        result = self.load(HEADER, terminal(), end(starts=0, terminals=1))
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["issues"], ["ambiguous_terminal"])

    def test_missing_terminal_and_missing_end_fail_closed(self):
        result = self.load(HEADER, start())
        self.assertFalse(result["evidence_eligible"])
        self.assertIn("missing_capture_end", result["issues"])
        self.assertIn("missing_terminals", result["issues"])

    def test_observer_loss_and_omitted_field_fail_closed(self):
        omitted = start()
        omitted["input"] = {"state": "omitted", "reason": "field_limit"}
        finish = end(failures=1, unavailable=1)
        finish["observer_failures"] = 1
        result = self.load(HEADER, omitted, terminal(), finish)
        self.assertFalse(result["evidence_eligible"])
        self.assertIn("observer_failures", result["issues"])
        self.assertIn("unavailable_fields", result["issues"])

    def test_sequence_gap_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            payload = [
                {"schema": SCHEMA, "sequence": 0, "observer_failures": 0, **HEADER},
                {"schema": SCHEMA, "sequence": 2, "observer_failures": 0, **start()},
            ]
            path.write_text("\n".join(json.dumps(item) for item in payload) + "\n", encoding="utf-8")
            result = load_native_observations(path)
        self.assertEqual(result["issues"], ["ambiguous_order"])

    def test_missing_capture_is_unavailable(self):
        result = load_native_observations(Path("/definitely/missing/native-observer.jsonl"))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["issues"], ["missing_capture"])


if __name__ == "__main__":
    unittest.main()
