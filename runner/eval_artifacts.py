"""Schema validation and integrity helpers for generic eval artifacts.

This module owns only the versioned on-disk envelope and integrity rules. It
must not interpret project metadata, behavioral checks, or runtime evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from container.runtime_evidence import RuntimeEvidenceError, validate_runtime_evidence


EVAL_RUN_SCHEMA = "opencode-eval-runner/eval-run/v1"
EVAL_ARTIFACT_SCHEMA = "opencode-eval-runner/eval-artifact/v1"
RUNNER_RESULT_SCHEMA = "opencode-eval-runner/v1"

CLASSIFICATIONS = frozenset({"pass", "fail", "non-evidence"})
LANES = frozenset({"standard", "runtime"})
READINESS_STATUSES = frozenset({"ready", "incomplete", "unsupported", "invalid"})
FAILURE_PLANES = frozenset({"infrastructure", "product", "evidence"})
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class EvalArtifactError(Exception):
    """Base error for artifact storage and integrity failures."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalArtifactError(message)


def _object(value: Any, where: str) -> dict[str, Any]:
    _require(type(value) is dict, f"{where} must be an object")
    return value


def _array(value: Any, where: str) -> list[Any]:
    _require(type(value) is list, f"{where} must be an array")
    return value


def _string(value: Any, where: str) -> str:
    _require(type(value) is str and bool(value.strip()), f"{where} must be a non-empty string")
    return value


