"""Explicit, restricted runtime-to-host capture profile; never trust target files.

The host launcher, selected immutable runtime image, kernel/container engine, and
private host capture directory are trusted. Evaluated code runs as Code Mode data
or in the separate tool container. In-process untrusted plugins are unsupported.
No HMAC or target-held signing key is used by this profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from typing import Any

PROFILE = "codemode-inner/direct-session/v1"
SCHEMA = "opencode-protected-observation/v1"
RUNTIME_SCHEMA = "opencode-local-observation/v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 10000
TOKEN = re.compile(r"[A-Za-z0-9_.:/@-]{1,256}\Z")
IMAGE = re.compile(r"[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}\Z")


class CaptureError(ValueError):
    """Only fixed reason codes; never echo raw capture data."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise CaptureError(reason)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "duplicate_key")
        result[key] = value
    return result


def _bad_number(_):
    raise CaptureError("nonfinite_number")


def strict_json(raw: bytes | str) -> Any:
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_number)
    json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return value


def _token(value) -> bool:
    return isinstance(value, str) and bool(TOKEN.fullmatch(value))


def _int(value) -> bool:
    return type(value) is int and 0 <= value <= 2**53 - 1


def _shape(value, fields):
    _require(isinstance(value, dict) and set(value) == set(fields), "invalid_shape")


def _field(value):
    _require(isinstance(value, dict), "invalid_field")
    state = value.get("state")
    _require(state in ("available", "redacted", "omitted", "truncated"), "invalid_field")
    if state in ("available", "redacted"):
        _shape(value, ("state", "value", "redaction"))
        _require(value["redaction"] == "safe", "unsafe_field")
        _require(len(json.dumps(value["value"], ensure_ascii=False).encode()) <= 32768, "field_limit")
        return {"state": state, "value": value["value"]}
    _shape(value, ("state", "reason"))
    _require(value["reason"] in ("policy_omission", "field_limit", "unsupported_snapshot"), "invalid_reason")
    return dict(value)


def empty_projection(run_id: str) -> dict:
    return {
        "kind": "execution-observer-projection", "version": 2,
        "profile": PROFILE, "run_id": run_id, "status": "unavailable",
        "evidence_eligible": False, "full_handoff_eligible": False,
        "records": [], "parents": [], "issues": [],
        "coverage": {"scope": PROFILE, "native": "unsupported", "delegated_sessions": "unsupported",
                     "in_process_untrusted_plugins": "unsupported", "capture_started": False,
                     "capture_ended": False, "starts": 0, "terminals": 0,
                     "missing_terminals": 0, "omitted_records": None, "truncated": False},
    }


