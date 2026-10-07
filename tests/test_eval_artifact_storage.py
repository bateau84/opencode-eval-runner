from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from runner.eval_artifact_storage import (
    EvalArtifactStorageError,
    artifact_identity_for_job,
    claim_run_artifact_directory,
)
from runner.eval_types import ArtifactIdentity, EvalJob, NormalizedCase, RunPlan


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

            store.write_job_artifact(identity, {"value": 1})
            store.write_job_artifact(identity, {"value": 2, "nested": [1, 2]})

            self.assertEqual(
                store.read_job_artifact(identity),
                {"value": 2, "nested": [1, 2]},
            )
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
            artifact = {
                "schema": "opencode-eval-runner/eval-artifact/v1",
                "run_id": "run-a",
                "case": "Case-1",
                "iteration": 1,
                "project_metadata": {
                    "nested": {"arbitrary": [1, True, None, "ø"]},
                    "future_field": {"keep": "opaque"},
                },
                "runtime_evidence": {"opaque": {"do_not_rewrite": ["x", "y"]}},
            }
            original = copy.deepcopy(artifact)
            manifest = {
                "schema": "opencode-eval-runner/eval-run/v1",
                "run_id": "run-a",
                "jobs": [{"case": "Case-1", "iteration": 1}],
                "project_metadata": {"suite": {"custom": ["a", "b"]}},
            }
            manifest_original = copy.deepcopy(manifest)

            store.write_job_artifact(identity, artifact)
            store.write_run_manifest(manifest)

            self.assertEqual(artifact, original)
            self.assertEqual(manifest, manifest_original)
            self.assertEqual(store.read_job_artifact(identity), original)
            self.assertEqual(store.read_run_manifest(), manifest_original)

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


if __name__ == "__main__":
    unittest.main()
