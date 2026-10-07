"""Filesystem storage for generic eval artifacts.

This module owns artifact paths, run-directory ownership, and durable JSON
reads/writes. Artifact schemas, semantic validation, and integrity IDs belong
to the sibling integrity layer.
"""
from __future__ import annotations

import errno
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from runner.eval_artifacts import EvalArtifactError
from runner.eval_types import ArtifactIdentity, EvalJob, JsonValue, RunPlan


_OWNER_FILE = ".eval-run-owner.json"
_RUN_MANIFEST_FILE = "run.json"
_JOBS_DIR = "jobs"
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
            return json.loads(raw)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise EvalArtifactStorageError(f"cannot read artifact {path}: {exc}") from exc

    def write_run_manifest(self, manifest: JsonValue) -> None:
        """Atomically persist the run manifest without rewriting its contents."""
        self._atomic_write_json(self.run_manifest_path, manifest)

    def read_run_manifest(self) -> JsonValue:
        return self._read_json(self.run_manifest_path)

    def write_job_artifact(self, identity: ArtifactIdentity, artifact: JsonValue) -> None:
        """Atomically persist one per-job artifact without semantic mutation."""
        self._assert_identity(identity)
        self._atomic_write_json(self.job_path(identity), artifact)

    def read_job_artifact(self, identity: ArtifactIdentity) -> JsonValue:
        self._assert_identity(identity)
        return self._read_json(self.job_path(identity))


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
