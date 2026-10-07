from __future__ import annotations

import copy
import unittest

from container.runtime_evidence import unsupported_runtime_evidence
from runner.eval_artifacts import (
    EVAL_ARTIFACT_SCHEMA,
    EVAL_RUN_SCHEMA,
    EvalArtifactError,
    attach_artifact_evidence_id,
    calculate_artifact_evidence_id,
    deserialize_eval_artifact,
    deserialize_eval_run,
    serialize_eval_artifact,
    serialize_eval_run,
    validate_eval_artifact,
    validate_eval_run,
)


def runner_result(*, runtime_evidence=None, exit_code=0):
    return {
        "schema": "opencode-eval-runner/v1",
        "transport": "opencode",
        "exit_code": exit_code,
        "runtime_evidence": (
            runtime_evidence
            if runtime_evidence is not None
            else unsupported_runtime_evidence("test_transport_unsupported")
        ),
    }


def attempt(number: int, *, result=None, failure=None, retry_decision=None):
    value = {
        "attempt": number,
        "started_at": f"2026-10-07T10:0{number}:00Z",
        "duration_seconds": 0.25 * number,
        "host_exit_code": 0 if result is not None else 2,
        "result": result,
        "failure": failure,
    }
    if retry_decision is not None:
        value["retry_decision"] = retry_decision
    return value


def artifact_without_id():
    return {
        "schema": EVAL_ARTIFACT_SCHEMA,
        "run_id": "run-123",
        "case": "CASE-1",
        "iteration": 2,
        "lane": "runtime",
        "classification": "pass",
        "timing": {
            "started_at": "2026-10-07T10:00:00Z",
            "duration_seconds": 1.5,
            "target_seconds": 1.0,
            "judge_seconds": 0.5,
        },
        "target": {
            "attempts": [attempt(1, result=runner_result())],
            "evidence_readiness": {
                "status": "ready",
                "reasons": [],
                "required_boundaries": ["native"],
            },
        },
        "deterministic_checks": [],
        "judge": {
            "attempts": [attempt(1, result=runner_result())],
            "semantic": {"status": "pass", "summary": "ok", "data": {"score": 1}},
        },
        "project_metadata": {
            "owner": "project",
            "nested": {"flags": [True, False, None], "weight": 1.25},
        },
    }


def run_manifest():
    return {
        "schema": EVAL_RUN_SCHEMA,
        "run_id": "run-123",
        "created_at": "2026-10-07T10:00:00Z",
        "selection": {"selectors": ["CASE-1"]},
        "iterations": 2,
        "concurrency": {"standard": 0, "runtime": 1},
        "jobs": [
            {"case": "CASE-1", "iteration": 1, "lane": "runtime"},
            {"case": "CASE-1", "iteration": 2, "lane": "runtime"},
        ],
        "summary": {"pass": 1, "fail": 0, "non_evidence": 0},
        "project_metadata": {"opaque": ["a", {"b": 2}]},
    }


