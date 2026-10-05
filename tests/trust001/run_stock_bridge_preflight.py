#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runner.trust001.runtime import ChannelSet
from runner.trust001.source_closure import build_source_closure, verify_source_closure


def container_script() -> str:
    return r"""
import json
import os
import sys
sys.path.insert(0, "/opt/opencode-eval-runner")
from container.invoke import _start_preflight_server, _standalone_json_request, _stop_preflight_server

env = dict(os.environ)
server, base, auth = _start_preflight_server(env, 30)
try:
    created = _standalone_json_request(
        base,
        "/api/session",
        method="POST",
        payload={
            "title": "TRUST-001 provider-free activation",
            "location": {"directory": "/workspace"},
        },
        timeout=10,
        authorization=auth,
    )
    session = created.get("data", created)
    session_id = session["id"]
    _standalone_json_request(
        base,
        f"/api/session/{session_id}/prompt",
        method="POST",
        payload={"text": "activate plugins only", "resume": False},
        timeout=10,
        authorization=auth,
    )
    inventory = _standalone_json_request(
        base,
        "/api/plugin?location%5Bdirectory%5D=%2Fworkspace",
        timeout=10,
        authorization=auth,
    )
    plugins = inventory.get("data", inventory)
    print(json.dumps({"plugins": plugins}, separators=(",", ":")))
finally:
    _stop_preflight_server(server)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    generation = "a" * 64
    result_queue: queue.Queue[object] = queue.Queue()

    with tempfile.TemporaryDirectory(prefix="trust001-stock-preflight-") as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir()
        hostile = workspace / ".opencode" / "plugins"
        hostile.mkdir(parents=True)
        (hostile / "hostile.mjs").write_text(
            "throw new Error('workspace plugin escape loaded');\n"
            "export default { id: 'hostile', async setup() {} };\n",
            encoding="utf-8",
        )

        product_config = root / "product-config.json"
        product_config.write_text(
            json.dumps({
                "$schema": "https://opencode.ai/config.json",
                "model": "openai/preflight-no-inference",
            }) + "\n",
            encoding="utf-8",
        )
        closure = root / "trusted-config"
        manifest = build_source_closure(
            destination=closure,
            bridge_source=ROOT / "trust001" / "bridge.mjs",
            product_config=product_config,
        )
        verify_source_closure(closure, manifest)

        with ChannelSet(generation=generation) as channels:
            paths = channels.paths()
            roots = channels.mount_roots()

            peer_env = dict(os.environ)
            peer_env.update({
                "TRUST001_GENERATION": generation,
                "TRUST001_CAPABILITY_SOCKET": str(paths["capability_loom"]),
            })
            peer = subprocess.Popen(
                ["node", str(ROOT / "trust001" / "synthetic-loom-peer.mjs")],
                cwd=ROOT,
                env=peer_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            result_box: queue.Queue[object] = queue.Queue()

            def admit_and_relay() -> None:
                try:
                    admitted = channels.admit(
                        bridge_uid=os.getuid(),
                        bridge_gid=os.getgid(),
                        loom_uid=os.getuid(),
                        loom_gid=os.getgid(),
                        timeout=30,
                    )
                    admitted.capability.relay_bridge_once()
                    admitted.capability.relay_loom_once()
                    saw_preflight = False
                    while not saw_preflight:
                        message = admitted.evidence.receive_once()
                        payload = message.get("payload") if isinstance(message, dict) else None
                        if isinstance(payload, dict) and payload.get("type") == "capability.preflight":
                            saw_preflight = True
                    admitted.evidence.request_close()
                    while not admitted.evidence.ledger.sealed:
                        admitted.evidence.receive_once()
                    result_box.put({
                        "complete": admitted.evidence.ledger.complete,
                        "observations": admitted.evidence.ledger.observations,
                    })
                    admitted.capability.bridge.sock.close()
                    admitted.capability.loom.sock.close()
                    admitted.evidence.channel.sock.close()
                except BaseException as exc:
                    result_box.put(exc)

            relay = threading.Thread(target=admit_and_relay, daemon=True)
            relay.start()

            uid = str(os.getuid())
            gid = str(os.getgid())
            command = [
                "docker", "run", "--rm",
                "--network", "none",
                "--read-only",
                "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=256m",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--user", f"{uid}:{gid}",
                "--workdir", "/workspace",
                "--volume", f"{workspace}:/workspace:rw",
                "--volume", f"{closure}:/trusted-opencode-config:ro",
                "--volume", f"{roots['evidence']}:/run/trust001/evidence:rw",
                "--volume", f"{roots['capability_bridge']}:/run/trust001/capability:rw",
                "--env", "HOME=/tmp/home",
                "--env", "XDG_DATA_HOME=/tmp/data",
                "--env", "XDG_CACHE_HOME=/tmp/cache",
                "--env", "XDG_STATE_HOME=/tmp/state",
                "--env", "XDG_CONFIG_HOME=/tmp/config",
                "--env", "OPENCODE_CONFIG_DIR=/trusted-opencode-config",
                "--env", "OPENCODE_DISABLE_PROJECT_CONFIG=1",
                "--env", "OPENCODE_DISABLE_AUTOUPDATE=1",
                "--env", f"TRUST001_GENERATION={generation}",
                "--env", "TRUST001_EVIDENCE_SOCKET=/run/trust001/evidence/evidence.sock",
                "--env", "TRUST001_CAPABILITY_SOCKET=/run/trust001/capability/bridge.sock",
                "--env", "TRUST001_PREFLIGHT=1",
                "--entrypoint", "python3",
                args.image,
                "-c", container_script(),
            ]
            proc = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

            peer_out, peer_err = peer.communicate(timeout=10)
            relay.join(10)
            if relay.is_alive():
                raise RuntimeError("channel relay did not terminate")
            outcome = result_box.get_nowait()
            if isinstance(outcome, BaseException):
                raise outcome
            if proc.returncode != 0:
                raise RuntimeError(
                    f"stock OpenCode bridge preflight failed: exit={proc.returncode} "
                    f"stdout={proc.stdout!r} stderr={proc.stderr!r} peer={peer_err!r}"
                )
            if peer.returncode != 0:
                raise RuntimeError(f"synthetic Loom peer failed: {peer_err!r}")

            payload = json.loads(proc.stdout.strip().splitlines()[-1])
            plugins = payload["plugins"]
            ids = {item.get("id") for item in plugins if isinstance(item, dict)}
            if "loom" not in ids:
                raise RuntimeError(f"bridge not active: {sorted(str(x) for x in ids)}")
            if "hostile" in ids:
                raise RuntimeError("workspace plugin escaped source closure")
            if not outcome["complete"]:
                raise RuntimeError("evidence generation did not seal completely")
            kinds = [
                item.get("type")
                for item in outcome["observations"]
                if isinstance(item, dict)
            ]
            if "bridge.activated" not in kinds or "capability.preflight" not in kinds:
                raise RuntimeError(f"missing bridge observations: {kinds!r}")

            print(json.dumps({
                "schema": "trust001-stock-bridge-preflight/v1",
                "passed": True,
                "generation": generation,
                "plugin_ids": sorted(str(x) for x in ids if x),
                "observation_types": kinds,
                "project_config_disabled": manifest["project_config_disabled"],
                "external_plugin_declarations": manifest["external_plugin_declarations"],
                "provider_inference": False,
                "network": "none",
            }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
