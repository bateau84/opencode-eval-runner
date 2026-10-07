from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from container.runtime_evidence import unsupported_runtime_evidence
from runner.eval_artifacts import (
    EVAL_ARTIFACT_SCHEMA,
    EVAL_RUN_SCHEMA,
    EvalArtifactError,
    EvalArtifactStorageError,
    artifact_identity_for_job,
    attach_artifact_evidence_id,
    claim_run_artifact_directory,
)
from runner.eval_types import ArtifactIdentity, EvalJob, NormalizedCase, RunPlan


def valid_artifact(
    run_id: str,
    case_id: str,
    iteration: int,
    *,
    project_metadata=None,
    runtime_evidence=None,
):
    attempts = []
    if runtime_evidence is not None:
        attempts.append(
            {
                "attempt": 1,
                "started_at": "2026-10-07T10:00:00Z",
                "duration_seconds": 0.1,
                "host_exit_code": 0,
                "result": {
                    "schema": "opencode-eval-runner/v1",
                    "transport": "opencode",
                    "exit_code": 0,
                    "runtime_evidence": runtime_evidence,
                },
                "failure": None,
            }
        )
    return attach_artifact_evidence_id(
        {
            "schema": EVAL_ARTIFACT_SCHEMA,
            "run_id": run_id,
            "case": case_id,
            "iteration": iteration,
            "lane": "standard",
            "classification": "non-evidence",
            "timing": {},
            "target": {"attempts": attempts, "evidence_readiness": {}},
            "deterministic_checks": [],
            "judge": {"attempts": [], "semantic": None},
            "project_metadata": project_metadata or {},
        }
    )


def valid_manifest(run_id: str, *, project_metadata=None):
    return {
        "schema": EVAL_RUN_SCHEMA,
        "run_id": run_id,
        "created_at": "2026-10-07T10:00:00Z",
        "selection": {},
        "iterations": 1,
        "concurrency": {"standard": 1, "runtime": 0},
        "jobs": [],
        "summary": {},
        "project_metadata": project_metadata or {},
    }


