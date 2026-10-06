import unittest

from runner.evidence_accounting import account_runtime_evidence, assertion_status


def start(invocation_id="a", sequence=1, boundary="native", **fields):
    return {
        "kind": "start",
        "sequence": sequence,
        "invocation_id": invocation_id,
        "boundary": boundary,
        "required_fields": fields or {"input": "available", "identity": "available"},
    }


def terminal(invocation_id="a", sequence=2, boundary="native", **fields):
    return {
        "kind": "terminal",
        "sequence": sequence,
        "invocation_id": invocation_id,
        "boundary": boundary,
        "required_fields": fields or {"outcome": "available", "result_or_error": "available"},
    }


class RuntimeEvidenceAccountingTests(unittest.TestCase):
    def account(self, observations=(), **kwargs):
        kwargs.setdefault("observation_closed", True)
        kwargs.setdefault("supported_boundaries", ("native",))
        return account_runtime_evidence(observations, **kwargs)

    def test_complete_balanced_capture(self):
        result = self.account([start(), terminal()])
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual(result["coverage"]["starts"], 1)
        self.assertEqual(result["coverage"]["terminals"], 1)
        self.assertEqual(result["coverage"]["missing_terminals"], 0)

    def test_closed_supported_boundary_can_prove_zero_observed_calls(self):
        result = self.account([])
        self.assertEqual(assertion_status(result, ["native"]), "complete")
        self.assertEqual(result["coverage"]["by_boundary"]["native"]["starts"], 0)

    def test_unclosed_scope_cannot_prove_absence(self):
        result = self.account([], observation_closed=False)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(assertion_status(result, ["native"]), "incomplete")
        self.assertIn("observation_not_closed", result["issues"])

    def test_start_without_terminal_is_incomplete(self):
        result = self.account([start()])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["coverage"]["missing_terminals"], 1)
        self.assertIn("missing_terminal", result["issues"])

    def test_observer_failure_and_loss_are_incomplete(self):
        for kwargs, issue in (
            ({"observer_failures": 1}, "observer_failure"),
            ({"callback_failures": 1}, "callback_failure"),
            ({"losses": 2}, "observation_loss"),
        ):
            with self.subTest(issue=issue):
                result = self.account([start(), terminal()], **kwargs)
                self.assertEqual(result["status"], "incomplete")
                self.assertIn(issue, result["issues"])

    def test_malformed_observation_is_invalid(self):
        result = self.account([{"kind": "start"}])
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["coverage"]["malformed_observations"], 1)

    def test_timeout_and_interruption_never_become_complete(self):
        for state, issue in (("timeout", "runtime_timeout"), ("interrupted", "process_interrupted")):
            with self.subTest(state=state):
                result = self.account([start(), terminal()], process_state=state)
                self.assertEqual(result["status"], "incomplete")
                self.assertIn(issue, result["issues"])

    def test_required_omitted_or_truncated_fields_are_incomplete(self):
        omitted = self.account([start(input="omitted"), terminal()])
        truncated = self.account([start(), terminal(result="truncated")])
        self.assertEqual(omitted["status"], "incomplete")
        self.assertEqual(truncated["status"], "incomplete")
        self.assertEqual(omitted["coverage"]["required_fields_omitted"], 1)
        self.assertEqual(truncated["coverage"]["required_fields_truncated"], 1)

    def test_required_unsupported_field_is_unsupported(self):
        result = self.account([start(input="unsupported"), terminal()])
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(assertion_status(result, ["native"]), "unsupported")

    def test_unsupported_boundary_only_affects_assertions_that_need_it(self):
        result = account_runtime_evidence(
            [start(), terminal()],
            observation_closed=True,
            supported_boundaries=("native",),
            unsupported_boundaries=("code_mode_final",),
        )
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(assertion_status(result, ["native"]), "complete")
        self.assertEqual(assertion_status(result, ["code_mode_final"]), "unsupported")
        self.assertEqual(assertion_status(result, ["native", "code_mode_final"]), "unsupported")

    def test_unknown_required_boundary_is_unsupported_not_empty(self):
        result = self.account([start(), terminal()])
        self.assertEqual(assertion_status(result, ["code_mode_final"]), "unsupported")

    def test_duplicate_invocation_identity_is_invalid(self):
        result = self.account([start(sequence=1), start(sequence=2), terminal(sequence=3)])
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["coverage"]["duplicate_invocations"], 1)

    def test_orphan_duplicate_or_reversed_terminal_is_invalid(self):
        cases = (
            [terminal(sequence=1)],
            [start(sequence=1), terminal(sequence=2), terminal(sequence=3)],
            [start(sequence=3), terminal(sequence=2)],
        )
        for observations in cases:
            with self.subTest(observations=observations):
                result = self.account(observations)
                self.assertEqual(result["status"], "invalid")
                self.assertGreaterEqual(result["coverage"]["ambiguous_invocations"], 1)

    def test_duplicate_sequence_is_invalid(self):
        result = self.account([start(sequence=1), terminal(sequence=1)])
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["coverage"]["duplicate_sequences"], 1)

    def test_concurrent_identical_calls_correlate_by_identity_not_fifo(self):
        result = self.account([
            start("a", 1),
            start("b", 2),
            terminal("b", 3),
            terminal("a", 4),
        ])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["coverage"]["starts"], 2)
        self.assertEqual(result["coverage"]["terminals"], 2)

    def test_product_failure_is_separate_from_capture_completeness(self):
        failed_terminal = terminal()
        failed_terminal["outcome"] = "failure"  # Product data is intentionally irrelevant here.
        result = self.account([start(), failed_terminal])
        self.assertEqual(result["status"], "complete")

    def test_global_capture_failure_affects_even_otherwise_supported_assertion(self):
        result = account_runtime_evidence(
            [start(), terminal()],
            observation_closed=True,
            supported_boundaries=("native",),
            unsupported_boundaries=("code_mode_final",),
            observer_failures=1,
        )
        self.assertEqual(assertion_status(result, ["native"]), "incomplete")

    def test_invalid_accounting_inputs_fail_closed(self):
        cases = (
            {"observer_failures": -1},
            {"callback_failures": -1},
            {"losses": True},
            {"process_state": "success"},
            {"observation_closed": 1},
            {"supported_boundaries": ("native",), "unsupported_boundaries": ("native",)},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                kwargs.setdefault("observation_closed", True)
                result = account_runtime_evidence([], **kwargs)
                self.assertEqual(result["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
