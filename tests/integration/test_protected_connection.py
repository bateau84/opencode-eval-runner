"""Actual Docker/runtime -> private channel -> host importer acceptance probe.

Fault injection edits NEW bytes received from actual executions on the host. It
never invents producer records or changes historical captures. Target attacks and
host transport faults are reported separately, not conflated as the same actor.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from runner import protected

SECRET = "FIXTURE-SECRET-NOT-A-CREDENTIAL-8675309"
ATTACK = {f"{path}_{operation}_denied": True for path in ("capture", "runtime_root", "runtime_input", "host")
          for operation in ("read", "write", "delete")}
SPOOF = {"observed_execution": {"evidence_eligible": True, "run_id": "invented-run"}, "actor": {"agent": "fabricated"}}
PROGRAM = '''
if (typeof fetch !== "undefined") throw new Error("script network must be absent");
const pair = await Promise.all([tools.isolated.echo({tag:"identical"}), tools.isolated.echo({tag:"identical"})]);
if (pair[0] !== "CALL-1" || pair[1] !== "CALL-2") throw new Error("bad pair");
if (await tools.isolated.denied({}) !== '{"ok":false,"error":"denied"}') throw new Error("bad denial");
const obj = await tools.isolated.denied_object({});
if (obj.ok !== false || obj.error !== "denied") throw new Error("bad object");
if (await tools.isolated.null({}) !== null) throw new Error("bad null");
let caught = false;
try { await tools.isolated.throws({}); } catch (e) { caught = String(e.message).includes("THROW-RAW"); }
if (!caught) throw new Error("bad throw");
const attack = await tools.isolated.attack({});
if (Object.values(attack).some(v => v !== true)) throw new Error("capture reachable by tool");
await tools.isolated.spoof({});
return "script-output-only";
'''
REDACTION_PROGRAM = '''
await tools.isolated.secret({});
await tools.isolated.encoded({});
await tools.isolated.structured({});
await tools.isolated.unknown({});
await tools.isolated.large({});
return "script-output-only";
'''


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--image", required=True)
    cli.add_argument("--tool-image", required=True)
    cli.add_argument("--output", required=True)
    options = cli.parse_args()
    out = Path(options.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    checks = {}
    originals = {}
    with tempfile.TemporaryDirectory(prefix="protected-proof-") as tmp:
        root = Path(tmp)
        names = ("echo", "denied", "denied_object", "null", "throws", "attack", "spoof", "redirect", "secret", "encoded", "structured", "unknown", "large")
        tools = [{"name": name, "input": {"type": "object", "properties": {"tag": {"type": "string"}}, "additionalProperties": False}} for name in names]
        policy = {"version": 1, "secrets": [SECRET], "allowed_values": [
            {}, {"tag": "identical"}, "CALL-1", "CALL-2", '{"ok":false,"error":"denied"}',
            {"ok": False, "error": "denied"}, None, {"name": "Error", "message": "THROW-RAW"}, ATTACK, SPOOF,
            {"name": "Error", "message": "isolated_tool_transport_failed"},
            "script-output-only", "[REDACTED]", {"password": "[REDACTED]"}, "ø" * 9000,
        ]}
        for name, value in (("tools.json", tools), ("policy.json", policy)):
            (root / name).write_text(json.dumps(value))
        (root / "program.js").write_text(PROGRAM)
        args = protected.parser().parse_args(["--image", options.image, "--tool-image", options.tool_image,
            "--program-file", str(root / "program.js"), "--tools-file", str(root / "tools.json"),
            "--policy-file", str(root / "policy.json"), "--output", str(out / "good.json")])

        def receive(name, transform=lambda raw: raw):
            def process(raw, run_id, policy_id):
                originals[name] = raw
                (out / (name + ".original.jsonl")).write_bytes(raw)
                modified = transform(raw)
                if modified != raw:
                    (out / (name + ".received.jsonl")).write_bytes(modified)
                return modified
            return process

        tool_oracle = []
        def target_probe(target, runtime_state, target_state):
            command = ["docker", "exec", "--user", "1000:1000", target, "python3", "-c",
                       "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/oracle').read().decode())"]
            tool_oracle.extend(json.loads(subprocess.check_output(command, text=True)))
            (out / "tool-oracle.json").write_text(json.dumps(tool_oracle, indent=2) + "\n")
            checks["separate_mounts_and_process_namespace"] = not target_state["Mounts"] and not target_state["HostConfig"].get("PidMode") and runtime_state["State"]["Running"] is False
            checks["target_no_signer_or_credentials"] = not any("TOKEN" in e or "SECRET" in e for e in target_state["Config"].get("Env", []))
        code = protected.invoke(args, _test_receive=receive("good"), _test_target_probe=target_probe)
        good = json.loads(Path(args.output).read_text())
        projection = good["observed_execution"]
        records = projection["records"]
        checks["legitimate_connection_eligible"] = code == 0 and projection["evidence_eligible"] is True
        checks["separate_receipt_binds_capture"] = good.get("collection_receipt") == {
            "sha256": hashlib.sha256(originals["good"]).hexdigest(), "bytes": len(originals["good"])}
        checks["receipt_profile_explicit"] = projection.get("version") == 5 and projection.get("launch_id") == good["launch_id"] and projection["coverage"].get("accounting_complete") is True
        echo = [r for r in records if r["tool"] == "isolated_echo"]
        checks["distinct_correlated_reverse_completion"] = (len(echo) == 2 and echo[0]["invocation_id"] != echo[1]["invocation_id"]
            and echo[0]["input"]["value"] == echo[1]["input"]["value"] == {"tag": "identical"}
            and echo[0]["result"]["value"] == "CALL-1" and echo[1]["result"]["value"] == "CALL-2"
            and echo[1]["terminal_sequence"] < echo[0]["terminal_sequence"])
        bytool = {r["tool"]: r for r in records}
        checks["target_cannot_access_capture"] = bytool.get("isolated_attack", {}).get("result", {}).get("value") == ATTACK
        checks["denial_string_preserved"] = bytool.get("isolated_denied", {}).get("result", {}).get("value") == '{"ok":false,"error":"denied"}'
        checks["denial_object_preserved"] = bytool.get("isolated_denied_object", {}).get("result", {}).get("value") == {"ok": False, "error": "denied"}
        checks["null_present"] = "value" in bytool.get("isolated_null", {}).get("result", {}) and bytool["isolated_null"]["result"]["value"] is None
        checks["caught_error_preserved"] = bytool.get("isolated_throws", {}).get("error", {}).get("value") == {"name": "Error", "message": "THROW-RAW"}
        checks["identity_preserved"] = bool(records) and all(r["actor"]["message_id"] == r["parent"]["message_id"]
            and r["actor"]["session_id"] == r["parent"]["session_id"] and r["runtime_call_id"] == "protected-execute" for r in records)
        checks["actual_image_and_input_binding"] = good.get("launched_images_verified") is True and good["launch"]["runtime_image"] == options.image and good["launch"]["program_sha256"] == hashlib.sha256(PROGRAM.encode()).hexdigest()
        checks["spoof_is_only_a_returned_value"] = bytool.get("isolated_spoof", {}).get("result", {}).get("value") == SPOOF and all(r["actor"]["agent"] != "fabricated" for r in records)
        starts = {e["context"]["invocation_id"]: e for e in tool_oracle if e["phase"] == "start"}
        ends = {e["context"]["invocation_id"]: e for e in tool_oracle if e["phase"] in ("returned", "threw")}
        checks["records_match_independent_tool_oracle"] = len(starts) == len(ends) == len(records) == 8 and all(
            r["invocation_id"] in starts and r["input"]["value"] == starts[r["invocation_id"]]["input"]
            and r["actor"] == {k: starts[r["invocation_id"]]["context"][k] for k in ("agent", "session_id", "message_id")}
            and r["outcome"] == ends[r["invocation_id"]]["phase"]
            and (r.get("result", {}).get("value") == ends[r["invocation_id"]]["value"] if r["outcome"] == "returned"
                 else r["error"]["value"]["message"] == ends[r["invocation_id"]]["value"])
            for r in records)
        checks["scope_exclusions_explicit"] = projection["full_handoff_eligible"] is False and projection["coverage"]["native"] == "unsupported" and projection["coverage"]["delegated_sessions"] == "unsupported"
        checks["no_script_output_as_inner_result"] = bool(records) and all(r.get("result", {}).get("value") != "script-output-only" for r in records)

        # Also exercise the user-facing entrypoint, not only a library call.
        args.output = str(out / "off.json")
        command = [sys.executable, str(ROOT / "bin/opencode-eval-runner"), "observe", "--image", options.image,
                   "--tool-image", options.tool_image, "--program-file", args.program_file,
                   "--tools-file", args.tools_file, "--policy-file", args.policy_file, "--output", args.output, "--no-observe"]
        off = subprocess.run(command, capture_output=True, text=True, timeout=120)
        off_result = json.loads(Path(args.output).read_text())
        checks["observer_off_same_program_result"] = off.returncode == 0 and off_result["script_output"] == good["script_output"] == {"state": "available", "value": "script-output-only"}
        checks["observer_off_no_evidence"] = off_result["observed_execution"]["evidence_eligible"] is False
        command.remove("--no-observe")
        command[command.index("--output") + 1] = str(out / "public-cli.json")
        public = subprocess.run(command, capture_output=True, text=True, timeout=120)
        public_result = json.loads((out / "public-cli.json").read_text())
        checks["public_cli_legitimate_capture"] = public.returncode == 0 and public_result["observed_execution"]["evidence_eligible"] is True and len(public_result["observed_execution"]["records"]) == 8

        def replace_result(raw):
            return raw.replace(b'CALL-1', b'FORGED', 1)
        def remove_middle(raw):
            lines = raw.splitlines(keepends=True)
            return b"".join(lines[:2] + lines[3:])
        def reorder(raw):
            lines = raw.splitlines(keepends=True)
            lines[2], lines[3] = lines[3], lines[2]
            return b"".join(lines)
        def rehash_deleted_terminal(raw):
            frames = [json.loads(line) for line in raw.splitlines()]
            index = next(i for i, f in enumerate(frames) if f.get("observation", {}).get("kind") == "call_end")
            del frames[index]
            for i, f in enumerate(frames): f["seq"] = i
            prefix = b"".join((json.dumps(f) + "\n").encode() for f in frames[:-1])
            frames[-1]["sha256"] = hashlib.sha256(prefix).hexdigest()
            frames[-1]["event_count"] = len(frames) - 2
            return prefix + (json.dumps(frames[-1]) + "\n").encode()
        def rehash_forged_result(raw):
            lines = replace_result(raw).splitlines(keepends=True)
            footer = json.loads(lines[-1])
            footer["sha256"] = hashlib.sha256(b"".join(lines[:-1])).hexdigest()
            return b"".join(lines[:-1]) + (json.dumps(footer) + "\n").encode()
        transforms = {"resealed_forgery": rehash_forged_result, "rehashed_deletion": rehash_deleted_terminal, "forged": replace_result, "replay": lambda raw: originals["good"], "deleted_record": remove_middle,
                      "deleted_footer": lambda raw: b"".join(raw.splitlines(keepends=True)[:-1]),
                      "partial": lambda raw: raw[:-5], "reordered": reorder,
                      "appended": lambda raw: raw + b'{"kind":"observation"}\n'}
        for name, transform in transforms.items():
            args.output = str(out / (name + ".json"))
            code = protected.invoke(args, _test_receive=receive(name, transform))
            result = json.loads(Path(args.output).read_text())
            checks[name + "_real_stream_rejected"] = (out / (name + ".received.jsonl")).exists() and code != 0 and result["observed_execution"]["evidence_eligible"] is False and result["observed_execution"]["records"] == []
            print(name, code, result["observed_execution"]["issues"], flush=True)

        args.output = str(out / "io-failure.json")
        code = protected.invoke(args, _test_prepare=lambda capture: capture.chmod(0o555))
        io_failed = json.loads(Path(args.output).read_text())
        checks["io_failure_not_evidence"] = code != 0 and io_failed["observed_execution"]["evidence_eligible"] is False
        checks["io_failure_did_not_change_script"] = io_failed.get("script_output") == {"state": "available", "value": "script-output-only"}

        # Verify the CLI's positive path too, including execution of the verified snapshot.
        args.output = str(out / "snapshot.json")
        def change_original(_capture):
            (root / "program.js").write_text('throw new Error("mutated source must not execute");')
        snapshot_code = protected.invoke(args, _test_prepare=change_original)
        snapshot_result = json.loads(Path(args.output).read_text())
        checks["executes_the_same_input_snapshot"] = snapshot_code == 0 and snapshot_result["script_output"] == {"state": "available", "value": "script-output-only"}
        (root / "program.js").write_text('try { await tools.isolated.redirect({}); } catch (e) {} return "script-output-only";')
        args.output = str(out / "redirect.json")
        redirect_code = protected.invoke(args, _test_receive=receive("redirect"))
        redirect_result = json.loads(Path(args.output).read_text())
        redirect_records = redirect_result["observed_execution"]["records"]
        checks["tool_cannot_redirect_bridge_to_local_services"] = (redirect_code == 0 and len(redirect_records) == 1
            and redirect_records[0].get("error", {}).get("value") == {"name": "Error", "message": "isolated_tool_transport_failed"})
        (root / "program.js").write_text(REDACTION_PROGRAM)
        args.output = str(out / "redaction.json")
        code = protected.invoke(args, _test_receive=receive("redaction"))
        redaction = json.loads(Path(args.output).read_text())
        states = {r["tool"]: r.get("result", {}).get("state") for r in redaction["observed_execution"]["records"]}
        checks["redaction_before_persistence"] = SECRET.encode() not in originals.get("redaction", b"") and base64.b64encode(SECRET.encode()) not in originals.get("redaction", b"") and b"ANOTHER-UNKNOWN-FIXTURE-SECRET" not in originals.get("redaction", b"")
        checks["redaction_and_omission_non_evidence"] = code == 4 and states == {"isolated_secret": "redacted", "isolated_encoded": "redacted", "isolated_structured": "redacted", "isolated_unknown": "omitted", "isolated_large": "truncated"}
        checks["unsafe_unknown_not_persisted"] = b"UNKNOWN-NONALLOWLISTED-TEXT" not in originals.get("redaction", b"")
        checks["redaction_did_not_change_script"] = redaction["script_output"] == {"state": "available", "value": "script-output-only"}
    summary = {"profile": protected.PROFILE, "runtime_image": options.image, "tool_image": options.tool_image,
               "checks": checks, "passed": all(checks.values()), "full_handoff_accepted": False,
               "independent_review": "not_performed", "native": "open", "delegated_sessions": "open",
               "in_process_untrusted_plugins": "unsupported",
               "fault_injection": "host-side receive shim modifies actual new runtime streams; target attacks are separate",
               "checkout": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
