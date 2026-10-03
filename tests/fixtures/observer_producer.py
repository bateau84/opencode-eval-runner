"""INSECURE TEST FIXTURE ONLY: independent encoder, not a production observer.

The fake OCI engine runs on the test host. It can read the fixture-only key;
this deliberately does NOT claim a protected OpenCode execution-hook boundary.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path


def field(value):
    return {"state": "available", "redaction": "safe", "value": value}


def start(invocation="inner-1", *, mode="code_mode", value=None):
    return {
        "kind": "call_start", "invocation_id": invocation, "tool": "sentinel",
        "input": field({"which": invocation} if value is None else value),
        "actor": {"agent": "worker", "session_id": "child-session"},
        "parent": {"session_id": "parent-session", "call_id": "shared-execute"} if mode == "code_mode" else None,
        "mode": mode,
    }


def end(invocation="inner-1", *, value="actual-sentinel", outcome="returned"):
    return {"kind": "call_end", "invocation_id": invocation, "outcome": outcome,
            "result" if outcome == "returned" else "error": field(value)}


def events(*calls):
    return [
        {"kind": "capture_start", "version": 1, "source": "loom-execution-hook",
         "boundary": "tool-return-to-caller", "correlation": "execution-invocation-id",
         "ordering": "monotonic-sequence"},
        *calls,
        {"kind": "capture_end", "calls_started": sum(c["kind"] == "call_start" for c in calls),
         "calls_ended": sum(c["kind"] == "call_end" for c in calls),
         "omitted_records": 0, "truncated": False, "unsupported": []},
    ]


def encode(items, key, run_id, transform=None):
    previous = bytes(32)
    lines = []
    for seq, item in enumerate(items):
        event = {**item, "run_id": run_id, "seq": item.get("seq", seq)}
        raw = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode()
        if transform:
            raw = transform(seq, raw)
        mac = hmac.new(key, b"opencode-eval-observer/v1\0" + run_id.encode() + b"\0" + previous + raw, hashlib.sha256).digest()
        lines.append(json.dumps({"payload": base64.b64encode(raw).decode(), "mac": mac.hex()}).encode())
        previous = mac
    return b"\n".join(lines) + b"\n"


def main():
    command = sys.argv[1:]
    mounts, environment = {}, {}
    for index, argument in enumerate(command[:-1]):
        if argument == "--volume":
            source, target, _ = command[index + 1].rsplit(":", 2)
            mounts[target] = source
        elif argument == "--env":
            name, _, value = command[index + 1].partition("=")
            environment[name] = value if "=" in command[index + 1] else os.environ.get(name, "")
    mode = os.environ.get("FIXTURE_MODE", "good")
    Path(os.environ["FIXTURE_COMMAND"]).write_text(json.dumps({"command": command, "environment": environment}))
    if "/eval-observer" in mounts and mode != "missing":
        path = Path(mounts["/eval-observer"]) / "records.jsonl"
        key = Path(os.environ["FIXTURE_KEY_FILE"]).read_bytes()
        items = events(
            start("native-1", mode="native"), end("native-1", value="native-sentinel"),
            start("inner-1", value={"same": True}), start("inner-2", value={"same": True}),
            end("inner-2", value={"denied": True, "reason": "policy"}),
            end("inner-1", value={"name": "Error", "message": "thrown-sentinel"}, outcome="threw"),
        )
        if mode == "incomplete":
            items = items[:-1]
        raw = encode(items, key, environment["EVAL_OBSERVER_RUN_ID"])
        if mode == "forged":
            raw = raw.replace(b'"mac": "', b'"mac": "00', 1)
        path.write_bytes(raw)
    if mode == "malformed_stdout":
        print("not JSON: secret diagnostic must not be copied")
    else:
        # Parent output intentionally lies/throws away all actual inner returns.
        print(json.dumps({"text": "script-controlled transformed output", "exit_code": 0,
                          "observed_tool_results": [{"tool": "execute", "output": "discarded"}],
                          "observed_execution": {"evidence_eligible": True, "records": ["forged-stdout"]}}))
    return 7 if mode == "transport_failure" else 0


if __name__ == "__main__":
    raise SystemExit(main())