def import_capture(raw: bytes, *, run_id: str, policy_id: str, tools: set[str], transport_ok: bool) -> dict:
    """Validate bytes read by the protected launcher, NOT arbitrary target bytes.

    A checksum detects stream damage; it is not an origin proof. Origin comes from
    the launcher's private mount and isolated runtime. This function alone cannot
    attest a file, and is deliberately not exposed as a file-import CLI command.
    """
    result = empty_projection(run_id)
    parents, calls = {}, {}
    try:
        _require(len(raw) <= MAX_BYTES, "capture_limit")
        _require(bool(raw) and raw.endswith(b"\n"), "missing_or_partial_capture")
        lines = raw.splitlines(keepends=True)
        _require(2 <= len(lines) <= MAX_EVENTS + 2, "frame_count")
        frames = [strict_json(line) for line in lines]
        for seq, frame in enumerate(frames):
            _require(isinstance(frame, dict) and frame.get("run_id") == run_id, "wrong_run")
            _require(type(frame.get("seq")) is int and frame["seq"] == seq, "sequence_gap")
        header, footer = frames[0], frames[-1]
        _shape(header, ("kind", "schema", "profile", "run_id", "seq", "policy_id"))
        _require(header["kind"] == "capture_start" and header["schema"] == SCHEMA
                 and header["profile"] == PROFILE and header["policy_id"] == policy_id, "wrong_profile")
        result["coverage"]["capture_started"] = True
        _shape(footer, ("kind", "run_id", "seq", "event_count", "sha256", "writer_exited", "runtime_exit"))
        _require(footer["kind"] == "capture_end" and footer["writer_exited"] is True, "missing_capture_end")
        _require(type(footer["runtime_exit"]) is int and footer["runtime_exit"] == 0, "runtime_failed")
        _require(type(footer["event_count"]) is int and footer["event_count"] == len(frames) - 2, "count_mismatch")
        _require(footer["sha256"] == hashlib.sha256(b"".join(lines[:-1])).hexdigest(), "stream_modified")
        result["coverage"]["capture_ended"] = True
        session = None
        for expected_source_seq, frame in enumerate(frames[1:-1], 1):
            _shape(frame, ("kind", "run_id", "seq", "observation"))
            _require(frame["kind"] == "observation", "unknown_record")
            event = frame["observation"]
            _require(isinstance(event, dict) and event.get("schema") == RUNTIME_SCHEMA, "unknown_runtime_schema")
            _require(type(event.get("sequence")) is int and event["sequence"] == expected_source_seq, "source_sequence_gap")
            _require(type(event.get("observer_failures")) is int and event["observer_failures"] == 0, "observer_failed")
            actor, parent = event.get("actor"), event.get("parent")
            _shape(actor, ("agent", "session_id", "message_id"))
            _shape(parent, ("invocation_id", "session_id", "message_id", "call_id"))
            _require(all(_token(v) for v in (*actor.values(), *parent.values())), "invalid_identity")
            _require(actor["session_id"] == parent["session_id"] and actor["message_id"] == parent["message_id"], "conflicting_parent")
            session = session or actor["session_id"]
            _require(actor["session_id"] == session, "delegated_session_unsupported")
            common = {"schema", "sequence", "parent", "actor", "observer_failures", "kind"}
            pid, kind = parent["invocation_id"], event.get("kind")
            if kind == "parent_start":
                _shape(event, common | {"boundary", "mode"})
                _require(event["boundary"] == "codemode-engine" and event["mode"] == "code_mode", "wrong_boundary")
                _require(pid not in parents, "duplicate_parent")
                parents[pid] = {"identity": parent, "actor": actor, "start_sequence": frame["seq"],
                                "terminal_sequence": None, "starts": 0, "terminals": 0}
                continue
            _require(pid in parents and parents[pid]["terminal_sequence"] is None, "unknown_or_closed_parent")
            bound = parents[pid]
            _require(parent == bound["identity"] and actor == bound["actor"], "conflicting_identity")
            if kind == "call_start":
                _shape(event, common | {"invocation_id", "tool", "catalog_path", "input", "boundary"})
                iid = event["invocation_id"]
                _require(_token(iid) and iid not in calls, "duplicate_or_invalid_invocation")
                _require(event["tool"] in tools and event["catalog_path"] == "isolated." + event["tool"][len("isolated_"):], "unapproved_registration")
                _require(event["boundary"] == "executable-input", "wrong_boundary")
                calls[iid] = {"invocation_id": iid, "tool": event["tool"], "catalog_path": event["catalog_path"],
                              "actor": actor, "parent": parent, "mode": "code_mode",
                              "runtime_call_id": parent["call_id"], "input": _field(event["input"]),
                              "start_sequence": frame["seq"], "terminal_sequence": None,
                              "outcome": "missing", "evidence_eligible": False}
                bound["starts"] += 1
            elif kind == "call_end":
                outcome = event.get("outcome")
                extra = {"result"} if outcome == "returned" else {"error", "error_representation"} if outcome == "threw" else set()
                _shape(event, common | {"invocation_id", "dispatched", "boundary", "outcome"} | extra)
                iid = event["invocation_id"]
                _require(iid in calls and calls[iid]["terminal_sequence"] is None, "ambiguous_terminal")
                call = calls[iid]
                _require(call["parent"] == parent and call["actor"] == actor, "conflicting_identity")
                _require(event["dispatched"] is True and event["boundary"] == "codemode-json-return", "wrong_boundary")
                _require(outcome in ("returned", "threw", "interrupted"), "invalid_outcome")
                call.update(outcome=outcome, terminal_sequence=frame["seq"])
                if outcome == "returned":
                    call["result"] = _field(event["result"])
                elif outcome == "threw":
                    _require(event["error_representation"] == "codemode-catch-name-message/v1", "unsupported_error_view")
                    call["error"] = _field(event["error"])
                    call["error_representation"] = event["error_representation"]
                else:
                    result["issues"].append("interrupted_call")
                bound["terminals"] += 1
            elif kind == "parent_end":
                _shape(event, common | {"admitted", "dispatched", "terminals", "missing_terminals", "unsupported_dispatches",
                                       "unavailable_fields", "scope", "evidence_eligible"})
                _require(event["scope"] == "one-codemode-engine-invocation" and event["evidence_eligible"] is False, "wrong_parent_profile")
                for name in ("admitted", "dispatched", "terminals", "missing_terminals", "unsupported_dispatches", "unavailable_fields"):
                    _require(_int(event[name]), "invalid_accounting")
                _require(event["admitted"] == event["dispatched"] == bound["starts"]
                         and event["terminals"] == bound["terminals"], "parent_count_mismatch")
                _require(event["missing_terminals"] == event["unsupported_dispatches"] == 0, "incomplete_parent")
                if event["unavailable_fields"]:
                    result["issues"].append("unsupported_snapshot")
                bound["terminal_sequence"] = frame["seq"]
            else:
                raise CaptureError("unknown_runtime_record")
        _require(bool(parents) and bool(calls), "empty_capture")
        _require(all(p["terminal_sequence"] is not None for p in parents.values()), "missing_parent_end")
        _require(all(c["terminal_sequence"] is not None for c in calls.values()), "missing_terminal")
        for call in calls.values():
            for name in ("input", "result", "error"):
                if name in call and call[name]["state"] != "available":
                    result["issues"].append("incomplete_field")
                    if call[name]["state"] == "truncated":
                        result["coverage"]["truncated"] = True
        if not transport_ok:
            result["issues"].append("transport_failed")
        result["issues"] = sorted(set(result["issues"]))
        result["status"] = "incomplete" if result["issues"] else "complete"
        result["evidence_eligible"] = not result["issues"]
        result["coverage"].update(starts=len(calls), terminals=sum(c["terminal_sequence"] is not None for c in calls.values()),
                                  missing_terminals=0, omitted_records=0)
        for call in calls.values():
            call["evidence_eligible"] = result["evidence_eligible"]
        result["records"], result["parents"] = list(calls.values()), list(parents.values())
    except (CaptureError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        result["status"] = "invalid"
        result["issues"] = [str(exc) if isinstance(exc, CaptureError) else "malformed_capture"]
        result["records"], result["parents"] = [], []
        result["evidence_eligible"] = False
    return result


def _run(args, *, timeout=120, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout, **kwargs)


def read_private(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_BYTES, "unsafe_capture_file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_BYTES + 1)
        _require(len(data) <= MAX_BYTES, "capture_limit")
        return data
    finally:
        os.close(fd)


def invoke(args, *, _test_receive=None, _test_prepare=None) -> int:
    # _test_receive is a host-only fault-injection seam, never a CLI/target option.
    for value in (args.image, args.tool_image):
        _require(bool(IMAGE.fullmatch(value)), "immutable_image_required")
    policy_raw = Path(args.policy_file).read_bytes()
    policy = strict_json(policy_raw)
    _require(isinstance(policy, dict) and policy.get("version") == 1, "invalid_policy")
    _require(len(policy_raw) <= 1024 * 1024, "policy_limit")
    _require(isinstance(policy.get("allowed_values"), list) and isinstance(policy.get("secrets"), list)
             and all(isinstance(s, str) and s for s in policy["secrets"]), "invalid_policy")
    policy_id = hashlib.sha256(policy_raw).hexdigest()
    tools = strict_json(Path(args.tools_file).read_bytes())
    _require(isinstance(tools, list) and 0 < len(tools) <= 64, "invalid_tools")
    _require(all(isinstance(t, dict) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", t.get("name", "")) for t in tools), "invalid_tools")
    _require(len({t["name"] for t in tools}) == len(tools), "duplicate_tool")
    program = Path(args.program_file).read_text()
    _require(len(program.encode()) <= 128 * 1024, "program_limit")
    run_id = secrets.token_hex(32)
    prefix = "capture-" + run_id[:16]
    network, target, runtime = prefix + "-net", prefix + "-tools", prefix + "-runtime"
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": "opencode-eval-runner/v1", "profile": PROFILE, "run_id": run_id,
              "runtime_image": args.image, "tool_image": args.tool_image, "policy_id": policy_id,
              "observed_execution": empty_projection(run_id)}
    code = 4
    with tempfile.TemporaryDirectory(prefix="protected-capture-") as tmp:
        root = Path(tmp)
        inputs, capture = root / "input", root / "capture"
        inputs.mkdir(mode=0o755)
        capture.mkdir(mode=0o777)
        capture.chmod(0o777)  # the mode-0700 parent is never mounted in either container
        (inputs / "request.json").write_text(json.dumps({"run_id": run_id, "program": program, "tools": tools,
            "tool_url": "http://" + target + ":8080", "policy_id": policy_id, "observe": not args.no_observe}))
        (inputs / "policy.json").write_bytes(policy_raw)
        for file in inputs.iterdir():
            file.chmod(0o644)  # private host directory; only trusted runtime receives this mount
        if _test_prepare is not None:
            _test_prepare(capture)
        hardening = ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                     "--pids-limit", "128", "--memory", "1g", "--cpus", "2", "--user", "1000:1000"]
        try:
            for image in {args.image, args.tool_image}:
                _run(["docker", "pull", image])
            _run(["docker", "network", "create", "--internal", network])
            _run(["docker", "run", "-d", "--name", target, "--network", network, *hardening,
                  "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m", args.tool_image])
            command = ["docker", "run", "--name", runtime, "--network", network, *hardening,
                       "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=1g",
                       "--tmpfs", "/workspace:rw,nosuid,nodev,size=32m,mode=1777",
                       "--volume", str(inputs) + ":/input:ro", "--volume", str(capture) + ":/capture:rw",
                       "--entrypoint", "python3", args.image, "/opt/protected/invoke.py"]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout, check=False)
            # Do not preserve raw CLI/target stdout or stderr. Only trusted supervisor
            # status data is retained, and it cannot inject the observation projection.
            envelope = strict_json(completed.stdout)
            _shape(envelope, ("profile", "run_id", "runtime_exit", "script_output", "writer_exited"))
            _require(envelope["profile"] == PROFILE and envelope["run_id"] == run_id, "invalid_supervisor")
            result["runtime_exit"] = envelope["runtime_exit"]
            result["script_output"] = envelope["script_output"]
            if args.no_observe:
                result["observed_execution"]["issues"] = ["capture_not_requested"]
                code = 0 if completed.returncode == 0 else 2
            else:
                try:
                    raw = read_private(capture / "events.jsonl")
                except FileNotFoundError:
                    raw = b""
                if _test_receive is not None:
                    raw = _test_receive(raw, run_id, policy_id)
                result["observed_execution"] = import_capture(raw, run_id=run_id, policy_id=policy_id,
                    tools={"isolated_" + t["name"] for t in tools},
                    transport_ok=completed.returncode == 0 and envelope["runtime_exit"] == 0 and envelope["writer_exited"] is True)
                code = 0 if result["observed_execution"]["evidence_eligible"] else 4
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError):
            result["observed_execution"] = empty_projection(run_id)
            result["observed_execution"]["issues"] = ["protected_transport_failed"]
            code = 2
        finally:
            for name in (runtime, target):
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20, check=False)
            subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=20, check=False)
        output.write_text(json.dumps(result, indent=2) + "\n")
        output.chmod(0o600)
    return code


def parser():
    p = argparse.ArgumentParser(description="Protected, provider-free direct-session Code Mode capture; in-process target plugins are unsupported.")
    p.add_argument("--image", required=True, help="Explicitly trusted immutable protected runtime image")
    p.add_argument("--tool-image", required=True, help="Untrusted isolated JSON tool server image, listening on port 8080")
    p.add_argument("--program-file", required=True)
    p.add_argument("--tools-file", required=True)
    p.add_argument("--policy-file", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument("--no-observe", action="store_true", help="Same restricted profile with capture disabled, for behavior comparison")
    return p


def main():
    try:
        return invoke(parser().parse_args())
    except (CaptureError, OSError, ValueError):
        print("protected-capture: invalid configuration", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
