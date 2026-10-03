#!/usr/bin/env python3
"""Provider-free compatibility proof for Loom's existing eval:live -> runner invoke path."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = 'return await tools.captureprobe.echo({tag:"same"});'

PLUGIN = r'''
import { appendFileSync } from "node:fs"
const path = "/workspace/runtime-observations.jsonl"
function log(channel: string, event: any) {
  appendFileSync(path, JSON.stringify({ channel, event }) + "\n")
}
export default {
  id: "eval-live-compat",
  async setup(ctx: any) {
    await ctx.tool.transform((editor: any) => {
      editor.namespace({ name: "captureprobe", description: "eval:live compatibility tools" })
      editor.add({
        name: "native", description: "native sentinel", input: { type: "object", properties: {}, additionalProperties: false },
        options: { namespace: "captureprobe", codemode: false },
        execute: async () => ({ content: "NATIVE-RAW\n" + "x".repeat(60000) }),
      })
      editor.add({
        name: "nativefail", description: "native failure sentinel", input: { type: "object", properties: {}, additionalProperties: false },
        options: { namespace: "captureprobe", codemode: false },
        execute: async () => { throw new Error("NATIVE-FAIL-RAW") },
      })
      editor.add({
        name: "echo", description: "Code Mode sentinel",
        input: { type: "object", properties: { tag: { type: "string" } }, additionalProperties: false },
        options: { namespace: "captureprobe", codemode: true },
        execute: async (input: any) => ({ content: input.tag === "same" ? "INNER-RAW" : "WRONG" }),
      })
    })
    await ctx.tool.hook("execute.native-observed", (event: any) => { log("native", event) })
    await ctx.tool.hook("execute.observed", (event: any) => { log("codemode", event) })
  },
}
'''


def read_jsonl(path: Path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def run(image: str, output: Path) -> int:
    if "@sha256:" not in image:
        raise ValueError("compatibility probe requires immutable image digest")
    output.mkdir(parents=True, exist_ok=True)
    requests = []
    stage = 0

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            nonlocal stage
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size))
            requests.append(body)
            names = [item["function"]["name"] for item in body.get("tools", [])]
            if stage == 0:
                native = next((name for name in names if "captureprobe" in name and name.endswith("native")), None)
                if native is None:
                    self.send_error(400, "native fixture tool missing")
                    return
                delta = {"role": "assistant", "tool_calls": [{
                    "index": 0, "id": "native-call", "type": "function",
                    "function": {"name": native, "arguments": "{}"},
                }]}
                finish = "tool_calls"
            elif stage == 1:
                nativefail = next((name for name in names if "captureprobe" in name and name.endswith("nativefail")), None)
                if nativefail is None:
                    self.send_error(400, "native failure fixture tool missing")
                    return
                delta = {"role": "assistant", "tool_calls": [{
                    "index": 0, "id": "native-fail-call", "type": "function",
                    "function": {"name": nativefail, "arguments": "{}"},
                }]}
                finish = "tool_calls"
            elif stage == 2:
                if "execute" not in names:
                    self.send_error(400, "execute tool missing")
                    return
                delta = {"role": "assistant", "tool_calls": [{
                    "index": 0, "id": "execute-call", "type": "function",
                    "function": {"name": "execute", "arguments": json.dumps({"code": PROGRAM})},
                }]}
                finish = "tool_calls"
            else:
                delta = {"role": "assistant", "content": "EVAL-LIVE-FINAL"}
                finish = "stop"
            stage += 1
            common = {"id": f"chatcmpl-{stage}", "created": 1, "model": body["model"]}
            chunks = [
                {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
            ]
            raw = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="eval-live-compat-") as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            plugin_dir = workspace / ".opencode/plugins"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "compat.ts").write_text(PLUGIN)
            (workspace / "opencode.json").write_text(json.dumps({
                "$schema": "https://opencode.ai/config.json",
                "model": "fixture/mock",
                "enabled_providers": ["fixture"],
                "provider": {"fixture": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Local eval:live fixture",
                    "options": {"baseURL": f"http://127.0.0.1:{server.server_port}/v1", "apiKey": "fixture"},
                    "models": {"mock": {"name": "Mock", "limit": {"context": 1000000, "output": 32768}}},
                }},
            }))
            prompt = root / "prompt.txt"
            system = root / "system.txt"
            result_path = root / "result.json"
            prompt.write_text("Run the fixture actions.")
            system.write_text("")
            empty = root / "empty"
            for name in ("home", "config", "data", "state", "cache"):
                (empty / name).mkdir(parents=True, exist_ok=True)
            env = dict(os.environ)
            for secret_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                                "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
                env.pop(secret_name, None)
            env.update({
                "HOME": str(empty / "home"),
                "XDG_CONFIG_HOME": str(empty / "config"),
                "XDG_DATA_HOME": str(empty / "data"),
                "XDG_STATE_HOME": str(empty / "state"),
                "XDG_CACHE_HOME": str(empty / "cache"),
            })
            command = [
                sys.executable, str(ROOT / "bin/opencode-eval-runner"), "invoke",
                "--engine", "docker", "--network", "host", "--image", image,
                "--transport", "opencode", "--workspace", str(workspace), "--workspace-mode", "rw",
                "--model", "fixture/mock", "--prompt-file", str(prompt), "--system-file", str(system),
                "--output", str(result_path), "--timeout-seconds", "45", "--container-timeout", "75",
            ]
            proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=100, check=False)
            result = json.loads(result_path.read_text()) if result_path.is_file() else {}
            observations = read_jsonl(workspace / "runtime-observations.jsonl")
            (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            (output / "observations.json").write_text(json.dumps(observations, indent=2) + "\n")
            native = [row["event"] for row in observations if row.get("channel") == "native"]
            inner = [row["event"] for row in observations if row.get("channel") == "codemode"]
            native_starts = [event for event in native if event.get("kind") == "call_start"]
            native_ends = {event.get("invocation_id"): event for event in native if event.get("kind") == "call_end"}
            outer = [event for event in native_starts if event.get("tool") == "execute"]
            inner_starts = [event for event in inner if event.get("kind") == "call_start"]
            inner_ends = [event for event in inner if event.get("kind") == "call_end"]
            evidence = result.get("tool_result_evidence", {}).get("events", [])
            native_success_starts = [event for event in native_starts if event.get("tool", "").endswith("native")]
            native_failure_starts = [event for event in native_starts if event.get("tool", "").endswith("nativefail")]
            native_success_end = (
                native_ends.get(native_success_starts[0].get("invocation_id"))
                if len(native_success_starts) == 1 else None
            )
            native_failure_end = (
                native_ends.get(native_failure_starts[0].get("invocation_id"))
                if len(native_failure_starts) == 1 else None
            )
            native_success_value = (native_success_end or {}).get("result", {}).get("value", {})
            native_failure_value = (native_failure_end or {}).get("error", {}).get("value", {})
            native_success_content = native_success_value.get("content", []) if isinstance(native_success_value, dict) else []
            checks = {
                "existing_invoke_entrypoint": command[1:3] == [str(ROOT / "bin/opencode-eval-runner"), "invoke"],
                "transport_success": proc.returncode == 0 and result.get("exit_code") == 0,
                "existing_result_text": result.get("text") == "EVAL-LIVE-FINAL",
                "native_product_result_preserved": any(
                    event.get("tool", "").endswith("native") and "NATIVE-RAW" in str(event.get("output", ""))
                    for event in evidence
                ),
                "native_failure_product_result_preserved": any(
                    event.get("tool", "").endswith("nativefail")
                    and event.get("status") == "error"
                    and "NATIVE-FAIL-RAW" in str(event.get("error", ""))
                    for event in evidence
                ),
                "execute_product_result_preserved": any(
                    event.get("tool") == "execute" and "INNER-RAW" in str(event.get("output", ""))
                    for event in evidence
                ),
                "native_observation_schema_v2": bool(native) and all(
                    event.get("schema") == "opencode-native-observation/v2" for event in native
                ),
                "native_observation_present": len(native_success_starts) == 1,
                "native_final_is_post_truncation_session_terminal": (
                    isinstance(native_success_value, dict)
                    and native_success_value.get("metadata", {}).get("truncated") is True
                    and any("[showing " in str(part.get("text", "")) for part in native_success_content if isinstance(part, dict))
                    and (native_success_end or {}).get("boundary") == "session-tool-terminal"
                ),
                "native_final_error_is_session_terminal": (
                    (native_failure_end or {}).get("outcome") == "threw"
                    and (native_failure_end or {}).get("boundary") == "session-tool-terminal"
                    and (native_failure_end or {}).get("error_representation") == "session-tool-failed/v1"
                    and isinstance(native_failure_value, dict)
                    and native_failure_value.get("error", {}).get("type") == "unknown"
                    and "NATIVE-FAIL-RAW" in str(native_failure_value.get("error", {}).get("message", ""))
                ),
                "outer_execute_observation_present": len(outer) == 1 and outer[0].get("invocation_id") in native_ends,
                "inner_final_observation_present": len(inner_starts) == len(inner_ends) == 1
                    and inner_ends[0].get("result", {}).get("value") == "INNER-RAW",
                "inner_parent_is_actual_outer_invocation": len(outer) == 1 and len(inner_starts) == 1
                    and inner_starts[0].get("parent", {}).get("invocation_id") == outer[0].get("invocation_id")
                    and inner_starts[0].get("parent", {}).get("call_id") == "execute-call",
                "shared_sequence_orders_boundaries": len(outer) == 1 and len(inner_starts) == len(inner_ends) == 1
                    and outer[0].get("sequence", 0) < inner_starts[0].get("sequence", 0)
                    < inner_ends[0].get("sequence", 0) < native_ends[outer[0].get("invocation_id")].get("sequence", 0),
                "no_real_provider_credentials": not any(env.get(key) for key in (
                    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                    "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN",
                )),
            }
            summary = {
                "kind": "eval-live-invoke-compatibility",
                "version": 2,
                "image": image,
                "runner_entrypoint": "opencode-eval-runner invoke",
                "loom_entrypoint_contract": "bun run eval:live -> python3 scripts/run-evals.py -> opencode-eval-runner invoke",
                "checks": checks,
                "passed": all(checks.values()),
                "semantic_scope": {
                    "normal_invoke": "demonstrated",
                    "native_tool_final_result_and_error": "demonstrated_after_session_truncation/publication",
                    "codemode_inner_final_result": "demonstrated",
                    "delegated_session_identity": "not_exercised",
                    "in_process_plugin_protection": "unsupported",
                },
                "evidence_status": "diagnostic_non_evidence",
                "reason": "The evaluated plugin shares the OpenCode process and can therefore share collector authority.",
            }
            (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary, indent=2))
            return 0 if summary["passed"] else 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.image, args.output))
