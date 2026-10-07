from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from container.runtime_evidence import (
    build_runtime_evidence,
    unsupported_runtime_evidence,
)
from runner.eval_api import load_eval_profile
from runner.eval_artifacts import (
    EVAL_RUN_SCHEMA,
    EvalArtifactError,
    artifact_identity_for_job,
    claim_run_artifact_directory,
    validate_eval_artifact,
    validate_eval_run,
)
from runner.eval_engine import build_eval_artifact, evaluate_target_outcome
from runner.eval_execute import (
    RESULT_SCHEMA,
    TransientProviderRetryPolicy,
    run_target_attempts,
)
from runner.eval_plan import build_run_plan, list_case_ids, list_cases, select_cases


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE_MODULE = "generic_eval_profile"
_FIXTURE_REF = f"{_FIXTURE_MODULE}:profile"


@contextmanager
def loaded_fixture_profile():
    sys.path.insert(0, str(_FIXTURE_DIR))
    sys.modules.pop(_FIXTURE_MODULE, None)
    try:
        yield load_eval_profile(_FIXTURE_REF)
    finally:
        sys.modules.pop(_FIXTURE_MODULE, None)
        try:
            sys.path.remove(str(_FIXTURE_DIR))
        except ValueError:
            pass


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


def result_for(spec, *, exit_code=0, stderr="", stdout="", runtime_evidence=None):
    return {
        "schema": RESULT_SCHEMA,
        "transport": spec.transport,
        "model": spec.model,
        "reasoning": spec.reasoning or "provider-default",
        "reasoning_source": "explicit" if spec.reasoning else "provider-default",
        "exit_code": exit_code,
        "stderr": stderr,
        "stdout": stdout,
        "runtime_evidence": (
            runtime_evidence
            if runtime_evidence is not None
            else unsupported_runtime_evidence("provider_free_acceptance")
        ),
    }


class ProviderFreeInvoker:
    """Deterministic invoke adapter: no provider, network, or container access."""

    def __init__(self):
        self.calls = []
        self.counts = Counter()

    def __call__(self, spec):
        self.calls.append(spec.model)
        self.counts[spec.model] += 1

        try:
            _, phase, case_id = spec.model.split("/", 2)
        except ValueError as exc:
            raise AssertionError(f"unexpected fixture model: {spec.model}") from exc

        if phase == "target" and case_id == "PF-RETRY" and self.counts[spec.model] == 1:
            return (
                2,
                result_for(
                    spec,
                    exit_code=2,
                    stderr="ProviderError: provider.no-route: Model unavailable",
                    runtime_evidence=complete_empty_runtime_evidence(),
                ),
            )

        stdout = ""
        if phase == "judge":
            status = "fail" if case_id == "PF-FAIL" else "pass"
            stdout = json.dumps({"case": case_id, "status": status})

        return 0, result_for(spec, stdout=stdout)


def run_fixture_job(profile, job, invoker):
    retry_policy = TransientProviderRetryPolicy()
    with profile.prepare(job.case, job.iteration) as prepared:
        target = run_target_attempts(
            profile.target_spec(job.case, prepared),
            retry_policy=retry_policy,
            max_attempts=2,
            invoker=invoker,
            evidence_requirement=profile.target_evidence_requirement(
                job.case,
                prepared,
            ),
        )
        result = evaluate_target_outcome(
            case=job.case,
            prepared=prepared,
            target=target,
            profile=profile,
            project_metadata=profile.artifact_metadata(job.case, prepared),
            judge_retry_policy=retry_policy,
            judge_max_attempts=2,
            judge_invoker=invoker,
        )
        artifact = build_eval_artifact(
            result,
            run_id="provider-free-run",
            iteration=job.iteration,
        )
    return result, artifact


