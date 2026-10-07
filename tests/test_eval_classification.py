from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

from runner.eval_classification import EvalProfileCallbacks, classify_evaluation
from runner.eval_evidence import EvidenceReadiness, EvidenceReadinessStatus
from runner.eval_types import (
    AttemptFailure,
    AttemptRecord,
    CheckOutcome,
    CheckStatus,
    InvocationSpec,
    NormalizedCase,
    SemanticDecision,
    SemanticStatus,
)


def readiness(status: EvidenceReadinessStatus) -> EvidenceReadiness:
    return EvidenceReadiness(
        status=status,
        reasons=() if status == "ready" else (status,),
        required_boundaries=(),
    )


INFRA_FAILURE = AttemptFailure(
    plane="infrastructure",
    code="test_failure",
    message="test failure",
    retry_safe=False,
)
PASS_CHECK = CheckOutcome("check", "pass", "ok", {})
FAIL_CHECK = CheckOutcome("check", "fail", "observed violation", {})
NO_EVIDENCE_CHECK = CheckOutcome("check", "non-evidence", "missing proof", {})
SEMANTIC_PASS = SemanticDecision("pass", "semantic pass", None)
SEMANTIC_FAIL = SemanticDecision("fail", "semantic fail", None)


def classify(
    *,
    target_failure=None,
    target_readiness=None,
    checks=(PASS_CHECK,),
    judge_required=True,
    judge_failure=None,
    semantic=SEMANTIC_PASS,
):
    return classify_evaluation(
        target_failure=target_failure,
        target_readiness=(
            readiness("ready") if target_readiness is None else target_readiness
        ),
        deterministic_checks=checks,
        judge_required=judge_required,
        judge_failure=judge_failure,
        semantic=semantic,
    )


class FakeProfile:
    def __init__(self, spec: InvocationSpec):
        self.spec = spec

    def deterministic_checks(self, case, prepared, target, readiness):
        return (PASS_CHECK,)

    def judge_spec(self, case, prepared, target, checks):
        return self.spec

    def parse_judge(self, case, prepared, judge):
        return SEMANTIC_PASS


