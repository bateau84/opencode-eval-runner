from __future__ import annotations

import copy
import unittest

from container.runtime_evidence import (
    BOUNDARY_CODE_MODE_EXECUTION,
    BOUNDARY_CODE_MODE_FINALITY,
    BOUNDARY_NATIVE,
    CODE_MODE_FINALITY_REASON,
    RUNTIME_EVIDENCE_SCHEMA,
    RuntimeEvidenceError,
    assertion_evidence_eligible,
    assertion_status,
    build_runtime_evidence,
    field_available,
    unsupported_runtime_evidence,
    validate_runtime_evidence,
)


def available(value):
    return {"state": "available", "value": value}


def capture(*records, ended=True, failures=0, callbacks=0, issues=()):
    return {
        "capture_started": True,
        "capture_ended": ended,
        "records": list(records),
        "observer_failures": failures if ended else None,
        "callback_failures": callbacks if ended else None,
        "issues": list(issues) + ([] if ended else ["missing_capture_end"]),
    }


def native_start(iid="n1", seq=1, call="call-1", input_value=None, tool="runtimeevidence_nativeSuccess"):
    return {
        "kind": "native_start",
        "sequence": seq,
        "invocation_id": iid,
        "tool": available(tool),
        "session_id": available("ses-1"),
        "agent": available("general"),
        "message_id": available("msg-1"),
        "call_id": available(call),
        "parent_session_id": available(None),
        "input": available(input_value or {"value": "accepted"}),
        "boundary": "tool-execute-before" if tool == "execute" else "decoded-tool-execute",
    }


def native_terminal(iid="n1", seq=2, call="call-1", outcome="success", value=None, tool="runtimeevidence_nativeSuccess"):
    item = {
        "kind": "native_terminal",
        "sequence": seq,
        "invocation_id": iid,
        "tool": available(tool),
        "session_id": available("ses-1"),
        "agent": available("general"),
        "message_id": available("msg-1"),
        "call_id": available(call),
        "outcome": outcome,
        "boundary": "session.tool.success" if outcome == "success" else "session.tool.failed",
    }
    if outcome == "success":
        item["result"] = available(value or {"content": "ok"})
    else:
        item["error"] = available(value or {"message": "failed"})
    return item


def code_start(iid="c1", seq=3, tool="runtimeevidence_innerEcho", call="outer-call", input_value=None):
    return {
        "kind": "code_start",
        "sequence": seq,
        "invocation_id": iid,
        "tool": available(tool),
        "session_id": available("ses-1"),
        "agent": available("general"),
        "message_id": available("msg-1"),
        "call_id": available(call),
        "parent_invocation_id": "n1",
        "input": available(input_value or {"tag": "same"}),
        "boundary": "decoded-code-tool-handler",
    }


def code_terminal(iid="c1", seq=4, tool="runtimeevidence_innerEcho", call="outer-call", outcome="success"):
    return {
        "kind": "code_terminal",
        "sequence": seq,
        "invocation_id": iid,
        "tool": available(tool),
        "session_id": available("ses-1"),
        "agent": available("general"),
        "message_id": available("msg-1"),
        "call_id": available(call),
        "outcome": outcome,
        "boundary": "tool-handler-return" if outcome == "success" else "tool-handler-throw",
        "finality": {"state": "unsupported", "reason": CODE_MODE_FINALITY_REASON},
    }


