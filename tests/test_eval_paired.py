from __future__ import annotations

import copy
import tempfile
import threading
import unittest
from collections import Counter
from pathlib import Path

from container.runtime_evidence import (
    BOUNDARY_NATIVE,
    build_runtime_evidence,
    unsupported_runtime_evidence,
)
from runner.eval_artifacts import (
    EvalArtifactError,
    calculate_pair_id,
    claim_run_artifact_directory,
    validate_paired_eval_artifact,
)
from runner.eval_evidence import EvidenceRequirement
from runner.eval_execute import RESULT_SCHEMA, TransientProviderRetryPolicy
from runner.eval_paired import (
    PairedExecutionPolicy,
    PairedSideExecution,
    build_paired_eval_artifact,
    run_paired_evaluation,
)
from runner.eval_types import (
    ArtifactIdentity,
    CheckOutcome,
    InvocationSpec,
    NormalizedCase,
    SemanticDecision,
)


def complete_empty_runtime_evidence():
    return build_runtime_evidence(
        {
            "capture_started": True,
            "capture_ended": True,
            "records": [],
            "observer_failures": 0,
            "callback_failures": 0,
            "issues": [],
        }
    )


def make_spec(workspace: Path, model: str) -> InvocationSpec:
    return InvocationSpec(
        transport="opencode",
        model=model,
        reasoning="medium",
        agent="general",
        skill=None,
        workspace=workspace,
        workspace_mode="ro",
        prompt=model,
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


def valid_result(
    spec: InvocationSpec,
    *,
    exit_code: int = 0,
    stderr: str = "",
    runtime_evidence: dict | None = None,
):
    return {
        "schema": RESULT_SCHEMA,
        "transport": spec.transport,
        "model": spec.model,
        "reasoning": spec.reasoning or "provider-default",
        "reasoning_source": "explicit" if spec.reasoning else "provider-default",
        "exit_code": exit_code,
        "stderr": stderr,
        "runtime_evidence": (
            runtime_evidence
            if runtime_evidence is not None
            else unsupported_runtime_evidence("paired_provider_free")
        ),
    }


class FakeProfile:
    def __init__(
        self,
        judge_spec: InvocationSpec | None = None,
        *,
        check_status: str = "pass",
        semantic_status: str = "pass",
    ):
        self._judge_spec = judge_spec
        self._check_status = check_status
        self._semantic_status = semantic_status

    def deterministic_checks(self, case, prepared, target, readiness):
        return (
            CheckOutcome(
                name="fixture",
                status=self._check_status,
                reason="provider-free fixture",
                metadata={"side": prepared["side"]},
            ),
        )

    def judge_spec(self, case, prepared, target, checks):
        return self._judge_spec

    def parse_judge(self, case, prepared, judge):
        return SemanticDecision(
            status=self._semantic_status,
            summary="provider-free judge",
            data={"side": prepared["side"]},
        )


class RecordingInvoker:
    def __init__(self, callback=None):
        self.callback = callback
        self.calls = []
        self.counts = Counter()
        self.lock = threading.Lock()

    def __call__(self, spec):
        with self.lock:
            self.calls.append(spec.model)
            self.counts[spec.model] += 1
            call_number = self.counts[spec.model]
        if self.callback is not None:
            return self.callback(spec, call_number)
        return 0, valid_result(spec)


class PairedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.case = NormalizedCase(
            id="PAIR-1",
            selectors=("PAIR-1",),
            lane="standard",
            project_data=None,
            metadata={"fixture": "paired"},
        )

    def tearDown(self):
        self.temp.cleanup()

    def side(
        self,
        name,
        *,
        judge=True,
        evidence_requirement=EvidenceRequirement(),
        target_retry_policy=None,
        target_max_attempts=1,
    ):
        target_spec = make_spec(self.workspace, f"fixture/{name}/target")
        judge_spec = make_spec(self.workspace, f"fixture/{name}/judge") if judge else None
        return PairedSideExecution(
            case=self.case,
            prepared={"side": name},
            target_spec=target_spec,
            evidence_requirement=evidence_requirement,
            profile=FakeProfile(judge_spec),
            project_metadata={"side": name},
            target_retry_policy=target_retry_policy,
            target_max_attempts=target_max_attempts,
        )

    def test_sequential_policy_runs_complete_sides_in_explicit_order(self):
        invoker = RecordingInvoker()

        result = run_paired_evaluation(
            run_id="run-pair",
            iteration=1,
            baseline=self.side("baseline"),
            candidate=self.side("candidate"),
            policy=PairedExecutionPolicy(
                mode="sequential",
                order=("candidate", "baseline"),
            ),
            target_invoker=invoker,
            judge_invoker=invoker,
        )

        self.assertEqual(
            invoker.calls,
            [
                "fixture/candidate/target",
                "fixture/candidate/judge",
                "fixture/baseline/target",
                "fixture/baseline/judge",
            ],
        )
        self.assertEqual(result.baseline.classification, "pass")
        self.assertEqual(result.candidate.classification, "pass")
        self.assertEqual(len(result.baseline.target.attempts), 1)
        self.assertEqual(len(result.candidate.target.attempts), 1)
        self.assertEqual(len(result.baseline.judge.attempts), 1)
        self.assertEqual(len(result.candidate.judge.attempts), 1)

    def test_parallel_policy_allows_both_target_phases_to_overlap(self):
        barrier = threading.Barrier(2)

        def callback(spec, call_number):
            if spec.model.endswith("/target"):
                barrier.wait(timeout=2)
            return 0, valid_result(spec)

        invoker = RecordingInvoker(callback)
        result = run_paired_evaluation(
            run_id="run-parallel",
            iteration=1,
            baseline=self.side("baseline", judge=False),
            candidate=self.side("candidate", judge=False),
            policy=PairedExecutionPolicy(mode="parallel"),
            target_invoker=invoker,
            judge_invoker=invoker,
        )

        self.assertEqual(result.baseline.classification, "pass")
        self.assertEqual(result.candidate.classification, "pass")
        self.assertCountEqual(
            invoker.calls,
            ["fixture/baseline/target", "fixture/candidate/target"],
        )

    def test_one_sided_non_evidence_is_preserved_without_artificial_zero(self):
        invoker = RecordingInvoker()
        result = run_paired_evaluation(
            run_id="run-non-evidence",
            iteration=1,
            baseline=self.side(
                "baseline",
                judge=False,
                evidence_requirement=EvidenceRequirement((BOUNDARY_NATIVE,)),
            ),
            candidate=self.side("candidate", judge=False),
            target_invoker=invoker,
            judge_invoker=invoker,
        )

        self.assertEqual(result.baseline.classification, "non-evidence")
        self.assertEqual(result.baseline.target.readiness.status, "unsupported")
        self.assertEqual(result.candidate.classification, "pass")

        artifact = build_paired_eval_artifact(result)
        self.assertEqual(
            artifact["sides"]["baseline"]["classification"],
            "non-evidence",
        )
        self.assertEqual(artifact["sides"]["candidate"]["classification"], "pass")
        self.assertNotIn("classification", artifact)
        self.assertNotIn("comparison", artifact)
        self.assertNotIn("score", artifact)
        self.assertNotIn("delta", artifact)

    def test_retries_and_attempt_history_are_independent_per_side(self):
        transient_evidence = complete_empty_runtime_evidence()

        def callback(spec, call_number):
            if spec.model == "fixture/baseline/target" and call_number == 1:
                return (
                    2,
                    valid_result(
                        spec,
                        exit_code=2,
                        stderr="ProviderError: provider.no-route: Model unavailable",
                        runtime_evidence=transient_evidence,
                    ),
                )
            return 0, valid_result(spec)

        invoker = RecordingInvoker(callback)
        result = run_paired_evaluation(
            run_id="run-retry",
            iteration=1,
            baseline=self.side(
                "baseline",
                judge=False,
                target_retry_policy=TransientProviderRetryPolicy(),
                target_max_attempts=2,
            ),
            candidate=self.side("candidate", judge=False),
            target_invoker=invoker,
            judge_invoker=invoker,
            sleep=lambda _: None,
        )

        self.assertEqual(len(result.baseline.target.attempts), 2)
        self.assertEqual(len(result.baseline.target.retry_decisions), 1)
        self.assertTrue(result.baseline.target.retry_decisions[0].retry)
        self.assertEqual(len(result.candidate.target.attempts), 1)
        self.assertEqual(result.candidate.target.retry_decisions, ())
        self.assertEqual(invoker.counts["fixture/baseline/target"], 2)
        self.assertEqual(invoker.counts["fixture/candidate/target"], 1)

    def test_judge_failure_on_one_side_does_not_replace_other_side(self):
        def callback(spec, call_number):
            result = valid_result(spec)
            if spec.model == "fixture/candidate/judge":
                result["schema"] = "wrong/v1"
            return 0, result

        invoker = RecordingInvoker(callback)
        result = run_paired_evaluation(
            run_id="run-judge-failure",
            iteration=1,
            baseline=self.side("baseline"),
            candidate=self.side("candidate"),
            target_invoker=invoker,
            judge_invoker=invoker,
        )

        self.assertEqual(result.baseline.classification, "pass")
        self.assertEqual(result.candidate.classification, "non-evidence")
        self.assertIsNone(result.baseline.judge.final_attempt.failure)
        self.assertEqual(
            result.candidate.judge.final_attempt.failure.code,
            "invoke_invalid_result",
        )

    def test_paired_artifact_round_trip_retains_both_sides_and_identity(self):
        invoker = RecordingInvoker()
        result = run_paired_evaluation(
            run_id="run-artifact",
            iteration=2,
            baseline=self.side("baseline"),
            candidate=self.side("candidate"),
            target_invoker=invoker,
            judge_invoker=invoker,
        )
        artifact = build_paired_eval_artifact(result)
        self.assertIs(validate_paired_eval_artifact(artifact), artifact)
        self.assertEqual(
            artifact["pair_id"],
            calculate_pair_id("run-artifact", "PAIR-1", 2),
        )

        identity = ArtifactIdentity(
            run_id="run-artifact",
            case_id="PAIR-1",
            iteration=2,
        )
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-artifact")
            store.write_paired_job_artifact(identity, artifact)
            durable = store.read_paired_job_artifact(identity)

        self.assertEqual(
            durable["sides"]["baseline"]["target"]["attempts"][0]["result"]["model"],
            "fixture/baseline/target",
        )
        self.assertEqual(
            durable["sides"]["candidate"]["judge"]["attempts"][0]["result"]["model"],
            "fixture/candidate/judge",
        )
        self.assertEqual(
            durable["sides"]["baseline"]["project_metadata"],
            {"side": "baseline"},
        )
        self.assertEqual(
            durable["sides"]["candidate"]["project_metadata"],
            {"side": "candidate"},
        )

        tampered = copy.deepcopy(durable)
        tampered["execution_policy"]["mode"] = "parallel"
        with self.assertRaisesRegex(
            EvalArtifactError,
            "paired_artifact_evidence_id mismatch",
        ):
            validate_paired_eval_artifact(tampered)

    def test_invalid_policy_and_mismatched_case_identity_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exactly once"):
            PairedExecutionPolicy(order=("baseline", "baseline"))

        other_case = NormalizedCase(
            id="PAIR-OTHER",
            selectors=("PAIR-OTHER",),
            lane="standard",
            project_data=None,
            metadata={},
        )
        candidate = self.side("candidate", judge=False)
        candidate = PairedSideExecution(
            case=other_case,
            prepared=candidate.prepared,
            target_spec=candidate.target_spec,
            evidence_requirement=candidate.evidence_requirement,
            profile=candidate.profile,
        )
        with self.assertRaisesRegex(ValueError, "share one normalized case identity"):
            run_paired_evaluation(
                run_id="run-mismatch",
                iteration=1,
                baseline=self.side("baseline", judge=False),
                candidate=candidate,
                target_invoker=RecordingInvoker(),
            )


if __name__ == "__main__":
    unittest.main()
