from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from container.evidence_safety import (
    JSON_SOURCE_LIMIT,
    MODEL_CATALOG_SOURCE_LIMIT,
    OMITTED,
    REDACTED,
    Projection,
    Sanitizer,
)
from container.invoke import (
    emit_result,
    extract_tool_result_evidence,
    invoke_opencode,
    runtime_sanitizer,
    sanitize_result_for_output,
)


def disposition(summary: dict, field: str, event: int | None = None) -> dict:
    return next(
        item
        for item in summary["fields"]
        if item["field"] == field and item["event"] == event
    )


class EvidenceSafetyTests(unittest.TestCase):
    def test_short_credentials_preserve_json_structure_and_protocol_fields(self):
        sanitizer = Sanitizer(["0", "1", "text", "low"])
        projection = Projection(sanitizer)

        status = projection.field("status", "completed", event=0, protocol=True)
        payload = projection.field(
            "output",
            {"choice": "text", "priority": "low", "ok": True},
            event=0,
        )
        numeric = projection.field("count", 0, event=0)

        self.assertEqual(status, "completed")
        self.assertEqual(
            payload,
            {"choice": REDACTED, "priority": REDACTED, "ok": True},
        )
        self.assertIs(numeric, OMITTED)
        self.assertEqual(disposition(projection.summary(), "output", 0)["state"], "redacted")
        self.assertEqual(
            disposition(projection.summary(), "count", 0)["reason"],
            "credential_match",
        )
        json.dumps(payload)

    def test_nested_sensitive_key_omits_enclosing_evidence_field(self):
        projection = Projection(Sanitizer())
        raw = {"nested": {"apiKey": "not-in-inventory", "public": "ok"}}

        self.assertIs(projection.field("input", raw, event=0), OMITTED)
        item = disposition(projection.summary(), "input", 0)
        self.assertEqual(item["state"], "omitted")
        self.assertEqual(item["reason"], "sensitive_key")
        self.assertNotIn("not-in-inventory", json.dumps(projection.summary()))

    def test_escaped_credential_representations_are_protected(self):
        secret = 'tok-"line\n\\ending'
        sanitizer = Sanitizer([secret])
        value = secret

        for _ in range(4):
            safe, changed = sanitizer.redact_text(value)
            self.assertTrue(changed)
            self.assertNotIn(secret, safe)
            value = json.dumps(value)[1:-1]

    def test_redaction_happens_before_size_decision(self):
        secret = "z" * 20_000
        projection = Projection(Sanitizer([secret]))

        safe = projection.field("output", secret, event=0, limit=64)

        self.assertEqual(safe, REDACTED)
        self.assertEqual(disposition(projection.summary(), "output", 0)["state"], "redacted")
        self.assertNotIn(secret, json.dumps(projection.summary()))

    def test_oversize_public_value_is_omitted_not_partially_kept(self):
        projection = Projection(Sanitizer())
        raw = "safe-prefix-" + ("x" * 500)

        self.assertIs(projection.field("output", raw, event=0, limit=64), OMITTED)
        item = disposition(projection.summary(), "output", 0)
        self.assertEqual(item["reason"], "size_limit")
        self.assertNotIn(raw[:32], json.dumps(projection.summary()))

    def test_missing_and_malformed_values_use_fixed_safe_reasons(self):
        projection = Projection(Sanitizer())
        cycle: dict[str, object] = {}
        cycle["self"] = cycle

        self.assertIs(projection.field("missing", event=0), OMITTED)
        self.assertIs(projection.field("cycle", cycle, event=0), OMITTED)
        self.assertIs(projection.field("nan", float("nan"), event=0), OMITTED)

        summary = projection.summary()
        self.assertEqual(disposition(summary, "missing", 0)["reason"], "missing")
        self.assertEqual(
            disposition(summary, "cycle", 0)["reason"],
            "unsupported_representation",
        )
        self.assertEqual(
            disposition(summary, "nan", 0)["reason"],
            "unsupported_representation",
        )
        self.assertNotIn("self", json.dumps(summary))

    def test_runtime_inventory_reads_env_json_and_credential_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = root / "auth.json"
            auth.write_text(
                json.dumps({"provider": {"key": "json-secret"}}),
                encoding="utf-8",
            )
            database = root / "opencode.db"
            with sqlite3.connect(database) as db:
                db.execute("CREATE TABLE credential (provider TEXT, data TEXT)")
                db.execute(
                    "INSERT INTO credential(provider, data) VALUES (?, ?)",
                    ("fixture", json.dumps({"token": "db-secret"})),
                )
                db.commit()

            sanitizer = Sanitizer.from_runtime(
                {"OPENAI_API_KEY": "env-secret"},
                json_sources=(auth,),
                database_sources=(database,),
            )

        self.assertTrue(sanitizer.inventory_complete)
        self.assertEqual(
            set(sanitizer.credentials),
            {"env-secret", "json-secret", "db-secret"},
        )

    def test_malformed_selected_inventory_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / "auth.json"
            auth.write_text("{bad", encoding="utf-8")
            sanitizer = Sanitizer.from_runtime({}, json_sources=(auth,))

        self.assertFalse(sanitizer.inventory_complete)
        projection = Projection(sanitizer)
        self.assertIs(projection.field("output", "possibly private", event=0), OMITTED)
        self.assertEqual(
            disposition(projection.summary(), "output", 0)["reason"],
            "credential_inventory_unavailable",
        )
        self.assertNotIn("evidence_eligible", projection.summary())

    def test_large_model_catalog_preserves_model_identity_and_redacts_secrets(self):
        # OpenCode generated caches commonly exceed the 4 MB auth/config cap.
        # A credential near the end must still be collected and never leak.
        secret = "MODEL-CACHE-TAIL-SECRET"
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "models.json"
            catalog.write_text(
                json.dumps({
                    "openai": {
                        "models": {
                            "gpt-6-luna": {
                                "description": "long-model-description-" * 210_000,
                            },
                        },
                        "apiKey": secret,
                    },
                }),
                encoding="utf-8",
            )
            self.assertGreater(catalog.stat().st_size, JSON_SOURCE_LIMIT)
            self.assertLess(catalog.stat().st_size, MODEL_CATALOG_SOURCE_LIMIT)

            sanitizer = Sanitizer.from_runtime(
                {}, model_catalog_sources=(catalog,)
            )
            self.assertTrue(sanitizer.inventory_complete)
            self.assertIn(secret, sanitizer.credentials)
            self.assertEqual(sanitizer.output_value("openai/gpt-6-luna"), "openai/gpt-6-luna")
            self.assertEqual(sanitizer.output_value(f"private {secret}"), f"private {REDACTED}")
            self.assertEqual(Projection(sanitizer).field("output", f"{secret}"), REDACTED)

            # Verify the actual runtime source wiring and result-sink behavior.
            with (
                patch("container.invoke.RUNTIME_JSON_CREDENTIAL_SOURCES", ()),
                patch("container.invoke.RUNTIME_MODEL_CATALOG_CREDENTIAL_SOURCES", (catalog,)),
                patch("container.invoke.RUNTIME_DATABASE_CREDENTIAL_SOURCES", ()),
            ):
                runtime = runtime_sanitizer({})
                output = sanitize_result_for_output(
                    {"model": "openai/gpt-6-luna", "text": secret},
                    runtime,
                )
            self.assertTrue(runtime.inventory_complete)
            self.assertEqual(output["model"], "openai/gpt-6-luna")
            self.assertEqual(output["text"], REDACTED)

    def test_large_auth_config_still_fails_closed_at_its_original_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / "auth.json"
            auth.write_text(
                json.dumps({"apiKey": "tail-secret", "filler": "a" * JSON_SOURCE_LIMIT}),
                encoding="utf-8",
            )
            sanitizer = Sanitizer.from_runtime({}, json_sources=(auth,))
            self.assertFalse(sanitizer.inventory_complete)
            self.assertEqual(sanitizer.output_value("openai/gpt-6-luna"), REDACTED)
            self.assertIs(Projection(sanitizer).field("output", "untrusted"), OMITTED)

    def test_oversized_or_invalid_model_catalog_remains_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "models.json"
            with catalog.open("wb") as stream:
                stream.truncate(MODEL_CATALOG_SOURCE_LIMIT + 1)
            oversized = Sanitizer.from_runtime({}, model_catalog_sources=(catalog,))
            self.assertFalse(oversized.inventory_complete)
            self.assertEqual(oversized.output_value("openai/gpt-6-luna"), REDACTED)

            catalog.write_text("{invalid", encoding="utf-8")
            invalid = Sanitizer.from_runtime({}, model_catalog_sources=(catalog,))
            self.assertFalse(invalid.inventory_complete)
            self.assertIs(Projection(invalid).field("output", "untrusted"), OMITTED)

    def test_success_failure_and_running_events_are_projected_without_invention(self):
        secret = "fixture-secret"
        events = [
            {
                "type": "tool_use",
                "sessionID": "ses-1",
                "part": {
                    "type": "tool",
                    "tool": "demo",
                    "callID": "call-1",
                    "state": {
                        "status": "completed",
                        "input": {"value": "public"},
                        "output": {"value": secret},
                    },
                },
            },
            {
                "type": "tool_use",
                "sessionID": "ses-1",
                "part": {
                    "type": "tool",
                    "tool": "demo",
                    "callID": "call-2",
                    "state": {
                        "status": "error",
                        "input": {"value": "public"},
                        "error": f"failed: {secret}",
                    },
                },
            },
            {
                "type": "tool_use",
                "sessionID": "ses-1",
                "part": {
                    "type": "tool",
                    "tool": "demo",
                    "callID": "call-3",
                    "state": {
                        "status": "running",
                        "input": {"value": "public"},
                    },
                },
            },
        ]

        evidence = extract_tool_result_evidence(events, Sanitizer([secret]))

        self.assertEqual(evidence["observed_events"], 3)
        self.assertEqual(evidence["events"][0]["status"], "completed")
        self.assertEqual(evidence["events"][0]["output"], {"value": REDACTED})
        self.assertEqual(evidence["events"][1]["status"], "error")
        self.assertEqual(evidence["events"][1]["error"], f"failed: {REDACTED}")
        self.assertEqual(evidence["events"][2]["status"], "running")
        self.assertNotIn("output", evidence["events"][2])
        self.assertNotIn("error", evidence["events"][2])
        self.assertNotIn("evidence_eligible", evidence)
        self.assertNotIn("evidence_eligible", evidence["safety"])
        self.assertNotIn(secret, json.dumps(evidence))

    def test_oversize_tool_result_field_is_explicitly_omitted(self):
        raw = "safe-prefix-" + ("x" * 7000)
        events = [{
            "type": "tool_use",
            "sessionID": "ses-1",
            "part": {
                "type": "tool",
                "tool": "demo",
                "callID": "call-1",
                "state": {
                    "status": "completed",
                    "input": {"value": "public"},
                    "output": raw,
                },
            },
        }]

        evidence = extract_tool_result_evidence(events, Sanitizer())

        self.assertNotIn("output", evidence["events"][0])
        self.assertEqual(
            disposition(evidence["safety"], "output", 0)["reason"],
            "size_limit",
        )
        self.assertNotIn("evidence_eligible", evidence)
        self.assertNotIn("evidence_eligible", evidence["safety"])
        self.assertNotIn(raw[:64], json.dumps(evidence))

    def test_actual_invoke_path_never_exports_secret_and_keeps_product_failure(self):
        secret = "ACTUAL-INVOKE-SECRET"
        event = {
            "type": "tool_use",
            "sessionID": "ses-safe",
            "part": {
                "type": "tool",
                "tool": "demo",
                "callID": "call-safe",
                "state": {
                    "status": "completed",
                    "input": {"query": "public"},
                    "output": {"answer": secret},
                },
            },
        }
        text_event = {
            "type": "text",
            "sessionID": "ses-safe",
            "part": {"type": "text", "text": f"model echo {secret}"},
        }

        class Result:
            returncode = 1
            stdout = "\n".join((json.dumps(event), json.dumps(text_event)))
            stderr = f"provider failure {secret}"

        env = {
            "OPENAI_API_KEY": secret,
            "OPENCODE_CONFIG_DIR": "/tmp/nonexistent-opencode-config",
        }
        with patch("container.invoke.prepare_opencode_env", return_value=env), patch(
            "container.invoke.run",
            return_value=Result(),
        ), patch.dict(
            os.environ,
            {"OPENAI_API_KEY": secret, "EVAL_EXPECT_PLUGIN": ""},
            clear=True,
        ):
            result = invoke_opencode(
                "openai/fixture",
                "general",
                "prompt",
                30,
            )
            output = io.StringIO()
            with patch("container.invoke.sys.stdout", output):
                emit_result(result)

        wire = output.getvalue()
        parsed = json.loads(wire)
        self.assertNotIn(secret, wire)
        self.assertEqual(parsed["exit_code"], 1)
        self.assertEqual(
            parsed["tool_result_evidence"]["events"][0]["output"],
            {"answer": REDACTED},
        )
        self.assertNotIn("evidence_eligible", parsed["tool_result_evidence"])
        self.assertNotIn("evidence_eligible", parsed["tool_result_evidence"]["safety"])

    def test_timeout_path_sanitizes_before_clipping_and_keeps_timeout_status(self):
        secret = "TIMEOUT-SECRET"
        event = {
            "type": "tool_use",
            "sessionID": "ses-timeout",
            "part": {
                "type": "tool",
                "tool": "demo",
                "callID": "call-timeout",
                "state": {
                    "status": "running",
                    "input": {"query": secret},
                },
            },
        }

        def fail(command, cwd, env, timeout):
            raise subprocess.TimeoutExpired(
                command,
                timeout,
                output=json.dumps(event),
                stderr=f"still running {secret}",
            )

        env = {
            "OPENAI_API_KEY": secret,
            "OPENCODE_CONFIG_DIR": "/tmp/nonexistent-opencode-config",
        }
        with patch("container.invoke.prepare_opencode_env", return_value=env), patch(
            "container.invoke.run",
            side_effect=fail,
        ), patch.dict(
            os.environ,
            {"OPENAI_API_KEY": secret, "EVAL_EXPECT_PLUGIN": ""},
            clear=True,
        ):
            result = invoke_opencode(
                "openai/fixture",
                "general",
                "prompt",
                1,
            )

        wire = json.dumps(result)
        self.assertNotIn(secret, wire)
        self.assertEqual(result["exit_code"], 124)
        self.assertTrue(result["timed_out"])
        self.assertNotIn("evidence_eligible", result["tool_result_evidence"])
        self.assertNotIn("evidence_eligible", result["tool_result_evidence"]["safety"])


if __name__ == "__main__":
    unittest.main()