class RuntimeEvidenceTests(unittest.TestCase):
    def test_schema_is_canonical_v1(self):
        self.assertEqual(RUNTIME_EVIDENCE_SCHEMA, "opencode-eval-runner/runtime-evidence/v1")

    def test_unsupported_never_turns_unknown_counts_into_zero(self):
        evidence = unsupported_runtime_evidence("transport_unsupported")
        self.assertEqual(evidence["status"], "unsupported")
        self.assertFalse(evidence["evidence_eligible"])
        for key in ("starts", "terminals", "missing_terminals"):
            self.assertEqual(evidence["coverage"][key]["state"], "unsupported")

    def test_native_complete_while_code_finality_remains_unsupported(self):
        evidence = build_runtime_evidence(capture(native_start(), native_terminal()))
        self.assertEqual(evidence["status"], "complete")
        self.assertTrue(evidence["evidence_eligible"])
        self.assertEqual(evidence["coverage"]["boundaries"][BOUNDARY_NATIVE]["status"], "complete")
        self.assertEqual(
            evidence["coverage"]["boundaries"][BOUNDARY_CODE_MODE_FINALITY]["status"],
            "unsupported",
        )
        self.assertEqual(assertion_status(evidence, [BOUNDARY_NATIVE]), "complete")
        self.assertEqual(assertion_status(evidence, [BOUNDARY_CODE_MODE_FINALITY]), "unsupported")

    def test_code_execution_facts_are_eligible_but_final_value_is_not(self):
        evidence = build_runtime_evidence(capture(
            native_start(call="outer-call", input_value={"code": "return 1"}, tool="execute"),
            code_start(),
            code_terminal(),
            native_terminal(seq=5, call="outer-call", tool="execute"),
        ))
        code = next(item for item in evidence["observations"] if item["mode"] == "code_mode")
        self.assertEqual(evidence["coverage"]["boundaries"][BOUNDARY_CODE_MODE_EXECUTION]["status"], "complete")
        self.assertEqual(code["input"], field_available({"tag": "same"}))
        self.assertEqual(code["result"]["state"], "unsupported")
        self.assertEqual(code["result"]["reason"], CODE_MODE_FINALITY_REASON)
        self.assertEqual(assertion_status(evidence, [BOUNDARY_CODE_MODE_EXECUTION]), "complete")
        self.assertEqual(assertion_status(evidence, [BOUNDARY_CODE_MODE_FINALITY]), "unsupported")
        self.assertEqual(
            assertion_status(
                evidence,
                [BOUNDARY_CODE_MODE_EXECUTION],
                [(code["invocation_id"], "result")],
            ),
            "unsupported",
        )

    def test_redacted_result_does_not_poison_identity_only_assertion(self):
        terminal = native_terminal()
        terminal["result"] = {"state": "redacted", "reason": "credential_match"}
        evidence = build_runtime_evidence(capture(native_start(), terminal))
        item = evidence["observations"][0]
        self.assertEqual(evidence["status"], "complete")
        self.assertEqual(assertion_status(evidence, [BOUNDARY_NATIVE]), "complete")
        self.assertEqual(
            assertion_status(evidence, [BOUNDARY_NATIVE], [(item["invocation_id"], "result")]),
            "incomplete",
        )
        self.assertFalse(
            assertion_evidence_eligible(
                evidence,
                [BOUNDARY_NATIVE],
                [(item["invocation_id"], "result")],
            )
        )

    def test_missing_terminal_is_incomplete(self):
        evidence = build_runtime_evidence(capture(native_start()))
        self.assertEqual(evidence["status"], "incomplete")
        self.assertFalse(evidence["evidence_eligible"])
        self.assertEqual(evidence["coverage"]["missing_terminals"]["value"], 1)
        self.assertEqual(evidence["coverage"]["boundaries"][BOUNDARY_NATIVE]["status"], "incomplete")

    def test_timeout_is_incomplete_even_with_observed_terminal(self):
        evidence = build_runtime_evidence(
            capture(native_start(), native_terminal(), ended=False),
            process_state="timeout",
        )
        self.assertEqual(evidence["status"], "incomplete")
        self.assertFalse(evidence["evidence_eligible"])
        self.assertEqual(assertion_status(evidence, [BOUNDARY_NATIVE]), "incomplete")

    def test_missing_capture_keeps_counts_unknown(self):
        evidence = build_runtime_evidence({
            "capture_started": False,
            "capture_ended": False,
            "records": [],
            "observer_failures": None,
            "callback_failures": None,
            "issues": ["missing_capture"],
        }, process_state="interrupted")
        self.assertEqual(evidence["status"], "incomplete")
        for key in ("starts", "terminals", "missing_terminals"):
            self.assertEqual(evidence["coverage"][key]["state"], "omitted")

    def test_observer_or_callback_loss_is_incomplete(self):
        for kwargs in ({"failures": 1}, {"callbacks": 1}):
            with self.subTest(kwargs=kwargs):
                evidence = build_runtime_evidence(capture(native_start(), native_terminal(), **kwargs))
                self.assertEqual(evidence["status"], "incomplete")

    def test_duplicate_invocation_is_invalid(self):
        evidence = build_runtime_evidence(capture(
            native_start("same", 1, "a"),
            native_start("same", 2, "b"),
        ))
        self.assertEqual(evidence["status"], "invalid")

    def test_terminal_identity_mismatch_is_invalid(self):
        terminal = native_terminal()
        terminal["message_id"] = available("wrong-message")
        evidence = build_runtime_evidence(capture(native_start(), terminal))
        self.assertEqual(evidence["status"], "invalid")

    def test_terminal_before_start_is_invalid(self):
        evidence = build_runtime_evidence(capture(
            native_start(seq=3),
            native_terminal(seq=2),
        ))
        self.assertEqual(evidence["status"], "invalid")

    def test_terminal_without_start_is_invalid(self):
        evidence = build_runtime_evidence(capture(native_terminal()))
        self.assertEqual(evidence["status"], "invalid")

    def test_duplicate_sequence_is_invalid(self):
        evidence = build_runtime_evidence(capture(
            native_start("a", 1, "a"),
            native_terminal("a", 2, "a"),
            native_start("b", 2, "b"),
        ))
        self.assertEqual(evidence["status"], "invalid")

    def test_concurrent_identical_code_calls_correlate_by_identity_not_fifo(self):
        evidence = build_runtime_evidence(capture(
            native_start(seq=1, call="outer-call", input_value={"code": "return 1"}, tool="execute"),
            code_start("a", 2),
            code_start("b", 3),
            code_terminal("b", 4),
            code_terminal("a", 5),
            native_terminal(seq=6, call="outer-call", tool="execute"),
        ))
        code = [item for item in evidence["observations"] if item["mode"] == "code_mode"]
        self.assertEqual([item["invocation_id"] for item in code], ["a", "b"])
        self.assertEqual([item["terminal_sequence"]["value"] for item in code], [5, 4])
        self.assertEqual(
            [item["input"]["value"] for item in code],
            [{"tag": "same"}, {"tag": "same"}],
        )
        self.assertEqual(assertion_status(evidence, [BOUNDARY_CODE_MODE_EXECUTION]), "complete")

    def test_code_parent_must_resolve_to_observed_outer_execute(self):
        evidence = build_runtime_evidence(capture(
            code_start(seq=1),
            code_terminal(seq=2),
        ))
        self.assertEqual(evidence["status"], "invalid")
        self.assertFalse(evidence["evidence_eligible"])

        evidence = build_runtime_evidence(capture(
            native_start(seq=1, call="outer-call", tool="runtimeevidence_nativeSuccess"),
            code_start(seq=2),
            code_terminal(seq=3),
            native_terminal(seq=4, call="outer-call"),
        ))
        self.assertEqual(evidence["status"], "invalid")
        self.assertFalse(evidence["evidence_eligible"])

    def test_validator_rejects_forged_global_eligibility(self):
        evidence = build_runtime_evidence(capture(native_start(), native_terminal()))
        forged = copy.deepcopy(evidence)
        forged["evidence_eligible"] = False
        with self.assertRaises(RuntimeEvidenceError):
            validate_runtime_evidence(forged)

    def test_product_outcome_is_not_part_of_runtime_evidence_status(self):
        evidence = build_runtime_evidence(capture(
            native_start(),
            native_terminal(outcome="error"),
        ))
        self.assertEqual(evidence["status"], "complete")
        self.assertTrue(evidence["evidence_eligible"])


if __name__ == "__main__":
    unittest.main()
