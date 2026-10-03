#!/usr/bin/env python3
"""Test the local runtime seam with the existing deterministic runner fixture.

Not Loom's unpublished smoke or a protected-producer acceptance test. Every raw
value is fixed fixture data. No provider credentials or host databases are used.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from runner.observer import ObserverCapture

spec = importlib.util.spec_from_file_location("base_probe", REPO / "tests/integration/run_capture_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
EXTRA_HOOKS = '''
    await ctx.tool.hook("execute.before", (event: any) => {
      if (String(event.tool) === "captureprobe_echo") event.input = { tag: "dispatched" }
    })
    await ctx.tool.hook("execute.observed", (event: any) => {
      if (process.env.PROBE_FAIL_OBSERVER === "1") throw new Error("fixture-observer-io-failure")
      log(hookPath, { phase: "runtime-observed", event })
    })
    await ctx.tool.hook("execute.native-observed", (event: any) => {
      if (process.env.PROBE_FAIL_OBSERVER === "1") throw new Error("fixture-native-observer-io-failure")
      log(hookPath, { phase: "runtime-native-observed", event })
    })
'''


def run(image: str, output: Path):
    if "@sha256:" not in image:
        raise ValueError("the runtime probe requires an immutable registry digest")
    output.mkdir(parents=True, exist_ok=True)
    reports = {}
    fixture_hash = None
    for name, observed, forge, failure in (
        ("off", False, False, False), ("on", True, False, False),
        ("forged", True, True, False), ("observer-fails", True, False, True),
    ):
        with tempfile.TemporaryDirectory(prefix="local-runtime-probe-") as tmp:
            root = Path(tmp)
            fixture = root / "fixture"
            (fixture / "tests/integration").mkdir(parents=True)
            shutil.copyfile(REPO / "tests/integration/run_capture_probe.py", fixture / "tests/integration/run_capture_probe.py")
            source = (REPO / "tests/integration/capture_probe.ts").read_text()
            anchor = '    writeFileSync("/tmp/capture-probe-loaded", "loaded")'
            if source.count(anchor) != 1:
                raise ValueError("unrecognized preserved runner fixture")
            source = source.replace(anchor, EXTRA_HOOKS + anchor)
            fixture_hash = hashlib.sha256(source.encode()).hexdigest()
            (fixture / "tests/integration/capture_probe.ts").write_text(source)
            key = root / "host-only-key"
            key.write_bytes(secrets.token_bytes(32))
            key.chmod(0o600)
            command = [
                "docker", "run", "--rm", "--read-only", "--network", "none", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=1g",
                "--tmpfs", "/workspace:rw,nosuid,nodev,size=32m,mode=1777", "--workdir", "/workspace",
                "--volume", f"{fixture}:/probe-repo:ro", "--env", "PROBE_HOOKS=1",
                "--env", f"PROBE_FORGE={int(forge)}", "--env", f"PROBE_FAIL_OBSERVER={int(failure)}",
                "--env", f"OPENCODE_EVAL_OBSERVATIONS={int(observed)}", "--entrypoint", "python3", image,
            ]
            capture = ObserverCapture(key, root, command, {})
            command.extend(["/probe-repo/tests/integration/run_capture_probe.py", "--inside"])
            try:
                proc = subprocess.run(command, text=True, capture_output=True, timeout=90, check=False)
                report = json.loads(proc.stdout)
                report["docker_exit_code"] = proc.returncode
                report["observed_execution"] = capture.finish(
                    transport_ok=proc.returncode == 0 and report.get("transport", {}).get("exit_code") == 0)
            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                report = {"probe_error": "container_timeout_or_invalid_json", "observed_execution": capture.finish(transport_ok=False)}
            reports[name] = report
            (output / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")
            print(name, "scenario_completed=", probe.scenario_completed(report), flush=True)

    def observations(name):
        return [item["record"]["event"] for item in reports[name].get("hooks", [])
                if item.get("record", {}).get("phase") == "runtime-observed"]

    def native_observations(name):
        return [item["record"]["event"] for item in reports[name].get("hooks", [])
                if item.get("record", {}).get("phase") == "runtime-native-observed"]

    checks = {
        "all_scripts_completed": all(probe.scenario_completed(r) for r in reports.values()),
        "product_outcomes_unchanged": bool(reports["off"].get("oracle")) and all(
            probe.oracle_signature(r) == probe.oracle_signature(reports["off"]) for r in reports.values()),
        "opt_in_only": not observations("off") and not native_observations("off"),
        "observer_failure_does_not_change_results": probe.scenario_completed(reports["observer-fails"]),
        "normal_invoke_runtime_version": all(
            "2.0.18-eval.3" in str(r.get("opencode_version") or "") for r in reports.values()
        ),
        "forged_sidecar_rejected": reports["forged"]["observed_execution"]["issues"] == ["authentication_failed"],
        "no_false_capture_acceptance": all(r["observed_execution"]["evidence_eligible"] is False for r in reports.values()),
    }
    for variant in ("on", "forged"):
        records = observations(variant)
        starts = [e for e in records if e.get("kind") == "call_start"]
        ends = [e for e in records if e.get("kind") == "call_end"]
        by_id = {e["invocation_id"]: e for e in ends}
        echoes = [e for e in starts if e.get("tool") == "captureprobe_echo"]
        throwing = [e for e in starts if e.get("tool") == "captureprobe_throws"]
        mutation = [e for e in starts if e.get("tool") == "captureprobe_mutate"]
        denial = [e for e in starts if e.get("tool") == "captureprobe_denied"]
        oracle = [e["record"] for e in reports[variant].get("oracle", []) if e["record"].get("name") == "echo" and e["record"].get("phase") == "start"]
        actual = oracle[0].get("context", {}) if oracle else {}
        def terminal(start):
            return by_id.get(start["invocation_id"], {})
        native_records = native_observations(variant)
        native_starts = [e for e in native_records if e.get("kind") == "call_start"]
        native_ends = [e for e in native_records if e.get("kind") == "call_end"]
        outer_execute = [e for e in native_starts if e.get("tool") == "execute"]
        native_by_id = {e.get("invocation_id"): e for e in native_ends}
        checks.update({
            f"{variant}:all_inner_terminals": len(starts) == len(ends) == 6 and len(by_id) == 6,
            f"{variant}:runtime_id_uniqueness": len({e["invocation_id"] for e in starts}) == 6,
            f"{variant}:exact_dispatched_inputs": len(echoes) == 2 and all(e.get("input", {}).get("value") == {"tag": "dispatched"} for e in echoes),
            f"{variant}:reverse_completion_correlated": len(echoes) == 2 and terminal(echoes[0]).get("result", {}).get("value") == "CALL-1" and terminal(echoes[1]).get("result", {}).get("value") == "CALL-2" and terminal(echoes[1]).get("sequence", 0) < terminal(echoes[0]).get("sequence", 0),
            f"{variant}:actual_actor_parent": len(echoes) == 2 and all(e.get("actor") == {"agent": actual.get("agent"), "session_id": actual.get("sessionID"), "message_id": actual.get("messageID")} and e.get("parent", {}).get("call_id") == actual.get("id") for e in echoes),
            f"{variant}:genuine_throw_terminal": len(throwing) == 1 and terminal(throwing[0]).get("outcome") == "threw" and "THROW-RAW" in terminal(throwing[0]).get("error", {}).get("value", {}).get("message", ""),
            f"{variant}:final_mutated_return": len(mutation) == 1 and terminal(mutation[0]).get("result", {}).get("value") == "FINAL-RETURN",
            f"{variant}:denial_stays_string": len(denial) == 1 and terminal(denial[0]).get("result", {}).get("value") == '{"ok":false,"error":"denied"}',
            f"{variant}:owned_parent_completion": bool(records) and records[-1].get("kind") == "parent_end" and records[-1].get("missing_terminals") == 0 and records[-1].get("observer_failures") == 0,
            f"{variant}:native_outer_execute_observed": len(outer_execute) == 1 and outer_execute[0].get("mode") == "native"
                and outer_execute[0].get("parent") is None
                and outer_execute[0].get("invocation_id") in native_by_id,
            f"{variant}:inner_parent_matches_native_execute": len(outer_execute) == 1 and bool(echoes)
                and all(e.get("parent", {}).get("invocation_id") == outer_execute[0].get("invocation_id") for e in starts),
            f"{variant}:shared_sequence_orders_native_and_inner": len(outer_execute) == 1 and bool(starts)
                and outer_execute[0].get("sequence", 0) < min(e.get("sequence", 0) for e in starts)
                and max(e.get("sequence", 0) for e in ends) < native_by_id[outer_execute[0].get("invocation_id")].get("sequence", 0),
        })
    summary = {
        "kind": "normal-invoke-runtime-seam-probe", "version": 2, "image": image,
        "runner_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "runtime_source_revision": "cd9a14a6b688d4021bee381dfd39d2cef9c0f862",
        "versions": {name: r.get("opencode_version") for name, r in reports.items()},
        "diagnostic_fixture_sha256": fixture_hash, "checks": checks, "runtime_seam_passed": all(checks.values()),
        "handoff_acceptance": "BLOCKED", "independent_code_approval": False,
        "limitations": [
            "The local hook is a runtime event seam, not a protected producer/export channel.",
            "This does not run Loom's uncommitted preserved producer/consumer smoke.",
            "Native and Code Mode semantic observations are diagnostic only; the in-process plugin can share runtime authority.",
            "Delegated-session identity follows the same Tool.Context path but is not exercised by this fixture.",
            "A target-unforgeable collector for the normal in-process plugin remains the feasibility blocker.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["runtime_seam_passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.image, args.output))
