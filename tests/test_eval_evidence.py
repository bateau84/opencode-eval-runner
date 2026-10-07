from __future__ import annotations

import copy
import unittest

from container.runtime_evidence import (
    BOUNDARY_CODE_MODE_EXECUTION,
    BOUNDARY_CODE_MODE_FINALITY,
    BOUNDARY_NATIVE,
    CODE_MODE_FINALITY_REASON,
    build_runtime_evidence,
    field_available,
    field_unavailable,
    unsupported_runtime_evidence,
)
from runner.eval_evidence import (
    EvidenceRequirement,
    check_evidence_readiness,
    check_field_readiness,
)


def capture(*records, ended=True, issues=()):
    return {
        "capture_started": True,
        "capture_ended": ended,
        "records": list(records),
        "observer_failures": 0 if ended else None,
        "callback_failures": 0 if ended else None,
        "issues": list(issues) + ([] if ended else ["missing_capture_end"]),
    }


def native_start(iid="n1", seq=1, call="call-1", tool="nativeEcho"):
    return {
        "kind": "native_start",
        "sequence": seq,
        "invocation_id": iid,
        "tool": field_available(tool),
        "session_id": field_available("ses-1"),
        "agent": field_available("general"),
        "message_id": field_available("msg-1"),
        "call_id": field_available(call),
        "parent_session_id": field_available(None),
        "input": field_available({"value": "accepted"}),
        "boundary": "decoded-tool-execute",
    }


def native_terminal(
    iid="n1",
    seq=2,
    call="call-1",
    tool="nativeEcho",
    result=None,
):
    return {
        "kind": "native_terminal",
        "sequence": seq,
        "invocation_id": iid,
        "tool": field_available(tool),
        "session_id": field_available("ses-1"),
        "agent": field_available("general"),
        "message_id": field_available("msg-1"),
        "call_id": field_available(call),
        "outcome": "success",
        "boundary": "session.tool.success",
        "result": result if result is not None else field_available({"content": "ok"}),
    }


def complete_evidence():
    return build_runtime_evidence(capture(native_start(), native_terminal()))


def incomplete_evidence():
    return build_runtime_evidence(capture(native_start()))


def invalid_evidence():
    malformed = {"kind": "not-an-observation", "sequence": 1}
    return build_runtime_evidence(capture(malformed))


