from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from container.invoke import emit_result
from container.runtime_evidence import (
    RUNTIME_EVIDENCE_SCHEMA,
    RuntimeEvidenceError,
    field_available,
    field_unavailable,
    unsupported_runtime_evidence,
    validate_runtime_evidence,
)


def complete_evidence() -> dict:
    return {
        "schema": RUNTIME_EVIDENCE_SCHEMA,
        "status": "complete",
        "evidence_eligible": True,
        "observations": [
            {
                "invocation_id": "obs-1",
                "tool": field_available("read"),
                "mode": "native",
                "actor": field_available("general"),
                "session_id": field_available("ses-1"),
                "message_id": field_available("msg-1"),
                "call_id": field_available("call-1"),
                "parent": field_unavailable("omitted", "not_applicable"),
                "input": field_available({"filePath": "/workspace/README.md"}),
                "outcome": "success",
                "result": field_available("contents"),
                "error": field_unavailable("omitted", "not_applicable"),
                "start_sequence": 4,
                "terminal_sequence": field_available(5),
            }
        ],
        "coverage": {
            "starts": field_available(1),
            "terminals": field_available(1),
            "missing_terminals": field_available(0),
            "losses": [],
            "unsupported": [],
        },
    }


class RuntimeEvidenceContractTests(unittest.TestCase):
    def test_unsupported_contract_never_uses_zero_as_unknown(self):
        evidence = unsupported_runtime_evidence("observer_not_implemented")
        self.assertEqual(evidence["status"], "unsupported")
        self.assertFalse(evidence["evidence_eligible"])
        self.assertEqual(evidence["observations"], [])
        for name in ("starts", "terminals", "missing_terminals"):
            self.assertEqual(
                evidence["coverage"][name],
                {"state": "unsupported", "reason": "observer_not_implemented"},
            )
        self.assertEqual(validate_runtime_evidence(evidence), evidence)

    def test_complete_evidence_is_eligible(self):
        evidence = complete_evidence()
        self.assertEqual(validate_runtime_evidence(evidence), evidence)

    def test_missing_field_fails_closed(self):
        evidence = complete_evidence()
        del evidence["observations"][0]["message_id"]
        with self.assertRaisesRegex(RuntimeEvidenceError, "keys must be exactly"):
            validate_runtime_evidence(evidence)

    def test_missing_terminal_cannot_be_eligible(self):
        evidence = complete_evidence()
        observation = evidence["observations"][0]
        observation["outcome"] = "missing"
        observation["result"] = field_unavailable("omitted", "missing_terminal")
        observation["error"] = field_unavailable("omitted", "missing_terminal")
        observation["terminal_sequence"] = field_unavailable("omitted", "missing_terminal")
        evidence["coverage"]["terminals"] = field_available(0)
        evidence["coverage"]["missing_terminals"] = field_available(1)
        evidence["coverage"]["losses"] = ["missing_terminal"]
        evidence["status"] = "incomplete"
        evidence["evidence_eligible"] = True
        with self.assertRaisesRegex(RuntimeEvidenceError, "evidence_eligible"):
            validate_runtime_evidence(evidence)

    def test_unknown_coverage_is_not_replaced_with_zero(self):
        evidence = complete_evidence()
        evidence["status"] = "incomplete"
        evidence["evidence_eligible"] = False
        evidence["coverage"]["starts"] = field_unavailable("unsupported", "capture_interrupted")
        evidence["coverage"]["terminals"] = field_unavailable("unsupported", "capture_interrupted")
        evidence["coverage"]["missing_terminals"] = field_unavailable("unsupported", "capture_interrupted")
        evidence["coverage"]["losses"] = ["capture_interrupted"]
        self.assertEqual(validate_runtime_evidence(evidence), evidence)

    def test_unsupported_observation_field_requires_coverage_marker(self):
        evidence = complete_evidence()
        evidence["status"] = "incomplete"
        evidence["evidence_eligible"] = False
        evidence["observations"][0]["message_id"] = field_unavailable(
            "unsupported", "message_identity_unavailable"
        )
        with self.assertRaisesRegex(RuntimeEvidenceError, "coverage.unsupported"):
            validate_runtime_evidence(evidence)

    def test_redaction_preserves_capture_eligibility_but_not_field_value(self):
        evidence = complete_evidence()
        evidence["observations"][0]["result"] = field_unavailable("redacted", "credential")
        self.assertEqual(validate_runtime_evidence(evidence), evidence)
        self.assertTrue(evidence["evidence_eligible"])
        self.assertNotIn("value", evidence["observations"][0]["result"])

    def test_rejects_sequence_reuse(self):
        evidence = complete_evidence()
        evidence["observations"][0]["terminal_sequence"] = field_available(4)
        with self.assertRaisesRegex(RuntimeEvidenceError, "must follow"):
            validate_runtime_evidence(evidence)

    def test_emit_result_rejects_missing_runtime_evidence(self):
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeEvidenceError):
                emit_result({"schema": "opencode-eval-runner/v1"})

    def test_emit_result_accepts_explicit_unsupported_contract(self):
        output = io.StringIO()
        result = {
            "schema": "opencode-eval-runner/v1",
            "runtime_evidence": unsupported_runtime_evidence("observer_not_implemented"),
        }
        with redirect_stdout(output):
            emit_result(result)
        self.assertIn('"runtime_evidence"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
