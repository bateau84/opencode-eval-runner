"""Shared contract surface for durable generic eval artifacts.

Task 3 workers build storage and integrity behavior on top of this module.
This scaffold intentionally contains no path, persistence, validation, or
hashing implementation.
"""
from __future__ import annotations


EVAL_RUN_SCHEMA = "opencode-eval-runner/eval-run/v1"
EVAL_ARTIFACT_SCHEMA = "opencode-eval-runner/eval-artifact/v1"


class EvalArtifactError(Exception):
    """Base error for artifact storage and integrity failures."""
