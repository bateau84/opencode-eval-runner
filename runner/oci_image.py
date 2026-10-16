"""Fail-closed, local-only validation for built-in OpenCode images."""
from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from urllib.parse import urlsplit

SUPPORTED_OPENCODE_VERSION = "2.0.23"
SUPPORTED_INVOKE_ADAPTER_ID = "opencode-eval-runner/opencode-invoke/v1"
IMAGE_VERSION_LABEL = "org.opencontainers.image.version"
IMAGE_ADAPTER_LABEL = "io.opencode-eval-runner.invoke-adapter"

_IMAGE_ID = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_DIGEST_REFERENCE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:([0-9a-f]{64})$")


class ImageSelectionError(ValueError):
    """A selected built-in image is not an approved local compatible image."""


def validate_immutable_image_identity(value: str | None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ImageSelectionError("built-in eval requires an immutable local OpenCode image identity")
    if _IMAGE_ID.fullmatch(value) or _DIGEST_REFERENCE.fullmatch(value):
        return value
    raise ImageSelectionError("built-in eval image identity must be a full image ID or digest-qualified reference")


def local_engine_prefix_and_environment(
    engine: str,
    host_environment: Mapping[str, str],
) -> tuple[list[str], dict[str, str]]:
    environment = dict(host_environment)
    if engine == "docker":
        configured_host = environment.get("DOCKER_HOST", "unix:///var/run/docker.sock")
        try:
            endpoint = urlsplit(configured_host)
        except ValueError as exc:
            raise ImageSelectionError("built-in eval requires a local Docker Unix socket") from exc
        if endpoint.scheme != "unix" or endpoint.netloc or not endpoint.path.startswith("/"):
            raise ImageSelectionError("built-in eval requires a local Docker Unix socket")
        for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            environment.pop(name, None)
        return [engine, "--host", configured_host], environment

    if engine == "podman":
        for name in ("CONTAINER_HOST", "CONTAINER_CONNECTION", "PODMAN_HOST"):
            environment.pop(name, None)
        return [engine, "--remote=false"], environment

    raise ImageSelectionError("built-in eval requires a supported local OCI engine")


def _image_record(stdout: str) -> Mapping[str, object]:
    try:
        decoded = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ImageSelectionError("built-in eval could not verify local image metadata") from exc
    if isinstance(decoded, list) and len(decoded) == 1:
        decoded = decoded[0]
    if not isinstance(decoded, Mapping):
        raise ImageSelectionError("built-in eval could not verify local image metadata")
    return decoded


def verify_local_opencode_image(
    engine: str,
    image: str,
    host_environment: Mapping[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Inspect only the local image store and enforce the runner release contract."""
    validate_immutable_image_identity(image)
    prefix, environment = local_engine_prefix_and_environment(engine, host_environment)
    try:
        process = subprocess.run(
            prefix + ["image", "inspect", "--format", "{{json .}}", image],
            env=environment,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ImageSelectionError("built-in eval could not inspect the selected local image") from exc
    if process.returncode != 0:
        raise ImageSelectionError("built-in eval image identity is not present in the local OCI engine")

    record = _image_record(process.stdout)
    selected_id = _IMAGE_ID.fullmatch(image)
    if selected_id:
        actual_id = record.get("Id")
        actual_id_match = _IMAGE_ID.fullmatch(actual_id) if isinstance(actual_id, str) else None
        identity_matches = actual_id_match is not None and actual_id_match.group(1) == selected_id.group(1)
    else:
        repo_digests = record.get("RepoDigests")
        selected_repository, selected_digest = image.rsplit("@", 1)
        selected_repository = _repository_without_tag(selected_repository)
        identity_matches = (
            isinstance(repo_digests, list)
            and any(
                isinstance(value, str)
                and value.rsplit("@", 1)[-1].lower() == selected_digest.lower()
                and _repository_without_tag(value.rsplit("@", 1)[0]).lower()
                == selected_repository.lower()
                for value in repo_digests
                if isinstance(value, str) and "@" in value
            )
        )
    if not identity_matches:
        raise ImageSelectionError("built-in eval image identity does not match local image metadata")

    config = record.get("Config")
    labels = config.get("Labels") if isinstance(config, Mapping) else None
    if not isinstance(labels, Mapping):
        raise ImageSelectionError("built-in eval image is missing runner compatibility metadata")
    if (
        labels.get(IMAGE_VERSION_LABEL) != SUPPORTED_OPENCODE_VERSION
        or labels.get(IMAGE_ADAPTER_LABEL) != SUPPORTED_INVOKE_ADAPTER_ID
    ):
        raise ImageSelectionError("built-in eval image is incompatible with this runner release")
    return prefix, environment


def _repository_without_tag(repository: str) -> str:
    final_segment = repository.rsplit("/", 1)[-1]
    if ":" not in final_segment:
        return repository
    return repository[: -len(final_segment)] + final_segment.split(":", 1)[0]
