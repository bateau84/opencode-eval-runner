from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from runner.cli import (
    COPILOT_AUTH_ENVS,
    DEFAULT_IMAGES,
    RunnerError,
    build_container_command,
    default_auth_path,
    default_database_path,
    default_models_path,
    sanitize_database_seed,
    resolve_engine,
    host_environment_for_transport,
)


class RunnerCliTests(unittest.TestCase):
    def test_default_auth_uses_xdg_data_home(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_DATA_HOME": tmp}, clear=False):
            self.assertEqual(default_auth_path(), Path(tmp) / "opencode" / "auth.json")


    def test_default_images_are_transport_specific(self):
        self.assertEqual(
            DEFAULT_IMAGES["opencode"],
            "ghcr.io/bateau84/opencode-eval-runner:opencode-edge",
        )
        self.assertEqual(
            DEFAULT_IMAGES["github-copilot-cli"],
            "ghcr.io/bateau84/opencode-eval-runner:copilot-edge",
        )
        self.assertNotEqual(
            DEFAULT_IMAGES["opencode"],
            DEFAULT_IMAGES["github-copilot-cli"],
        )

    def test_default_models_uses_xdg_cache_home(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=False):
            self.assertEqual(default_models_path(), Path(tmp) / "opencode" / "models.json")

    def test_default_database_uses_xdg_data_home(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_DATA_HOME": tmp}, clear=False):
            self.assertEqual(default_database_path(), Path(tmp) / "opencode" / "opencode.db")

    def test_sanitized_database_keeps_credentials_and_clears_runtime_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "opencode.db"
            destination = root / "sanitized.db"
            with sqlite3.connect(source) as db:
                db.execute(
                    "CREATE TABLE credential ("
                    "id TEXT PRIMARY KEY, integration_id TEXT, label TEXT NOT NULL, value TEXT NOT NULL)"
                )
                db.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")
                db.execute("CREATE TABLE migration (id TEXT PRIMARY KEY, time_completed INTEGER NOT NULL)")
                db.execute(
                    "INSERT INTO credential VALUES (?, ?, ?, ?)",
                    ("cred_1", "openai", "default", '{"type":"oauth","access":"secret"}'),
                )
                db.execute("INSERT INTO session VALUES (?, ?)", ("ses_1", "private session"))
                db.execute("INSERT INTO migration VALUES (?, ?)", ("m1", 1))
                db.commit()

            sanitize_database_seed(source, destination)

            with sqlite3.connect(destination) as db:
                credential = db.execute(
                    "SELECT integration_id, label, value FROM credential"
                ).fetchone()
                sessions = db.execute("SELECT COUNT(*) FROM session").fetchone()[0]
                migrations = db.execute("SELECT COUNT(*) FROM migration").fetchone()[0]

            self.assertEqual(credential[0:2], ("openai", "default"))
            self.assertIn('"type":"oauth"', credential[2])
            self.assertEqual(sessions, 0)
            self.assertEqual(migrations, 1)

    def test_explicit_missing_engine_is_rejected(self):
        with patch("runner.cli.shutil.which", return_value=None):
            with self.assertRaises(RunnerError):
                resolve_engine("podman")


    def test_podman_disables_selinux_labeling_without_relabeling_host_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            workspace.mkdir()
            input_dir.mkdir()
            output_dir.mkdir()
            args = argparse.Namespace(
                engine="podman",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                output=str(root / "result.json"),
                transport="opencode",
                model="openai/test",
                agent="reviewer",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
            )
            with patch("runner.cli.shutil.which", return_value="/usr/bin/podman"), patch.dict(os.environ, {}, clear=True):
                command, _ = build_container_command(args, input_dir, output_dir)

            rendered = " ".join(command)
            self.assertIn("--security-opt label=disable", rendered)
            self.assertIn("--userns keep-id:uid=1000,gid=1000", rendered)
            self.assertNotIn(":Z", rendered)
            self.assertNotIn(":z", rendered)
            self.assertNotIn("/output", rendered)
            self.assertNotIn("EVAL_RESULT_FILE", rendered)

    def test_skill_under_test_is_passed_to_opencode_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            args = argparse.Namespace(
                engine="podman",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                output=str(root / "result.json"),
                transport="opencode",
                model="openai/test",
                agent="reviewer",
                skill="architectural-design",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
            )
            with patch("runner.cli.shutil.which", return_value="/usr/bin/podman"), patch.dict(
                os.environ, {}, clear=True
            ):
                command, _ = build_container_command(args, input_dir, output_dir)

            self.assertIn("--env EVAL_SKILL=architectural-design", " ".join(command))

    def test_skill_under_test_is_rejected_for_copilot_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            args = argparse.Namespace(
                engine="podman",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                output=str(root / "result.json"),
                transport="github-copilot-cli",
                model="gpt-5.4",
                agent="",
                skill="architectural-design",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
            )
            with self.assertRaisesRegex(RunnerError, "--skill is only supported"):
                build_container_command(args, input_dir, output_dir)

    def test_docker_does_not_add_podman_label_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            workspace.mkdir()
            input_dir.mkdir()
            output_dir.mkdir()
            args = argparse.Namespace(
                engine="docker",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                output=str(root / "result.json"),
                transport="opencode",
                model="openai/test",
                agent="reviewer",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
            )
            with patch("runner.cli.shutil.which", return_value="/usr/bin/docker"), patch.dict(os.environ, {}, clear=True):
                command, _ = build_container_command(args, input_dir, output_dir)

            self.assertNotIn("label=disable", command)
            rendered = " ".join(command)
            if hasattr(os, "getuid") and os.getuid() != 0:
                self.assertIn(f"--user {os.getuid()}:{os.getgid()}", rendered)
            self.assertNotIn("/output", rendered)
            self.assertNotIn("EVAL_RESULT_FILE", rendered)


    def test_config_root_is_mounted_read_only_when_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            config_root = root / "config-root"
            for path in (workspace, input_dir, output_dir, config_root):
                path.mkdir()
            args = argparse.Namespace(
                engine="podman",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                output=str(root / "result.json"),
                transport="opencode",
                model="openai/test",
                agent="general",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
                config_root=str(config_root),
            )
            with patch("runner.cli.shutil.which", return_value="/usr/bin/podman"), patch.dict(os.environ, {}, clear=True):
                command, _ = build_container_command(args, input_dir, output_dir)

            rendered = " ".join(command)
            self.assertIn(str(config_root.resolve()), rendered)
            self.assertIn("/seed/opencode-config:ro", rendered)


    def test_models_catalog_defaults_to_host_cache_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            workspace.mkdir()
            input_dir.mkdir()
            output_dir.mkdir()
            args = argparse.Namespace(
                engine="podman",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                output=str(root / "result.json"),
                transport="opencode",
                model="openai/test",
                agent="reviewer",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
            )
            cache_dir = root / "cache" / "opencode"
            cache_dir.mkdir(parents=True)
            models = cache_dir / "models.json"
            models.write_text("{}", encoding="utf-8")
            with patch("runner.cli.shutil.which", return_value="/usr/bin/podman"), patch.dict(
                os.environ,
                {"XDG_CACHE_HOME": str(root / "cache")},
                clear=True,
            ):
                command, _ = build_container_command(args, input_dir, output_dir)

            rendered = " ".join(command)
            self.assertIn(str(models.resolve()), rendered)
            self.assertIn("/seed/models.json:ro", rendered)


    def test_copilot_uses_gh_auth_token_fallback_without_exposing_value(self):
        fake = subprocess.CompletedProcess(["gh", "auth", "token"], 0, stdout="gho_example\n", stderr="")
        with patch("runner.cli.shutil.which", side_effect=lambda name: "/usr/bin/gh" if name == "gh" else "/usr/bin/podman"), \
             patch("runner.cli.subprocess.run", return_value=fake), \
             patch.dict(os.environ, {}, clear=True):
            env = host_environment_for_transport("github-copilot-cli")

        self.assertEqual(env["COPILOT_GITHUB_TOKEN"], "gho_example")

    def test_copilot_explicit_env_beats_gh_fallback(self):
        with patch("runner.cli.subprocess.run") as run, patch.dict(
            os.environ,
            {"GH_TOKEN": "explicit"},
            clear=True,
        ):
            env = host_environment_for_transport("github-copilot-cli")

        self.assertEqual(env["GH_TOKEN"], "explicit")
        run.assert_not_called()

    def test_copilot_transport_passes_supported_token_names_only_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            workspace.mkdir()
            input_dir.mkdir()
            output_dir.mkdir()
            output = root / "result.json"
            args = argparse.Namespace(
                engine="podman",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                output=str(output),
                transport="github-copilot-cli",
                model="gpt-5.4",
                agent="",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
            )
            with patch("runner.cli.shutil.which", return_value="/usr/bin/podman"), patch.dict(
                os.environ,
                {"COPILOT_GITHUB_TOKEN": "secret"},
                clear=True,
            ):
                command, _ = build_container_command(args, input_dir, output_dir)

            rendered = " ".join(command)
            self.assertIn("--env COPILOT_GITHUB_TOKEN", rendered)
            self.assertNotIn("secret", rendered)
            for name in COPILOT_AUTH_ENVS[1:]:
                self.assertNotIn(f"--env {name}", rendered)


if __name__ == "__main__":
    unittest.main()
