"""Regression cases for capture identity/accounting, not origin attestation."""
import json
import unittest

from test_protected import load, stream


def events():
    return [json.loads(line)["observation"] for line in stream().splitlines()[1:-1]]


class CaptureIdentityTests(unittest.TestCase):
    def test_child_cannot_reuse_its_parent_invocation_id(self):
        records = events()
        for record in records:
            if "invocation_id" in record:
                record["invocation_id"] = "p"
        result = load(stream(records))
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["records"], [])
        self.assertIn("duplicate_or_invalid_invocation", result["issues"])

    def test_later_parent_cannot_reuse_a_completed_child_id(self):
        records = events()
        next_parent = dict(records[0], parent=dict(records[0]["parent"], invocation_id="i"), sequence=5)
        records.append(next_parent)
        result = load(stream(records))
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["issues"], ["duplicate_parent"])


class CaptureAccountingTests(unittest.TestCase):
    def test_missing_terminal_retains_diagnostic_prefix_counts(self):
        records = events()
        del records[2]
        records[-1].update(terminals=0, missing_terminals=1)
        for index, record in enumerate(records, 1):
            record["sequence"] = index
        result = load(stream(records))
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["records"], [])
        self.assertEqual(result["issues"], ["incomplete_parent"])
        self.assertEqual(result["coverage"]["starts"], 1)
        self.assertEqual(result["coverage"]["terminals"], 0)
        self.assertEqual(result["coverage"]["missing_terminals"], 1)
        self.assertIsNone(result["coverage"]["omitted_records"])

    def test_unverified_capture_does_not_claim_zero_missing_terminals(self):
        result = load(stream(), receipt=None)
        self.assertFalse(result["evidence_eligible"])
        self.assertIsNone(result["coverage"]["missing_terminals"])

    def test_invalid_terminal_field_is_not_counted_as_a_terminal(self):
        records = events()
        records[2]["result"] = {"state": "available", "redaction": "unsafe", "value": "x"}
        result = load(stream(records))
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["coverage"]["starts"], 1)
        self.assertEqual(result["coverage"]["terminals"], 0)
        self.assertEqual(result["coverage"]["missing_terminals"], 1)


if __name__ == "__main__":
    unittest.main()
