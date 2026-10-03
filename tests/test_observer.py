import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runner import cli
from runner.observer import ObserverCapture, load_capture, MAX_CAPTURE_BYTES

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "observer_producer.py"
spec = importlib.util.spec_from_file_location("observer_test_producer", FIXTURE)
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)
field, start, end, events, encode = (getattr(producer, name) for name in ("field", "start", "end", "events", "encode"))
KEY = b"fixture-only-key-not-a-real-secret-0123456789"
RUN = "a" * 64


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "records.jsonl"

    def load(self, items=None, **kwargs):
        self.path.write_bytes(encode(items or events(start(), end()), KEY, RUN))
        return load_capture(self.path, key=KEY, run_id=RUN, **kwargs)

    def assert_rejected(self, result, issue=None):
        self.assertIs(result["evidence_eligible"], False)
        self.assertTrue(all(record["evidence_eligible"] is False for record in result["records"]))
        if issue:
            self.assertIn(issue, result["issues"])

    def test_actual_results_and_exact_identity(self):
        result = self.load(events(start(mode="native", value={"n": 42}), end(value="raw-sentinel")))
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual(result["records"], [{
            "invocation_id": "inner-1", "tool": "sentinel",
            "actor": {"agent": "worker", "session_id": "child-session"},
            "parent": None, "mode": "native", "input": {"state": "available", "value": {"n": 42}},
            "start_sequence": 1, "terminal_sequence": 2, "outcome": "returned",
            "evidence_eligible": True, "result": {"state": "available", "value": "raw-sentinel"},
        }])

    def test_same_input_shared_parent_reverse_completion_order(self):
        result = self.load(events(start("a", value={}), start("b", value={}),
                                  end("b", value="second"), end("a", value="first")))
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual([r["result"]["value"] for r in result["records"]], ["first", "second"])
        self.assertEqual([r["terminal_sequence"] for r in result["records"]], [4, 3])
        self.assertEqual(result["records"][0]["parent"], result["records"][1]["parent"])

    def test_domain_denial_is_returned_not_thrown(self):
        denial = '{"ok":false,"error":"denied"}'
        result = self.load(events(start("a"), end("a", value=denial), start("b"),
                                  end("b", value={"name": "Error", "message": "boom"}, outcome="threw")))
        self.assertTrue(result["evidence_eligible"])
        self.assertEqual(result["records"][0]["outcome"], "returned")
        self.assertEqual(result["records"][0]["result"]["value"], denial)
        self.assertEqual(result["records"][1]["outcome"], "threw")
        self.assertNotIn("result", result["records"][1])

    def test_explicit_null_return_is_preserved(self):
        self.assertIsNone(self.load(events(start(), end(value=None)))["records"][0]["result"]["value"])

    def test_missing_capture_and_empty_capture(self):
        self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN), "missing_capture")
        self.path.touch()
        self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN), "empty_capture")

    def test_missing_footer(self):
        result = self.load(events(start(), end())[:-1])
        self.assert_rejected(result, "missing_capture_end")
        self.assertEqual(result["records"][0]["result"]["value"], "actual-sentinel")
        self.assertIsNone(result["coverage"]["omitted_records"])

    def test_missing_terminal_with_authenticated_footer(self):
        result = self.load(events(start()))
        self.assert_rejected(result, "missing_terminals")
        self.assertEqual(result["coverage"]["missing_terminals"], 1)
        self.assertEqual(result["records"][0]["outcome"], "missing")

    def test_completeness_and_supported_boundary_flags(self):
        for name, value, issue in (("omitted_records", 1, "omitted_records"),
                                    ("truncated", True, "truncated_capture"),
                                    ("unsupported", ["inner_correlation"], "unsupported_capture")):
            with self.subTest(name=name):
                items = events(start(), end())
                items[-1][name] = value
                self.assert_rejected(self.load(items), issue)
        items = events(start(), end())
        items[0]["boundary"] = "before_other_plugins_transform_result"
        self.assert_rejected(self.load(items), "unsupported_capture_boundary")

    def test_parent_call_id_cannot_be_reused_as_unique_invocation(self):
        self.assert_rejected(self.load(events(start(), start(), end())), "duplicate_invocation")

    def test_orphan_and_duplicate_terminals(self):
        for items in (events(end()), events(start(), end(), end())):
            self.assert_rejected(self.load(items), "ambiguous_terminal")

    def test_code_mode_requires_parent(self):
        record = start()
        record["parent"] = None
        self.assert_rejected(self.load(events(record, end())), "missing_parent")

    def test_malformed_identity_never_falls_back_to_requested_actor(self):
        for actor in ({"agent": "worker"}, {"agent": None, "session_id": "s"}):
            record = start()
            record["actor"] = actor
            self.assert_rejected(self.load(events(record, end())))

    def test_wrong_key_forged_payload_and_replay(self):
        raw = encode(events(start(), end()), KEY, RUN)
        self.path.write_bytes(raw)
        self.assert_rejected(load_capture(self.path, key=b"wrong" * 8, run_id=RUN), "authentication_failed")
        self.assert_rejected(load_capture(self.path, key=KEY, run_id="b" * 64), "authentication_failed")
        lines = raw.splitlines()
        frame = json.loads(lines[2])
        payload = json.loads(base64.b64decode(frame["payload"]))
        payload["result"]["value"] = "FORGED PASS"
        frame["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
        lines[2] = json.dumps(frame).encode()
        self.path.write_bytes(b"\n".join(lines) + b"\n")
        self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN), "authentication_failed")

    def test_removed_reordered_appended_records_and_partial_last_line(self):
        raw = encode(events(start(), end()), KEY, RUN)
        lines = raw.splitlines(keepends=True)
        for bad in (b"".join([lines[0], lines[2], lines[3]]),
                    b"".join([lines[0], lines[2], lines[1], lines[3]]),
                    raw + lines[-1], raw[:-1]):
            with self.subTest(raw=bad[:16]):
                self.path.write_bytes(bad)
                self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN))

    def test_sequence_gaps_bool_and_count_mismatch(self):
        for seq in (8, True, "1"):
            items = events(start(), end())
            items[1]["seq"] = seq
            self.assert_rejected(self.load(items), "ambiguous_order")
        items = events(start(), end())
        items[-1]["calls_started"] = 9
        self.assert_rejected(self.load(items), "count_mismatch")

    def test_duplicate_json_keys_nonfinite_and_deep_json(self):
        transforms = (
            lambda seq, raw: raw[:-1] + b',"seq":0}' if seq == 0 else raw,
            lambda seq, raw: raw.replace(b'"version":1', b'"version":NaN') if seq == 0 else raw,
            lambda seq, raw: b'[' * 2000 + b'0' + b']' * 2000 if seq == 0 else raw,
        )
        for transform in transforms:
            self.path.write_bytes(encode(events(start(), end()), KEY, RUN, transform))
            self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN))

    def test_malformed_records_and_unsupported_versions(self):
        for raw in (b'{bad}\n', b'{"payload": "!", "mac": "x"}\n', b'[]\n', b'\xff\n'):
            self.path.write_bytes(raw)
            self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN))
        items = events(start(), end())
        items[0]["version"] = 2
        self.assert_rejected(self.load(items), "unsupported_version")

    def test_redact_before_clipping(self):
        secret = "secret-material-" * 100
        result = self.load(events(start(), end(value=secret)), known_secrets=(secret,), field_limit=64)
        self.assert_rejected(result, "incomplete_fields")
        self.assertEqual(result["records"][0]["result"], {"state": "redacted", "value": "[REDACTED]"})
        self.assertNotIn("secret-material", json.dumps(result))
        self.assertFalse(result["coverage"]["truncated"])

    def test_unknown_redaction_is_omitted_without_preview(self):
        record = end(value="private-raw-value")
        del record["result"]["redaction"]
        result = self.load(events(start(), record))
        self.assert_rejected(result, "incomplete_fields")
        self.assertNotIn("private-raw-value", json.dumps(result))
        self.assertEqual(result["records"][0]["result"]["state"], "omitted")

    def test_sensitive_nested_keys_and_embedded_known_secrets(self):
        result = self.load(events(start(value={"nested": {"password": "unlisted-secret"}}),
                                  end(value='{"text":"known-secret"}')), known_secrets=("known-secret",))
        self.assert_rejected(result, "incomplete_fields")
        self.assertNotIn("unlisted-secret", json.dumps(result))
        self.assertNotIn("known-secret", json.dumps(result))

    def test_omissions_truncation_and_unsafe_identity_never_pass(self):
        result = self.load(events(start(), end(value="a" * 2000)), field_limit=64)
        self.assert_rejected(result, "incomplete_fields")
        self.assertTrue(result["coverage"]["truncated"])
        self.assertNotIn("value", result["records"][0]["result"])
        record = end()
        record["result"] = {"state": "omitted", "reason": "SECRET", "value": "SECRET"}
        result = self.load(events(start(), record))
        self.assert_rejected(result)
        self.assertNotIn("SECRET", json.dumps(result))
        self.assert_rejected(self.load(known_secrets=("worker",)), "unsafe_identity")

    def test_filesystem_symlink_fifo_hardlink_and_limits(self):
        target = self.path.with_name("other")
        target.write_bytes(encode(events(start(), end()), KEY, RUN))
        self.path.symlink_to(target)
        self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN))
        self.path.unlink()
        os.mkfifo(self.path)
        self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN), "unsafe_capture_file")
        self.path.unlink()
        os.link(target, self.path)
        self.assert_rejected(load_capture(self.path, key=KEY, run_id=RUN), "unsafe_capture_file")
        self.path.unlink()
        with self.path.open("wb") as stream:
            stream.truncate(MAX_CAPTURE_BYTES + 1)
        result = load_capture(self.path, key=KEY, run_id=RUN)
        self.assert_rejected(result, "capture_limit")
        self.assertTrue(result["coverage"]["truncated"])

    def test_import_is_read_only_and_input_objects_unchanged(self):
        items = events(start(), end())
        original = copy.deepcopy(items)
        raw = encode(items, KEY, RUN)
        self.path.write_bytes(raw)
        self.assertTrue(load_capture(self.path, key=KEY, run_id=RUN)["evidence_eligible"])
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(items, original)

    def test_failed_transport_disqualifies_even_complete_capture(self):
        self.assert_rejected(self.load(transport_ok=False), "transport_failed")


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.key = self.root / "signing-key"
        self.key.write_bytes(KEY)
        self.key.chmod(0o600)
        self.prompt = self.root / "prompt.txt"
        self.prompt.write_text("fixture prompt; no provider inference")
        self.output = self.root / "result.json"
        self.command_log = self.root / "command.json"
        fake = self.root / "docker"
        fake.write_text(f'#!/bin/sh\nexec "{os.sys.executable}" "{FIXTURE}" "$@"\n')
        fake.chmod(0o755)
        env = {"PATH": str(self.root) + os.pathsep + os.defpath,
               "HOME": str(self.root / "home"), "XDG_DATA_HOME": str(self.root / "data"),
               "XDG_STATE_HOME": str(self.root / "state"), "XDG_CACHE_HOME": str(self.root / "cache"),
               "XDG_CONFIG_HOME": str(self.root / "config"),
               "FIXTURE_KEY_FILE": str(self.key), "FIXTURE_COMMAND": str(self.command_log)}
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.args = cli.parser().parse_args([
            "invoke", "--engine", "docker", "--model", "fixture/model", "--workspace", str(self.workspace),
            "--prompt-file", str(self.prompt), "--output", str(self.output), "--observer-key-file", str(self.key),
            "--image", "fixture@sha256:" + "6" * 64,
        ])

    def run_mode(self, mode):
        with patch.dict(os.environ, {"FIXTURE_MODE": mode}):
            code = cli.invoke(self.args)
        return code, json.loads(self.output.read_text())

    def test_real_subprocess_export_is_independent_of_outer_output(self):
        code, result = self.run_mode("good")
        self.assertEqual(code, 0)
        self.assertEqual(result["text"], "script-controlled transformed output")
        self.assertEqual(result["observed_tool_results"], [{"tool": "execute", "output": "discarded"}])
        projection = result["observed_execution"]
        self.assertTrue(projection["evidence_eligible"])
        self.assertEqual([r["invocation_id"] for r in projection["records"]], ["native-1", "inner-1", "inner-2"])
        self.assertEqual(projection["records"][0]["result"]["value"], "native-sentinel")
        self.assertEqual(projection["records"][1]["error"]["value"]["message"], "thrown-sentinel")
        self.assertEqual(projection["records"][2]["result"]["value"], {"denied": True, "reason": "policy"})
        log = json.loads(self.command_log.read_text())
        self.assertNotIn("FIXTURE_KEY_FILE", log["environment"])
        self.assertNotIn(str(self.key), json.dumps(log))
        self.assertNotIn(KEY.decode(), json.dumps(log))
        self.assertEqual(log["command"][-1], "fixture@sha256:" + "6" * 64)
        self.assertFalse(any("opencode.db" in arg for arg in log["command"]))
        self.assertEqual(self.prompt.read_text(), "fixture prompt; no provider inference")
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_missing_malformed_and_forged_sidecar_cannot_exit_success(self):
        for mode in ("missing", "incomplete", "forged"):
            with self.subTest(mode=mode):
                code, result = self.run_mode(mode)
                self.assertEqual(code, 4)
                self.assertFalse(result["observed_execution"]["evidence_eligible"])
                self.assertNotIn("forged-stdout", json.dumps(result))

    def test_original_failure_code_is_preserved(self):
        code, result = self.run_mode("transport_failure")
        self.assertEqual(code, 7)
        self.assertFalse(result["observed_execution"]["evidence_eligible"])

    def test_bad_stdout_still_writes_non_evidence_without_raw_diagnostics(self):
        code, result = self.run_mode("malformed_stdout")
        self.assertEqual(code, 2)
        self.assertFalse(result["observed_execution"]["evidence_eligible"])
        self.assertNotIn("secret diagnostic", json.dumps(result))

    def test_timeout_writes_explicit_non_evidence(self):
        with patch.object(cli.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 1)):
            self.assertEqual(cli.invoke(self.args), 2)
        self.assertFalse(json.loads(self.output.read_text())["observed_execution"]["evidence_eligible"])

    def test_opt_out_cannot_launder_observer_claims_from_stdout(self):
        self.args.observer_key_file = None
        code, result = self.run_mode("good")
        self.assertEqual(code, 0)
        self.assertEqual(result["observed_execution"]["issues"], ["capture_not_requested"])
        self.assertNotIn("forged-stdout", json.dumps(result))
        self.assertNotIn("/eval-observer", json.dumps(json.loads(self.command_log.read_text())))

    def test_unique_nonce_and_private_capture_per_invocation(self):
        _, one = self.run_mode("good")
        _, two = self.run_mode("good")
        self.assertNotEqual(one["observed_execution"]["run_id"], two["observed_execution"]["run_id"])

    def test_key_cannot_be_mounted_via_workspace_or_explicit_bind(self):
        for mode in ("workspace", "explicit"):
            args = copy.deepcopy(self.args)
            if mode == "workspace":
                args.workspace = str(self.root)
            else:
                args.mount = [f"{self.key}:/visible-key:ro"]
            with self.assertRaises(cli.RunnerError):
                cli.invoke(args)
        self.assertFalse(self.command_log.exists())

    def test_key_and_reserved_variables_cannot_be_forwarded(self):
        for name, value in (("KEY", KEY.decode()), ("EVAL_OBSERVER_RUN_ID", "forged")):
            with patch.dict(os.environ, {name: value}):
                args = copy.deepcopy(self.args)
                args.env.append(name)
                with self.assertRaises(cli.RunnerError):
                    cli.invoke(args)
        self.assertFalse(self.command_log.exists())

    def test_encoded_key_and_nonprivate_key_are_rejected(self):
        for value in (KEY.hex(), base64.b64encode(KEY).decode()):
            with patch.dict(os.environ, {"KEY": value}):
                args = copy.deepcopy(self.args)
                args.env.append("KEY")
                with self.assertRaises(cli.RunnerError):
                    cli.invoke(args)
        self.key.chmod(0o644)
        with self.assertRaises(cli.RunnerError):
            cli.invoke(self.args)
        self.assertFalse(self.command_log.exists())

    def test_observer_only_opencode(self):
        self.args.transport = "github-copilot-cli"
        with self.assertRaises(cli.RunnerError):
            cli.invoke(self.args)
        self.assertFalse(self.command_log.exists())


if __name__ == "__main__":
    unittest.main()
