#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import selectors
import subprocess
import sys
import tempfile
import threading
import time
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
            "title": "TRUST-001 remote-context preflight",
            "location": {"directory": "/workspace"},
        },
        timeout=10,
        authorization=auth,
    )
    session = created.get("data", created)
    _standalone_json_request(
        base,
        f"/api/session/{session['id']}/prompt",
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
    tools = _standalone_json_request(
        base,
        "/experimental/tool/ids?location%5Bdirectory%5D=%2Fworkspace",
        timeout=10,
        authorization=auth,
    )
    print(json.dumps({"plugins": plugins, "tools": tools}, separators=(",", ":")), flush=True)
    print("TRUST001_CONTAINER_READY", flush=True)
    sys.stdin.readline()
finally:
    _stop_preflight_server(server)
"""


def wait_for_marker(stream, marker: str, timeout: float) -> list[str]:
    selector = selectors.DefaultSelector()
    selector.register(stream, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    lines: list[str] = []
    try:
        while time.monotonic() < deadline:
            events = selector.select(max(0.1, deadline - time.monotonic()))
            if not events:
                continue
            line = stream.readline()
            if line == "":
                raise RuntimeError(f"{marker} stream closed before readiness")
            lines.append(line.rstrip("\n"))
            if marker in line:
                return lines
    finally:
        selector.close()
    raise RuntimeError(f"{marker} readiness timeout")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    generation = "b" * 64
    with tempfile.TemporaryDirectory(prefix="trust001-remote-context-") as tmp:
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

            isolated_env = dict(os.environ)
            isolated_env.update({
                "TRUST001_GENERATION": generation,
                "TRUST001_CAPABILITY_SOCKET": str(paths["capability_loom"]),
                "TRUST001_LOOM_ENTRYPOINT": str(ROOT / "trust001" / "synthetic-remote-plugin.mjs"),
            })
            isolated = subprocess.Popen(
                ["node", str(ROOT / "trust001" / "isolated-host.mjs")],
                cwd=ROOT,
                env=isolated_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            result_box: queue.Queue[object] = queue.Queue()
            close_request = threading.Event()

            def run_channels() -> None:
                try:
                    admitted = channels.admit(
                        bridge_uid=os.getuid(),
                        bridge_gid=os.getgid(),
                        loom_uid=os.getuid(),
                        loom_gid=os.getgid(),
                        timeout=30,
                    )
                    stop, errors, threads = admitted.capability.serve()
                    if not close_request.wait(30):
                        raise RuntimeError("trusted close was not requested")
                    admitted.evidence.request_close()
                    while not admitted.evidence.ledger.sealed:
                        admitted.evidence.receive_once()
                    stop.wait(10)
                    for thread in threads:
                        thread.join(2)
                    if not errors.empty():
                        raise errors.get_nowait()
                    result_box.put({
                        "complete": admitted.evidence.ledger.complete,
                        "observations": admitted.evidence.ledger.observations,
                        "router_failed": admitted.capability.router.failed,
                        "host_outstanding": len(admitted.capability.router.host_calls.outstanding),
                        "callback_outstanding": len(admitted.capability.router.callbacks.outstanding),
                    })
                    admitted.evidence.channel.sock.close()
                except BaseException as exc:
                    result_box.put(exc)

            channel_thread = threading.Thread(target=run_channels, daemon=True)
            channel_thread.start()

            uid = str(os.getuid())
            gid = str(os.getgid())
            command = [
                "docker", "run", "--rm", "-i",
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
                "--entrypoint", "python3",
                args.image,
                "-c", container_script(),
            ]
            proc = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            if proc.stdout is None or proc.stdin is None or isolated.stdout is None:
                raise RuntimeError("preflight process pipes unavailable")

            container_lines = wait_for_marker(proc.stdout, "TRUST001_CONTAINER_READY", 30)
            isolated_lines = wait_for_marker(isolated.stdout, "TRUST001_READY", 30)
            close_request.set()

            channel_thread.join(15)
            if channel_thread.is_alive():
                isolated.terminate()
                isolated.communicate(timeout=5)
                proc.terminate()
                proc.communicate(timeout=5)
                raise RuntimeError("channel service did not terminate")
            outcome = result_box.get_nowait()
            if isinstance(outcome, BaseException):
                isolated.terminate()
                isolated.communicate(timeout=5)
                proc.terminate()
                proc.communicate(timeout=5)
                raise outcome

            proc.stdin.write("\n")
            proc.stdin.flush()
            remaining_out, remaining_err = proc.communicate(timeout=10)
            container_output = "\n".join(container_lines) + "\n" + remaining_out

            fenced = False
            try:
                remaining_isolated_out, isolated_err = isolated.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                fenced = True
                isolated.terminate()
                remaining_isolated_out, isolated_err = isolated.communicate(timeout=5)
            isolated_out = "\n".join(isolated_lines) + "\n" + remaining_isolated_out

            if proc.returncode != 0:
                raise RuntimeError(f"remote-context OpenCode preflight failed: exit={proc.returncode}")
            if isolated.returncode not in (0, -15):
                raise RuntimeError("isolated remote context failed")
            if "TRUST001_READY" not in isolated_out:
                raise RuntimeError("isolated remote context did not become ready")

            json_line = next((line for line in container_lines if line.startswith("{")), None)
            if json_line is None:
                raise RuntimeError("container preflight payload missing")
            payload = json.loads(json_line)
            plugins = payload["plugins"]
            ids = {item.get("id") for item in plugins if isinstance(item, dict)}
            if "loom" not in ids or "hostile" in ids:
                raise RuntimeError(f"unexpected plugin inventory: {sorted(str(x) for x in ids)}")
            if not outcome["complete"] or outcome["router_failed"]:
                raise RuntimeError("remote-context generation did not close cleanly")
            if outcome["host_outstanding"] or outcome["callback_outstanding"]:
                raise RuntimeError("remote-context generation closed with outstanding requests")

            kinds = [
                item.get("type")
                for item in outcome["observations"]
                if isinstance(item, dict)
            ]
            if "bridge.activated" not in kinds:
                raise RuntimeError("bridge activation observation missing")

            print(json.dumps({
                "schema": "trust001-remote-context-preflight/v1",
                "passed": True,
                "generation": generation,
                "plugin_ids": sorted(str(x) for x in ids if x),
                "isolated_ready": True,
                "isolated_fenced_after_seal": fenced,
                "evidence_complete": True,
                "router_failed": False,
                "project_config_disabled": manifest["project_config_disabled"],
                "provider_inference": False,
                "network": "none",
            }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
