from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from container.runtime_evidence import unsupported_runtime_evidence
from runner.eval_artifacts import validate_eval_artifact
from runner.eval_engine import build_eval_artifact, evaluate_target_outcome
from runner.eval_evidence import EvidenceRequirement
from runner.eval_execute import RESULT_SCHEMA, run_target_attempts
from runner.eval_types import (
    CheckOutcome,
    InvocationSpec,
    NormalizedCase,
    SemanticDecision,
)


PASS_CHECK = CheckOutcome("deterministic", "pass", "ok", {})
SEMANTIC_PASS = SemanticDecision("pass", "judge pass", {"score": 1})


def make_spec(workspace: Path, *, model: str) -> InvocationSpec:
    return InvocationSpec(
        transport="opencode",
        model=model,
        reasoning="medium",
        agent=None,
        skill=None,
        workspace=workspace,
        workspace_mode="ro",
        prompt=f"prompt for {model}",
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
        timeout_seconds=10,
        container_timeout=20,
    )


def valid_result(spec: InvocationSpec) -> dict:
    return {
        "schema": RESULT_SCHEMA,
        "transport": spec.transport,
        "model": spec.model,
        "reasoning": spec.reasoning,
        "reasoning_source": "explicit",
        "exit_code": 0,
        "stderr": "",
        "runtime_evidence": unsupported_runtime_evidence(
            "provider_free_lifecycle_fixture"
        ),
    }


class SequenceInvoker:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, spec):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeProfile:
    def __init__(
        self,
        judge_spec: InvocationSpec | None,
        *,
        semantic: SemanticDecision = SEMANTIC_PASS,
        parse_error: Exception | None = None,
    ):
        self._judge_spec = judge_spec
        self._semantic = semantic
        self._parse_error = parse_error
        self.check_calls = 0
        self.judge_spec_calls = 0
        self.parse_calls = 0
        self.parsed_attempt = None

    def deterministic_checks(self, case, prepared, target, readiness):
        self.check_calls += 1
        return (PASS_CHECK,)

    def judge_spec(self, case, prepared, target, checks):
        self.judge_spec_calls += 1
        return self._judge_spec

    def parse_judge(self, case, prepared, judge):
        self.parse_calls += 1
        self.parsed_attempt = judge
        if self._parse_error is not None:
            raise self._parse_error
        return self._semantic


class EvalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.case = NormalizedCase(
            id="CASE-1",
            selectors=("CASE-1",),
            lane="standard",
            project_data=None,
            metadata={"fixture": "provider-free"},
        )
        self.target_spec = make_spec(self.workspace, model="test/target")
        self.judge_spec = make_spec(self.workspace, model="test/judge")

    def tearDown(self):
        self.temp.cleanup()

    def target_outcome(self, requirement=EvidenceRequirement()):
        invoker = SequenceInvoker([(0, valid_result(self.target_spec))])
        outcome = run_target_attempts(
            self.target_spec,
            invoker=invoker,
            evidence_requirement=requirement,
        )
        self.assertEqual(invoker.calls, 1)
        return outcome

    def test_provider_free_target_judge_parse_classify_artifact_lifecycle(self):
        target = self.target_outcome()
        self.assertEqual(target.readiness.status, "ready")

        profile = FakeProfile(self.judge_spec)
        judge_invoker = SequenceInvoker([(0, valid_result(self.judge_spec))])

        result = evaluate_target_outcome(
            case=self.case,
            prepared={"workspace": str(self.workspace)},
            target=target,
            profile=profile,
            judge_invoker=judge_invoker,
            project_metadata={"source": "fixture"},
        )

        self.assertEqual(result.classification, "pass")
        self.assertTrue(result.judge_required)
        self.assertIsNotNone(result.judge)
        self.assertEqual(judge_invoker.calls, 1)
        self.assertEqual(profile.check_calls, 1)
        self.assertEqual(profile.judge_spec_calls, 1)
        self.assertEqual(profile.parse_calls, 1)
        self.assertIs(profile.parsed_attempt, result.judge.final_attempt)
        self.assertEqual(result.semantic, SEMANTIC_PASS)

        artifact = build_eval_artifact(result, run_id="run-1", iteration=1)
        self.assertIs(validate_eval_artifact(artifact), artifact)
        self.assertEqual(artifact["classification"], "pass")
        self.assertEqual(len(artifact["target"]["attempts"]), 1)
        self.assertEqual(len(artifact["judge"]["attempts"]), 1)
        self.assertEqual(artifact["judge"]["semantic"]["status"], "pass")
        self.assertEqual(artifact["project_metadata"], {"source": "fixture"})

    def test_deterministic_only_case_does_not_invoke_judge(self):
        target = self.target_outcome()
        profile = FakeProfile(None)
        judge_invoker = SequenceInvoker([])

        result = evaluate_target_outcome(
            case=self.case,
            prepared=None,
            target=target,
            profile=profile,
            judge_invoker=judge_invoker,
        )

        self.assertEqual(result.classification, "pass")
        self.assertFalse(result.judge_required)
        self.assertIsNone(result.judge)
        self.assertIsNone(result.semantic)
        self.assertEqual(judge_invoker.calls, 0)
        self.assertEqual(profile.parse_calls, 0)

        artifact = build_eval_artifact(result, run_id="run-2", iteration=1)
        self.assertIs(validate_eval_artifact(artifact), artifact)
        self.assertEqual(artifact["judge"]["attempts"], [])
        self.assertIsNone(artifact["judge"]["semantic"])

    def test_actual_judge_execution_failure_flows_to_non_evidence(self):
        target = self.target_outcome()
        profile = FakeProfile(self.judge_spec)
        invalid = valid_result(self.judge_spec)
        invalid["schema"] = "wrong/v1"
        judge_invoker = SequenceInvoker([(0, invalid)])

        result = evaluate_target_outcome(
            case=self.case,
            prepared=None,
            target=target,
            profile=profile,
            judge_invoker=judge_invoker,
        )

        self.assertEqual(result.classification, "non-evidence")
        self.assertIsNotNone(result.judge)
        self.assertEqual(
            result.judge.final_attempt.failure.code,
            "invoke_invalid_result",
        )
        self.assertEqual(profile.parse_calls, 0)

        artifact = build_eval_artifact(result, run_id="run-3", iteration=1)
        self.assertIs(validate_eval_artifact(artifact), artifact)
        self.assertEqual(
            artifact["judge"]["attempts"][0]["failure"]["code"],
            "invoke_invalid_result",
        )

    def test_parse_contract_failure_preserves_successful_judge_execution(self):
        target = self.target_outcome()
        profile = FakeProfile(
            self.judge_spec,
            parse_error=ValueError("judge output missing required verdict"),
        )
        judge_invoker = SequenceInvoker([(0, valid_result(self.judge_spec))])

        result = evaluate_target_outcome(
            case=self.case,
            prepared=None,
            target=target,
            profile=profile,
            judge_invoker=judge_invoker,
        )

        self.assertEqual(result.classification, "non-evidence")
        self.assertIsNotNone(result.judge)
        self.assertIsNone(result.judge.final_attempt.failure)
        self.assertIsNotNone(result.judge_contract_failure)
        self.assertEqual(
            result.judge_contract_failure.code,
            "judge_contract_invalid",
        )
        self.assertIsNone(result.semantic)

        artifact = build_eval_artifact(result, run_id="run-4", iteration=1)
        self.assertIs(validate_eval_artifact(artifact), artifact)
        self.assertIsNone(artifact["judge"]["attempts"][0]["failure"])
        self.assertEqual(
            artifact["judge"]["contract_failure"]["code"],
            "judge_contract_invalid",
        )

    def test_nonready_target_stops_before_project_checks_and_judge(self):
        target = self.target_outcome(EvidenceRequirement(("native",)))
        self.assertEqual(target.readiness.status, "unsupported")
        self.assertEqual(target.final_attempt.failure.plane, "evidence")
        profile = FakeProfile(self.judge_spec)
        judge_invoker = SequenceInvoker([])

        result = evaluate_target_outcome(
            case=self.case,
            prepared=None,
            target=target,
            profile=profile,
            judge_invoker=judge_invoker,
        )

        self.assertEqual(result.classification, "non-evidence")
        self.assertEqual(profile.check_calls, 0)
        self.assertEqual(profile.judge_spec_calls, 0)
        self.assertEqual(profile.parse_calls, 0)
        self.assertEqual(judge_invoker.calls, 0)

        artifact = build_eval_artifact(result, run_id="run-5", iteration=1)
        self.assertIs(validate_eval_artifact(artifact), artifact)
        self.assertEqual(
            artifact["target"]["evidence_readiness"]["status"],
            "unsupported",
        )


if __name__ == "__main__":
    unittest.main()
