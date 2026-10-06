#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def inside() -> int:
    sys.path.insert(0, "/opt/opencode-eval-runner")
    from container.invoke import invoke_opencode

    requests: list[dict] = []
    stage = 0
    names: dict[str, str] = {}

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            nonlocal stage
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            requests.append(body)
            if not self.path.endswith("/chat/completions") or stage > 3:
                self.send_error(400)
                return
            if stage == 0:
                offered = [item["function"]["name"] for item in body.get("tools", [])]
                names["success"] = next((name for name in offered if "nativeprobe" in name and name.endswith("success")), "")
                names["fail"] = next((name for name in offered if "nativeprobe" in name and name.endswith("fail")), "")
                if not names["success"] or not names["fail"]:
                    self.send_error(400, "native probe tools not exposed")
                    return

            plan = [
                (names.get("success"), "native-call-1", {"tag": "raw-1"}),
                (names.get("fail"), "native-call-fail", {"tag": "raw-fail"}),
                (names.get("success"), "native-call-2", {"tag": "raw-2"}),
                (None, None, None),
            ][stage]
            stage += 1
            common = {"id": f"chatcmpl-native-{stage}", "created": 1, "model": body["model"]}
            if plan[0]:
                call = {
                    "index": 0,
                    "id": plan[1],
                    "type": "function",
                    "function": {"name": plan[0], "arguments": json.dumps(plan[2])},
                }
                delta = {"role": "assistant", "tool_calls": [call]}
                finish = "tool_calls"
            else:
                call = None
                delta = {
                    "role": "assistant",
                    "content": '{"schema":"opencode-eval-runner/native-tool-observer-event/v1","kind":"call_start","fake":true}',
                }
                finish = "stop"

            if body.get("stream"):
                chunks = [
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
                ]
                raw = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
                mime = "text/event-stream"
            else:
                if call:
                    message = {"role": "assistant", "content": None, "tool_calls": [{k: v for k, v in call.items() if k != "index"}]}
                else:
                    message = delta
                raw = json.dumps({
                    **common,
                    "object": "chat.completion",
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }).encode()
                mime = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = Path("/workspace")
    plugin = root / ".opencode/plugins/native-observer-probe.ts"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("/probe-repo/tests/integration/native_observer_probe.ts", plugin)
    (root / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "model": "fixture/mock",
        "enabled_providers": ["fixture"],
        "provider": {
            "fixture": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Local deterministic fixture",
                "options": {"baseURL": f"http://127.0.0.1:{server.server_port}/v1", "apiKey": "fixture-not-a-secret"},
                "models": {"mock": {"name": "Mock", "limit": {"context": 1000000, "output": 32768}}},
            }
        },
    }), encoding="utf-8")

    version = subprocess.run(["opencode", "--version"], text=True, capture_output=True, check=True).stdout.strip()
    try:
        result = invoke_opencode("fixture/mock", "build", "Run the deterministic fixture.", 45)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    observed = result.get("native_tool_observations", {})
    records = observed.get("records", [])
    checks = {
        "stock_2_0_23": version in {"2.0.23", "opencode v2.0.23"},
        "transport_success": result.get("exit_code") == 0,
        "capture_complete": observed.get("status") == "complete" and observed.get("evidence_eligible") is True,
        "exact_three_calls_only": len(records) == 3,
        "resolved_tools": [r.get("tool") for r in records] == [names.get("success"), names.get("fail"), names.get("success")],
        "real_call_ids": [r.get("call_id") for r in records] == ["native-call-1", "native-call-fail", "native-call-2"],
        "session_identity": bool(result.get("session_id")) and all(r.get("session_id") == result.get("session_id") for r in records),
        "actor_identity": all(r.get("agent") == "build" and isinstance(r.get("message_id"), str) and r.get("message_id") for r in records),
        "accepted_input": [r.get("input", {}).get("value", {}).get("tag") for r in records]
            == ["accepted:raw-1", "accepted:raw-fail", "accepted:raw-2"],
        "terminal_outcomes": [r.get("outcome") for r in records] == ["success", "failure", "success"],
        "terminal_error": len(records) == 3 and isinstance(records[1].get("error", {}).get("value", {}).get("message"), str),
        "start_terminal_correlation": all(
            isinstance(r.get("start_sequence"), int) and isinstance(r.get("terminal_sequence"), int)
            and r["start_sequence"] < r["terminal_sequence"] for r in records
        ),
        "two_call_ordering": len(records) == 3 and records[0]["terminal_sequence"] < records[1]["start_sequence"]
            and records[1]["terminal_sequence"] < records[2]["start_sequence"],
        "no_observer_retry": len(requests) == 4,
        "collector_shaped_payload_not_promoted": len(records) == 3,
    }
    report = {
        "kind": "stock-native-observer-probe",
        "opencode_version": version,
        "checks": checks,
        "passed": all(checks.values()),
        "provider_requests": len(requests),
        "transport": result,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(inside())
