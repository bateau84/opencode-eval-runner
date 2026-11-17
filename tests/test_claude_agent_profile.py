"""Provider-free Claude Agent image and native-account routing checks."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from runner.cli import (RunnerError, build_container_command, claude_profile_dir,
                        claude_profile_lock, invoke)
from container.invoke import require_claude_subscription, bootstrap_claude_model


class ClaudeAgentProfileTests(unittest.TestCase):
    def args(self, root, **kw):
        p = root / "claude-profile"
        p.mkdir()
        p.chmod(0o700)
        (p / ".credentials.json").write_text('{"claudeAiOauth":{"accessToken":"TEST-ONLY"}}')
        (p / ".credentials.json").chmod(0o600)
        cfg = root / "config.json"
        cfg.write_text(json.dumps({
            "share": "disabled", "plugins": ["-opencode.skill", "-opencode.browser"],
            "instructions": [], "permissions": [{"action":"*","resource":"*","effect":"deny"}],
            "default_agent": "eval-target", "agents": {
                "eval-target": {"mode": "primary", "permissions": [
                    {"action":"*","resource":"*","effect":"deny"},
                    {"action":"skill","resource":"agent-run-audit","effect":"allow"}
                ]}
            }
        }))
        args = dict(
            transport="opencode", engine="podman", network=None,
            image="sha256:" + "a" * 64, workspace=str(root),
            workspace_mode="ro", output=str(root / "result.json"),
            mount=[], model="claude-agent/claude-sonnet-5-5", reasoning=None,
            agent="eval-target", skill="agent-run-audit", expected_plugin=None,
            auth=None, database=None, config=str(cfg), config_root=None,
            models_catalog=None, env=[], timeout_seconds=120,
            claude_config_dir=str(p), claude_billing_confirmed=True,
            require_local_opencode_image=False,
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

    def test_rejects_public_symlinked_and_unrelated_profile_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            credential = Path(args.claude_config_dir) / ".credentials.json"
            credential.chmod(0o644)
            with self.assertRaisesRegex(RunnerError, "private"):
                claude_profile_dir(args, {})
            credential.chmod(0o600)
            (credential.parent / "private-notes.txt").write_text("unexpected")
            with self.assertRaisesRegex(RunnerError, "unrelated"):
                claude_profile_dir(args, {})
            (credential.parent / "private-notes.txt").unlink()
            credential.rename(credential.parent / "settings.json")
            credential.symlink_to(credential.parent / "settings.json")
            with self.assertRaisesRegex(RunnerError, "not linked|real"):
                claude_profile_dir(args, {})

    def test_rejects_unrestricted_agent_permissions_and_extra_mounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            config = json.loads(Path(args.config).read_text())
            config["agents"]["eval-target"]["permissions"].append(
                {"action": "read", "resource": "/seed/claude-profile/.credentials.json", "effect": "allow"}
            )
            Path(args.config).write_text(json.dumps(config))
            with self.assertRaisesRegex(RunnerError, "selected skill resources"):
                claude_profile_dir(args, {})
            config["agents"]["eval-target"]["permissions"].pop()
            Path(args.config).write_text(json.dumps(config))
            args.mount = ["/tmp:/injected"]
            with self.assertRaisesRegex(RunnerError, "extra mounts"):
                claude_profile_dir(args, {})

    def test_host_profile_lock_blocks_competing_invocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            profile = Path(args.claude_config_dir)
            with claude_profile_lock(profile):
                with self.assertRaisesRegex(RunnerError, "already in use"):
                    with claude_profile_lock(profile):
                        pass

    def test_invalid_container_diagnostics_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root, model="openai/not-called", claude_config_dir=None,
                             transport="github-copilot-cli", prompt_file=str(root / "prompt.txt"),
                             system_file=None, container_timeout=3, print_result=False)
            (root / "prompt.txt").write_text("no model call")
            with patch("runner.cli.build_container_command", return_value=(["synthetic"], root)), patch(
                "runner.cli.subprocess.run"
            ) as run:
                run.return_value.returncode = 91
                run.return_value.stdout = "MALFORMED SECRET-MARKER"
                run.return_value.stderr = "SECRET-MARKER in raw stderr"
                with self.assertRaises(RunnerError) as caught:
                    invoke(args)
            self.assertNotIn("SECRET-MARKER", str(caught.exception))
            self.assertFalse(Path(args.output).exists())

    def test_native_discovery_requires_exact_catalog_model_without_prompt(self):
        model = "claude-agent/claude-sonnet-5-5"
        integration = {"id": "claude-agent", "methods": [{"id": "claude-login", "type": "external"}], "connections": []}
        discovered = [{"providerID": "claude-agent", "id": "claude-sonnet-5-5"}]
        responses = [{"id":"ses_fixture"}, None, integration, None, [], discovered]
        with patch("container.invoke._start_preflight_server", return_value=(object(), "http://fake", "auth")), patch(
            "container.invoke._standalone_json_request", side_effect=responses
        ) as request, patch("container.invoke._stop_preflight_server") as stop, patch(
            "container.invoke.time.sleep"
        ):
            bootstrap_claude_model({}, model, 3)
            self.assertEqual(request.call_args_list[1].args[1], "/api/session/ses_fixture/prompt")
            self.assertIs(request.call_args_list[1].kwargs["payload"]["resume"], False)
            self.assertEqual(request.call_args_list[3].args[1], "/api/integration/claude-agent/connect/external")
            self.assertEqual(request.call_args_list[3].kwargs["payload"], {"methodID": "claude-login"})
            stop.assert_called_once()
        with patch("container.invoke._start_preflight_server", return_value=(object(), "http://fake", "auth")), patch(
            "container.invoke._standalone_json_request", side_effect=[
                {"id":"ses_fixture"}, None, integration, None, {"data": "wrong-shape"}]
        ), patch("container.invoke._stop_preflight_server"):
            with self.assertRaisesRegex(RuntimeError, "before inference"):
                bootstrap_claude_model({}, model, 3)

    def test_profile_native_settings_cannot_install_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            settings = Path(args.claude_config_dir) / "settings.json"
            settings.write_text('{"hooks":{"PreToolUse":[{"command":"cat /seed/claude-profile/.credentials.json"}]}}')
            settings.chmod(0o600)
            with self.assertRaisesRegex(RunnerError, "executable hooks"):
                claude_profile_dir(args, {})
            settings.write_text("{}")
            self.assertEqual(claude_profile_dir(args, {}), Path(args.claude_config_dir).resolve())

    def test_selected_skill_symlink_cannot_escape_to_credential_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            skill_dir = root / ".opencode" / "skills" / "agent-run-audit"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").symlink_to("/seed/claude-profile/.credentials.json")
            with self.assertRaisesRegex(RunnerError, "must not traverse symlinks"):
                claude_profile_dir(args, {})

    def test_billing_acknowledgement_is_required_but_not_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp), claude_billing_confirmed=False)
            with self.assertRaisesRegex(RunnerError, "--claude-billing-confirmed"):
                claude_profile_dir(args, {})
            args.claude_billing_confirmed = True
            self.assertEqual(claude_profile_dir(args, {}), Path(args.claude_config_dir).resolve())


    def test_native_state_profile_is_accepted_on_repeated_preflights(self):
        """Native Claude writes account metadata and session state under CLAUDE_CONFIG_DIR."""
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            profile = Path(args.claude_config_dir)
            (profile / ".claude.json").write_text(json.dumps({
                "oauthAccount": {"accountUuid": "fixture-account", "organizationUuid": "fixture-org"},
                "hasCompletedOnboarding": True, "mcpServers": {},
                "projects": {"/workspace": {"hasTrustDialogAccepted": True, "allowedTools": []}},
            }))
            (profile / ".claude.json").chmod(0o600)
            backup = profile / "backups"
            backup.mkdir(mode=0o700)
            (backup / ".claude.json.backup").write_text('{"oauthAccount":{"accountUuid":"fixture-account"}}')
            (backup / ".claude.json.backup").chmod(0o600)
            projects = profile / "projects"
            projects.mkdir(mode=0o700)
            project = projects / "fixture-workspace"
            project.mkdir(mode=0o700)
            (project / "fixture-session.jsonl").write_text('{"type":"system","subtype":"init"}\\n')
            (project / "fixture-session.jsonl").chmod(0o600)
            for _ in range(2):
                self.assertEqual(claude_profile_dir(args, {}), profile.resolve())

    def test_native_state_rejects_tool_and_provider_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            profile = Path(args.claude_config_dir)
            state = profile / ".claude.json"
            for value in (
                {"mcpServers": {"unexpected": {"command": "sh", "args": []}}},
                {"projects": {"/workspace": {"allowedTools": ["Bash(*)"]}}},
                {"hooks": {"PreToolUse": [{"command": "echo unexpected"}]}},
                {"env": {"ANTHROPIC_API_KEY": "FAKE-ONLY"}},
            ):
                with self.subTest(value=value):
                    state.write_text(json.dumps(value))
                    state.chmod(0o600)
                    with self.assertRaisesRegex(RunnerError, "native state|provider|executable"):
                        claude_profile_dir(args, {})
            state.unlink()
            (profile / "plugins").mkdir(mode=0o700)
            with self.assertRaisesRegex(RunnerError, "unrelated|unsupported"):
                claude_profile_dir(args, {})

    def test_native_state_rejects_symlinks_and_public_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            profile = Path(args.claude_config_dir)
            project = profile / "projects"
            project.mkdir(mode=0o700)
            file = project / "session.jsonl"
            file.write_text('{"type":"system"}\\n')
            file.chmod(0o644)
            with self.assertRaisesRegex(RunnerError, "private"):
                claude_profile_dir(args, {})
            file.chmod(0o600)
            self.assertEqual(claude_profile_dir(args, {}), profile.resolve())
            file.rename(project / "actual.jsonl")
            file.symlink_to(project / "actual.jsonl")
            with self.assertRaisesRegex(RunnerError, "linked|private|regular"):
                claude_profile_dir(args, {})


    def test_rotated_credential_cannot_escape_through_protocol_evidence(self):
        """The final sink must rescan credentials minted after observer startup."""
        import io
        from contextlib import redirect_stdout
        from container.invoke import emit_result, unsupported_runtime_evidence
        with tempfile.TemporaryDirectory() as tmp:
            credential = Path(tmp) / ".credentials.json"
            credential.write_text(json.dumps({
                "claudeAiOauth": {"refreshToken": "SYNTHETIC-POST-START-ROTATED-SECRET"}
            }))
            result = {
                "schema": "opencode-eval-runner/v1", "transport": "opencode",
                "model": "claude-agent/claude-sonnet-5-5",
                "reasoning": "provider-default", "reasoning_source": "provider-default",
                "exit_code": 0, "text": "benign model output",
                "tool_result_evidence": {"unexpected": "SYNTHETIC-POST-START-ROTATED-SECRET"},
                "runtime_evidence": unsupported_runtime_evidence(
                    "runtime_observer_unavailable_after_infrastructure_error"
                ),
            }
            out = io.StringIO()
            with patch.dict("os.environ", {"EVAL_CLAUDE_CONFIG_DIR": "/seed/claude-profile"}, clear=True), patch(
                "container.invoke.RUNTIME_JSON_CREDENTIAL_SOURCES", (credential,)
            ), redirect_stdout(out):
                emit_result(result)
            body = out.getvalue()
            self.assertNotIn("SYNTHETIC-POST-START-ROTATED-SECRET", body)
            emitted = json.loads(body)
            self.assertTrue(emitted["infrastructure_error"])
            self.assertEqual(emitted["exit_code"], 2)
            self.assertEqual(emitted["runtime_evidence"]["status"], "unsupported")

    def test_late_corrupt_credential_inventory_withholds_success(self):
        import io
        from contextlib import redirect_stdout
        from container.invoke import emit_result, unsupported_runtime_evidence
        with tempfile.TemporaryDirectory() as tmp:
            credential = Path(tmp) / ".credentials.json"
            credential.write_text("{invalid-json")
            result = {
                "schema": "opencode-eval-runner/v1", "transport": "opencode",
                "model": "claude-agent/test", "reasoning": "provider-default",
                "reasoning_source": "provider-default", "exit_code": 0,
                "text": "would otherwise pass",
                "runtime_evidence": unsupported_runtime_evidence(
                    "runtime_observer_unavailable_after_infrastructure_error"
                ),
            }
            out = io.StringIO()
            with patch.dict("os.environ", {"EVAL_CLAUDE_CONFIG_DIR": "/seed/claude-profile"}, clear=True), patch(
                "container.invoke.RUNTIME_JSON_CREDENTIAL_SOURCES", (credential,)
            ), redirect_stdout(out):
                emit_result(result)
            emitted = json.loads(out.getvalue())
            self.assertEqual(emitted["exit_code"], 2)
            self.assertTrue(emitted["infrastructure_error"])
            self.assertNotIn("would otherwise pass", out.getvalue())


    def test_post_refresh_sink_includes_initial_and_rotated_credentials(self):
        import io
        from contextlib import redirect_stdout
        from container.invoke import emit_result, unsupported_runtime_evidence
        with tempfile.TemporaryDirectory() as tmp:
            credential = Path(tmp) / ".credentials.json"
            credential.write_text('{"claudeAiOauth":{"refreshToken":"SYNTHETIC-ROTATED"}}')
            result = {
                "schema": "opencode-eval-runner/v1", "transport": "opencode",
                "model": "claude-agent/test", "reasoning": "provider-default",
                "reasoning_source": "provider-default", "exit_code": 0,
                "runtime_evidence": unsupported_runtime_evidence(
                    "runtime_observer_unavailable_after_infrastructure_error"
                ),
                "tool_result_evidence": {"unexpected": "SYNTHETIC-BEFORE-REFRESH"},
                "text": "innocent",
            }
            out = io.StringIO()
            with patch.dict("os.environ", {
                "EVAL_CLAUDE_CONFIG_DIR": "/seed/claude-profile",
                "OPENCODE_EVAL_OBSERVER_CREDENTIALS": '["SYNTHETIC-BEFORE-REFRESH"]',
            }, clear=True), patch("container.invoke.RUNTIME_JSON_CREDENTIAL_SOURCES", (credential,)), redirect_stdout(out):
                emit_result(result)
            body = out.getvalue()
            self.assertNotIn("SYNTHETIC-BEFORE-REFRESH", body)
            self.assertNotIn("SYNTHETIC-ROTATED", body)
            self.assertTrue(json.loads(body)["infrastructure_error"])

    def test_post_refresh_missing_credential_file_cannot_claim_success(self):
        import io
        from contextlib import redirect_stdout
        from container.invoke import emit_result, unsupported_runtime_evidence
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / ".credentials.json"
            result = {
                "schema": "opencode-eval-runner/v1", "transport": "opencode",
                "model": "claude-agent/test", "reasoning": "provider-default",
                "reasoning_source": "provider-default", "exit_code": 0,
                "runtime_evidence": unsupported_runtime_evidence(
                    "runtime_observer_unavailable_after_infrastructure_error"
                ),
                "text": "cannot prove auth persists",
            }
            out = io.StringIO()
            with patch.dict("os.environ", {"EVAL_CLAUDE_CONFIG_DIR": "/seed/claude-profile"}, clear=True), patch(
                "container.invoke.RUNTIME_JSON_CREDENTIAL_SOURCES", (missing,)
            ), redirect_stdout(out):
                emit_result(result)
            self.assertTrue(json.loads(out.getvalue())["infrastructure_error"])
            self.assertNotIn("cannot prove auth persists", out.getvalue())


    def test_claude_process_creates_native_state_with_private_umask(self):
        from container.invoke import main
        with patch.dict("os.environ", {
            "EVAL_CLAUDE_CONFIG_DIR": "/seed/claude-profile",
            "EVAL_MODEL": "claude-agent/test",
            "EVAL_PROMPT_FILE": "/nonexistent-eval-prompt",
        }, clear=True), patch("container.invoke.os.umask") as umask, patch(
            "container.invoke.emit_result"
        ):
            self.assertEqual(main(), 2)
            umask.assert_called_once_with(0o077)


if __name__ == "__main__":
    unittest.main()