class GenericProfileAcceptanceTests(unittest.TestCase):
    def test_discovery_listing_and_explicit_selection_use_frozen_profile(self):
        with loaded_fixture_profile() as profile:
            cases = list_cases(profile.discover_cases())

        self.assertEqual(
            list_case_ids(cases),
            (
                "PF-PASS",
                "PF-FAIL",
                "PF-DETERMINISTIC",
                "PF-NON-EVIDENCE",
                "PF-RETRY",
            ),
        )
        self.assertEqual(
            [case.id for case in select_cases(cases, selectors=("standard",))],
            ["PF-PASS", "PF-FAIL", "PF-DETERMINISTIC"],
        )
        self.assertEqual(
            [case.id for case in select_cases(cases, selectors=("retry",))],
            ["PF-RETRY"],
        )

    def test_multiple_iterations_and_standard_runtime_planning(self):
        with loaded_fixture_profile() as profile:
            plan = build_run_plan(
                "provider-free-plan",
                profile.discover_cases(),
                select_all=True,
                iterations=2,
                standard_parallelism=2,
                runtime_parallelism=1,
            )

        self.assertEqual(len(plan.jobs), 10)
        self.assertEqual(plan.standard_parallelism, 2)
        self.assertEqual(plan.runtime_parallelism, 1)
        self.assertEqual(
            [job.label for job in plan.jobs[:6]],
            [
                "PF-PASS#1",
                "PF-PASS#2",
                "PF-FAIL#1",
                "PF-FAIL#2",
                "PF-DETERMINISTIC#1",
                "PF-DETERMINISTIC#2",
            ],
        )
        self.assertEqual(
            [job.label for job in plan.jobs[6:]],
            [
                "PF-NON-EVIDENCE#1",
                "PF-NON-EVIDENCE#2",
                "PF-RETRY#1",
                "PF-RETRY#2",
            ],
        )

    def test_target_readiness_judge_classification_and_retry_accounting(self):
        with loaded_fixture_profile() as profile:
            plan = build_run_plan(
                "provider-free-run",
                profile.discover_cases(),
                select_all=True,
                iterations=1,
                standard_parallelism=2,
                runtime_parallelism=1,
            )
            invoker = ProviderFreeInvoker()
            outcomes = {
                job.case.id: run_fixture_job(profile, job, invoker)
                for job in plan.jobs
            }

        self.assertEqual(outcomes["PF-PASS"][0].classification, "pass")
        self.assertEqual(outcomes["PF-FAIL"][0].classification, "fail")
        self.assertEqual(outcomes["PF-DETERMINISTIC"][0].classification, "pass")
        self.assertEqual(outcomes["PF-NON-EVIDENCE"][0].classification, "non-evidence")
        self.assertEqual(outcomes["PF-RETRY"][0].classification, "pass")

        pass_result = outcomes["PF-PASS"][0]
        self.assertEqual(pass_result.target.readiness.status, "ready")
        self.assertTrue(pass_result.judge_required)
        self.assertEqual(pass_result.semantic.status, "pass")

        fail_result = outcomes["PF-FAIL"][0]
        self.assertTrue(fail_result.judge_required)
        self.assertEqual(fail_result.semantic.status, "fail")

        deterministic = outcomes["PF-DETERMINISTIC"][0]
        self.assertFalse(deterministic.judge_required)
        self.assertIsNone(deterministic.judge)
        self.assertNotIn("fixture/judge/PF-DETERMINISTIC", invoker.calls)

        non_evidence = outcomes["PF-NON-EVIDENCE"][0]
        self.assertEqual(non_evidence.target.readiness.status, "unsupported")
        self.assertIsNone(non_evidence.judge)
        self.assertNotIn("fixture/judge/PF-NON-EVIDENCE", invoker.calls)

        retry = outcomes["PF-RETRY"][0]
        self.assertEqual(len(retry.target.attempts), 2)
        self.assertEqual(len(retry.target.retry_decisions), 1)
        self.assertTrue(retry.target.retry_decisions[0].retry)
        retry_artifact = outcomes["PF-RETRY"][1]
        self.assertEqual(len(retry_artifact["target"]["attempts"]), 2)
        self.assertTrue(
            retry_artifact["target"]["attempts"][0]["retry_decision"]["retry"]
        )

    def test_artifacts_round_trip_with_integrity_and_run_summary(self):
        with loaded_fixture_profile() as profile:
            plan = build_run_plan(
                "provider-free-run",
                profile.discover_cases(),
                select_all=True,
                iterations=1,
                standard_parallelism=2,
                runtime_parallelism=1,
            )
            invoker = ProviderFreeInvoker()

            with tempfile.TemporaryDirectory() as temp:
                store = claim_run_artifact_directory(
                    Path(temp) / "artifacts",
                    plan.run_id,
                )
                classifications = []
                artifacts = []

                for job in plan.jobs:
                    result, artifact = run_fixture_job(profile, job, invoker)
                    identity = artifact_identity_for_job(plan.run_id, job)
                    store.write_job_artifact(identity, artifact)
                    durable = store.read_job_artifact(identity)
                    self.assertEqual(durable["artifact_evidence_id"], artifact["artifact_evidence_id"])
                    self.assertIs(validate_eval_artifact(durable), durable)
                    classifications.append(durable["classification"])
                    artifacts.append(durable)

                counts = Counter(classifications)
                manifest = {
                    "schema": EVAL_RUN_SCHEMA,
                    "run_id": plan.run_id,
                    "created_at": "2026-10-07T00:00:00Z",
                    "selection": {"all": True},
                    "iterations": 1,
                    "concurrency": {
                        "standard": plan.standard_parallelism,
                        "runtime": plan.runtime_parallelism,
                    },
                    "jobs": [
                        {
                            "case": job.case.id,
                            "iteration": job.iteration,
                            "artifact": path,
                        }
                        for job, path in zip(
                            plan.jobs,
                            store.manifest_job_paths(plan),
                            strict=True,
                        )
                    ],
                    "summary": {
                        "pass": counts["pass"],
                        "fail": counts["fail"],
                        "non-evidence": counts["non-evidence"],
                        "total": len(classifications),
                    },
                    "project_metadata": {"fixture": "provider-free"},
                }
                store.write_run_manifest(manifest)
                durable_run = store.read_run_manifest()

                self.assertIs(validate_eval_run(durable_run), durable_run)
                self.assertEqual(
                    durable_run["summary"],
                    {
                        "pass": 3,
                        "fail": 1,
                        "non-evidence": 1,
                        "total": 5,
                    },
                )

                tampered = json.loads(json.dumps(artifacts[0]))
                tampered["project_metadata"]["case"] = "tampered"
                with self.assertRaisesRegex(
                    EvalArtifactError,
                    "artifact_evidence_id mismatch",
                ):
                    validate_eval_artifact(tampered)


if __name__ == "__main__":
    unittest.main()
