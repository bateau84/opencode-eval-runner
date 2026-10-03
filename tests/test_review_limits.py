"""QA boundary cases: the declared UTF-8 value limit must match admission."""
import unittest

from test_protected import load, stream
from test_review_accounting import events


class FieldLimitTests(unittest.TestCase):
    def test_over_16k_utf8_value_cannot_be_admitted_as_complete(self):
        records = events()
        records[2]["result"]["value"] = "ø" * 8192  # 16,386 JSON UTF-8 bytes, including quotes.
        result = load(stream(records))
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["issues"], ["field_limit"])
        self.assertTrue(result["coverage"]["truncated"])
        self.assertEqual(result["records"], [])

    def test_exact_utf8_limit_is_available(self):
        records = events()
        records[2]["result"]["value"] = "ø" * 8191  # Exactly 16,384 JSON bytes.
        result = load(stream(records))
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual(result["records"][0]["result"]["value"], "ø" * 8191)

    def test_size_is_wire_json_not_pretty_printing(self):
        records = events()
        records[2]["result"]["value"] = [0] * 8000  # Compact 16,001; spaced 24,000.
        self.assertTrue(load(stream(records))["evidence_eligible"])

    def test_too_few_frames_does_not_claim_a_size_truncation(self):
        header = stream().splitlines(keepends=True)[0]
        result = load(header)
        self.assertFalse(result["evidence_eligible"])
        self.assertFalse(result["coverage"]["truncated"])


if __name__ == "__main__":
    unittest.main()
