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
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ["opencode", "run"])
        self.assertIn("--model", calls[0])
        self.assertNotIn("--refresh", calls[0])
        self.assertNotIn("models", calls[0][1:])

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
            'for name in ("plugins", "node_modules")',
            "useradd --uid 1000 --gid 1000",
            "USER 1000:1000",
        ):
            self.assertIn(expected, containerfile)


if __name__ == "__main__":
    unittest.main()
