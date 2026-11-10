"""Provider-free Claude Agent image and native-account routing checks."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from runner.cli import RunnerError, build_container_command, claude_profile_dir
from container.invoke import require_claude_subscription


class ClaudeAgentProfileTests(unittest.TestCase):
    def args(self, root, **kw):
        p = root / "claude-profile"
        p.mkdir()
        (p / ".credentials.json").write_text('{"claudeAiOauth":{"accessToken":"TEST-ONLY"}}')
        cfg = root / "config.json"
        cfg.write_text('{"providers":{}}')
        args = dict(
            transport="opencode", engine="podman", network=None,
            image="sha256:" + "a" * 64, workspace=str(root),
            workspace_mode="ro", output=str(root / "result.json"),
            mount=[], model="claude-agent/claude-sonnet-5-5", reasoning=None,
            agent="eval-target", skill="agent-run-audit", expected_plugin=None,
            auth=None, database=None, config=str(cfg), config_root=None,
            models_catalog=None, env=[], timeout_seconds=120,
            claude_config_dir=str(p), require_local_opencode_image=False,
        )
        args.update(kw)
        return argparse.Namespace(**args)

    def test_explicit_subscription_profile_uses_pinned_image_and_no_api_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            with patch("runner.cli.resolve_engine", return_value="podman"), patch(
                "runner.cli.verify_local_opencode_image",
                return_value=(["podman", "--remote=false"], {}),
            ) as verify:
                command, _ = build_container_command(args, root, root, host_env={})
            verify.assert_called_once_with("podman", args.image, {}, expected_version="2.2.6")
            text = " ".join(command)
            self.assertIn(f"{Path(args.claude_config_dir).resolve()}:/seed/claude-profile:rw", text)
            self.assertIn("--env EVAL_CLAUDE_CONFIG_DIR=/seed/claude-profile", text)
            self.assertIn("--pull=never", text)
            self.assertNotIn("/seed/auth.json", text)
            self.assertNotIn("/seed/opencode.db", text)
            self.assertNotIn("ANTHROPIC_API_KEY", text)

    def test_missing_profile_cannot_fallback_to_anthropic_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp), claude_config_dir=None)
            with self.assertRaisesRegex(RunnerError, "require --claude-config-dir"):
                claude_profile_dir(args, {})

    def test_account_overrides_and_other_model_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            with self.assertRaisesRegex(RunnerError, "refuses API"):
                claude_profile_dir(args, {"ANTHROPIC_API_KEY": "TEST-ONLY"})
            args.model = "openai/gpt-6"
            with self.assertRaisesRegex(RunnerError, "other models forbid"):
                claude_profile_dir(args, {})
            args.model = "claude-agent/claude-sonnet-5-5"
            args.auth = "/tmp/test-auth"
            with self.assertRaisesRegex(RunnerError, "cannot inherit"):
                claude_profile_dir(args, {})

    def test_native_status_is_required_before_inference(self):
        with patch.dict("os.environ", {"EVAL_CLAUDE_CONFIG_DIR": "/seed/claude-profile"}), patch(
            "container.invoke.Path.is_dir", return_value=True
        ), patch("container.invoke.Path.is_file", return_value=True), patch(
            "container.invoke.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"})
            env = {}
            require_claude_subscription(env, "claude-agent/claude-sonnet-5-5")
            self.assertEqual(env["CLAUDE_CONFIG_DIR"], "/seed/claude-profile")
            run.return_value.stdout = json.dumps({"loggedIn": True, "authMethod": "api-key"})
            with self.assertRaisesRegex(RuntimeError, "native Claude subscription"):
                require_claude_subscription({}, "claude-agent/claude-sonnet-5-5")


if __name__ == "__main__":
    unittest.main()