class EvalArtifactIntegrityTests(unittest.TestCase):
    def test_valid_artifact_round_trip(self):
        artifact = attach_artifact_evidence_id(artifact_without_id())

        encoded = serialize_eval_artifact(artifact)
        decoded = deserialize_eval_artifact(encoded)

        self.assertEqual(decoded, artifact)
        self.assertEqual(encoded, serialize_eval_artifact(decoded))
        self.assertIs(validate_eval_artifact(artifact), artifact)

    def test_valid_run_manifest_round_trip(self):
        manifest = run_manifest()

        encoded = serialize_eval_run(manifest)
        decoded = deserialize_eval_run(encoded)

        self.assertEqual(decoded, manifest)
        self.assertIs(validate_eval_run(manifest), manifest)

    def test_malformed_schema_and_required_containers_are_rejected(self):
        malformed = artifact_without_id()
        malformed["schema"] = "opencode-eval-runner/eval-artifact/v0"
        with self.assertRaisesRegex(EvalArtifactError, "schema"):
            attach_artifact_evidence_id(malformed)

        malformed = artifact_without_id()
        malformed["target"] = {"attempts": []}
        with self.assertRaisesRegex(EvalArtifactError, "evidence_readiness"):
            attach_artifact_evidence_id(malformed)

        malformed = artifact_without_id()
        malformed["judge"] = {"attempts": []}
        with self.assertRaisesRegex(EvalArtifactError, "semantic"):
            attach_artifact_evidence_id(malformed)

    def test_integrity_mismatch_fails_closed(self):
        artifact = attach_artifact_evidence_id(artifact_without_id())
        original_id = artifact["artifact_evidence_id"]
        artifact["project_metadata"]["nested"]["weight"] = 9.5

        with self.assertRaisesRegex(EvalArtifactError, "mismatch"):
            validate_eval_artifact(artifact)
        self.assertNotEqual(calculate_artifact_evidence_id(artifact), original_id)

    def test_integrity_id_excludes_the_id_field_and_is_canonical(self):
        artifact = attach_artifact_evidence_id(artifact_without_id())
        expected = artifact["artifact_evidence_id"]
        replaced = dict(artifact)
        replaced["artifact_evidence_id"] = "0" * 64

        self.assertEqual(calculate_artifact_evidence_id(replaced), expected)

        reordered = {key: artifact[key] for key in reversed(tuple(artifact))}
        self.assertEqual(calculate_artifact_evidence_id(reordered), expected)

    def test_project_metadata_is_opaque_and_preserved(self):
        raw = artifact_without_id()
        metadata = {
            "loom-like-but-not-required": {"trap": "opaque", "scores": [1, 2, 3]},
            "unicode": "blåbær",
            "null": None,
        }
        raw["project_metadata"] = copy.deepcopy(metadata)

        decoded = deserialize_eval_artifact(
            serialize_eval_artifact(attach_artifact_evidence_id(raw))
        )

        self.assertEqual(decoded["project_metadata"], metadata)

    def test_runtime_evidence_is_preserved_without_rewrite(self):
        evidence = unsupported_runtime_evidence("test_transport_unsupported")
        original = copy.deepcopy(evidence)
        raw = artifact_without_id()
        raw["target"]["attempts"][0]["result"] = runner_result(runtime_evidence=evidence)

        artifact = attach_artifact_evidence_id(raw)
        decoded = deserialize_eval_artifact(serialize_eval_artifact(artifact))

        self.assertEqual(evidence, original)
        self.assertEqual(
            decoded["target"]["attempts"][0]["result"]["runtime_evidence"],
            original,
        )

    def test_attempt_and_retry_data_survive_round_trip(self):
        raw = artifact_without_id()
        raw["target"]["attempts"] = [
            attempt(
                1,
                failure={
                    "plane": "infrastructure",
                    "code": "invoke_no_result",
                    "message": "no result file",
                    "retry_safe": True,
                },
                retry_decision={
                    "retry": True,
                    "reason": "transient provider failure",
                    "delay_seconds": 0.5,
                },
            ),
            attempt(
                2,
                result=runner_result(),
                retry_decision={
                    "retry": False,
                    "reason": "success",
                    "delay_seconds": 0.0,
                },
            ),
        ]

        artifact = attach_artifact_evidence_id(raw)
        decoded = deserialize_eval_artifact(serialize_eval_artifact(artifact))

        self.assertEqual(decoded["target"]["attempts"], raw["target"]["attempts"])

    def test_attempt_numbering_and_shapes_are_validated(self):
        raw = artifact_without_id()
        raw["target"]["attempts"] = [attempt(2, result=runner_result())]
        with self.assertRaisesRegex(EvalArtifactError, "contiguous"):
            attach_artifact_evidence_id(raw)

        raw = artifact_without_id()
        raw["target"]["attempts"][0]["result"] = None
        with self.assertRaisesRegex(EvalArtifactError, "result or failure"):
            attach_artifact_evidence_id(raw)

    def test_runtime_evidence_contract_is_validated(self):
        raw = artifact_without_id()
        raw["target"]["attempts"][0]["result"] = runner_result(
            runtime_evidence={"schema": "wrong"}
        )
        with self.assertRaisesRegex(EvalArtifactError, "runtime_evidence"):
            attach_artifact_evidence_id(raw)

    def test_readiness_timing_and_classification_are_validated(self):
        raw = artifact_without_id()
        raw["classification"] = "error"
        with self.assertRaisesRegex(EvalArtifactError, "classification"):
            attach_artifact_evidence_id(raw)

        raw = artifact_without_id()
        raw["target"]["evidence_readiness"]["status"] = "maybe"
        with self.assertRaisesRegex(EvalArtifactError, "status"):
            attach_artifact_evidence_id(raw)

        raw = artifact_without_id()
        raw["timing"]["duration_seconds"] = -1
        with self.assertRaisesRegex(EvalArtifactError, "duration_seconds"):
            attach_artifact_evidence_id(raw)

    def test_empty_readiness_placeholder_is_allowed_for_task3_envelope(self):
        raw = artifact_without_id()
        raw["target"]["evidence_readiness"] = {}
        validate_eval_artifact(attach_artifact_evidence_id(raw))

    def test_non_json_project_metadata_is_rejected(self):
        raw = artifact_without_id()
        raw["project_metadata"] = {"bad": float("nan")}
        with self.assertRaisesRegex(EvalArtifactError, "non-finite"):
            attach_artifact_evidence_id(raw)

    def test_duplicate_json_keys_are_rejected_on_read(self):
        artifact = attach_artifact_evidence_id(artifact_without_id())
        encoded = serialize_eval_artifact(artifact).decode("utf-8")
        duplicate = encoded[:-1] + ',"run_id":"other"}'
        with self.assertRaisesRegex(EvalArtifactError, "duplicate JSON object key"):
            deserialize_eval_artifact(duplicate)

    def test_malformed_run_manifest_is_rejected(self):
        manifest = run_manifest()
        manifest["concurrency"]["runtime"] = True
        with self.assertRaisesRegex(EvalArtifactError, "integer"):
            validate_eval_run(manifest)

        manifest = run_manifest()
        manifest["schema"] = "wrong"
        with self.assertRaisesRegex(EvalArtifactError, "schema"):
            validate_eval_run(manifest)


if __name__ == "__main__":
    unittest.main()
