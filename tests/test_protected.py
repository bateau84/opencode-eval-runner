"""Parser unit cases. These fixtures are not runtime integration evidence."""
import copy
import hashlib
import json
import unittest

from runner.protected import import_capture, PROFILE, SCHEMA, RUNTIME_SCHEMA

RUN = "a" * 64
POLICY = "b" * 64
ACTOR = {"agent": "build", "session_id": "s", "message_id": "m"}
PARENT = {"invocation_id": "p", "session_id": "s", "message_id": "m", "call_id": "c"}


def stream(events=None):
    events = events or [
        {"kind": "parent_start", "boundary": "codemode-engine", "mode": "code_mode"},
        {"kind": "call_start", "invocation_id": "i", "tool": "isolated_echo", "catalog_path": "isolated.echo",
         "input": {"state": "available", "redaction": "safe", "value": {}}, "boundary": "executable-input"},
        {"kind": "call_end", "invocation_id": "i", "dispatched": True, "boundary": "codemode-json-return", "outcome": "returned",
         "result": {"state": "available", "redaction": "safe", "value": "actual"}},
        {"kind": "parent_end", "admitted": 1, "dispatched": 1, "terminals": 1, "missing_terminals": 0,
         "unsupported_dispatches": 0, "unavailable_fields": 0, "scope": "one-codemode-engine-invocation", "evidence_eligible": False},
    ]
    frames = [{"kind": "capture_start", "schema": SCHEMA, "profile": PROFILE, "run_id": RUN, "seq": 0, "policy_id": POLICY}]
    for n, event in enumerate(events, 1):
        frames.append({"kind": "observation", "run_id": RUN, "seq": n, "observation": {
            "schema": RUNTIME_SCHEMA, "sequence": n, "parent": PARENT, "actor": ACTOR, "observer_failures": 0, **event}})
    raw = b"".join((json.dumps(f) + "\n").encode() for f in frames)
    footer = {"kind": "capture_end", "run_id": RUN, "seq": len(frames), "event_count": len(events),
              "sha256": hashlib.sha256(raw).hexdigest(), "writer_exited": True, "runtime_exit": 0}
    return raw + (json.dumps(footer) + "\n").encode()


def load(raw, **kwargs):
    return import_capture(raw, run_id=RUN, policy_id=POLICY, tools={"isolated_echo"}, transport_ok=kwargs.get("transport_ok", True))


class ProtectedParserTests(unittest.TestCase):
    def test_complete_restricted_profile_preserves_all_bindings(self):
        value = load(stream())
        self.assertTrue(value["evidence_eligible"])
        self.assertFalse(value["full_handoff_eligible"])
        call = value["records"][0]
        self.assertEqual(call["actor"], ACTOR)
        self.assertEqual(call["parent"], PARENT)
        self.assertEqual(call["runtime_call_id"], "c")
        self.assertEqual(call["result"]["value"], "actual")

    def test_changes_and_replay_cannot_pass(self):
        for raw in (stream().replace(b"actual", b"FORGED"), stream().replace(RUN.encode(), ("c" * 64).encode()),
                    stream().splitlines(keepends=True)[0], stream()[:-10], stream() + b"{}\n"):
            with self.subTest(raw=raw[:10]):
                self.assertFalse(load(raw)["evidence_eligible"])
                self.assertEqual(load(raw)["records"], [])

    def test_bad_json_empty_duplicate_and_nonfinite(self):
        for raw in (b"", b'{}\n', b'[]\n[]\n', b'{"a":1,"a":2}\n{}\n', b'{"x":NaN}\n{}\n'):
            self.assertFalse(load(raw)["evidence_eligible"])

    def test_transport_failure_does_not_promote_valid_capture(self):
        value = load(stream(), transport_ok=False)
        self.assertFalse(value["evidence_eligible"])
        self.assertTrue(all(r["evidence_eligible"] is False for r in value["records"]))

    def test_unknown_record_and_closed_parent_fail(self):
        frames = [json.loads(s) for s in stream().splitlines()]
        events = [f["observation"] for f in frames[1:-1]]
        events[2]["kind"] = "something_else"
        self.assertFalse(load(stream(events))["evidence_eligible"])

    def test_omitted_redacted_and_truncated_are_non_evidence(self):
        for field in ({"state": "omitted", "reason": "policy_omission"},
                      {"state": "truncated", "reason": "field_limit"},
                      {"state": "redacted", "redaction": "safe", "value": "[REDACTED]"}):
            frames = [json.loads(s) for s in stream().splitlines()]
            events = [f["observation"] for f in frames[1:-1]]
            events[2]["result"] = field
            value = load(stream(events))
            self.assertFalse(value["evidence_eligible"])
            self.assertEqual(value["status"], "incomplete")

    def test_deleted_middle_and_forged_completeness_rejected(self):
        frames = stream().splitlines(keepends=True)
        self.assertFalse(load(b"".join(frames[:2] + frames[3:]))["evidence_eligible"])
        events = [f["observation"] for f in map(json.loads, frames[1:-1])]
        events[-1]["terminals"] = 10
        self.assertFalse(load(stream(events))["evidence_eligible"])

    def test_unknown_error_representation_and_conflicting_actor_rejected(self):
        frames = [json.loads(s) for s in stream().splitlines()]
        events = [f["observation"] for f in frames[1:-1]]
        events[2]["actor"]["agent"] = "other"
        self.assertFalse(load(stream(events))["evidence_eligible"])


if __name__ == "__main__":
    unittest.main()