def _integer(value: Any, where: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{where} must be an integer >= {minimum}")
    return value


def _number(value: Any, where: str, *, minimum: float = 0.0) -> int | float:
    valid = (
        (type(value) is int and value >= minimum)
        or (type(value) is float and math.isfinite(value) and value >= minimum)
    )
    _require(valid, f"{where} must be a finite number >= {minimum:g}")
    return value


def _strict_json_value(value: Any, where: str = "value") -> None:
    if value is None or type(value) in {bool, int, str}:
        return
    if type(value) is float:
        _require(math.isfinite(value), f"{where} must not contain non-finite numbers")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _strict_json_value(item, f"{where}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, f"{where} object keys must be strings")
            _strict_json_value(item, f"{where}.{key}")
        return
    raise EvalArtifactError(f"{where} must contain only strict JSON-compatible values")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the deterministic UTF-8 JSON representation used for integrity IDs."""
    _strict_json_value(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvalArtifactError(f"value is not canonical JSON: {exc}") from exc


def _validate_runner_result(value: Any, where: str) -> None:
    result = _object(value, where)
    _strict_json_value(result, where)
    _require(result.get("schema") == RUNNER_RESULT_SCHEMA, f"{where}.schema is unsupported")
    _require("runtime_evidence" in result, f"{where}.runtime_evidence is required")
    try:
        validate_runtime_evidence(result["runtime_evidence"])
    except RuntimeEvidenceError as exc:
        raise EvalArtifactError(f"{where}.runtime_evidence is invalid: {exc}") from exc


def _validate_attempt_failure(value: Any, where: str) -> None:
    failure = _object(value, where)
    _strict_json_value(failure, where)
    required = {"plane", "code", "message", "retry_safe"}
    _require(required <= set(failure), f"{where} is missing required fields: {sorted(required - set(failure))}")
    _require(failure["plane"] in FAILURE_PLANES, f"{where}.plane is unsupported")
    _string(failure["code"], f"{where}.code")
    _require(type(failure["message"]) is str, f"{where}.message must be a string")
    _require(type(failure["retry_safe"]) is bool, f"{where}.retry_safe must be a boolean")


def _validate_retry_decision(value: Any, where: str) -> None:
    decision = _object(value, where)
    _strict_json_value(decision, where)
    required = {"retry", "reason", "delay_seconds"}
    _require(required <= set(decision), f"{where} is missing required fields: {sorted(required - set(decision))}")
    _require(type(decision["retry"]) is bool, f"{where}.retry must be a boolean")
    _require(type(decision["reason"]) is str, f"{where}.reason must be a string")
    _number(decision["delay_seconds"], f"{where}.delay_seconds")


def _validate_attempt(value: Any, where: str) -> int:
    attempt = _object(value, where)
    _strict_json_value(attempt, where)
    required = {
        "attempt",
        "started_at",
        "duration_seconds",
        "host_exit_code",
        "result",
        "failure",
    }
    _require(required <= set(attempt), f"{where} is missing required fields: {sorted(required - set(attempt))}")

    number = _integer(attempt["attempt"], f"{where}.attempt", minimum=1)
    _string(attempt["started_at"], f"{where}.started_at")
    _number(attempt["duration_seconds"], f"{where}.duration_seconds")
    _require(
        attempt["host_exit_code"] is None or type(attempt["host_exit_code"]) is int,
        f"{where}.host_exit_code must be an integer or null",
    )

    result = attempt["result"]
    failure = attempt["failure"]
    if result is not None:
        _validate_runner_result(result, f"{where}.result")
    if failure is not None:
        _validate_attempt_failure(failure, f"{where}.failure")
    _require(result is not None or failure is not None, f"{where} must contain a result or failure")

    if "retry_decision" in attempt and attempt["retry_decision"] is not None:
        _validate_retry_decision(attempt["retry_decision"], f"{where}.retry_decision")
    return number


def _validate_attempts(value: Any, where: str) -> None:
    attempts = _array(value, where)
    for index, attempt in enumerate(attempts, start=1):
        number = _validate_attempt(attempt, f"{where}[{index - 1}]")
        _require(number == index, f"{where} attempt numbering must be contiguous starting at 1")


def _validate_evidence_readiness(value: Any, where: str) -> None:
    readiness = _object(value, where)
    _strict_json_value(readiness, where)
    if not readiness:
        return

    required = {"status", "reasons", "required_boundaries"}
    _require(required <= set(readiness), f"{where} is missing required fields: {sorted(required - set(readiness))}")
    _require(readiness["status"] in READINESS_STATUSES, f"{where}.status is unsupported")
    for field in ("reasons", "required_boundaries"):
        items = _array(readiness[field], f"{where}.{field}")
        for index, item in enumerate(items):
            _string(item, f"{where}.{field}[{index}]")


def _validate_timing(value: Any, where: str) -> None:
    timing = _object(value, where)
    _strict_json_value(timing, where)
    for key, item in timing.items():
        if key.endswith("_seconds"):
            _number(item, f"{where}.{key}")
        elif key.endswith("_at") and item is not None:
            _string(item, f"{where}.{key}")


def _validate_target(value: Any, where: str) -> None:
    target = _object(value, where)
    _strict_json_value(target, where)
    required = {"attempts", "evidence_readiness"}
    _require(required <= set(target), f"{where} is missing required fields: {sorted(required - set(target))}")
    _validate_attempts(target["attempts"], f"{where}.attempts")
    _validate_evidence_readiness(target["evidence_readiness"], f"{where}.evidence_readiness")


def _validate_judge(value: Any, where: str) -> None:
    judge = _object(value, where)
    _strict_json_value(judge, where)
    required = {"attempts", "semantic"}
    _require(required <= set(judge), f"{where} is missing required fields: {sorted(required - set(judge))}")
    _validate_attempts(judge["attempts"], f"{where}.attempts")
    if judge["semantic"] is not None:
        _object(judge["semantic"], f"{where}.semantic")
        _strict_json_value(judge["semantic"], f"{where}.semantic")


def _validate_eval_artifact_shape(value: Any, *, require_evidence_id: bool) -> dict[str, Any]:
    artifact = _object(value, "eval artifact")
    _strict_json_value(artifact, "eval artifact")
    required = {
        "schema",
        "run_id",
        "case",
        "iteration",
        "lane",
        "classification",
        "timing",
        "target",
        "deterministic_checks",
        "judge",
        "project_metadata",
    }
    if require_evidence_id:
        required.add("artifact_evidence_id")
    _require(required <= set(artifact), f"eval artifact is missing required fields: {sorted(required - set(artifact))}")

    _require(artifact["schema"] == EVAL_ARTIFACT_SCHEMA, "eval artifact schema is unsupported")
    _string(artifact["run_id"], "eval artifact.run_id")
    _string(artifact["case"], "eval artifact.case")
    _integer(artifact["iteration"], "eval artifact.iteration", minimum=1)
    _require(artifact["lane"] in LANES, "eval artifact.lane is unsupported")
    _require(artifact["classification"] in CLASSIFICATIONS, "eval artifact.classification is unsupported")
    _validate_timing(artifact["timing"], "eval artifact.timing")
    _validate_target(artifact["target"], "eval artifact.target")

    checks = _array(artifact["deterministic_checks"], "eval artifact.deterministic_checks")
    for index, check in enumerate(checks):
        _object(check, f"eval artifact.deterministic_checks[{index}]")
        _strict_json_value(check, f"eval artifact.deterministic_checks[{index}]")

    _validate_judge(artifact["judge"], "eval artifact.judge")
    metadata = _object(artifact["project_metadata"], "eval artifact.project_metadata")
    _strict_json_value(metadata, "eval artifact.project_metadata")

    if require_evidence_id:
        evidence_id = artifact["artifact_evidence_id"]
        _require(
            type(evidence_id) is str and _SHA256_HEX.fullmatch(evidence_id) is not None,
            "eval artifact.artifact_evidence_id must be a lowercase SHA-256 hex digest",
        )
    return artifact


def calculate_artifact_evidence_id(value: Mapping[str, Any]) -> str:
    """Calculate the artifact integrity ID, excluding the ID field itself."""
    artifact = _validate_eval_artifact_shape(dict(value), require_evidence_id=False)
    evidence = dict(artifact)
    evidence.pop("artifact_evidence_id", None)
    return hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()


def artifact_evidence_id(value: Mapping[str, Any]) -> str:
    """Compatibility-friendly name for calculating the artifact integrity ID."""
    return calculate_artifact_evidence_id(value)


def attach_artifact_evidence_id(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow artifact copy with a freshly calculated integrity ID."""
    artifact = dict(value)
    artifact.pop("artifact_evidence_id", None)
    artifact["artifact_evidence_id"] = calculate_artifact_evidence_id(artifact)
    return artifact


def verify_artifact_evidence_id(value: Any) -> dict[str, Any]:
    """Validate the artifact envelope and fail closed on integrity mismatch."""
    artifact = _validate_eval_artifact_shape(value, require_evidence_id=True)
    expected = calculate_artifact_evidence_id(artifact)
    _require(
        artifact["artifact_evidence_id"] == expected,
        "eval artifact artifact_evidence_id mismatch",
    )
    return artifact


def validate_eval_artifact(value: Any) -> dict[str, Any]:
    """Validate one complete eval-artifact/v1 object including its integrity ID."""
    return verify_artifact_evidence_id(value)


def validate_eval_run(value: Any) -> dict[str, Any]:
    """Validate the generic eval-run/v1 manifest/summary envelope."""
    run = _object(value, "eval run")
    _strict_json_value(run, "eval run")
    required = {
        "schema",
        "run_id",
        "created_at",
        "selection",
        "iterations",
        "concurrency",
        "jobs",
        "summary",
    }
    _require(required <= set(run), f"eval run is missing required fields: {sorted(required - set(run))}")
    _require(run["schema"] == EVAL_RUN_SCHEMA, "eval run schema is unsupported")
    _string(run["run_id"], "eval run.run_id")
    _string(run["created_at"], "eval run.created_at")

    selection = _object(run["selection"], "eval run.selection")
    _strict_json_value(selection, "eval run.selection")
    _integer(run["iterations"], "eval run.iterations", minimum=1)

    concurrency = _object(run["concurrency"], "eval run.concurrency")
    _strict_json_value(concurrency, "eval run.concurrency")
    for lane in ("standard", "runtime"):
        _require(lane in concurrency, f"eval run.concurrency.{lane} is required")
        _integer(concurrency[lane], f"eval run.concurrency.{lane}", minimum=0)

    jobs = _array(run["jobs"], "eval run.jobs")
    for index, job in enumerate(jobs):
        _strict_json_value(job, f"eval run.jobs[{index}]")

    summary = _object(run["summary"], "eval run.summary")
    _strict_json_value(summary, "eval run.summary")
    if "project_metadata" in run:
        metadata = _object(run["project_metadata"], "eval run.project_metadata")
        _strict_json_value(metadata, "eval run.project_metadata")
    return run


def _reject_json_constant(value: str) -> None:
    raise EvalArtifactError(f"JSON constant {value!r} is not permitted")


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvalArtifactError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _load_json(data: str | bytes, where: str) -> Any:
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvalArtifactError(f"{where} must be UTF-8 JSON") from exc
    _require(type(data) is str, f"{where} must be JSON text or UTF-8 bytes")
    try:
        return json.loads(
            data,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except EvalArtifactError:
        raise
    except json.JSONDecodeError as exc:
        raise EvalArtifactError(f"{where} contains invalid JSON: {exc}") from exc


def serialize_eval_artifact(value: Any) -> bytes:
    artifact = validate_eval_artifact(value)
    return canonical_json_bytes(artifact)


def deserialize_eval_artifact(data: str | bytes) -> dict[str, Any]:
    return validate_eval_artifact(_load_json(data, "eval artifact"))


def serialize_eval_run(value: Any) -> bytes:
    run = validate_eval_run(value)
    return canonical_json_bytes(run)


def deserialize_eval_run(data: str | bytes) -> dict[str, Any]:
    return validate_eval_run(_load_json(data, "eval run"))
