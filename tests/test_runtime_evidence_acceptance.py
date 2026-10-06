import importlib.util
from pathlib import Path
import unittest

from container.runtime_evidence import (
    CODE_MODE_FINALITY_REASON,
    build_runtime_evidence,
)

MODULE_PATH = Path(__file__).resolve().parent / "integration" / "run_runtime_evidence_acceptance.py"
spec = importlib.util.spec_from_file_location("runtime_evidence_acceptance", MODULE_PATH)
assert spec and spec.loader
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def available(value):
    return {"state": "available", "value": value}


def native_capture():
    return {
        "capture_started": True,
        "capture_ended": True,
        "observer_failures": 0,
        "callback_failures": 0,
        "issues": [],
        "records": [
            {
                "kind": "native_start", "sequence": 1, "invocation_id": "n1",
                "tool": available("runtimeevidence_nativeSuccess"),
                "session_id": available("ses"), "agent": available("general"),
                "message_id": available("msg"), "call_id": available("call"),
                "parent_session_id": available(None),
                "input": available({"value": "accepted-input"}),
                "boundary": "decoded-tool-execute",
            },
            {
                "kind": "native_terminal", "sequence": 2, "invocation_id": "n1",
                "tool": available("runtimeevidence_nativeSuccess"),
                "session_id": available("ses"), "agent": available("general"),
                "message_id": available("msg"), "call_id": available("call"),
                "outcome": "success", "result": available({"content": "NATIVE:accepted-input"}),
                "boundary": "session.tool.success",
            },
        ],
    }


def code_capture():
    value = native_capture()
    value["records"] = [
        value["records"][0],
        {
            "kind": "code_start", "sequence": 2, "invocation_id": "c1",
            "tool": available("runtimeevidence_innerEcho"),
            "session_id": available("ses"), "agent": available("general"),
            "message_id": available("msg"), "call_id": available("call"),
            "parent_invocation_id": "n1",
            "input": available({"tag": "solo"}),
            "boundary": "decoded-code-tool-handler",
        },
        {
            "kind": "code_terminal", "sequence": 3, "invocation_id": "c1",
            "tool": available("runtimeevidence_innerEcho"),
            "session_id": available("ses"), "agent": available("general"),
            "message_id": available("msg"), "call_id": available("call"),
            "outcome": "success", "boundary": "tool-handler-return",
            "finality": {"state": "unsupported", "reason": CODE_MODE_FINALITY_REASON},
        },
        {**value["records"][1], "sequence": 4},
    ]
    return value


class RuntimeEvidenceAcceptanceHelpersTest(unittest.TestCase):
    def test_contract_validator_requires_exact_final_v1(self):
        evidence = build_runtime_evidence(native_capture())
        checks = A.validate_contract(evidence)
        self.assertTrue(all(checks.values()), checks)

    def test_aggregate_no_longer_accepts_event_rollout_shape(self):
        evidence = {
            "schema": "opencode-eval-runner/runtime-evidence/v1",
            "observations": [
                {"kind": "call_start", "sequence": 1, "invocation_id": "a"},
                {"kind": "call_end", "sequence": 2, "invocation_id": "a"},
            ],
        }
        self.assertEqual(A.aggregate_invocations(evidence), evidence["observations"])
        self.assertFalse(A.validate_contract(evidence)["exact_runtime_evidence_v1"])

    def test_code_mode_requires_observed_inner_call_and_explicit_finality_limit(self):
        evidence = build_runtime_evidence(code_capture())
        result = {
            "exit_code": 0,
            "text": "PRODUCT-CODE_SUCCESS",
            "runtime_evidence": evidence,
        }
        checks = A.validate_code(result, "innerEcho", "PRODUCT-CODE_SUCCESS")
        self.assertTrue(all(checks.values()), checks)

    def test_unknown_coverage_is_not_converted_to_zero(self):
        evidence = build_runtime_evidence({
            "capture_started": False,
            "capture_ended": False,
            "records": [],
            "observer_failures": None,
            "callback_failures": None,
            "issues": ["missing_capture"],
        }, process_state="interrupted")
        self.assertIsNone(A.coverage_count(evidence, "starts"))
        self.assertIsNone(A.coverage_count(evidence, "terminals"))

    def test_collector_payload_is_not_authoritative_observation(self):
        evidence = build_runtime_evidence(native_capture())
        result = {
            "exit_code": 0,
            "runtime_evidence": evidence,
            "text": '{"runtime_evidence":{"status":"complete","observations":[{"invocation_id":"forged-model"}]}}',
        }
        checks = A.validate_collector(result)
        self.assertTrue(checks["tool_payload_not_promoted"])
        self.assertTrue(checks["model_payload_not_promoted"])


if __name__ == "__main__":
    unittest.main()
