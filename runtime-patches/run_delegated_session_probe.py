#!/usr/bin/env python3
"""Provider-free proof of real delegated Session identity/lifecycle under runner invoke."""
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

PLUGIN = r'''
import { appendFileSync } from "node:fs"

const path = "/workspace/delegated-observations.jsonl"
function log(event: any) { appendFileSync(path, JSON.stringify(event) + "\n") }
const calls = new Map<string, { tool: string; parentSession: string }>()

export default {
  id: "delegateprobe",
  async setup(ctx: any) {
    await ctx.tool.transform((editor: any) => {
      editor.namespace({ name: "delegateprobe", description: "Delegated session fixture" })
      editor.add({
        name: "marker",
        description: "Return a child-session marker",
        input: { type: "object", properties: { marker: { type: "string" } }, required: ["marker"], additionalProperties: false },
        options: { namespace: "delegateprobe", codemode: false },
        execute: async (input: any) => ({ content: "MARKER-" + input.marker }),
      })
    })
    await ctx.tool.hook("execute.native-observed", async (event: any) => {
      log(event)
      if (event.kind === "call_start") {
        calls.set(String(event.invocation_id), {
          tool: String(event.tool),
          parentSession: String(event.actor?.session_id ?? ""),
        })
        return
      }
      if (event.kind !== "call_end") return
      const call = calls.get(String(event.invocation_id))
      if (!call) return
      calls.delete(String(event.invocation_id))
      const childID = event.outcome === "returned"
        ? event.result?.value?.metadata?.sessionID
        : undefined
      if (call.tool === "subagent" && typeof childID === "string" && childID) {
        const child = await ctx.session.get({ sessionID: childID })
        log({
          kind: "session_ancestry",
          child_session_id: child.id,
          child_parent_id: child.parentID ?? null,
          parent_actor_session_id: call.parentSession,
        })
      }
    })
    await ctx.session.hook("http.request", (event: any) => {
      const headers = new Headers(event.request.headers)
      headers.set("x-probe-session", String(event.sessionID))
      headers.set("x-probe-agent", String(event.agent))
      event.request = new Request(event.request, { headers })
    })
  },
}
'''

GENERAL_ALLOW = """---
description: Parent fixture
mode: primary
model: fixture/mock
permissions:
  - action: "*"
    resource: "*"
    effect: allow
---

Use the requested tools.
"""

GENERAL_DENY = """---
description: Parent fixture with reviewer denial
mode: primary
model: fixture/mock
permissions:
  - action: "*"
    resource: "*"
    effect: allow
  - action: subagent
    resource: reviewer
    effect: deny
---

Use the requested tools.
"""

REVIEWER = """---
description: Child reviewer fixture
mode: subagent
model: fixture/mock
permissions:
  - action: "*"
    resource: "*"
    effect: allow
---

Complete the delegated task.
"""