class EvalClassificationTests(unittest.TestCase):
    def test_profile_callback_surface_is_provider_free(self):
        spec = InvocationSpec(
            transport="opencode",
            model="test/model",
            reasoning=None,
            agent=None,
            skill=None,
            workspace=Path("."),
            workspace_mode="ro",
            prompt="judge",
            system=None,
            expected_plugin=None,
            engine="auto",
            network=None,
            image=None,
            auth=None,
            database=None,
            models_catalog=None,
            config=None,
            config_root=None,
            env_names=(),
            timeout_seconds=1,
            container_timeout=2,
        )
        profile: EvalProfileCallbacks = FakeProfile(spec)
        case = NormalizedCase("case", ("case",), "standard", None, {})
        attempt = AttemptRecord(1, "now", 0.0, 0, {}, None)
        ready = readiness("ready")

        checks = profile.deterministic_checks(case, object(), attempt, ready)
        self.assertEqual(checks, (PASS_CHECK,))
        self.assertIs(profile.judge_spec(case, object(), attempt, checks), spec)
        self.assertEqual(
            profile.parse_judge(case, object(), attempt),
            SEMANTIC_PASS,
        )

    def test_target_failure_dominates_every_downstream_outcome(self):
        for status in ("ready", "incomplete", "unsupported", "invalid"):
            for checks in ((PASS_CHECK,), (FAIL_CHECK,), (NO_EVIDENCE_CHECK,)):
                for semantic in (None, SEMANTIC_PASS, SEMANTIC_FAIL):
                    with self.subTest(status=status, checks=checks, semantic=semantic):
                        self.assertEqual(
                            classify(
                                target_failure=INFRA_FAILURE,
                                target_readiness=readiness(status),
                                checks=checks,
                                semantic=semantic,
                            ),
                            "non-evidence",
                        )

    def test_nonready_target_evidence_dominates_behavioral_failures(self):
        for status in ("incomplete", "unsupported", "invalid"):
            for checks in ((PASS_CHECK,), (FAIL_CHECK,), (NO_EVIDENCE_CHECK,)):
                for semantic in (SEMANTIC_PASS, SEMANTIC_FAIL):
                    with self.subTest(status=status, checks=checks, semantic=semantic):
                        self.assertEqual(
                            classify(
                                target_readiness=readiness(status),
                                checks=checks,
                                semantic=semantic,
                            ),
                            "non-evidence",
                        )

    def test_missing_target_readiness_fails_closed(self):
        self.assertEqual(
            classify_evaluation(
                target_failure=None,
                target_readiness=None,
                deterministic_checks=(FAIL_CHECK,),
                judge_required=False,
                judge_failure=None,
                semantic=None,
            ),
            "non-evidence",
        )

    def test_required_judge_failure_dominates_behavioral_failures(self):
        for checks in ((PASS_CHECK,), (FAIL_CHECK,), (NO_EVIDENCE_CHECK,)):
            for semantic in (None, SEMANTIC_PASS, SEMANTIC_FAIL):
                with self.subTest(checks=checks, semantic=semantic):
                    self.assertEqual(
                        classify(
                            checks=checks,
                            judge_failure=INFRA_FAILURE,
                            semantic=semantic,
                        ),
                        "non-evidence",
                    )

    def test_missing_required_semantic_is_contract_non_evidence(self):
        for checks in ((PASS_CHECK,), (FAIL_CHECK,), (NO_EVIDENCE_CHECK,)):
            with self.subTest(checks=checks):
                self.assertEqual(classify(checks=checks, semantic=None), "non-evidence")

    def test_any_deterministic_fail_wins_after_required_evidence_is_valid(self):
        combinations = (
            (FAIL_CHECK,),
            (PASS_CHECK, FAIL_CHECK),
            (FAIL_CHECK, NO_EVIDENCE_CHECK),
            (PASS_CHECK, FAIL_CHECK, NO_EVIDENCE_CHECK),
        )
        for checks in combinations:
            for semantic in (SEMANTIC_PASS, SEMANTIC_FAIL):
                with self.subTest(checks=checks, semantic=semantic):
                    self.assertEqual(classify(checks=checks, semantic=semantic), "fail")

    def test_deterministic_non_evidence_wins_over_semantic_failure(self):
        for checks in (
            (NO_EVIDENCE_CHECK,),
            (PASS_CHECK, NO_EVIDENCE_CHECK),
        ):
            with self.subTest(checks=checks):
                self.assertEqual(
                    classify(checks=checks, semantic=SEMANTIC_FAIL),
                    "non-evidence",
                )

    def test_semantic_failure_fails_when_required_evidence_and_checks_pass(self):
        self.assertEqual(classify(semantic=SEMANTIC_FAIL), "fail")

    def test_semantic_pass_passes_when_required_evidence_and_checks_pass(self):
        for checks in ((), (PASS_CHECK,), (PASS_CHECK, PASS_CHECK)):
            with self.subTest(checks=checks):
                self.assertEqual(classify(checks=checks), "pass")

    def test_no_judge_required_passes_when_required_checks_pass(self):
        for checks in ((), (PASS_CHECK,), (PASS_CHECK, PASS_CHECK)):
            with self.subTest(checks=checks):
                self.assertEqual(
                    classify(
                        checks=checks,
                        judge_required=False,
                        semantic=None,
                    ),
                    "pass",
                )

    def test_no_judge_required_still_honors_deterministic_outcomes(self):
        self.assertEqual(
            classify(
                checks=(FAIL_CHECK,),
                judge_required=False,
                semantic=None,
            ),
            "fail",
        )
        self.assertEqual(
            classify(
                checks=(NO_EVIDENCE_CHECK,),
                judge_required=False,
                semantic=None,
            ),
            "non-evidence",
        )

    def test_unknown_project_outcomes_fail_closed(self):
        unknown_check = CheckOutcome(
            "check",
            cast(CheckStatus, "unknown"),
            "bad status",
            {},
        )
        unknown_semantic = SemanticDecision(
            cast(SemanticStatus, "unknown"),
            "bad status",
            None,
        )
        self.assertEqual(classify(checks=(unknown_check,)), "non-evidence")
        self.assertEqual(classify(semantic=unknown_semantic), "non-evidence")


if __name__ == "__main__":
    unittest.main()