class EvalArtifactStorageTests(unittest.TestCase):
    def test_claim_fresh_directory_and_reopen_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "artifacts"
            first = claim_run_artifact_directory(root, "run-a")
            second = claim_run_artifact_directory(root, "run-a")

            self.assertEqual(first, second)
            self.assertTrue(first.owner_path.is_file())

    def test_claim_rejects_conflicting_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "artifacts"
            claim_run_artifact_directory(root, "run-a")

            with self.assertRaises(EvalArtifactStorageError):
                claim_run_artifact_directory(root, "run-b")

    def test_claim_rejects_unowned_nonempty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "artifacts"
            root.mkdir()
            (root / "stale.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaises(EvalArtifactStorageError):
                claim_run_artifact_directory(root, "run-a")

            self.assertFalse((root / ".eval-run-owner.json").exists())

    def test_case_iteration_paths_are_stable_safe_and_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            case = NormalizedCase(
                id="suite/a ../ümlaut",
                selectors=("suite/a ../ümlaut",),
                lane="standard",
                project_data=None,
                metadata={},
            )
            first = ArtifactIdentity("run-a", case.id, 1)
            second = ArtifactIdentity("run-a", case.id, 2)

            path1 = store.job_path(first)
            path1_again = store.job_path(first)
            path2 = store.job_path(second)

            self.assertEqual(path1, path1_again)
            self.assertNotEqual(path1, path2)
            self.assertEqual(path1.parent.parent, store.root / "jobs")
            self.assertNotIn("/", path1.parent.name)
            self.assertNotIn("\\", path1.parent.name)
            path1.relative_to(store.root)

    def test_plan_job_paths_match_job_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            case = NormalizedCase(
                id="Case-1",
                selectors=("Case-1",),
                lane="runtime",
                project_data=None,
                metadata={},
            )
            jobs = (
                EvalJob(case=case, iteration=1, label="Case-1#1"),
                EvalJob(case=case, iteration=2, label="Case-1#2"),
            )
            plan = RunPlan(
                run_id="run-a",
                jobs=jobs,
                standard_parallelism=0,
                runtime_parallelism=1,
            )

            paths = store.manifest_job_paths(plan)

            self.assertEqual(
                paths,
                tuple(
                    store.job_path_for(job).relative_to(store.root).as_posix()
                    for job in jobs
                ),
            )
            self.assertEqual(
                artifact_identity_for_job("run-a", jobs[1]),
                ArtifactIdentity("run-a", "Case-1", 2),
            )

    def test_atomic_job_write_replace_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            identity = ArtifactIdentity("run-a", "Case-1", 1)
            first = valid_artifact("run-a", "Case-1", 1, project_metadata={"value": 1})
            second = valid_artifact(
                "run-a",
                "Case-1",
                1,
                project_metadata={"value": 2, "nested": [1, 2]},
            )

            store.write_job_artifact(identity, first)
            store.write_job_artifact(identity, second)

            self.assertEqual(store.read_job_artifact(identity), second)
            self.assertEqual(
                [
                    p.name
                    for p in store.job_path(identity).parent.iterdir()
                    if p.name.endswith(".tmp")
                ],
                [],
            )

    def test_manifest_and_opaque_metadata_round_trip_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            identity = ArtifactIdentity("run-a", "Case-1", 1)
            evidence = unsupported_runtime_evidence("test_transport_unsupported")
            artifact = valid_artifact(
                "run-a",
                "Case-1",
                1,
                project_metadata={
                    "nested": {"arbitrary": [1, True, None, "ø"]},
                    "future_field": {"keep": "opaque"},
                },
                runtime_evidence=evidence,
            )
            original = copy.deepcopy(artifact)
            manifest = valid_manifest(
                "run-a",
                project_metadata={"suite": {"custom": ["a", "b"]}},
            )
            manifest_original = copy.deepcopy(manifest)

            store.write_job_artifact(identity, artifact)
            store.write_run_manifest(manifest)

            self.assertEqual(artifact, original)
            self.assertEqual(manifest, manifest_original)
            self.assertEqual(store.read_job_artifact(identity), original)
            self.assertEqual(store.read_run_manifest(), manifest_original)
            self.assertEqual(
                store.read_job_artifact(identity)["target"]["attempts"][0]["result"][
                    "runtime_evidence"
                ],
                evidence,
            )

    def test_read_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            identity = ArtifactIdentity("run-a", "Case-1", 1)
            path = store.job_path(identity)
            path.parent.mkdir(parents=True)
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaises(EvalArtifactStorageError):
                store.read_job_artifact(identity)

    def test_write_rejects_identity_from_other_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            with self.assertRaises(EvalArtifactStorageError):
                store.write_job_artifact(
                    ArtifactIdentity("run-b", "Case-1", 1),
                    {"value": 1},
                )


    def test_write_rejects_artifact_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            identity = ArtifactIdentity("run-a", "Case-1", 1)
            artifact = valid_artifact("run-a", "Case-2", 1)

            with self.assertRaises(EvalArtifactStorageError):
                store.write_job_artifact(identity, artifact)

    def test_read_rejects_integrity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            identity = ArtifactIdentity("run-a", "Case-1", 1)
            artifact = valid_artifact("run-a", "Case-1", 1, project_metadata={"value": 1})
            store.write_job_artifact(identity, artifact)

            path = store.job_path(identity)
            tampered = path.read_text(encoding="utf-8").replace('"value": 1', '"value": 9')
            path.write_text(tampered, encoding="utf-8")

            with self.assertRaises(EvalArtifactError):
                store.read_job_artifact(identity)

    def test_manifest_run_identity_must_match_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = claim_run_artifact_directory(Path(temp) / "artifacts", "run-a")
            with self.assertRaises(EvalArtifactStorageError):
                store.write_run_manifest(valid_manifest("run-b"))


if __name__ == "__main__":
    unittest.main()
