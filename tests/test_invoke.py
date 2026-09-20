from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from container.invoke import invoke_opencode


class OpenCodeTransportTests(unittest.TestCase):
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
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ["opencode", "plugin", "list"])
        self.assertEqual(calls[1][0:2], ["opencode", "run"])
        self.assertIn("--model", calls[1])
        self.assertNotIn("--refresh", calls[1])
        self.assertNotIn("models", calls[1][1:])

    def test_required_plugin_missing_is_infrastructure_error(self):
        class Result:
            returncode = 0
            stdout = "ID    VERSION  SOURCE\nother local    /tmp/other\n"
            stderr = ""

        with patch("container.invoke.prepare_opencode_env", return_value={}), patch(
            "container.invoke.run", return_value=Result()
        ), patch.dict("container.invoke.os.environ", {"EVAL_EXPECT_PLUGIN": "loom"}, clear=False):
            result = invoke_opencode(
                "openai/gpt-5.5",
                "general",
                "test prompt",
                30,
            )

        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result["infrastructure_error"])
        self.assertIn("required OpenCode plugin not loaded: loom", result["stderr"])


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
