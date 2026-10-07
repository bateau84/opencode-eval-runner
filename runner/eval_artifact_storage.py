"""Compatibility shim for the reconciled Task 3 artifact API.

The canonical artifact surface lives in runner.eval_artifacts. New callers
should import storage, schema, and integrity helpers from there.
"""
from runner.eval_artifacts import (
    EvalArtifactStorageError,
    RunArtifactStore,
    artifact_identity_for_job,
    claim_run_artifact_directory,
)

__all__ = [
    "EvalArtifactStorageError",
    "RunArtifactStore",
    "artifact_identity_for_job",
    "claim_run_artifact_directory",
]
