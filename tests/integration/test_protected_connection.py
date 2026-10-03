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
PROGRAM = '''
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
        names = ("echo", "denied", "denied_object", "null", "throws", "attack", "secret", "encoded", "structured", "unknown", "large")
        tools = [{"name": name, "input": {"type": "object", "properties": {"tag": {"type": "string"}}, "additionalProperties": False}} for name in names]
        policy = {"version": 1, "secrets": [SECRET], "allowed_values": [
            {}, {"tag": "identical"}, "CALL-1", "CALL-2", '{"ok":false,"error":"denied"}',
            {"ok": False, "error": "denied"}, None, {"name": "Error", "message": "THROW-RAW"}, ATTACK,
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

        code = protected.invoke(args, _test_receive=receive("good"))
        good = json.loads(Path(args.output).read_text())
        projection = good["observed_execution"]
        checks["legitimate_connection_eligible"] = code == 0 and projection["evidence_eligible"] is True
        records = projection["records"]
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

        def replace_result(raw):
            return raw.replace(b'CALL-1', b'FORGED', 1)
        def remove_middle(raw):
            lines = raw.splitlines(keepends=True)
            return b"".join(lines[:2] + lines[3:])
        def reorder(raw):
            lines = raw.splitlines(keepends=True)
            lines[2], lines[3] = lines[3], lines[2]
            return b"".join(lines)
        transforms = {"forged": replace_result, "replay": lambda raw: originals["good"], "deleted_record": remove_middle,
                      "deleted_footer": lambda raw: b"".join(raw.splitlines(keepends=True)[:-1]),
                      "partial": lambda raw: raw[:-5], "reordered": reorder,
                      "appended": lambda raw: raw + b'{"kind":"observation"}\n'}
        for name, transform in transforms.items():
            args.output = str(out / (name + ".json"))
            code = protected.invoke(args, _test_receive=receive(name, transform))
            result = json.loads(Path(args.output).read_text())
            checks[name + "_real_stream_rejected"] = code != 0 and result["observed_execution"]["evidence_eligible"] is False and result["observed_execution"]["records"] == []
            print(name, code, result["observed_execution"]["issues"], flush=True)

        args.output = str(out / "io-failure.json")
        code = protected.invoke(args, _test_prepare=lambda capture: capture.chmod(0o555))
        io_failed = json.loads(Path(args.output).read_text())
        checks["io_failure_not_evidence"] = code != 0 and io_failed["observed_execution"]["evidence_eligible"] is False
        checks["io_failure_did_not_change_script"] = io_failed.get("script_output") == {"state": "available", "value": "script-output-only"}

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
