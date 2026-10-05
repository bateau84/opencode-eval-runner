from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .protocol import ProtocolError, require

BRIDGE_ID = "trust001-bridge"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _plain_json_config(source: Path | None) -> dict[str, Any]:
    if source is None:
        return {"$schema": "https://opencode.ai/config.json"}
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("trust001_config_must_be_strict_json") from exc
    require(type(value) is dict, "trust001_config_not_object")
    # Candidate OpenCode may not consume product-selected external plugin
    # declarations. Loom is isolated and the bridge is runner-owned.
    require("plugin" not in value and "plugins" not in value, "external_plugin_declaration")
    return value


def build_source_closure(
    *,
    destination: Path,
    bridge_source: Path,
    product_config: Path | None = None,
) -> dict[str, Any]:
    require(bridge_source.is_file() and not bridge_source.is_symlink(), "invalid_bridge_source")
    if destination.exists():
        shutil.rmtree(destination)
    plugins = destination / "plugins"
    plugins.mkdir(parents=True, mode=0o700)

    config = _plain_json_config(product_config)
    config_path = destination / "opencode.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    bridge_path = plugins / f"{BRIDGE_ID}.ts"
    shutil.copyfile(bridge_source, bridge_path)

    for path in (config_path, bridge_path):
        path.chmod(0o444)
    plugins.chmod(0o555)
    destination.chmod(0o555)

    return {
        "schema": "opencode-eval-runner/trust001-plugin-source-closure/v1",
        "project_config_disabled": True,
        "external_plugin_declarations": False,
        "config": {
            "relative_path": "opencode.json",
            "sha256": sha256(config_path),
        },
        "plugins": [{
            "id": BRIDGE_ID,
            "relative_path": f"plugins/{BRIDGE_ID}.ts",
            "sha256": sha256(bridge_path),
        }],
        "expected_external_plugin_ids": [BRIDGE_ID],
    }


def verify_source_closure(root: Path, manifest: dict[str, Any]) -> None:
    require(manifest.get("schema") == "opencode-eval-runner/trust001-plugin-source-closure/v1",
            "invalid_closure_manifest")
    require(manifest.get("project_config_disabled") is True, "project_config_not_disabled")
    require(manifest.get("external_plugin_declarations") is False, "external_plugin_declaration")

    config = manifest.get("config")
    plugins = manifest.get("plugins")
    require(type(config) is dict and type(plugins) is list and len(plugins) == 1, "invalid_closure_manifest")
    expected = [
        (root / str(config.get("relative_path")), config.get("sha256")),
        (root / str(plugins[0].get("relative_path")), plugins[0].get("sha256")),
    ]
    for path, digest in expected:
        require(path.is_file() and not path.is_symlink(), "closure_path_changed")
        require(type(digest) is str and sha256(path) == digest, "closure_digest_changed")
        require(path.stat().st_mode & 0o222 == 0, "closure_path_writable")

    require(root.stat().st_mode & 0o222 == 0, "closure_root_writable")
    require((root / "plugins").stat().st_mode & 0o222 == 0, "closure_plugins_writable")