def read_jsonl(path: Path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def run_once(image: str, output: Path, *, denied: bool):
    request_log = []
    child_calls = 0
    parent_calls = 0

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            nonlocal child_calls, parent_calls
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size))
            agent = self.headers.get("x-probe-agent", "")
            session = self.headers.get("x-probe-session", "")
            names = [item["function"]["name"] for item in body.get("tools", [])]
            request_log.append({"agent": agent, "session": session, "tools": names})
            tool = None
            if agent == "reviewer":
                child_calls += 1
                if child_calls == 1:
                    marker = next((name for name in names if name.endswith("delegateprobe_marker")), None)
                    if marker is None:
                        self.send_error(400, "child marker tool missing")
                        return
                    tool = (marker, {"marker": "child"})
                else:
                    delta, finish = {"role": "assistant", "content": "CHILD-DONE"}, "stop"
            else:
                parent_calls += 1
                if parent_calls == 1:
                    if "subagent" not in names:
                        self.send_error(400, "subagent tool missing")
                        return
                    tool = ("subagent", {
                        "agent": "reviewer",
                        "description": "delegation fixture",
                        "prompt": "Call delegateprobe.marker with marker child, then answer CHILD-DONE.",
                        "background": False,
                    })
                else:
                    delta, finish = {"role": "assistant", "content": "PARENT-DONE"}, "stop"
            if tool is not None:
                delta = {"role": "assistant", "tool_calls": [{
                    "index": 0, "id": ("child-marker-call" if agent == "reviewer" else "parent-subagent-call"),
                    "type": "function",
                    "function": {"name": tool[0], "arguments": json.dumps(tool[1])},
                }]}
                finish = "tool_calls"
            common = {"id": f"chatcmpl-{len(request_log)}", "created": 1, "model": body["model"]}
            chunks = [
                {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
            ]
            raw = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="delegated-session-probe-") as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            plugin_dir = workspace / ".opencode/plugins"
            agent_dir = workspace / ".opencode/agents"
            plugin_dir.mkdir(parents=True)
            agent_dir.mkdir(parents=True)
            (plugin_dir / "delegateprobe.ts").write_text(PLUGIN)
            (agent_dir / "general.md").write_text(GENERAL_DENY if denied else GENERAL_ALLOW)
            (agent_dir / "reviewer.md").write_text(REVIEWER)
            (workspace / "opencode.json").write_text(json.dumps({
                "$schema": "https://opencode.ai/config.json",
                "default_agent": "general",
                "model": "fixture/mock",
                "enabled_providers": ["fixture"],
                "provider": {"fixture": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Delegated fixture",
                    "options": {"baseURL": f"http://127.0.0.1:{server.server_port}/v1", "apiKey": "fixture"},
                    "models": {"mock": {"name": "Mock", "limit": {"context": 1000000, "output": 32768}}},
                }},
            }))
            prompt = root / "prompt.txt"; prompt.write_text("Delegate the fixture task to reviewer.")
            system = root / "system.txt"; system.write_text("")
            result_path = root / "result.json"
            xdg = root / "xdg"
            for name in ("home", "config", "data", "state", "cache"):
                (xdg / name).mkdir(parents=True, exist_ok=True)
            env = dict(os.environ)
            for key in ("OPENAI_API_KEY","ANTHROPIC_API_KEY","OPENROUTER_API_KEY","COPILOT_GITHUB_TOKEN","GH_TOKEN","GITHUB_TOKEN"):
                env.pop(key, None)
            env.update({
                "HOME": str(xdg/"home"), "XDG_CONFIG_HOME": str(xdg/"config"),
                "XDG_DATA_HOME": str(xdg/"data"), "XDG_STATE_HOME": str(xdg/"state"),
                "XDG_CACHE_HOME": str(xdg/"cache"),
            })
            command = [
                sys.executable, str(ROOT/"bin/opencode-eval-runner"), "invoke",
                "--engine","docker","--network","host","--image",image,
                "--transport","opencode","--workspace",str(workspace),"--workspace-mode","rw",
                "--model","fixture/mock","--agent","general","--prompt-file",str(prompt),
                "--system-file",str(system),"--output",str(result_path),
                "--timeout-seconds","60","--container-timeout","90",
            ]
            proc = subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=110,check=False)
            result = json.loads(result_path.read_text()) if result_path.is_file() else {}
            events = read_jsonl(workspace/"delegated-observations.jsonl")
            starts = [e for e in events if e.get("kind")=="call_start"]
            ends = {e.get("invocation_id"):e for e in events if e.get("kind")=="call_end"}
            ancestry = [e for e in events if e.get("kind")=="session_ancestry"]
            sub_start = next((e for e in starts if e.get("tool")=="subagent"), None)
            sub_end = ends.get(sub_start.get("invocation_id")) if sub_start else None
            child_start = next((e for e in starts if str(e.get("tool","")).endswith("delegateprobe_marker")), None)
            child_end = ends.get(child_start.get("invocation_id")) if child_start else None
            parent_session = sub_start.get("actor",{}).get("session_id") if sub_start else None
            child_session = None
            if sub_end and sub_end.get("outcome")=="returned":
                child_session = sub_end.get("result",{}).get("value",{}).get("metadata",{}).get("sessionID")
            if denied:
                checks = {
                    "invoke_completed": proc.returncode == 0 and result.get("exit_code") == 0,
                    "subagent_attempt_observed": sub_start is not None,
                    "canonical_denial_terminal": sub_end is not None and sub_end.get("outcome")=="threw"
                        and "denied" in json.dumps(sub_end).lower(),
                    "no_child_session_request": all(r["agent"] != "reviewer" for r in request_log),
                    "no_child_tool_observation": child_start is None,
                }
            else:
                checks = {
                    "invoke_completed": proc.returncode == 0 and result.get("exit_code") == 0 and result.get("text")=="PARENT-DONE",
                    "parent_subagent_observed": sub_start is not None and sub_end is not None,
                    "child_session_returned_by_real_subagent": isinstance(child_session,str) and bool(child_session),
                    "child_provider_used_reviewer_identity": any(r["agent"]=="reviewer" and r["session"]==child_session for r in request_log),
                    "child_tool_actor_matches_child": child_start is not None
                        and child_start.get("actor",{}).get("agent")=="reviewer"
                        and child_start.get("actor",{}).get("session_id")==child_session,
                    "parent_and_child_sessions_distinct": bool(parent_session) and bool(child_session) and parent_session != child_session,
                    "actual_session_parent_id_matches_parent": len(ancestry) == 1
                        and ancestry[0].get("child_session_id") == child_session
                        and ancestry[0].get("child_parent_id") == parent_session
                        and ancestry[0].get("parent_actor_session_id") == parent_session,
                    "child_completed_before_parent_subagent_terminal": child_end is not None and sub_end is not None
                        and child_end.get("sequence",0) < sub_end.get("sequence",0),
                    "foreground_completion_delivered": sub_end is not None and "CHILD-DONE" in json.dumps(sub_end),
                }
            report = {
                "denied": denied, "image": image, "checks": checks, "passed": all(checks.values()),
                "requests": request_log, "events": events,
                "result": {"exit_code": result.get("exit_code"), "text": result.get("text")},
            }
            (output/("denied.json" if denied else "success.json")).write_text(json.dumps(report,indent=2)+"\n")
            return report
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--image",required=True); p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    success=run_once(args.image,args.output,denied=False)
    denied=run_once(args.image,args.output,denied=True)
    summary={"kind":"delegated-session-normal-invoke","version":1,"image":args.image,
             "success":success["checks"],"denied":denied["checks"],"passed":success["passed"] and denied["passed"],
             "scope":"real built-in foreground subagent + actual Session parentID + permission enforcement; provider-free",
             "remaining":["background delegation and cancellation/OQ lifecycle are not exercised by this focused probe"]}
    (args.output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))
    return 0 if summary["passed"] else 1

if __name__=="__main__":
    raise SystemExit(main())
