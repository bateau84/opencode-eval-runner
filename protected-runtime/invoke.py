"""Trusted supervisor: fixed config/code, loopback deterministic provider.

Only this container sees /capture. Tool code runs in another container, never as
an in-process plugin. Raw OpenCode stdout/stderr are held in memory and discarded.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROFILE = "codemode-inner/direct-session/v1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect_refused", headers, fp)


def health_check(url):
    # A target-controlled /health response must not redirect into runtime services.
    with urllib.request.build_opener(NoRedirect).open(url, timeout=1) as response:
        return response.status == 200


def safe_output(value, policy):
    """Script diagnostics follow the same redact-before-retain rule as capture."""
    if not isinstance(value, str):
        return {"state": "omitted", "reason": "not_observed"}
    secrets = {form for raw in policy["secrets"] for form in
               (raw, base64.b64encode(raw.encode()).decode(), raw.encode().hex(), urllib.parse.quote(raw, safe="~()*!.'-"))}
    safe = value
    for secret in sorted(secrets, key=len, reverse=True):
        safe = safe.replace(secret, "[REDACTED]")
    if safe not in policy["allowed_values"]:
        return {"state": "omitted", "reason": "policy_omission"}
    if len(safe.encode()) > 16384:
        return {"state": "truncated", "reason": "field_limit"}
    return {"state": "available" if safe == value else "redacted", "value": safe}


def main():
    request = json.loads(Path("/input/request.json").read_text())
    policy_raw = Path("/input/policy.json").read_bytes()
    if hashlib.sha256(policy_raw).hexdigest() != request["policy_id"]:
        raise ValueError("policy_mismatch")
    launch_raw = Path("/input/launch.json").read_bytes()
    if hashlib.sha256(launch_raw).hexdigest() != request["launch_id"]:
        raise ValueError("launch_mismatch")
    launch = json.loads(launch_raw)
    tools_raw = Path("/input/tools.json").read_bytes()
    if (launch["run_id"] != request["run_id"] or launch["profile"] != PROFILE
            or launch["program_sha256"] != hashlib.sha256(request["program"].encode()).hexdigest()
            or launch["tools_sha256"] != hashlib.sha256(tools_raw).hexdigest()
            or json.loads(tools_raw) != request["tools"] or launch["policy_sha256"] != request["policy_id"]):
        raise ValueError("launch_inputs_mismatch")
    version = subprocess.run(["opencode", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if version != "opencode v2.0.18-eval.2":
        raise ValueError("protected_runtime_version_required")
    for attempt in range(100):
        try:
            if health_check(request["tool_url"] + "/health"):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise ValueError("isolated_tool_unavailable")
    stage, script_output = 0, {"state": "omitted", "reason": "not_observed"}
    policy = json.loads(policy_raw)

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            nonlocal stage, script_output
            length = int(self.headers.get("Content-Length", "0"))
            if not self.path.endswith("/chat/completions") or length > 4 * 1024 * 1024 or stage >= 4:
                self.send_error(400)
                return
            body = json.loads(self.rfile.read(length))
            if stage == 0:
                tool = {"index": 0, "id": "protected-execute", "type": "function",
                        "function": {"name": "execute", "arguments": json.dumps({"code": request["program"]})}}
                delta, finish = {"role": "assistant", "tool_calls": [tool]}, "tool_calls"
            else:
                # A behavior-test diagnostic only, never a source for inner values.
                messages = [m for m in body.get("messages", []) if m.get("role") == "tool"]
                if messages:
                    value = messages[-1].get("content")
                    script_output = safe_output(value, policy)
                delta, finish = {"role": "assistant", "content": "capture-complete"}, "stop"
            stage += 1
            common = {"id": "protected-fixture-" + str(stage), "created": 1, "model": body["model"]}
            if body.get("stream"):
                chunks = [
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
                ]
                raw = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
                mime = "text/event-stream"
            else:
                raw = json.dumps({**common, "object": "chat.completion", "choices": [{"index": 0, "message": delta, "finish_reason": finish}]}).encode()
                mime = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    # Never copy ambient host config, credentials, plugin roots or database seeds.
    home = Path("/tmp/protected")
    for part in ("home", "config", "data", "state", "cache", "run"):
        (home / part).mkdir(parents=True, exist_ok=True)
    root = Path("/workspace")
    plugins = root / ".opencode/plugins"
    plugins.mkdir(parents=True)
    shutil.copyfile("/opt/protected/bridge.ts", plugins / "bridge.ts")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (root / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json", "model": "capture/mock", "enabled_providers": ["capture"],
        "provider": {"capture": {"npm": "@ai-sdk/openai-compatible", "name": "Local capture fixture",
            "options": {"baseURL": f"http://127.0.0.1:{server.server_port}/v1", "apiKey": "fixture"},
            "models": {"mock": {"name": "Mock", "limit": {"context": 1000000, "output": 32768}}}}},
    }))
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home / "home"),
           "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "data"),
           "XDG_STATE_HOME": str(home / "state"), "XDG_CACHE_HOME": str(home / "cache"),
           "XDG_RUNTIME_DIR": str(home / "run"), "OPENCODE_DISABLE_AUTOUPDATE": "1",
           "OPENCODE_EVAL_OBSERVATIONS": "1" if request["observe"] else "0", "OPENCODE_EVAL_PROTECTED_CHANNEL": "1", "OPENCODE_DB": "opencode.db"}
    runtime_exit, exited = 124, False
    proc = subprocess.Popen(["opencode", "run", "--standalone", "--format", "json", "--auto",
                             "--title", "protected capture", "--model", "capture/mock", "Run the prescribed capture program."],
                            cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        proc.communicate(timeout=50)
        runtime_exit = proc.returncode
        # The leader exiting alone is not a drain proof if children still hold state.
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            exited = True
        if not exited:
            os.killpg(proc.pid, signal.SIGKILL)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate(timeout=5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    path = Path("/capture/events.jsonl")
    if request["observe"] and exited and runtime_exit == 0 and path.is_file() and not Path("/capture/fault").exists():
        raw = path.read_bytes()
        if len(raw) < 8 * 1024 * 1024 - 1024 and raw.endswith(b"\n"):
            # Seal only after the whole writer process group is gone. The importer
            # independently checks runtime sequence, parent accounting and terminals.
            lines = raw.splitlines()
            footer = {"kind": "capture_end", "run_id": request["run_id"], "seq": len(lines),
                      "event_count": len(lines) - 1, "sha256": hashlib.sha256(raw).hexdigest(),
                      "writer_exited": True, "runtime_exit": runtime_exit}
            with path.open("ab") as out:
                out.write((json.dumps(footer) + "\n").encode())
    # Host and container may have different UIDs. The host's mode-0700 temporary
    # parent provides privacy; only this runtime container receives the child mount.
    receipt = None
    if path.is_file():
        path.chmod(0o644)
        # Independent trusted control channel; not a hash accepted from this file.
        # The launcher checks this receipt against the received capture, so editing
        # records and recomputing the inline footer cannot conceal the alteration.
        sealed = path.read_bytes()
        if exited and len(sealed) <= 8 * 1024 * 1024:
            receipt = {"sha256": hashlib.sha256(sealed).hexdigest(), "bytes": len(sealed)}
    print(json.dumps({"profile": PROFILE, "run_id": request["run_id"], "launch_id": request["launch_id"],
                      "runtime_exit": runtime_exit, "writer_exited": exited,
                      "script_output": script_output, "receipt": receipt}))
    return 0 if exited and runtime_exit == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
