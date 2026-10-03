#!/usr/bin/env python3
"""Real pinned-runtime diagnostic + PR host importer; NOT a substitute producer.

Run on a disposable Docker host. No real provider, seeds, or user's state. The
capture acceptance deliberately remains BLOCKED for this old-image baseline.
An explicit negative-control mode can pass CI only when all baseline checks pass
and no capture is eligible. Unsigned hook/oracle logs are never imported as proof.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IMAGE = "ghcr.io/bateau84/opencode-eval-runner@sha256:68ef7322c75aede0e8cc76d0e3531e8b82dd417bbb5e5100264a89eab7fe8627"
SCRIPT = '''
const pair = await Promise.all([
  tools.captureprobe.echo({tag:"identical"}),
  tools.captureprobe.echo({tag:"identical"})
]);
if (pair[0] !== "CALL-1" || pair[1] !== "CALL-2") throw new Error("WRONG-CORRELATION");
const denial = await tools.captureprobe.denied({});
if (denial !== '{"ok":false,"error":"denied"}') throw new Error("WRONG-DENIAL");
let caught = false;
try { await tools.captureprobe.throws({}); }
catch (error) { caught = String(error?.message ?? error).includes("THROW-RAW"); }
if (!caught) throw new Error("WRONG-THROW");
const final = await tools.captureprobe.mutate({});
if (final !== "FINAL-RETURN") throw new Error("WRONG-FINAL-BOUNDARY");
const forged = await tools.captureprobe.forge({});
if (forged !== "FORGE-TOOL-UNCHANGED") throw new Error("FORGERY-CHANGED-TOOL");
return "script-output-only";
'''


def read_records(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def inside():
    """Runs in --network none; the only model endpoint is in-container loopback."""
    sys.path.insert(0, "/opt/opencode-eval-runner")
    from container.invoke import invoke_opencode
    requests = []
    stage = 0

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            nonlocal stage
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            requests.append(body)
            if not self.path.endswith("/chat/completions") or stage > 8:
                self.send_error(400)
                return
            tool = None
            if stage == 0:
                names = [item["function"]["name"] for item in body.get("tools", [])]
                native = next((name for name in names if "captureprobe" in name and name.endswith("native")), None)
                if native is None:
                    self.send_error(400, "captureprobe native tool not exposed")
                    return
                tool = (native, {})
            elif stage == 1:
                tool = ("execute", {"code": SCRIPT})
            stage += 1
            call = {"index": 0, "id": f"fixture-call-{stage}", "type": "function",
                    "function": {"name": tool[0], "arguments": json.dumps(tool[1])}} if tool else None
            delta = {"role": "assistant", "tool_calls": [call]} if call else {"role": "assistant", "content": "provider-done"}
            finish = "tool_calls" if call else "stop"
            common = {"id": f"chatcmpl-fixture-{stage}", "created": 1, "model": body["model"]}
            if body.get("stream"):
                chunks = [
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
                ]
                raw = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
                mime = "text/event-stream"
            else:
                message = {"role": "assistant", "content": None, "tool_calls": [{k: v for k, v in call.items() if k != "index"}]} if call else delta
                raw = json.dumps({**common, "object": "chat.completion", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                                  "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
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
    plugin = root / ".opencode/plugins/captureprobe.ts"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("/probe-repo/tests/integration/capture_probe.ts", plugin)
    (root / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json", "model": "fixture/mock",
        "enabled_providers": ["fixture"],
        "provider": {"fixture": {"npm": "@ai-sdk/openai-compatible", "name": "Local deterministic fixture",
                     "options": {"baseURL": f"http://127.0.0.1:{server.server_port}/v1", "apiKey": "fixture-not-a-secret"},
                     "models": {"mock": {"name": "Mock", "limit": {"context": 1000000, "output": 32768}}}}},
    }))
    version = subprocess.run(["opencode", "--version"], text=True, capture_output=True, check=True).stdout.strip()
    try:
        result = invoke_opencode("fixture/mock", "", "capture-probe", 45)
    except Exception as exc:
        result = {"exit_code": 2, "fixture_error": str(exc)}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print(json.dumps({"opencode_version": version, "transport": result,
                      "plugin_loaded": Path("/tmp/capture-probe-loaded").exists(),
                      "oracle": read_records(Path("/tmp/capture-probe-oracle.jsonl")),
                      "hooks": read_records(Path("/tmp/capture-probe-hooks.jsonl")),
                      "provider_requests": requests}))


def scenario_completed(value):
    # Look only at an actual completed outer result, never script source.
    # This proves fixture execution, NOT admissibility of individual inner calls.
    events = value.get("transport", {}).get("tool_result_evidence", {}).get("events", [])
    return any(event.get("tool") == "execute" and event.get("status") == "completed"
               and event.get("output", "").strip().strip('"') == "script-output-only" for event in events)


def oracle_signature(value):
    return [{key: event["record"].get(key) for key in ("phase", "name", "n", "input", "content", "error")}
            for event in value.get("oracle", [])]


def overlap(value):
    echo = [event["record"] for event in value.get("oracle", []) if event["record"].get("name") == "echo"]
    return (len(echo) == 4 and [e["phase"] for e in echo] == ["start", "start", "returned", "returned"]
            and echo[0]["input"] == echo[1]["input"] == {"tag": "identical"}
            and echo[2]["n"] == echo[1]["n"] and echo[3]["n"] == echo[0]["n"])


def hook_observations(value):
    hooks = [item["record"] for item in value.get("hooks", [])]

    def selected(name, phase):
        return [item for item in hooks if item.get("phase") == phase
                and item.get("event", {}).get("tool") == "captureprobe_" + name]

    def content(item):
        raw = item.get("event", {}).get("result", {}).get("content")
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list) and len(raw) == 1 and raw[0].get("type") == "text":
            return raw[0].get("text")
        return None

    starts = selected("echo", "before")
    terminals = selected("echo", "early-after")
    early = selected("mutate", "early-after")
    late = selected("mutate", "late-after")
    return {
        "echo_start_ids": [item["event"].get("id") for item in starts],
        "echo_terminal_ids": [item["event"].get("id") for item in terminals],
        "echo_terminal_values_in_observed_order": [content(item) for item in terminals],
        "echo_start_input_object_refs": [item.get("inputRef") for item in starts],
        "echo_terminal_input_object_refs": [item.get("inputRef") for item in terminals],
        "object_reference_note": "Runtime observation only; object identity is not an agreed supported correlation contract.",
        "throw_before_count": len(selected("throws", "before")),
        "throw_after_count": len(selected("throws", "early-after")),
        "early_mutate_result": content(early[0]) if len(early) == 1 else None,
        "late_mutate_result": content(late[0]) if len(late) == 1 else None,
    }


BASELINE_CHECKS = frozenset({
    "pinned_image", "runtime_2_0_18", "scenarios_completed",
    "identical_calls_overlap_and_finish_reversed", "tool_behavior_unchanged",
    "missing_producer_not_evidence", "forged_sidecar_rejected",
    "diagnostic_hooks_toggle", "shared_id_counterexample",
    "caught_throw_has_no_after_hook", "early_after_is_not_final_return",
    "no_capture_eligible",
})


def probe_exit_code(summary: dict, *, expect_unsupported_baseline: bool = False) -> int:
    """Separate a passing rejection regression from successful evidence capture.

    Only the exact old-image counterexample suite may use the zero-exit mode.
    Missing checks, execution failures and unexpected eligible capture still fail.
    The default remains exit 4 for correctly reproduced, blocked capture.
    """
    checks = summary.get("checks")
    if (summary.get("kind") != "capture-boundary-probe"
            or type(summary.get("version")) is not int or summary["version"] != 1
            or summary.get("image") != IMAGE
            or not isinstance(checks, dict) or set(checks) != BASELINE_CHECKS
            or any(value is not True for value in checks.values())
            or summary.get("diagnostics_passed") is not True
            or summary.get("handoff_acceptance") != "BLOCKED"
            or summary.get("independent_code_approval") is not False):
        return 1
    return 0 if expect_unsupported_baseline else 4


def host(output: Path, *, expect_unsupported_baseline: bool = False) -> int:
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    from runner.observer import ObserverCapture
    output.mkdir(parents=True, exist_ok=True)
    inspected = subprocess.run(["docker", "image", "inspect", IMAGE], text=True, capture_output=True, check=True)
    image = json.loads(inspected.stdout)[0]
    reports = {}
    for name, hooks, forge in (("off", False, False), ("on", True, False), ("off-forged", False, True), ("on-forged", True, True)):
        with tempfile.TemporaryDirectory(prefix="capture-probe-") as tmp:
            root = Path(tmp)
            key = root / "host-only-key"
            key.write_bytes(secrets.token_bytes(32))
            key.chmod(0o600)
            command = ["docker", "run", "--rm", "--read-only", "--network", "none", "--cap-drop", "ALL",
                       "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=1g",
                       "--tmpfs", "/workspace:rw,nosuid,nodev,size=32m,mode=1777", "--workdir", "/workspace",
                       "--volume", f"{repo}:/probe-repo:ro", "--env", f"PROBE_HOOKS={int(hooks)}",
                       "--env", f"PROBE_FORGE={int(forge)}", "--entrypoint", "python3", IMAGE]
            capture = ObserverCapture(key, root, command, {})
            command.extend(["/probe-repo/tests/integration/run_capture_probe.py", "--inside"])
            try:
                proc = subprocess.run(command, text=True, capture_output=True, timeout=80, check=False)
                try:
                    report = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    report = {"driver_error": "invalid_json", "stdout": proc.stdout, "stderr": proc.stderr}
                transport_ok = proc.returncode == 0 and report.get("transport", {}).get("exit_code") == 0
                report["docker_exit_code"] = proc.returncode
                report["observed_execution"] = capture.finish(transport_ok=transport_ok)
            except subprocess.TimeoutExpired:
                report = {"driver_error": "timeout", "observed_execution": capture.finish(transport_ok=False)}
            reports[name] = report
            (output / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"{name}: scenario_completed={scenario_completed(report)}, observer={report['observed_execution']['status']}", flush=True)
    observations = {name: hook_observations(reports[name]) for name in ("on", "on-forged")}
    checks = {
        "pinned_image": IMAGE in image.get("RepoDigests", []),
        "runtime_2_0_18": all(r.get("opencode_version") in {"2.0.18", "opencode v2.0.18"} for r in reports.values()),
        "scenarios_completed": all(scenario_completed(r) for r in reports.values()),
        "identical_calls_overlap_and_finish_reversed": all(overlap(r) for r in reports.values()),
        "tool_behavior_unchanged": bool(reports["off"].get("oracle")) and all(oracle_signature(r) == oracle_signature(reports["off"]) for r in reports.values()),
        "missing_producer_not_evidence": all(reports[n]["observed_execution"]["issues"] == ["missing_capture"] for n in ("off", "on")),
        "forged_sidecar_rejected": all(reports[n]["observed_execution"]["issues"] == ["authentication_failed"] for n in ("off-forged", "on-forged")),
        "diagnostic_hooks_toggle": all(not reports[n].get("hooks") for n in ("off", "off-forged")) and all(reports[n].get("hooks") for n in ("on", "on-forged")),
        "shared_id_counterexample": all(o["echo_start_ids"] == ["fixture-call-2", "fixture-call-2"] and o["echo_terminal_values_in_observed_order"] == ["CALL-2", "CALL-1"] for o in observations.values()),
        "caught_throw_has_no_after_hook": all(o["throw_before_count"] == 1 and o["throw_after_count"] == 0 for o in observations.values()),
        "early_after_is_not_final_return": all(o["early_mutate_result"] == "BEFORE-MUTATION" and o["late_mutate_result"] == "FINAL-RETURN" for o in observations.values()),
        "no_capture_eligible": all(r["observed_execution"]["evidence_eligible"] is False for r in reports.values()),
    }
    summary = {"kind": "capture-boundary-probe", "version": 1,
               "image": IMAGE, "image_id": image["Id"], "image_labels": image.get("Config", {}).get("Labels"),
               "checks": checks, "observations": observations, "diagnostics_passed": all(checks.values()),
               "checkout": subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip(),
               "handoff_acceptance": "BLOCKED", "independent_code_approval": False,
               "blockers": ["No demonstrated Loom producer/export boundary is supplied. Diagnostic hooks are not a production observer.",
                            "No authenticated inner results are admitted; signing remains a proposal.",
                            "The caught nested throw produced no execute.after terminal in the pinned-runtime probe.",
                            "Nested calls share the parent id; observed input object identity is not a supported correlation contract.",
                            "An early execute.after observer sees a value that a later hook can change."],
               "scope": "Real pinned OpenCode + original container invoke_opencode + PR host ObserverCapture. Not the complete host CLI or Loom assertion consumer."}
    code = probe_exit_code(summary, expect_unsupported_baseline=expect_unsupported_baseline)
    summary["ci_check"] = {
        "mode": "old-image-rejection-regression" if expect_unsupported_baseline else "capture-acceptance",
        "passed": code == 0,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    # A negative-control PASS never changes BLOCKED or any record's eligibility.
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("capture-probe-results"))
    parser.add_argument(
        "--expect-unsupported-baseline", action="store_true",
        help="Test the pinned old image as a rejection regression; capture stays BLOCKED.",
    )
    args = parser.parse_args()
    if args.inside:
        inside()
    else:
        raise SystemExit(host(args.output, expect_unsupported_baseline=args.expect_unsupported_baseline))