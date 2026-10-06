#!/usr/bin/env python3
"""Provider-free stock OpenCode 2.0.23 Code Mode observation boundary probe.

This is an experiment, not an evidence producer. It drives the actual runner image
with a deterministic loopback OpenAI-compatible provider and checks which facts a
runner-owned same-process plugin can and cannot observe on stock OpenCode.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_IMAGE = "opencode-eval-runner:opencode-test"
FABRICATED_ID = "fabricated-from-script"

SCRIPT = r"""
const success = await tools.codemodeprobe.success({tag:"one"});
if (success !== "SUCCESS-FINAL") throw new Error("WRONG-SUCCESS");

const pair = await Promise.all([
  tools.codemodeprobe.echo({tag:"identical"}),
  tools.codemodeprobe.echo({tag:"identical"})
]);
if (pair[0] !== "ECHO-1" || pair[1] !== "ECHO-2") throw new Error("WRONG-CORRELATION");

let caught = false;
try {
  await tools.codemodeprobe.throws({tag:"caught"});
} catch (error) {
  caught = String(error?.message ?? error).includes("THROW-RAW");
}
if (!caught) throw new Error("WRONG-THROW");

const mutated = await tools.codemodeprobe.mutate({tag:"mutate"});
if (mutated !== "AFTER-MUTATION") throw new Error("WRONG-FINAL-BOUNDARY");

