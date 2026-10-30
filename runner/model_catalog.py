"""Resolve and pin the catalog consumed by an OpenCode invocation."""
from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from container.evidence_safety import (
    MODEL_CATALOG_SOURCE_LIMIT,
    _json_source_credentials,
)

CATALOG_URL = "https://models.opencode.ai/api.json"
CATALOG_ENV = "OPENCODE_EVAL_RUNNER_MODELS"


def _valid_reasoning_option(option: object) -> bool:
    if not isinstance(option, dict) or not isinstance(option.get("type"), str):
        return False
    values = option.get("values")
    if option["type"] == "effort":
        if not isinstance(values, list) or not all(
            isinstance(value, str) or value is None for value in values
        ):
            return False
    elif "values" in option and (
        not isinstance(values, list)
        or not all(isinstance(value, str) or value is None for value in values)
    ):
        return False
    return all(
        field not in option
        or isinstance(option[field], (int, float)) and not isinstance(option[field], bool)
        for field in ("min", "max")
    )


def _validate_catalog(path: Path) -> None:
    if not _json_source_credentials(path, set(), max_bytes=MODEL_CATALOG_SOURCE_LIMIT):
        raise ValueError(
            f"model catalog must be valid JSON within {MODEL_CATALOG_SOURCE_LIMIT} bytes"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"model catalog is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError("model catalog must be an object")
    for provider_id, provider in value.items():
        if not isinstance(provider_id, str) or not provider_id or not isinstance(provider, dict):
            raise TypeError("model catalog providers must be named objects")
        if not isinstance(provider.get("id"), str) or not isinstance(provider.get("name"), str):
            raise TypeError(f"model catalog provider {provider_id!r} requires string id and name")
        if not isinstance(provider.get("env"), list) or not all(isinstance(item, str) for item in provider["env"]):
            raise TypeError(f"model catalog provider {provider_id!r} requires an env string list")
        if not isinstance(provider.get("npm"), str):
            raise TypeError(f"model catalog provider {provider_id!r} requires a string npm package")
        models = provider.get("models")
        if not isinstance(models, dict):
            raise TypeError(f"model catalog provider {provider_id!r} requires a models object")
        for model_id, model in models.items():
            if not isinstance(model_id, str) or not model_id or not isinstance(model, dict):
                raise ValueError(f"model catalog provider {provider_id!r} has an invalid model")
            limit = model.get("limit")
            if not all(isinstance(model.get(field), str) for field in ("id", "name", "release_date")) or not isinstance(limit, dict):
                raise TypeError(
                    f"model catalog model {model_id!r} requires string id, name, release_date and limit object"
                )
            if not all(
                isinstance(limit.get(field), (int, float)) and not isinstance(limit.get(field), bool)
                for field in ("context", "output")
            ):
                raise ValueError(f"model catalog model {model_id!r} requires numeric context and output limits")
            options = model.get("reasoning_options", [])
            if not isinstance(options, list) or not all(map(_valid_reasoning_option, options)):
                raise ValueError(f"model catalog model {model_id!r} has invalid reasoning options")


@contextmanager
def pinned_model_catalog(explicit: str | Path | None = None) -> Iterator[Path]:
    """Yield a validated immutable-by-convention snapshot; precedence is explicit, env, fetch."""
    source = explicit or os.environ.get(CATALOG_ENV)
    with tempfile.TemporaryDirectory(prefix="opencode-model-catalog-") as tmp:
        snapshot = Path(tmp) / "models.json"
        if source:
            source_path = Path(source).expanduser()
            if not source_path.is_file():
                raise ValueError(f"model catalog source not found: {source_path}")
            if source_path.stat().st_size > MODEL_CATALOG_SOURCE_LIMIT:
                raise ValueError(f"model catalog exceeds {MODEL_CATALOG_SOURCE_LIMIT} bytes")
            with source_path.open("rb") as source_file, snapshot.open("wb") as output:
                total = 0
                while chunk := source_file.read(64 * 1024):
                    total += len(chunk)
                    if total > MODEL_CATALOG_SOURCE_LIMIT:
                        raise ValueError(f"model catalog exceeds {MODEL_CATALOG_SOURCE_LIMIT} bytes")
                    output.write(chunk)
        else:
            request = urllib.request.Request(
                CATALOG_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "opencode-eval-runner/1",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response, snapshot.open("wb") as output:
                total = 0
                while chunk := response.read(64 * 1024):
                    total += len(chunk)
                    if total > MODEL_CATALOG_SOURCE_LIMIT:
                        raise ValueError(f"model catalog exceeds {MODEL_CATALOG_SOURCE_LIMIT} bytes")
                    output.write(chunk)
        _validate_catalog(snapshot)
        snapshot.chmod(0o444)
        yield snapshot
