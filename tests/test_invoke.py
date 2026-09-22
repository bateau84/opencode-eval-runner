from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from container.invoke import (
    assistant_from_export,
    extract_actions,
    extract_loaded_skills,
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

    def test_expected_plugin_preflight_accepts_materialized_plugin_and_agent(self):
        calls = []

        class Result:
            returncode = 0
            stderr = ""

            def __init__(self, stdout):
                self.stdout = stdout

        def fake_run(command, cwd, env, timeout):
            calls.append(command)
            if command[-1] == "/api/agent":
                return Result(json.dumps([
                    {"id": "general", "name": "general"},
                    {"id": "reviewer", "name": "reviewer"},
                ]))
            if command[-1] == "/api/experimental/tool/ids":
                return Result(json.dumps(["read", "loom_start", "loom_route", "loom_status"]))
            raise AssertionError(command)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke.run", side_effect=fake_run
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
        self.assertEqual(result["tools"], ["loom_route", "loom_start", "loom_status"])
        self.assertEqual(result["verification"], "plugin-entrypoint+opencode-startup+tool-registry")
        self.assertEqual(calls[0], ["opencode", "api", "--standalone", "get", "/api/agent"])
        self.assertEqual(
            calls[1],
            ["opencode", "api", "--standalone", "get", "/api/experimental/tool/ids"],
        )

    def test_expected_plugin_preflight_bounds_standalone_startup_timeout(self):
        seen = []

        class Result:
            returncode = 0
            stderr = ""

            def __init__(self, stdout):
                self.stdout = stdout

        def fake_run(command, cwd, env, timeout):
            seen.append(timeout)
            if command[-1] == "/api/agent":
                return Result(json.dumps([{"id": "general", "name": "general"}]))
            return Result(json.dumps(["loom_start"]))

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke.run", side_effect=fake_run
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

        self.assertEqual(seen, [30, 30])

    def test_expected_plugin_preflight_rejects_plugin_without_registered_tools(self):
        class Result:
            returncode = 0
            stderr = ""

            def __init__(self, stdout):
                self.stdout = stdout

        def fake_run(command, cwd, env, timeout):
            if command[-1] == "/api/agent":
                return Result(json.dumps([{"id": "general", "name": "general"}]))
            return Result(json.dumps(["read", "grep", "execute"]))

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke.run", side_effect=fake_run
        ):
            config = Path(tmp)
            plugins = config / "plugins"
            plugins.mkdir()
            (plugins / "loom.ts").write_text("export default {}\n", encoding="utf-8")
            env = {"OPENCODE_CONFIG_DIR": tmp}
            with self.assertRaisesRegex(RuntimeError, "registered no tools"):
                verify_expected_plugin(env, "general", "openai/gpt-5.5", "loom", 30)

    def test_expected_plugin_preflight_rejects_missing_materialized_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"OPENCODE_CONFIG_DIR": tmp}
            with self.assertRaisesRegex(RuntimeError, "is not materialized"):
                verify_expected_plugin(env, "general", "openai/gpt-5.5", "loom", 30)

    def test_expected_plugin_preflight_rejects_missing_agent(self):
        class Result:
            returncode = 0
            stdout = json.dumps([{"id": "reviewer", "name": "reviewer"}])
            stderr = ""

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke.run", return_value=Result()
        ):
            config = Path(tmp)
            plugins = config / "plugins"
            plugins.mkdir()
            (plugins / "loom.ts").write_text("export default {}\n", encoding="utf-8")
            env = {"OPENCODE_CONFIG_DIR": tmp}
            with self.assertRaisesRegex(RuntimeError, "could not resolve agent 'general'"):
                verify_expected_plugin(env, "general", "openai/gpt-5.5", "loom", 30)

    def test_expected_plugin_preflight_rejects_opencode_startup_failure(self):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "plugin initialization failed"

        with tempfile.TemporaryDirectory() as tmp, patch(
            "container.invoke.run", return_value=Result()
        ):
            config = Path(tmp)
            plugins = config / "plugins"
            plugins.mkdir()
            (plugins / "loom.ts").write_text("export default {}\n", encoding="utf-8")
            env = {"OPENCODE_CONFIG_DIR": tmp}
            with self.assertRaisesRegex(RuntimeError, "plugin initialization failed"):
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
        self.assertNotIn("target.symlink_to(source, target_is_directory=True)", invoke)


if __name__ == "__main__":
    unittest.main()
