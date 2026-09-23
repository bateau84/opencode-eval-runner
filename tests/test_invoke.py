from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from container.invoke import (
    assistant_from_export,
    extract_actions,
    extract_loaded_skills,
    extract_tool_result_evidence,
    loaded_skills_from_export,
    invoke_opencode,
    verify_expected_plugin,
)


class OpenCodeTransportTests(unittest.TestCase):
    def test_extracts_normalized_tool_actions_with_inputs(self):
        events = [
            {
                "type": "tool_use",
                "part": {
                    "type": "tool",
                    "tool": "read",
                    "state": {
                        "status": "completed",
                        "input": {"filePath": "/workspace/ASSESSMENT.md"},
                    },
                },
            }
        ]
        self.assertEqual(
            extract_actions(events),
            [
                {
                    "tool": "read",
                    "args": {"filePath": "/workspace/ASSESSMENT.md"},
                }
            ],
        )

    def test_extract_loaded_skills_counts_only_completed_native_skill_calls(self):
        events = [
            {
                "type": "tool_use",
                "part": {
                    "type": "tool",
                    "tool": "skill",
                    "state": {"status": "completed", "input": {"name": "golang-concurrency"}},
                },
            },
            {
                "type": "tool_use",
                "part": {
                    "type": "tool",
                    "tool": "skill",
                    "state": {"status": "error", "input": {"id": "missing-skill"}},
                },
            },
            {
                "type": "tool_use",
                "part": {
                    "type": "tool",
                    "tool": "skill",
                    "state": {"status": "completed", "input": {"id": "architectural-design"}},
                },
            },
        ]
        self.assertEqual(
            extract_loaded_skills(events),
            ["golang-concurrency", "architectural-design"],
        )

    def test_failed_exported_skill_call_is_not_reported_as_loaded(self):
        exported = [
            {
                "info": {"role": "assistant"},
                "parts": [
                    {
                        "type": "tool",
                        "tool": "skill",
                        "state": {
                            "status": "error",
                            "input": {"id": "missing-skill"},
                        },
                    }
                ],
            }
        ]
        self.assertEqual(loaded_skills_from_export(exported), [])

    def test_session_export_preserves_tool_inputs_as_actions(self):
        exported = [
            {
                "info": {"role": "assistant"},
                "parts": [
                    {
                        "type": "tool",
                        "tool": "skill",
                        "state": {
                            "status": "completed",
                            "input": {"name": "golang-concurrency"},
                            "output": "omitted",
                        },
                    },
                    {
                        "type": "tool",
                        "tool": "read",
                        "state": {
                            "status": "completed",
                            "input": {
                                "filePath": "/workspace/.opencode/skills/golang-concurrency/ASSESSMENT.md"
                            },
                        },
                    },
                ],
            }
        ]
        text, tools, actions = assistant_from_export(exported)
        self.assertEqual(text, "")
        self.assertEqual(tools, ["skill", "read"])
        self.assertEqual(
            actions,
            [
                {"tool": "skill", "args": {"name": "golang-concurrency"}},
                {
                    "tool": "read",
                    "args": {
                        "filePath": "/workspace/.opencode/skills/golang-concurrency/ASSESSMENT.md"
                    },
                },
            ],
        )

    def test_v2_invocation_does_not_use_models_refresh_preflight(self):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        calls: list[list[str]] = []

        def fake_run(command, cwd, env, timeout):
            calls.append(command)
            return Result()

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", side_effect=fake_run
        ):
            result = invoke_opencode(
                "openai/gpt-5.3-codex-spark",
                "reviewer",
                "test prompt",
                30,
            )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ["opencode", "run"])
        self.assertIn("--model", calls[0])
        self.assertNotIn("--refresh", calls[0])
        self.assertNotIn("models", calls[0][1:])

    def test_opencode_uses_event_stream_without_session_export(self):
        class Result:
            returncode = 0
            stderr = ""
            stdout = "\n".join([
                '{"type":"step_start","sessionID":"ses_test","part":{"type":"step-start"}}',
                '{"type":"tool_use","sessionID":"ses_test","part":{"type":"tool","tool":"skill","state":{"status":"completed","input":{"id":"web-ui-design"}}}}',
                '{"type":"text","sessionID":"ses_test","part":{"type":"text","text":"done"}}',
            ])

        calls: list[list[str]] = []

        def fake_run(command, cwd, env, timeout):
            calls.append(command)
            return Result()

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", side_effect=fake_run
        ):
            result = invoke_opencode(
                "openai/gpt-5.5",
                "skill-eval",
                "test prompt",
                30,
                "web-ui-design",
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ["opencode", "run"])
        self.assertEqual(result["session_id"], "ses_test")
        self.assertEqual(result["text"], "done")
        self.assertEqual(result["tools"], ["skill"])
        self.assertEqual(
            result["actions"],
            [{"tool": "skill", "args": {"id": "web-ui-design"}}],
        )
        self.assertEqual(result["skills_loaded"], ["web-ui-design"])
        self.assertEqual(result["timing"]["export_seconds"], 0.0)
        self.assertIsNone(result["timing"]["export_exit_code"])


    def test_full_tool_result_projection_survives_raw_stdout_clipping(self):
        class Result:
            returncode = 0
            stderr = ""
            stdout = "\n".join(
                [
                    json.dumps({
                        "type": "step_start",
                        "sessionID": "ses_long",
                        "part": {"type": "step-start", "padding": "x" * 1000},
                    })
                    for _ in range(240)
                ]
                + [
                    json.dumps({
                        "type": "tool_use",
                        "sessionID": "ses_long",
                        "part": {
                            "type": "tool",
                            "tool": "loom_status",
                            "state": {
                                "status": "completed",
                                "input": {"workflowId": "wf-long"},
                                "output": "FINAL COMPLETE 3/3",
                            },
                        },
                    })
                ]
            )

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", return_value=Result()
        ):
            result = invoke_opencode(
                "openai/gpt-5.6-luna",
                "general",
                "test prompt",
                30,
            )

        self.assertTrue(result["stdout_truncated"])
        self.assertGreater(result["stdout_total_chars"], len(result["stdout"]))
        self.assertNotIn("FINAL COMPLETE 3/3", result["stdout"])
        self.assertIn(
            "FINAL COMPLETE 3/3",
            json.dumps(result["tool_result_evidence"]),
        )
        self.assertEqual(result["tool_result_evidence"]["observed_events"], 1)
        self.assertEqual(result["tool_result_evidence"]["omitted_events"], 0)

    def test_opencode_reports_stderr_truncation_metadata(self):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "x" * 21000

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", return_value=Result()
        ):
            result = invoke_opencode(
                "openai/gpt-5.6-luna",
                "general",
                "test prompt",
                30,
            )

        self.assertTrue(result["stderr_truncated"])
        self.assertEqual(result["stderr_total_chars"], 21000)
        self.assertEqual(len(result["stderr"]), 20000)

    def test_opencode_timeout_preserves_partial_runtime_progress(self):
        stdout = "\n".join([
            '{"type":"step_start","sessionID":"ses_timeout","part":{"type":"step-start"}}',
            '{"type":"tool_use","sessionID":"ses_timeout","part":{"type":"tool","tool":"loom_start","state":{"status":"completed","input":{"request":"tracked investigation"}}}}',
            '{"type":"tool_use","sessionID":"ses_timeout","part":{"type":"tool","tool":"subagent","state":{"status":"running","input":{"agent":"diagnostic"}}}}',
        ])

        def fake_run(command, cwd, env, timeout):
            raise subprocess.TimeoutExpired(
                command,
                timeout,
                output=stdout,
                stderr="provider still running",
            )

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", side_effect=fake_run
        ), patch.dict(os.environ, {"EVAL_EXPECT_PLUGIN": ""}, clear=False):
            result = invoke_opencode(
                "openai/gpt-5.6-luna",
                "general",
                "test prompt",
                240,
            )

        self.assertEqual(result["exit_code"], 124)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["session_id"], "ses_timeout")
        self.assertEqual(result["tools"], ["loom_start", "subagent"])
        self.assertEqual(
            result["actions"],
            [
                {"tool": "loom_start", "args": {"request": "tracked investigation"}},
                {"tool": "subagent", "args": {"agent": "diagnostic"}},
            ],
        )
        self.assertIn("partial_events=3", result["stderr"])
        self.assertIn('"part_tool": "subagent"', result["stderr"])
        self.assertIn("provider still running", result["stderr"])

    def test_opencode_eval_uses_fixed_title_to_avoid_title_agent(self):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        calls: list[list[str]] = []

        def fake_run(command, cwd, env, timeout):
            calls.append(command)
            return Result()

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", side_effect=fake_run
        ):
            invoke_opencode(
                "openai/gpt-5.5",
                "general",
                "test prompt",
                30,
            )

        self.assertEqual(len(calls), 1)
        command = calls[0]
        self.assertIn("--title", command)
        self.assertEqual(command[command.index("--title") + 1], "opencode-eval-runner")

    def test_skill_under_test_is_reported_without_forcing_a_load(self):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", return_value=Result()
        ):
            result = invoke_opencode(
                "openai/gpt-5.5",
                "reviewer",
                "review this change",
                30,
                "architectural-design",
            )

        self.assertEqual(result["skill"], "architectural-design")
        self.assertEqual(result["skills_loaded"], [])

    def test_expected_plugin_preflight_waits_for_activation_then_accepts_active_plugin(self):
        server = object()
        requests = []

        def fake_request(base_url, path, *, method="GET", payload=None, timeout=5.0, authorization=None):
            requests.append((base_url, path, method, payload, timeout, authorization))
            self.assertEqual(authorization, "Basic test-auth")
            if path == "/api/session":
                return {"data": {"id": "ses_test"}}
            if path == "/api/session/ses_test/prompt":
                self.assertEqual(payload, {"text": "plugin activation preflight", "resume": False})
                return {"data": {"id": "msg_test"}}
            if path.startswith("/api/plugin?"):
                return {
                    "location": {"directory": "/workspace"},
                    "data": [
                        {"id": "builtin", "state": {"status": "active"}},
                        {"id": "loom", "state": {"status": "active"}},
                    ],
                }
            raise AssertionError(path)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke._start_preflight_server",
            return_value=(server, "http://127.0.0.1:1234", "Basic test-auth"),
        ), patch(
            "container.invoke._standalone_json_request",
            side_effect=fake_request,
        ), patch(
            "container.invoke._stop_preflight_server",
            return_value="server logs",
        ):
            config = Path(tmp)
            plugins = config / "plugins"
            plugins.mkdir()
            (plugins / "loom.ts").write_text("export default {}\n", encoding="utf-8")
            env = {"OPENCODE_CONFIG_DIR": tmp}
            result = verify_expected_plugin(env, "general", "openai/gpt-5.5", "loom", 30)

        self.assertEqual(result["expected"], "loom")
        self.assertEqual(result["agent"], "general")
        self.assertEqual(result["entrypoints"], ["plugins/loom.ts"])
        self.assertEqual(result["plugin"]["id"], "loom")
        self.assertEqual(result["plugin"]["state"]["status"], "active")
        self.assertEqual(
            result["verification"],
            "plugin-entrypoint+activation-barrier+plugin-inventory",
        )
        self.assertTrue(all(request[5] == "Basic test-auth" for request in requests))
        self.assertEqual(
            [request[1] for request in requests],
            [
                "/api/session",
                "/api/session/ses_test/prompt",
                "/api/plugin?location%5Bdirectory%5D=%2Fworkspace",
            ],
        )

    def test_expected_plugin_preflight_uses_bounded_server_timeout(self):
        seen = []

        def fake_start(env, timeout):
            seen.append(timeout)
            return object(), "http://127.0.0.1:1234", "Basic test-auth"

        def fake_request(base_url, path, *, method="GET", payload=None, timeout=5.0, authorization=None):
            if path == "/api/session":
                return {"data": {"id": "ses_test"}}
            if path == "/api/session/ses_test/prompt":
                return {"data": {"id": "msg_test"}}
            return {"data": [{"id": "loom", "state": {"status": "active"}}]}

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke._start_preflight_server",
            side_effect=fake_start,
        ), patch(
            "container.invoke._standalone_json_request",
            side_effect=fake_request,
        ), patch(
            "container.invoke._stop_preflight_server",
            return_value="",
        ):
            config = Path(tmp)
            plugins = config / "plugins"
            plugins.mkdir()
            (plugins / "loom.ts").write_text("export default {}\n", encoding="utf-8")
            verify_expected_plugin(
                {"OPENCODE_CONFIG_DIR": tmp},
                "general",
                "openai/gpt-5.5",
                "loom",
                240,
            )

        self.assertEqual(seen, [30])

    def test_expected_plugin_preflight_rejects_missing_plugin_after_activation(self):
        server = object()

        def fake_request(base_url, path, *, method="GET", payload=None, timeout=5.0, authorization=None):
            if path == "/api/session":
                return {"data": {"id": "ses_test"}}
            if path == "/api/session/ses_test/prompt":
                return {"data": {"id": "msg_test"}}
            return {"data": [{"id": "builtin", "state": {"status": "active"}}]}

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke._start_preflight_server",
            return_value=(server, "http://127.0.0.1:1234", "Basic test-auth"),
        ), patch(
            "container.invoke._standalone_json_request",
            side_effect=fake_request,
        ), patch(
            "container.invoke._stop_preflight_server",
            return_value="activation logs",
        ):
            config = Path(tmp)
            plugins = config / "plugins"
            plugins.mkdir()
            (plugins / "loom.ts").write_text("export default {}\n", encoding="utf-8")
            env = {"OPENCODE_CONFIG_DIR": tmp}
            with self.assertRaisesRegex(
                RuntimeError,
                "not present in OpenCode plugin inventory after activation",
            ):
                verify_expected_plugin(env, "general", "openai/gpt-5.5", "loom", 30)

    def test_expected_plugin_preflight_surfaces_failed_plugin_error_after_activation(self):
        server = object()

        def fake_request(base_url, path, *, method="GET", payload=None, timeout=5.0, authorization=None):
            if path == "/api/session":
                return {"data": {"id": "ses_test"}}
            if path == "/api/session/ses_test/prompt":
                return {"data": {"id": "msg_test"}}
            return {"data": [{
                "id": "loom",
                "state": {
                    "status": "failed",
                    "error": "Cannot resolve @opencode/plugin/rpc",
                    "ref": "err_fixture",
                },
            }]}

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke._start_preflight_server",
            return_value=(server, "http://127.0.0.1:1234", "Basic test-auth"),
        ), patch(
            "container.invoke._standalone_json_request",
            side_effect=fake_request,
        ), patch(
            "container.invoke._stop_preflight_server",
            return_value="server diagnostic output",
        ):
            config = Path(tmp)
            plugins = config / "plugins"
            plugins.mkdir()
            (plugins / "loom.ts").write_text("export default {}\n", encoding="utf-8")
            env = {"OPENCODE_CONFIG_DIR": tmp}
            with self.assertRaisesRegex(
                RuntimeError,
                "Cannot resolve @opencode/plugin/rpc",
            ):
                verify_expected_plugin(env, "general", "openai/gpt-5.5", "loom", 30)

    def test_expected_plugin_preflight_rejects_missing_materialized_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"OPENCODE_CONFIG_DIR": tmp}
            with self.assertRaisesRegex(RuntimeError, "is not materialized"):
                verify_expected_plugin(env, "general", "openai/gpt-5.5", "loom", 30)

    def test_plugin_diagnostic_does_not_spawn_managed_service(self):
        calls = []

        class Result:
            returncode = 0
            stdout = '{"type":"text","text":"ok"}\n'
            stderr = ""

        def fake_run(command, cwd, env, timeout):
            calls.append(command)
            return Result()

        with patch("container.invoke.prepare_opencode_env", return_value={
            "OPENCODE_CONFIG_DIR": "/tmp/runtime/config/opencode"
        }), patch("container.invoke.run", side_effect=fake_run):
            result = invoke_opencode(
                "openai/gpt-5.5",
                "general",
                "test prompt",
                30,
            )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ["opencode", "run"])
        self.assertNotIn(["opencode", "plugin", "list"], calls)
        self.assertEqual(
            result["plugin_diagnostic"]["config_root"],
            "/tmp/runtime/config/opencode",
        )


    def test_workflows_pin_external_actions_by_commit(self):
        root = Path(__file__).resolve().parents[1]
        ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        publish = (root / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        expected = {
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "docker/login-action@c94ce9fb468520275223c153574b00df6fe4bcc9",
            "docker/metadata-action@c299e40c65443455700f0fdfc63efafe5b349051",
            "docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8",
        }
        for value in expected:
            self.assertIn(value, ci + publish)
        for mutable in (
            "actions/checkout@v4",
            "docker/login-action@v3",
            "docker/metadata-action@v5",
            "docker/build-push-action@v6",
        ):
            self.assertNotIn(mutable, ci + publish)

    def test_container_pins_opencode_2_0_15(self):
        containerfile = (Path(__file__).resolve().parents[1] / "Containerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("ARG OPENCODE_VERSION=2.0.15", containerfile)
        self.assertNotIn("ARG OPENCODE_VERSION=2.0.12", containerfile)

    def test_container_pins_base_images_and_copilot_release_asset(self):
        containerfile = (Path(__file__).resolve().parents[1] / "Containerfile").read_text(
            encoding="utf-8"
        )
        for expected in (
            "node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6",
            "debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251",
            "python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e",
            "ffbe1c429664b8a05efed67ecdb467123e40fcaa3c6c14ef9a98ba74da4687b7",
            "213b3a267042dbac3cd8ae22c82f5ea04ff3cabc008108c0f895055d46be4473",
            "sha256sum -c -",
            "github.com/github/copilot-cli/releases/download/v${COPILOT_VERSION}/$asset",
        ):
            self.assertIn(expected, containerfile)
        self.assertNotIn("curl -fsSL https://gh.io/copilot-install", containerfile)
        self.assertNotIn("FROM node:24-bookworm-slim AS", containerfile)
        self.assertNotIn("FROM debian:bookworm-slim AS", containerfile)
        self.assertNotIn("FROM python:3.12-slim-bookworm AS", containerfile)
    def test_container_routes_default_runtime_state_to_tmpfs(self):
        containerfile = (Path(__file__).resolve().parents[1] / "Containerfile").read_text(
            encoding="utf-8"
        )
        for expected in (
            "HOME=/tmp/runtime/home",
            "XDG_CONFIG_HOME=/tmp/runtime/config",
            "XDG_DATA_HOME=/tmp/runtime/data",
            "XDG_CACHE_HOME=/tmp/runtime/cache",
            "XDG_STATE_HOME=/tmp/runtime/state",
            "OPENCODE_DB=opencode.db",
            "OPENCODE_DISABLE_AUTOUPDATE=1",
            "useradd --uid 1000 --gid 1000",
            "USER 1000:1000",
        ):
            self.assertIn(expected, containerfile)


    def test_runtime_exposes_seeded_global_plugins(self):
        invoke = (Path(__file__).resolve().parents[1] / "container" / "invoke.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('seed_config_root = Path("/seed/opencode-config")', invoke)
        self.assertIn('loom_source = seed_config_root / "plugins" / "loom"', invoke)
        self.assertIn('"OPENCODE_CONFIG_DIR": str(config)', invoke)
        self.assertIn('module_root = config / "loom-plugin"', invoke)
        self.assertIn('plugin_root = config / "plugins"', invoke)
        self.assertIn("shutil.copytree(loom_source, module_root, dirs_exist_ok=True)", invoke)
        self.assertIn('(plugin_root / "loom.ts").write_text(', invoke)
        self.assertIn('workspace_node_modules = Path("/workspace/node_modules")', invoke)
        self.assertIn('config_node_modules = config / "node_modules"', invoke)
        self.assertIn(
            "config_node_modules.symlink_to(workspace_node_modules, target_is_directory=True)",
            invoke,
        )
        self.assertNotIn("target.symlink_to(source, target_is_directory=True)", invoke)


if __name__ == "__main__":
    unittest.main()
