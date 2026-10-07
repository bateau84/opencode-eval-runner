from __future__ import annotations

import math
import unittest
from dataclasses import dataclass

from runner.eval_api import validate_eval_profile
from runner.eval_compare import (
    COMPARISON_RESULT_SCHEMA,
    ComparisonDecision,
    compare_completed_outcomes,
    comparison_result_envelope,
    validate_comparison_result_envelope,
)


@dataclass(frozen=True)
class FakeCompletedOutcome:
    classification: str
    score: float | None = None


class RecordingExtension:
    def __init__(self):
        self.calls = []

    def compare_pair(self, baseline, candidate):
        self.calls.append((baseline, candidate))
        if baseline.classification == "fail" and candidate.classification == "pass":
            return ComparisonDecision(
                classification="improvement",
                summary="candidate improved",
                data={"value": candidate.score},
            )
        if baseline.classification == "pass" and candidate.classification == "fail":
            return ComparisonDecision(
                classification="regression",
                summary="candidate regressed",
                data={"value": candidate.score},
            )
        return ComparisonDecision(
            classification="equivalent",
            summary="project considers the outcomes equivalent",
            data={"value": candidate.score},
        )


class NormalProfileWithoutComparison:
    def discover_cases(self):
        return ()

    def prepare(self, case, iteration):
        raise AssertionError("validation must not execute profile hooks")

    def target_spec(self, case, prepared):
        raise AssertionError("validation must not execute profile hooks")

    def target_evidence_requirement(self, case, prepared):
        raise AssertionError("validation must not execute profile hooks")

    def deterministic_checks(self, case, prepared, target, readiness):
        raise AssertionError("validation must not execute profile hooks")

    def judge_spec(self, case, prepared, target, checks):
        raise AssertionError("validation must not execute profile hooks")

    def parse_judge(self, case, prepared, judge):
        raise AssertionError("validation must not execute profile hooks")

    def artifact_metadata(self, case, prepared):
        raise AssertionError("validation must not execute profile hooks")


class InvalidOutputExtension:
    def __init__(self, output):
        self.output = output

    def compare_pair(self, baseline, candidate):
        return self.output


class EvalComparisonTests(unittest.TestCase):
    def test_valid_comparison_returns_structured_envelope(self):
        extension = RecordingExtension()
        baseline = FakeCompletedOutcome("pass", score=0.7)
        candidate = FakeCompletedOutcome("pass", score=0.8)

        result = compare_completed_outcomes(
            extension,
            baseline=baseline,
            candidate=candidate,
        )
        envelope = comparison_result_envelope(result)

        self.assertEqual(result.status, "compared")
        self.assertEqual(result.decision.classification, "equivalent")
        self.assertEqual(result.decision.data, {"value": 0.8})
        self.assertIsNone(result.failure)
        self.assertEqual(envelope["schema"], COMPARISON_RESULT_SCHEMA)
        self.assertEqual(envelope["baseline_classification"], "pass")
        self.assertEqual(envelope["candidate_classification"], "pass")
        self.assertEqual(envelope["decision"]["classification"], "equivalent")

    def test_project_can_classify_improvement_and_regression(self):
        extension = RecordingExtension()

        improvement = compare_completed_outcomes(
            extension,
            baseline=FakeCompletedOutcome("fail", score=0.2),
            candidate=FakeCompletedOutcome("pass", score=0.9),
        )
        regression = compare_completed_outcomes(
            extension,
            baseline=FakeCompletedOutcome("pass", score=0.9),
            candidate=FakeCompletedOutcome("fail", score=0.2),
        )

        self.assertEqual(improvement.status, "compared")
        self.assertEqual(improvement.decision.classification, "improvement")
        self.assertEqual(regression.status, "compared")
        self.assertEqual(regression.decision.classification, "regression")

    def test_invalid_comparison_output_is_explicit(self):
        cases = (
            {"classification": "improvement"},
            ComparisonDecision("", "missing classification", None),
            ComparisonDecision("improvement", "bad data", {"score": math.nan}),
        )

        for output in cases:
            with self.subTest(output=output):
                result = compare_completed_outcomes(
                    InvalidOutputExtension(output),
                    baseline=FakeCompletedOutcome("pass"),
                    candidate=FakeCompletedOutcome("pass"),
                )
                envelope = comparison_result_envelope(result)

                self.assertEqual(result.status, "invalid")
                self.assertIsNone(result.decision)
                self.assertEqual(result.failure.code, "comparison_output_invalid")
                self.assertEqual(envelope["status"], "invalid")
                self.assertEqual(
                    envelope["failure"]["code"],
                    "comparison_output_invalid",
                )

    def test_one_sided_non_evidence_does_not_call_comparison_or_invent_zero(self):
        extension = RecordingExtension()

        result = compare_completed_outcomes(
            extension,
            baseline=FakeCompletedOutcome("non-evidence", score=None),
            candidate=FakeCompletedOutcome("pass", score=0.9),
        )
        envelope = comparison_result_envelope(result)

        self.assertEqual(extension.calls, [])
        self.assertEqual(result.status, "non-evidence")
        self.assertIsNone(result.decision)
        self.assertEqual(result.baseline_classification, "non-evidence")
        self.assertEqual(result.candidate_classification, "pass")
        self.assertEqual(result.failure.code, "comparison_side_non_evidence")
        self.assertIsNone(envelope["decision"])
        self.assertNotIn("score", envelope)
        self.assertNotIn("value", envelope)


    def test_comparison_envelope_contract_rejects_inconsistent_fields(self):
        valid = comparison_result_envelope(compare_completed_outcomes(
            RecordingExtension(),
            baseline=FakeCompletedOutcome("pass"),
            candidate=FakeCompletedOutcome("fail"),
        ))
        self.assertIs(validate_comparison_result_envelope(valid), valid)
        with self.assertRaisesRegex(ValueError, "candidate_classification"):
            validate_comparison_result_envelope(
                valid, candidate_classification="pass"
            )
        invalid = dict(valid)
        invalid["status"] = "non-evidence"
        with self.assertRaisesRegex(ValueError, "non-compared"):
            validate_comparison_result_envelope(invalid)
        invalid = dict(valid)
        invalid["schema"] = "unknown/v1"
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_comparison_result_envelope(invalid)

    def test_normal_profile_contract_does_not_require_comparison_extension(self):
        profile = NormalProfileWithoutComparison()

        self.assertIs(validate_eval_profile(profile), profile)
        self.assertFalse(hasattr(profile, "compare_pair"))


if __name__ == "__main__":
    unittest.main()
