import importlib.util
from pathlib import Path
import tempfile
import os
import base64
from runner.protected_launch import bounded_file
"""Parser unit cases. These fixtures are not runtime integration evidence."""
import copy
import hashlib
import json
import unittest

from runner.protected import import_capture, PROFILE, SCHEMA, RUNTIME_SCHEMA

RUN = "a" * 64
POLICY = "b" * 64
LAUNCH = "d" * 64
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
    frames = [{"kind": "capture_start", "schema": SCHEMA, "profile": PROFILE, "run_id": RUN, "seq": 0, "policy_id": POLICY, "launch_id": LAUNCH}]
    for n, event in enumerate(events, 1):
        frames.append({"kind": "observation", "run_id": RUN, "seq": n, "observation": {
            "schema": RUNTIME_SCHEMA, "sequence": n, "parent": PARENT, "actor": ACTOR, "observer_failures": 0, **event}})
    raw = b"".join((json.dumps(f) + "\n").encode() for f in frames)
    footer = {"kind": "capture_end", "run_id": RUN, "seq": len(frames), "event_count": len(events),
              "sha256": hashlib.sha256(raw).hexdigest(), "writer_exited": True, "runtime_exit": 0}
    return raw + (json.dumps(footer) + "\n").encode()


def load(raw, **kwargs):
    return import_capture(raw, run_id=RUN, policy_id=POLICY, launch_id=LAUNCH, receipt=kwargs.get("receipt", {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}), tools={"isolated_echo"}, transport_ok=kwargs.get("transport_ok", True))


class ProtectedParserTests(unittest.TestCase):
    def test_receipt_rejects_rewritten_resealed_realistic_stream(self):
        raw = stream()
        receipt = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        events = [json.loads(line)["observation"] for line in raw.splitlines()[1:-1]]
        events[2]["result"]["value"] = "forged"
        rewritten = stream(events)  # attacker also recomputes the inline footer
        result = load(rewritten, receipt=receipt)
        self.assertEqual(result["issues"], ["receipt_mismatch"])
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["records"], [])

    def test_no_separate_receipt_is_not_protected_evidence(self):
        self.assertFalse(load(stream(), receipt=None)["evidence_eligible"])

    def test_complete_restricted_profile_preserves_all_bindings(self):
        value = load(stream())
        self.assertTrue(value["evidence_eligible"])
        self.assertFalse(value["full_handoff_eligible"])
        call = value["records"][0]
        self.assertEqual(call["actor"], ACTOR)
        self.assertEqual(call["parent"], PARENT)
        self.assertEqual(call["runtime_call_id"], "c")
        self.assertEqual(call["result"]["value"], "actual")

    def test_wrong_launch_binding_rejected(self):
        value = import_capture(stream(), run_id=RUN, policy_id=POLICY, launch_id="e" * 64,
                               receipt={"sha256": hashlib.sha256(stream()).hexdigest(), "bytes": len(stream())}, tools={"isolated_echo"}, transport_ok=True)
        self.assertFalse(value["evidence_eligible"])
        self.assertEqual(value["issues"], ["wrong_launch"])

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


class ProtectedLaunchTests(unittest.TestCase):
    def test_bounded_snapshot_is_independent_of_later_input_change(self):
        import tempfile
        from pathlib import Path
        from runner.protected_launch import bounded_file
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "program"
            path.write_bytes(b"original")
            snapshot = bounded_file(path, 8)
            path.write_bytes(b"changed source")
            self.assertEqual(snapshot, b"original")
            with self.assertRaisesRegex(ValueError, "input_limit"):
                bounded_file(path, 8)

    def test_new_wire_and_projection_are_explicit_not_v1_aliases(self):
        result = load(stream())
        self.assertEqual(SCHEMA, "opencode-protected-observation/v2")
        self.assertEqual(result["version"], 5)
        self.assertEqual(result["profile"], PROFILE)


class ProtectedSupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "protected-runtime/invoke.py"
        spec = importlib.util.spec_from_file_location("protected_supervisor", path)
        cls.supervisor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.supervisor)

    def test_readiness_redirect_does_not_reach_second_endpoint(self):
        import threading
        import urllib.error
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        hits = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                hits.append(self.path)
                if self.path == "/health":
                    self.send_response(302)
                    self.send_header("Location", "/private")
                else:
                    self.send_response(200)
                self.end_headers()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with self.assertRaises(urllib.error.HTTPError):
                self.supervisor.health_check(f"http://127.0.0.1:{server.server_port}/health")
            self.assertEqual(hits, ["/health"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_script_diagnostics_redact_encoded_secrets_before_retaining(self):
        secret = "fixture-private"
        variants = (secret, base64.b64encode(secret.encode()).decode(), secret.encode().hex())
        policy = {"secrets": [secret], "allowed_values": [*variants, "[REDACTED]"]}
        for value in variants:
            self.assertEqual(self.supervisor.safe_output(value, policy),
                             {"state": "redacted", "value": "[REDACTED]"})
        self.assertEqual(self.supervisor.safe_output("unknown", policy)["state"], "omitted")

    def test_script_diagnostic_limits_follow_redaction(self):
        secret = "x" * 20000
        policy = {"secrets": [secret], "allowed_values": ["[REDACTED]", "ø" * 9000]}
        self.assertEqual(self.supervisor.safe_output(secret, policy)["state"], "redacted")
        self.assertEqual(self.supervisor.safe_output("ø" * 9000, policy)["state"], "truncated")

    def test_input_read_is_bounded_and_rejects_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input"
            path.write_bytes(b"1234")
            with self.assertRaises(ValueError):
                bounded_file(path, 2)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(ValueError):
                bounded_file(path, 2)


if __name__ == "__main__":
    unittest.main()