class EvidenceReadinessTests(unittest.TestCase):
    def test_native_complete_is_ready(self):
        readiness = check_evidence_readiness(
            complete_evidence(),
            EvidenceRequirement((BOUNDARY_NATIVE,)),
        )
        self.assertEqual(readiness.status, "ready")
        self.assertEqual(readiness.reasons, ())
        self.assertEqual(readiness.required_boundaries, (BOUNDARY_NATIVE,))

    def test_code_mode_execution_boundary_can_be_ready(self):
        readiness = check_evidence_readiness(
            complete_evidence(),
            EvidenceRequirement((BOUNDARY_CODE_MODE_EXECUTION,)),
        )
        self.assertEqual(readiness.status, "ready")

    def test_code_mode_finality_remains_unsupported(self):
        readiness = check_evidence_readiness(
            complete_evidence(),
            EvidenceRequirement((BOUNDARY_CODE_MODE_FINALITY,)),
        )
        self.assertEqual(readiness.status, "unsupported")
        self.assertIn(
            f"boundary_unsupported:{BOUNDARY_CODE_MODE_FINALITY}",
            readiness.reasons,
        )
        self.assertIn(
            f"boundary_issue:{BOUNDARY_CODE_MODE_FINALITY}:{CODE_MODE_FINALITY_REASON}",
            readiness.reasons,
        )

    def test_any_required_unsupported_boundary_makes_scope_unsupported(self):
        readiness = check_evidence_readiness(
            complete_evidence(),
            EvidenceRequirement((BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_FINALITY)),
        )
        self.assertEqual(readiness.status, "unsupported")
        self.assertEqual(
            readiness.required_boundaries,
            (BOUNDARY_NATIVE, BOUNDARY_CODE_MODE_FINALITY),
        )

    def test_incomplete_capture_fails_closed_for_nonempty_requirement(self):
        readiness = check_evidence_readiness(
            incomplete_evidence(),
            EvidenceRequirement((BOUNDARY_NATIVE,)),
        )
        self.assertEqual(readiness.status, "incomplete")
        self.assertIn("runtime_evidence_incomplete", readiness.reasons)
        self.assertIn(f"boundary_incomplete:{BOUNDARY_NATIVE}", readiness.reasons)

    def test_invalid_capture_fails_closed_for_nonempty_requirement(self):
        readiness = check_evidence_readiness(
            invalid_evidence(),
            EvidenceRequirement((BOUNDARY_NATIVE,)),
        )
        self.assertEqual(readiness.status, "invalid")
        self.assertIn("runtime_evidence_invalid", readiness.reasons)

    def test_unsupported_transport_is_unsupported_for_runtime_requirement(self):
        readiness = check_evidence_readiness(
            unsupported_runtime_evidence("transport_unsupported"),
            EvidenceRequirement((BOUNDARY_NATIVE,)),
        )
        self.assertEqual(readiness.status, "unsupported")
        self.assertIn(f"boundary_unsupported:{BOUNDARY_NATIVE}", readiness.reasons)

    def test_empty_requirement_is_ready_after_schema_validation(self):
        readiness = check_evidence_readiness(
            incomplete_evidence(),
            EvidenceRequirement(),
        )
        self.assertEqual(readiness.status, "ready")
        self.assertEqual(readiness.reasons, ())
        self.assertEqual(readiness.required_boundaries, ())

    def test_empty_requirement_does_not_skip_schema_validation(self):
        malformed = {"schema": "opencode-eval-runner/runtime-evidence/v1"}
        readiness = check_evidence_readiness(malformed, EvidenceRequirement())
        self.assertEqual(readiness.status, "invalid")
        self.assertEqual(readiness.reasons[0], "runtime_evidence_invalid")

    def test_requirement_behaves_as_a_boundary_set(self):
        readiness = check_evidence_readiness(
            complete_evidence(),
            EvidenceRequirement((BOUNDARY_NATIVE, BOUNDARY_NATIVE)),
        )
        self.assertEqual(readiness.status, "ready")
        self.assertEqual(readiness.required_boundaries, (BOUNDARY_NATIVE,))

    def test_unknown_required_boundary_is_invalid(self):
        requirement = EvidenceRequirement(("future_boundary",))  # type: ignore[arg-type]
        readiness = check_evidence_readiness(complete_evidence(), requirement)
        self.assertEqual(readiness.status, "invalid")
        self.assertEqual(
            readiness.reasons,
            ("requirement_invalid_boundary:future_boundary",),
        )

    def test_available_exact_field_is_ready(self):
        readiness = check_field_readiness(field_available({"answer": 42}))
        self.assertEqual(readiness.status, "ready")
        self.assertEqual(readiness.reasons, ())

    def test_available_json_null_is_ready(self):
        self.assertEqual(check_field_readiness(field_available(None)).status, "ready")

    def test_redacted_exact_field_is_incomplete(self):
        readiness = check_field_readiness(field_unavailable("redacted", "credential_match"))
        self.assertEqual(readiness.status, "incomplete")
        self.assertEqual(readiness.reasons, ("field_redacted:credential_match",))

    def test_omitted_exact_field_is_incomplete(self):
        readiness = check_field_readiness(field_unavailable("omitted", "size_limit"))
        self.assertEqual(readiness.status, "incomplete")
        self.assertEqual(readiness.reasons, ("field_omitted:size_limit",))

    def test_unsupported_exact_field_is_unsupported(self):
        readiness = check_field_readiness(
            field_unavailable("unsupported", CODE_MODE_FINALITY_REASON)
        )
        self.assertEqual(readiness.status, "unsupported")
        self.assertEqual(
            readiness.reasons,
            (f"field_unsupported:{CODE_MODE_FINALITY_REASON}",),
        )

    def test_malformed_exact_field_is_invalid(self):
        self.assertEqual(check_field_readiness({"state": "available"}).status, "invalid")
        self.assertEqual(check_field_readiness({"state": "mystery"}).status, "invalid")
        self.assertEqual(
            check_field_readiness({"state": "available", "value": float("nan")}).status,
            "invalid",
        )

    def test_diagnostic_convenience_data_cannot_backfill_omitted_evidence(self):
        evidence = build_runtime_evidence(
            capture(
                native_start(),
                native_terminal(result=field_unavailable("omitted", "size_limit")),
            )
        )
        outer_result = {
            "runtime_evidence": evidence,
            "tools": [{"name": "nativeEcho", "result": {"content": "diagnostic only"}}],
            "actions": [{"kind": "tool", "result": {"content": "diagnostic only"}}],
        }

        readiness = check_evidence_readiness(
            outer_result["runtime_evidence"],
            EvidenceRequirement((BOUNDARY_NATIVE,)),
        )
        exact_field = outer_result["runtime_evidence"]["observations"][0]["result"]

        self.assertEqual(readiness.status, "incomplete")
        self.assertEqual(check_field_readiness(exact_field).status, "incomplete")
        self.assertEqual(outer_result["tools"][0]["result"]["content"], "diagnostic only")

    def test_readiness_does_not_mutate_runtime_evidence(self):
        evidence = complete_evidence()
        before = copy.deepcopy(evidence)
        check_evidence_readiness(evidence, EvidenceRequirement((BOUNDARY_NATIVE,)))
        self.assertEqual(evidence, before)


if __name__ == "__main__":
    unittest.main()
