"""Persistence, schema validation, and integrity for generic eval artifacts.

This module owns the Task 3 artifact surface: run-directory ownership, stable
paths, atomic persistence, versioned envelopes, and integrity verification. It
must not interpret project metadata, behavioral checks, or runtime evidence.
"""
from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from container.runtime_evidence import RuntimeEvidenceError, validate_runtime_evidence
from runner.eval_compare import validate_comparison_result_envelope
from runner.eval_types import ArtifactIdentity, EvalJob, JsonValue, RunPlan


EVAL_RUN_SCHEMA = "opencode-eval-runner/eval-run/v1"
EVAL_ARTIFACT_SCHEMA = "opencode-eval-runner/eval-artifact/v1"
EVAL_PAIRED_ARTIFACT_SCHEMA = "opencode-eval-runner/eval-paired-artifact/v1"
EVAL_PAIR_IDENTITY_SCHEMA = "opencode-eval-runner/eval-pair-identity/v1"
RUNNER_RESULT_SCHEMA = "opencode-eval-runner/v1"

CLASSIFICATIONS = frozenset({"pass", "fail", "non-evidence"})
LANES = frozenset({"standard", "runtime"})
READINESS_STATUSES = frozenset({"ready", "incomplete", "unsupported", "invalid"})
FAILURE_PLANES = frozenset({"infrastructure", "product", "evidence"})
PAIRED_EXECUTION_MODES = frozenset({"sequential", "parallel"})
PAIRED_SIDES = ("baseline", "candidate")
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


def calculate_pair_id(run_id: str, case_id: str, iteration: int) -> str:
    """Return the stable identity shared by both sides of one paired eval."""

    _string(run_id, "paired identity.run_id")
    _string(case_id, "paired identity.case")
    _integer(iteration, "paired identity.iteration", minimum=1)
    identity = {
        "schema": EVAL_PAIR_IDENTITY_SCHEMA,
        "run_id": run_id,
        "case": case_id,
        "iteration": iteration,
    }
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def _validate_paired_execution_policy(value: Any, where: str) -> dict[str, Any]:
    policy = _object(value, where)
    _strict_json_value(policy, where)
    required = {"mode", "order"}
    _require(
        required <= set(policy),
        f"{where} is missing required fields: {sorted(required - set(policy))}",
    )
    _require(policy["mode"] in PAIRED_EXECUTION_MODES, f"{where}.mode is unsupported")
    order = _array(policy["order"], f"{where}.order")
    _require(
        len(order) == 2 and set(order) == set(PAIRED_SIDES),
        f"{where}.order must contain baseline and candidate exactly once",
    )
    return policy


def _validate_paired_eval_artifact_shape(
    value: Any,
    *,
    require_evidence_id: bool,
) -> dict[str, Any]:
    artifact = _object(value, "paired eval artifact")
    _strict_json_value(artifact, "paired eval artifact")
    required = {
        "schema",
        "run_id",
        "case",
        "iteration",
        "pair_id",
        "execution_policy",
        "sides",
    }
    if require_evidence_id:
        required.add("paired_artifact_evidence_id")
    _require(
        required <= set(artifact),
        "paired eval artifact is missing required fields: "
        f"{sorted(required - set(artifact))}",
    )

    _require(
        artifact["schema"] == EVAL_PAIRED_ARTIFACT_SCHEMA,
        "paired eval artifact schema is unsupported",
    )
    run_id = _string(artifact["run_id"], "paired eval artifact.run_id")
    case_id = _string(artifact["case"], "paired eval artifact.case")
    iteration = _integer(
        artifact["iteration"],
        "paired eval artifact.iteration",
        minimum=1,
    )
    expected_pair_id = calculate_pair_id(run_id, case_id, iteration)
    _require(
        artifact["pair_id"] == expected_pair_id,
        "paired eval artifact pair_id does not match run/case/iteration identity",
    )
    _validate_paired_execution_policy(
        artifact["execution_policy"],
        "paired eval artifact.execution_policy",
    )

    sides = _object(artifact["sides"], "paired eval artifact.sides")
    _require(
        set(sides) == set(PAIRED_SIDES),
        "paired eval artifact.sides must contain exactly baseline and candidate",
    )
    expected_identity = (run_id, case_id, iteration)
    for side in PAIRED_SIDES:
        nested = validate_eval_artifact(sides[side])
        actual_identity = (
            nested["run_id"],
            nested["case"],
            nested["iteration"],
        )
        _require(
            actual_identity == expected_identity,
            f"paired eval artifact side {side!r} identity does not match pair identity",
        )

    if "comparison" in artifact:
        try:
            validate_comparison_result_envelope(
                artifact["comparison"],
                baseline_classification=sides["baseline"]["classification"],
                candidate_classification=sides["candidate"]["classification"],
            )
        except (TypeError, ValueError) as exc:
            raise EvalArtifactError(f"paired eval artifact.comparison: {exc}") from exc

    if require_evidence_id:
        evidence_id = artifact["paired_artifact_evidence_id"]
        _require(
            type(evidence_id) is str
            and _SHA256_HEX.fullmatch(evidence_id) is not None,
            "paired eval artifact.paired_artifact_evidence_id must be a lowercase "
            "SHA-256 hex digest",
        )
    return artifact


