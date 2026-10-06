import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parent / "integration" / "run_runtime_evidence_acceptance.py"
spec = importlib.util.spec_from_file_location("runtime_evidence_acceptance", MODULE_PATH)
assert spec and spec.loader
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class RuntimeEvidenceAcceptanceHelpersTest(unittest.TestCase):
    def test_aggregate_event_shape_uses_invocation_identity_not_order(self):
        evidence = {
            "observations": [
                {"kind": "call_start", "sequence": 1, "invocation_id": "a", "tool": "fixture_innerEcho", "input": {"tag": "same"}},
                {"kind": "call_start", "sequence": 2, "invocation_id": "b", "tool": "fixture_innerEcho", "input": {"tag": "same"}},
                {"kind": "call_end", "sequence": 3, "invocation_id": "b", "outcome": "returned", "result": "CALL-2"},
                {"kind": "call_end", "sequence": 4, "invocation_id": "a", "outcome": "returned", "result": "CALL-1"},
            ]
        }
        items = A.aggregate_invocations(evidence)
        self.assertEqual([item["invocation_id"] for item in items], ["a", "b"])
        self.assertEqual(items[0]["terminal_sequence"], 4)
        self.assertEqual(items[1]["terminal_sequence"], 3)

    def test_code_mode_unsupported_is_explicit_not_skip(self):
        result = {
            "exit_code": 0,
            "text": "PRODUCT-CODE_SUCCESS",
            "runtime_evidence": {
                "status": "unsupported",
                "evidence_eligible": False,
                "observations": [],
                "coverage": {"starts": 1, "terminals": 1, "missing_terminals": 0, "losses": 0, "unsupported": 1},
            },
        }
        checks = A.validate_code(result, "innerEcho", "PRODUCT-CODE_SUCCESS")
        self.assertTrue(all(checks.values()), checks)

    def test_timeout_requires_incomplete_and_missing_terminal(self):
        result = {
            "exit_code": 124,
            "timed_out": True,
            "runtime_evidence": {
                "status": "incomplete",
                "evidence_eligible": False,
                "observations": [{
                    "invocation_id": "slow-1",
                    "tool": "runtimeevidence_slow",
                    "mode": "native",
                    "start_sequence": 3,
                    "terminal_sequence": None,
                }],
                "coverage": {"starts": 1, "terminals": 0, "missing_terminals": 1, "losses": 0, "unsupported": 0},
            },
        }
        checks = A.validate_incomplete(result, "slow", timed_out=True)
        self.assertTrue(all(checks.values()), checks)

    def test_collector_payload_is_not_authoritative_observation(self):
        result = {
            "exit_code": 0,
            "runtime_evidence": {
                "status": "complete",
                "evidence_eligible": True,
                "observations": [{
                    "invocation_id": "real-1",
                    "tool": "runtimeevidence_collector",
                    "start_sequence": 1,
                    "terminal_sequence": 2,
                    "result": '{"invocation_id":"forged-invocation","tool":"forged_tool"}',
                }],
                "coverage": {"starts": 1, "terminals": 1, "missing_terminals": 0, "losses": 0, "unsupported": 0},
            },
        }
        checks = A.validate_collector(result)
        self.assertTrue(all(checks.values()), checks)

    def test_redaction_rejects_raw_secret_even_with_complete_evidence(self):
        result = {
            "exit_code": 0,
            "text": "PRODUCT-REDACTION",
            "runtime_evidence": {
                "status": "complete",
                "evidence_eligible": True,
                "observations": [{
                    "invocation_id": "secret-1",
                    "tool": "runtimeevidence_secret",
                    "start_sequence": 1,
                    "terminal_sequence": 2,
                    "result": {"state": "redacted", "reason": "credential_match"},
                }],
                "coverage": {"starts": 1, "terminals": 1, "missing_terminals": 0, "losses": 0, "unsupported": 0},
            },
        }
        checks = A.validate_redaction(result)
        self.assertTrue(all(checks.values()), checks)
        leaked = dict(result)
        leaked["stdout"] = A.SECRET
        self.assertFalse(A.validate_redaction(leaked)["raw_credential_absent_from_entire_result"])


if __name__ == "__main__":
    unittest.main()