return JSON.stringify({
  schema: "opencode-eval-runner/code-mode-observer-experiment/v1",
  kind: "inner_handler_terminal",
  invocation_id: "fabricated-from-script",
  outcome: "returned",
  handler_result: "FAKE"
});
"""


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    result: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            result.append(value)
    return result


def inside() -> int:
    sys.path.insert(0, "/opt/opencode-eval-runner")
    from container.invoke import invoke_opencode

    requests: list[dict] = []
    stage = 0

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            nonlocal stage
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            requests.append(body)

            if not self.path.endswith("/chat/completions") or stage > 4:
                self.send_error(400)
                return

            tool = None
            if stage == 0:
                names = [
                    item.get("function", {}).get("name")
                    for item in body.get("tools", [])
                    if isinstance(item, dict)
                ]
                if "execute" not in names:
                    self.send_error(400, "stock Code Mode execute tool not exposed")
                    return
                tool = ("execute", {"code": SCRIPT})

            stage += 1
            call = (
                {
                    "index": 0,
                    "id": f"fixture-call-{stage}",
                    "type": "function",
                    "function": {
                        "name": tool[0],
                        "arguments": json.dumps(tool[1]),
                    },
                }
                if tool
                else None
            )
            delta = (
                {"role": "assistant", "tool_calls": [call]}
                if call
                else {"role": "assistant", "content": "provider-done"}
            )
            finish = "tool_calls" if call else "stop"
            common = {
                "id": f"chatcmpl-fixture-{stage}",
                "created": 1,
                "model": body["model"],
            }

            if body.get("stream"):
                chunks = [
                    {
                        **common,
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    },
                    {
                        **common,
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                    },
                ]
                raw = (
                    "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                    + "data: [DONE]\n\n"
                ).encode()
                mime = "text/event-stream"
            else:
                message = (
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{k: v for k, v in call.items() if k != "index"}],
                    }
                    if call
                    else delta
                )
                raw = json.dumps(
                    {
                        **common,
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": finish,
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                    }
                ).encode()
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
    plugin = root / ".opencode/plugins/code-mode-observer-probe.ts"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        "/probe-repo/tests/integration/code_mode_observer_probe.ts",
        plugin,
    )
    (root / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "model": "fixture/mock",
                "enabled_providers": ["fixture"],
                "provider": {
                    "fixture": {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Local deterministic fixture",
                        "options": {
                            "baseURL": f"http://127.0.0.1:{server.server_port}/v1",
                            "apiKey": "fixture-not-a-secret",
                        },
                        "models": {
                            "mock": {
                                "name": "Mock",
                                "limit": {"context": 1000000, "output": 32768},
                            }
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    version = subprocess.run(
        ["opencode", "--version"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    try:
        result = invoke_opencode("fixture/mock", "", "code-mode-observer-probe", 45)
    except Exception as exc:
        result = {"exit_code": 2, "fixture_error": str(exc)}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    report = {
        "opencode_version": version,
        "transport": result,
        "plugin_loaded": Path("/tmp/code-mode-observer-loaded").is_file(),
        "records": read_jsonl(Path("/tmp/code-mode-observer-records.jsonl")),
        "provider_requests": requests,
    }
    print(json.dumps(report))
    return 0


def completed_outer_output(report: dict) -> str:
    events = (
        report.get("transport", {})
        .get("tool_result_evidence", {})
        .get("events", [])
    )
    for event in events:
        if event.get("tool") != "execute" or event.get("status") != "completed":
            continue
        output = event.get("output")
        if isinstance(output, str):
            return output
    return ""


def record_id(record: dict) -> str | None:
    value = record.get("invocation_id")
    return value if isinstance(value, str) else None


def summarize(report: dict, image: str) -> dict:
    records = report.get("records", [])
    starts = [r for r in records if r.get("kind") == "inner_start"]
    handler_ends = [r for r in records if r.get("kind") == "inner_handler_terminal"]
    afters = [r for r in records if r.get("kind") == "inner_after_hook"]
    parent_starts = [r for r in records if r.get("kind") == "parent_start"]
    parent_ends = [r for r in records if r.get("kind") == "parent_end"]

    by_id = {
        record_id(item): item
        for item in handler_ends
        if record_id(item) is not None
    }

    echo_starts = [r for r in starts if r.get("tool") == "codemodeprobe_echo"]
    echo_ends = [r for r in handler_ends if r.get("tool") == "codemodeprobe_echo"]
    throw_ends = [r for r in handler_ends if r.get("tool") == "codemodeprobe_throws"]
    success_ends = [r for r in handler_ends if r.get("tool") == "codemodeprobe_success"]
    mutate_ends = [r for r in handler_ends if r.get("tool") == "codemodeprobe_mutate"]
    mutate_afters = [r for r in afters if r.get("tool") == "codemodeprobe_mutate"]

    parent = (
        parent_starts[0].get("parent")
        if len(parent_starts) == 1 and isinstance(parent_starts[0].get("parent"), dict)
        else {}
    )
    parent_tuple = (
        parent.get("session_id"),
        parent.get("message_id"),
        parent.get("call_id"),
    )

    start_ids = [record_id(r) for r in starts]
    echo_start_ids = [record_id(r) for r in echo_starts]
    echo_end_ids = [record_id(r) for r in echo_ends]
    shared_public_ids = [r.get("shared_call_id") for r in afters]

    fabricated_in_observer = any(record_id(r) == FABRICATED_ID for r in records)
    outer_output = completed_outer_output(report)

    def handler_content(item: dict) -> str | None:
        value = item.get("handler_result")
        if isinstance(value, dict):
            content = value.get("content")
            return content if isinstance(content, str) else None
        return None

    def after_content(item: dict) -> str | None:
        result = item.get("result")
        if not isinstance(result, dict):
            return None
        # Stock Tool.Result may be represented directly or through normalized
        # content parts depending on the fixture adapter.
        content = result.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list) and len(content) == 1:
            part = content[0]
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                return text if isinstance(text, str) else None
        output = result.get("output")
        return output if isinstance(output, str) else None

    checks = {
        "stock_runtime_2_0_23": report.get("opencode_version") in {
            "2.0.23",
            "opencode v2.0.23",
        },
        "provider_free_execution_completed": (
            report.get("transport", {}).get("exit_code") == 0
            and report.get("plugin_loaded") is True
        ),
        "one_successful_inner_call": (
            len(success_ends) == 1
            and success_ends[0].get("outcome") == "returned"
            and handler_content(success_ends[0]) == "SUCCESS-FINAL"
        ),
        "caught_inner_throw_observed_at_handler": (
            len(throw_ends) == 1
            and throw_ends[0].get("outcome") == "threw"
            and "THROW-RAW" in json.dumps(throw_ends[0].get("handler_error"))
        ),
        "identical_concurrent_calls_have_unique_ids": (
            len(echo_starts) == 2
            and len(set(echo_start_ids)) == 2
            and all(r.get("input") == {"tag": "identical"} for r in echo_starts)
        ),
        "reverse_completion_keeps_identity": (
            len(echo_ends) == 2
            and echo_end_ids == list(reversed(echo_start_ids))
            and [handler_content(r) for r in echo_ends] == ["ECHO-2", "ECHO-1"]
            and all(by_id.get(item_id) is not None for item_id in echo_start_ids)
        ),
        "multiple_calls_bind_to_one_outer_execute": (
            len(starts) == 5
            and len(parent_starts) == 1
            and all(
                isinstance(r.get("parent"), dict)
                and (
                    r["parent"].get("session_id"),
                    r["parent"].get("message_id"),
                    r["parent"].get("call_id"),
                )
                == parent_tuple
                for r in starts
            )
        ),
        "public_inner_hooks_share_outer_call_id": (
            len(afters) >= 4
            and parent.get("call_id") is not None
            and all(value == parent.get("call_id") for value in shared_public_ids)
        ),
        "handler_terminal_is_not_final_caller_value": (
            len(mutate_ends) == 1
            and handler_content(mutate_ends[0]) == "BEFORE-MUTATION"
            and len(mutate_afters) == 1
            and after_content(mutate_afters[0]) == "AFTER-MUTATION"
            and report.get("transport", {}).get("exit_code") == 0
        ),
        "outer_script_cannot_fabricate_inner_observation": (
            FABRICATED_ID in outer_output and not fabricated_in_observer
        ),
        "ordering_is_monotonic": (
            bool(records)
            and [r.get("sequence") for r in records]
            == list(range(1, len(records) + 1))
        ),
        "starts_have_matching_handler_terminals": (
            len(start_ids) == len(handler_ends) == 5
            and set(start_ids) == set(by_id)
        ),
        "observer_loss_visible_and_zero": (
            all(r.get("observer_losses_before") == 0 for r in records)
            and len(parent_ends) == 1
            and parent_ends[0].get("observer_losses") == 0
        ),
        "caller_terminal_explicitly_unsupported": (
            len(handler_ends) == 5
            and all(
                r.get("caller_terminal")
                == {
                    "status": "unsupported",
                    "reason": "stock_codemode_final_boundary_not_exposed",
                }
                for r in handler_ends
            )
        ),
    }

    return {
        "kind": "code-mode-inner-observation-probe",
        "version": 1,
        "image": image,
        "runtime": "stock OpenCode 2.0.23",
        "checks": checks,
        "diagnostics_passed": all(checks.values()),
        "capabilities": {
            "unique_invocation_identity": "supported",
            "selected_tool": "supported",
            "executable_input": "supported",
            "outer_execute_binding": "supported",
            "start_and_handler_terminal_ordering": "supported",
            "caller_terminal": {
                "status": "unsupported",
                "reason": "stock_codemode_final_boundary_not_exposed",
                "missing_boundary": (
                    "@opencode/codemode tool.after sees the final CallResult, "
                    "but stock CodeModeTool wires it only to private progressHooks"
                ),
            },
        },
        "status": "unsupported",
        "evidence_eligible": False,
        "note": (
            "The transform wrapper proves correlation and execution facts only. "
            "Its handler terminal is diagnostic and is not the final value/error "
            "seen by the Code Mode script."
        ),
    }


def host(image: str, output: Path) -> int:
    repo = Path(__file__).resolve().parents[2]
    output.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,size=1g",
        "--tmpfs",
        "/workspace:rw,nosuid,nodev,size=64m,mode=1777",
        "--workdir",
        "/workspace",
        "--volume",
        f"{repo}:/probe-repo:ro",
        "--entrypoint",
        "python3",
        image,
        "/probe-repo/tests/integration/run_code_mode_observer_probe.py",
        "--inside",
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        report = {
            "docker_exit_code": proc.returncode,
            "driver_error": "invalid_json",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    report["docker_exit_code"] = proc.returncode
    summary = summarize(report, image)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if proc.returncode == 0 and summary["diagnostics_passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--output", type=Path, default=Path("code-mode-observer-probe-results"))
    args = parser.parse_args()
    raise SystemExit(inside() if args.inside else host(args.image, args.output))
