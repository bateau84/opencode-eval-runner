#!/usr/bin/env python3
"""Exercise the real Podman image-preflight path without provider inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runner import safe_invoke


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    version = subprocess.run(
        ["podman", "--version"], capture_output=True, text=True, check=False, timeout=30
    )
    if version.returncode:
        raise SystemExit("podman unavailable")

    requested = args.image
    command = ["podman", "run", requested]
    loaded = safe_invoke.resolved_image(command)

    inspected = subprocess.run(
        ["podman", "image", "inspect", requested],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if inspected.returncode:
        raise SystemExit("podman inspect failed after resolved_image")
    info = json.loads(inspected.stdout)[0]
    raw_id = info.get("Id")
    canonical, execution_ref = safe_invoke.canonical_image_config_id(raw_id)

    exact = subprocess.run(
        ["podman", "image", "inspect", execution_ref],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if exact.returncode:
        raise SystemExit("podman cannot inspect exact execution config")
    exact_info = json.loads(exact.stdout)[0]
    exact_canonical, _ = safe_invoke.canonical_image_config_id(exact_info.get("Id"))

    checks = {
        "podman_available": version.returncode == 0,
        "requested_immutable_digest": "@sha256:" in requested,
        "canonical_image_config": loaded.get("image_config") == canonical,
        "canonical_has_sha256_prefix": canonical.startswith("sha256:") and len(canonical) == 71,
        "execution_ref_is_exact_inspected_id": command[-1] == execution_ref == raw_id,
        "execution_ref_is_content_addressed": execution_ref != requested,
        "exact_ref_reinspects_same_config": exact_canonical == canonical,
        "source_revision_is_pinned": isinstance(loaded.get("image_source_revision"), str)
            and len(loaded["image_source_revision"]) == 40,
        "initializer_hash_bound": isinstance(loaded.get("image_package_init_sha256"), str)
            and len(loaded["image_package_init_sha256"]) == 64,
        "module_hash_bound": isinstance(loaded.get("image_policy_module_sha256"), str)
            and len(loaded["image_policy_module_sha256"]) == 64,
        "invoke_hash_bound": isinstance(loaded.get("image_invoke_sha256"), str)
            and len(loaded["image_invoke_sha256"]) == 64,
    }

    report = {
        "schema": "opencode-eval-runner/podman-preflight-proof/v1",
        "podman_version": version.stdout.strip(),
        "image": requested,
        "raw_image_id": raw_id,
        "canonical_image_config": canonical,
        "execution_ref": execution_ref,
        "loaded": loaded,
        "checks": checks,
        "passed": all(checks.values()),
        "provider_inference": False,
    }
    (args.output / "podman-preflight.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