def calculate_paired_artifact_evidence_id(value: Mapping[str, Any]) -> str:
    """Calculate paired-artifact integrity without altering either side."""

    artifact = _validate_paired_eval_artifact_shape(
        dict(value),
        require_evidence_id=False,
    )
    evidence = dict(artifact)
    evidence.pop("paired_artifact_evidence_id", None)
    return hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()


def attach_paired_artifact_evidence_id(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a paired artifact with a fresh top-level integrity identifier."""

    artifact = dict(value)
    artifact.pop("paired_artifact_evidence_id", None)
    artifact["paired_artifact_evidence_id"] = calculate_paired_artifact_evidence_id(
        artifact
    )
    return artifact


def validate_paired_eval_artifact(value: Any) -> dict[str, Any]:
    """Validate both side artifacts, paired identity, policy, and integrity."""

    artifact = _validate_paired_eval_artifact_shape(
        value,
        require_evidence_id=True,
    )
    expected = calculate_paired_artifact_evidence_id(artifact)
    _require(
        artifact["paired_artifact_evidence_id"] == expected,
        "paired eval artifact paired_artifact_evidence_id mismatch",
    )
    return artifact


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


def serialize_paired_eval_artifact(value: Any) -> bytes:
    artifact = validate_paired_eval_artifact(value)
    return canonical_json_bytes(artifact)


def deserialize_paired_eval_artifact(data: str | bytes) -> dict[str, Any]:
    return validate_paired_eval_artifact(_load_json(data, "paired eval artifact"))


def serialize_eval_run(value: Any) -> bytes:
    run = validate_eval_run(value)
    return canonical_json_bytes(run)


def deserialize_eval_run(data: str | bytes) -> dict[str, Any]:
    return validate_eval_run(_load_json(data, "eval run"))


# Filesystem storage ---------------------------------------------------------

_OWNER_FILE = ".eval-run-owner.json"
_RUN_MANIFEST_FILE = "run.json"
_JOBS_DIR = "jobs"
_PAIRS_DIR = "pairs"
_MAX_CASE_COMPONENT_BYTES = 200


class EvalArtifactStorageError(EvalArtifactError):
    """Raised when artifact storage cannot be used safely."""


def _validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not run_id:
        raise EvalArtifactStorageError("run_id must be a non-empty string")
    return run_id


def _validate_identity(identity: ArtifactIdentity) -> None:
    _validate_run_id(identity.run_id)
    if not isinstance(identity.case_id, str) or not identity.case_id:
        raise EvalArtifactStorageError("case_id must be a non-empty string")
    if (
        isinstance(identity.iteration, bool)
        or not isinstance(identity.iteration, int)
        or identity.iteration < 1
    ):
        raise EvalArtifactStorageError("iteration must be an integer >= 1")


def artifact_identity_for_job(run_id: str, job: EvalJob) -> ArtifactIdentity:
    """Build the storage identity for a planned job without mutating it."""
    identity = ArtifactIdentity(
        run_id=_validate_run_id(run_id),
        case_id=job.case.id,
        iteration=job.iteration,
    )
    _validate_identity(identity)
    return identity


def _case_component(case_id: str) -> str:
    """Return a stable, single-component representation of a case ID."""
    if not isinstance(case_id, str) or not case_id:
        raise EvalArtifactStorageError("case_id must be a non-empty string")
    encoded = "case-" + quote(case_id, safe="")
    if len(encoded.encode("utf-8")) > _MAX_CASE_COMPONENT_BYTES:
        raise EvalArtifactStorageError("case_id is too long for a safe artifact path")
    return encoded


def _owner_payload(run_id: str) -> str:
    return json.dumps({"run_id": run_id}, ensure_ascii=False, separators=(",", ":")) + "\n"


def _read_owner(owner_path: Path) -> str:
    if owner_path.is_symlink():
        raise EvalArtifactStorageError(
            f"artifact-directory ownership claim is a symlink: {owner_path}"
        )
    try:
        raw = owner_path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalArtifactStorageError(
            f"cannot read artifact-directory ownership claim {owner_path}: {exc}"
        ) from exc
    run_id = value.get("run_id") if isinstance(value, dict) else None
    if not isinstance(run_id, str) or not run_id:
        raise EvalArtifactStorageError(
            f"artifact-directory ownership claim {owner_path} is malformed"
        )
    return run_id


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync after an atomic replace."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
                raise
    finally:
        os.close(fd)


@dataclass(frozen=True)
class RunArtifactStore:
    """Claimed filesystem storage for one eval run."""

    root: Path
    run_id: str

    @property
    def owner_path(self) -> Path:
        return self.root / _OWNER_FILE

    @property
    def run_manifest_path(self) -> Path:
        return self.root / _RUN_MANIFEST_FILE

    def _assert_owned(self) -> None:
        current = _read_owner(self.owner_path)
        if current != self.run_id:
            raise EvalArtifactStorageError(
                f"artifact directory {self.root} is claimed by run {current!r}, "
                f"not current run {self.run_id!r}"
            )

    def _assert_identity(self, identity: ArtifactIdentity) -> None:
        _validate_identity(identity)
        if identity.run_id != self.run_id:
            raise EvalArtifactStorageError(
                f"artifact identity belongs to run {identity.run_id!r}, "
                f"not current run {self.run_id!r}"
            )

    def job_relative_path(self, identity: ArtifactIdentity) -> Path:
        """Return the stable path of one case/iteration relative to the run root."""
        self._assert_identity(identity)
        return (
            Path(_JOBS_DIR)
            / _case_component(identity.case_id)
            / f"iteration-{identity.iteration}.json"
        )

    def job_path(self, identity: ArtifactIdentity) -> Path:
        return self.root / self.job_relative_path(identity)

    def job_path_for(self, job: EvalJob) -> Path:
        return self.job_path(artifact_identity_for_job(self.run_id, job))

    def paired_job_relative_path(self, identity: ArtifactIdentity) -> Path:
        """Return the stable path of one paired case/iteration artifact."""
        self._assert_identity(identity)
        return (
            Path(_PAIRS_DIR)
            / _case_component(identity.case_id)
            / f"iteration-{identity.iteration}.json"
        )

    def paired_job_path(self, identity: ArtifactIdentity) -> Path:
        return self.root / self.paired_job_relative_path(identity)

    def manifest_job_paths(self, plan: RunPlan) -> tuple[str, ...]:
        """Return portable per-job relative paths for run-manifest plumbing."""
        if plan.run_id != self.run_id:
            raise EvalArtifactStorageError(
                f"run plan belongs to run {plan.run_id!r}, not {self.run_id!r}"
            )
        return tuple(
            self.job_relative_path(artifact_identity_for_job(self.run_id, job)).as_posix()
            for job in plan.jobs
        )

    def _prepare_parent(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise EvalArtifactStorageError(
                f"artifact path escapes run directory: {path}"
            ) from exc
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            root_resolved = self.root.resolve(strict=True)
            parent_resolved = path.parent.resolve(strict=True)
            parent_resolved.relative_to(root_resolved)
        except (OSError, ValueError) as exc:
            raise EvalArtifactStorageError(
                f"unsafe artifact parent for {path}: {exc}"
            ) from exc

    def _atomic_write_json(self, path: Path, value: JsonValue) -> None:
        self._assert_owned()
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ) + "\n"
        except (TypeError, ValueError) as exc:
            raise EvalArtifactStorageError(f"artifact is not valid JSON: {exc}") from exc

        self._prepare_parent(path)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temp_name = stream.name
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
            temp_name = None
            _fsync_directory(path.parent)
        except OSError as exc:
            raise EvalArtifactStorageError(
                f"cannot atomically write artifact {path}: {exc}"
            ) from exc
        finally:
            if temp_name is not None:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass

    def _read_json(self, path: Path) -> JsonValue:
        self._assert_owned()
        if path.is_symlink():
            raise EvalArtifactStorageError(f"artifact path is a symlink: {path}")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root.resolve(strict=True))
            raw = path.read_text(encoding="utf-8")
            return _load_json(raw, f"artifact {path}")
        except EvalArtifactError as exc:
            raise EvalArtifactStorageError(f"cannot read artifact {path}: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise EvalArtifactStorageError(f"cannot read artifact {path}: {exc}") from exc

    def write_run_manifest(self, manifest: JsonValue) -> None:
        """Validate and atomically persist one eval-run/v1 manifest."""
        validated = validate_eval_run(manifest)
        if validated["run_id"] != self.run_id:
            raise EvalArtifactStorageError(
                f"run manifest belongs to run {validated['run_id']!r}, "
                f"not current run {self.run_id!r}"
            )
        self._atomic_write_json(self.run_manifest_path, validated)

    def read_run_manifest(self) -> dict[str, Any]:
        """Re-read and validate the durable eval-run/v1 manifest."""
        manifest = validate_eval_run(self._read_json(self.run_manifest_path))
        if manifest["run_id"] != self.run_id:
            raise EvalArtifactStorageError(
                f"run manifest belongs to run {manifest['run_id']!r}, "
                f"not current run {self.run_id!r}"
            )
        return manifest

    def write_job_artifact(self, identity: ArtifactIdentity, artifact: JsonValue) -> None:
        """Validate, verify, and atomically persist one eval-artifact/v1 object."""
        self._assert_identity(identity)
        validated = validate_eval_artifact(artifact)
        actual = (
            validated["run_id"],
            validated["case"],
            validated["iteration"],
        )
        expected = (identity.run_id, identity.case_id, identity.iteration)
        if actual != expected:
            raise EvalArtifactStorageError(
                f"artifact identity {actual!r} does not match storage identity {expected!r}"
            )
        self._atomic_write_json(self.job_path(identity), validated)

    def read_job_artifact(self, identity: ArtifactIdentity) -> dict[str, Any]:
        """Re-read and verify the durable eval-artifact/v1 object."""
        self._assert_identity(identity)
        artifact = validate_eval_artifact(self._read_json(self.job_path(identity)))
        actual = (artifact["run_id"], artifact["case"], artifact["iteration"])
        expected = (identity.run_id, identity.case_id, identity.iteration)
        if actual != expected:
            raise EvalArtifactStorageError(
                f"artifact identity {actual!r} does not match storage identity {expected!r}"
            )
        return artifact

    def write_paired_job_artifact(
        self,
        identity: ArtifactIdentity,
        artifact: JsonValue,
    ) -> None:
        """Validate and atomically persist one eval-paired-artifact/v1 object."""
        self._assert_identity(identity)
        validated = validate_paired_eval_artifact(artifact)
        actual = (
            validated["run_id"],
            validated["case"],
            validated["iteration"],
        )
        expected = (identity.run_id, identity.case_id, identity.iteration)
        if actual != expected:
            raise EvalArtifactStorageError(
                f"paired artifact identity {actual!r} does not match storage "
                f"identity {expected!r}"
            )
        self._atomic_write_json(self.paired_job_path(identity), validated)

    def read_paired_job_artifact(
        self,
        identity: ArtifactIdentity,
    ) -> dict[str, Any]:
        """Re-read and verify one durable eval-paired-artifact/v1 object."""
        self._assert_identity(identity)
        artifact = validate_paired_eval_artifact(
            self._read_json(self.paired_job_path(identity))
        )
        actual = (artifact["run_id"], artifact["case"], artifact["iteration"])
        expected = (identity.run_id, identity.case_id, identity.iteration)
        if actual != expected:
            raise EvalArtifactStorageError(
                f"paired artifact identity {actual!r} does not match storage "
                f"identity {expected!r}"
            )
        return artifact


def claim_run_artifact_directory(
    artifact_dir: str | os.PathLike[str], run_id: str
) -> RunArtifactStore:
    """Create or safely claim an artifact directory for exactly one run.

    A fresh directory must be empty. A directory already claimed by the same
    run can be reopened for resumption. Conflicting, malformed, or unowned
    non-empty directories fail closed.
    """
    run_id = _validate_run_id(run_id)
    root = Path(artifact_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EvalArtifactStorageError(
            f"cannot create artifact directory {root}: {exc}"
        ) from exc
    if not root.is_dir():
        raise EvalArtifactStorageError(f"artifact path is not a directory: {root}")

    root = root.resolve(strict=True)
    owner = root / _OWNER_FILE
    try:
        fd = os.open(owner, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing_run = _read_owner(owner)
        if existing_run != run_id:
            raise EvalArtifactStorageError(
                f"artifact directory {root} is claimed by run {existing_run!r}, "
                f"not current run {run_id!r}"
            )
        return RunArtifactStore(root=root, run_id=run_id)
    except OSError as exc:
        raise EvalArtifactStorageError(
            f"cannot claim artifact directory {root}: {exc}"
        ) from exc

    try:
        stale_entries = sorted(item.name for item in root.iterdir() if item != owner)
        if stale_entries:
            raise EvalArtifactStorageError(
                f"artifact directory {root} is non-empty and has no compatible ownership "
                f"claim; existing entries: {stale_entries[:20]}"
            )
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(_owner_payload(run_id))
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(root)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            owner.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return RunArtifactStore(root=root, run_id=run_id)
