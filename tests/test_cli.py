from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from container.evidence_safety import JSON_SOURCE_LIMIT, MODEL_CATALOG_SOURCE_LIMIT
from runner.cli import (
    COPILOT_AUTH_ENVS,
    DEFAULT_IMAGES,
    RunnerError,
    build_container_command,
    default_auth_path,
    default_database_path,
    default_models_path,
    extra_mount_arg,
    host_environment_for_transport,
    resolve_engine,
    sanitize_database_seed,
)
from runner.oci_image import SUPPORTED_INVOKE_ADAPTER_ID, SUPPORTED_OPENCODE_VERSION


def inspected_image_result(
    image: str, *, version=None, adapter=None, image_id=None,
    repo_digest=None, returncode=0,
):
    labels = {}
    if version is not None:
        labels["org.opencontainers.image.version"] = version
    if adapter is not None:
        labels["io.opencode-eval-runner.invoke-adapter"] = adapter
    result = {
        "Id": "sha256:" + (image_id or "a" * 64),
        "RepoDigests": [repo_digest if repo_digest is not None else image]
        if "@" in image else [],
        "Config": {"Labels": labels},
    }
    return SimpleNamespace(returncode=returncode, stdout=json.dumps(result), stderr="")


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

    def test_builtin_eval_accepts_multiple_caller_selected_immutable_local_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace, input_dir, output_dir = (
                root / "workspace", root / "input", root / "output"
            )
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            identities = (
                ("a" * 64, "a" * 64),
                ("sha256:" + "b" * 64, "b" * 64),
                ("registry.example/opencode@sha256:" + "c" * 64, "d" * 64),
            )
            for image, image_id in identities:
                args = argparse.Namespace(
                    engine="docker",
                    image=image,
                    require_local_opencode_image=True,
                    workspace=str(workspace),
                    workspace_mode="ro",
                    output=str(root / "result.json"),
                    transport="opencode",
                    model="openai/test",
                    agent="general",
                    timeout_seconds=30,
                    env=[],
                    auth=None,
                    config=None,
                    models_catalog=None,
                )
                inspect = inspected_image_result(
                    image,
                    version=SUPPORTED_OPENCODE_VERSION,
                    adapter=SUPPORTED_INVOKE_ADAPTER_ID,
                    image_id=image_id,
                )
                calls: list[tuple[list[str], dict]] = []

                def fake_run(command, *, capture=calls, result=inspect, **kwargs):
                    capture.append((command, kwargs))
                    return result

                with patch("runner.cli.shutil.which", return_value="/usr/bin/docker"), patch(
                    "runner.cli.subprocess.run", side_effect=fake_run
                ):
                    command, _ = build_container_command(
                        args, input_dir, output_dir,
                        host_env={"OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE": image},
                    )

                self.assertEqual(command[-1], image)
                self.assertIn("--pull=never", command)
                self.assertEqual(len(calls), 1)
                inspect_command, inspect_kwargs = calls[0]
                self.assertIn("image", inspect_command)
                self.assertIn("inspect", inspect_command)
                self.assertNotIn("pull", inspect_command)
                self.assertIn("--host", inspect_command)
                self.assertIn("unix:///var/run/docker.sock", inspect_command)
                self.assertNotIn("DOCKER_HOST", inspect_kwargs["env"])
                self.assertNotIn("DOCKER_CONTEXT", inspect_kwargs["env"])

    def test_builtin_eval_rejects_invalid_or_incompatible_images_before_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace, input_dir, output_dir = (
                root / "workspace", root / "input", root / "output"
            )
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            cases = (
                (None, None, None, 0, None),
                ("registry.example/opencode:latest", None, None, 0, None),
                ("registry.example/opencode@sha256:" + "e" * 64, None, None, 1, None),
                ("f" * 64, "9.9.9", SUPPORTED_INVOKE_ADAPTER_ID, 0, None),
                ("1" * 64, SUPPORTED_OPENCODE_VERSION, "wrong-adapter", 0, None),
                ("2" * 64, None, SUPPORTED_INVOKE_ADAPTER_ID, 0, None),
                ("registry.example/opencode@sha256:" + "3" * 64,
                 SUPPORTED_OPENCODE_VERSION, SUPPORTED_INVOKE_ADAPTER_ID, 0,
                 "registry.example/opencode@sha256:" + "4" * 64),
                ("5" * 64, SUPPORTED_OPENCODE_VERSION, SUPPORTED_INVOKE_ADAPTER_ID, 1, None),
            )
            for image, version, adapter, inspect_returncode, repo_digest in cases:
                args = argparse.Namespace(
                    engine="docker",
                    image=image,
                    require_local_opencode_image=True,
                    workspace=str(workspace),
                    workspace_mode="ro",
                    output=str(root / "result.json"),
                    transport="opencode",
                    model="openai/test",
                    agent="general",
                    timeout_seconds=30,
                    env=[],
                    auth=None,
                    config=None,
                    models_catalog=None,
                )
                calls = []

                def fake_run(
                    command,
                    *,
                    capture=calls,
                    selected_image=image,
                    selected_version=version,
                    selected_adapter=adapter,
                    selected_repo_digest=repo_digest,
                    inspect_result=inspect_returncode,
                    **kwargs,
                ):
                    capture.append(command)
                    return inspected_image_result(
                        selected_image or "",
                        version=selected_version,
                        adapter=selected_adapter,
                        image_id="f" * 64,
                        repo_digest=selected_repo_digest,
                        returncode=inspect_result,
                    )

                host_env = (
                    {"OPENCODE_EVAL_RUNNER_IMAGE": "registry.example/default:latest"}
                    if image is None else
                    {"OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE": image}
                )
                with self.subTest(image=image, version=version, adapter=adapter), patch(
                    "runner.cli.shutil.which", return_value="/usr/bin/docker"
                ), patch("runner.cli.subprocess.run", side_effect=fake_run):
                    with self.assertRaises(RunnerError) as raised:
                        build_container_command(args, input_dir, output_dir, host_env=host_env)
                    self.assertNotIn(image or "<missing>", str(raised.exception))
                    self.assertFalse(any("run" in call for call in calls))
                    if image is None or ":latest" in image:
                        self.assertEqual(calls, [])
                    else:
                        self.assertEqual(len(calls), 1)

            selected = "a" * 64
            args = argparse.Namespace(
                engine="docker", image=selected, require_local_opencode_image=True,
                workspace=str(workspace), workspace_mode="ro",
                output=str(root / "result.json"), transport="opencode",
                model="openai/test", agent="general", timeout_seconds=30,
                env=[], auth=None, config=None, models_catalog=None,
            )
            with (
                patch("runner.cli.shutil.which", return_value="/usr/bin/docker"),
                patch("runner.cli.subprocess.run") as inspect,
            ):
                with self.assertRaisesRegex(RunnerError, "selection changed"):
                    build_container_command(
                        args, input_dir, output_dir,
                        host_env={"OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE": "b" * 64},
                    )
            inspect.assert_not_called()

    def test_builtin_eval_rejects_remote_engine_endpoints_without_invoking_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace, input_dir, output_dir = (
                root / "workspace", root / "input", root / "output"
            )
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            image = "a" * 64
            args = argparse.Namespace(
                engine="docker", image=image, require_local_opencode_image=True,
                workspace=str(workspace), workspace_mode="ro",
                output=str(root / "result.json"), transport="opencode",
                model="openai/test", agent="general", timeout_seconds=30,
                env=[], auth=None, config=None, models_catalog=None,
            )
            with (
                patch("runner.cli.shutil.which", return_value="/usr/bin/docker"),
                patch("runner.cli.subprocess.run") as inspect,
            ):
                with self.assertRaisesRegex(RunnerError, "local Docker Unix socket"):
                    build_container_command(
                        args, input_dir, output_dir,
                        host_env={
                            "OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE": image,
                            "DOCKER_HOST": "tcp://remote.example:2376",
                        },
                    )
            inspect.assert_not_called()

    def test_builtin_eval_forces_podman_local_metadata_and_pull_never(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace, input_dir, output_dir = (
                root / "workspace", root / "input", root / "output"
            )
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            image = "9" * 64
            args = argparse.Namespace(
                engine="podman", image=image, require_local_opencode_image=True,
                workspace=str(workspace), workspace_mode="ro",
                output=str(root / "result.json"), transport="opencode",
                model="openai/test", agent="general", timeout_seconds=30,
                env=[], auth=None, config=None, models_catalog=None,
            )
            inspect = inspected_image_result(
                image,
                version=SUPPORTED_OPENCODE_VERSION,
                adapter=SUPPORTED_INVOKE_ADAPTER_ID,
                image_id=image,
            )
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                return inspect

            with patch("runner.cli.shutil.which", return_value="/usr/bin/podman"), patch(
                "runner.cli.subprocess.run", side_effect=fake_run
            ):
                command, _ = build_container_command(
                    args,
                    input_dir,
                    output_dir,
                    host_env={
                        "OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE": image,
                        "CONTAINER_HOST": "tcp://remote.example:2376",
                    },
                )

            self.assertEqual(command[:3], ["podman", "--remote=false", "run"])
            self.assertEqual(command[-1], image)
            self.assertIn("--pull=never", command)
            self.assertIn("--remote=false", calls[0][0])
            self.assertNotIn("CONTAINER_HOST", calls[0][1]["env"])

    def test_default_models_uses_xdg_cache_home(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=False):
            self.assertEqual(default_models_path(), Path(tmp) / "opencode" / "models.json")

    def test_large_valid_model_catalog_mounts_and_inventories_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace, input_dir, output_dir = (
                root / "workspace", root / "input", root / "output"
            )
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            catalog = root / "models.json"
            catalog.write_text(
                json.dumps({
                    "openai": {
                        "models": {"gpt-6-luna": {"description": "x" * JSON_SOURCE_LIMIT}},
                        "api_key": "tail-secret",
                    },
                }),
                encoding="utf-8",
            )
            self.assertGreater(catalog.stat().st_size, JSON_SOURCE_LIMIT)
            args = argparse.Namespace(
                engine="docker", image="reviewed-image", workspace=str(workspace),
                workspace_mode="ro", output=str(root / "result.json"),
                transport="opencode", model="openai/gpt-6-luna", agent="general",
                timeout_seconds=30, env=[], auth=None, config=None,
                models_catalog=str(catalog),
            )
            with (
                patch("runner.cli.shutil.which", return_value="/usr/bin/docker"),
                patch.dict(os.environ, {}, clear=True),
                patch("runner.cli.subprocess.run") as inspect,
            ):
                command, _ = build_container_command(args, input_dir, output_dir)
            self.assertIn(f"{catalog.resolve()}:/seed/models.json:ro", command)
            self.assertEqual(command[-1], "reviewed-image")
            self.assertNotIn("--pull=never", command)
            inspect.assert_not_called()

    def test_invalid_model_catalog_fails_before_container_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace, input_dir, output_dir = (
                root / "workspace", root / "input", root / "output"
            )
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            catalog = root / "models.json"
            args = argparse.Namespace(
                engine="docker", image="reviewed-image", workspace=str(workspace),
                workspace_mode="ro", output=str(root / "result.json"),
                transport="opencode", model="openai/gpt-6-luna", agent="general",
                timeout_seconds=30, env=[], auth=None, config=None,
                models_catalog=str(catalog),
            )
            with (
                patch("runner.cli.shutil.which", return_value="/usr/bin/docker"),
                patch.dict(os.environ, {}, clear=True),
                patch("runner.cli.subprocess.run") as run,
            ):
                catalog.write_text("{invalid", encoding="utf-8")
                with self.assertRaisesRegex(RunnerError, "credential inventory unavailable"):
                    build_container_command(args, input_dir, output_dir)
                with catalog.open("wb") as source:
                    source.truncate(MODEL_CATALOG_SOURCE_LIMIT + 1)
                with self.assertRaisesRegex(RunnerError, "credential inventory unavailable"):
                    build_container_command(args, input_dir, output_dir)
                run.assert_not_called()

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

    def test_extra_mount_defaults_to_read_only_and_accepts_rw(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "node_modules"
            source.mkdir()
            self.assertEqual(
                extra_mount_arg(f"{source}:/workspace/node_modules"),
                ["--volume", f"{source.resolve()}:/workspace/node_modules:ro"],
            )
            self.assertEqual(
                extra_mount_arg(f"{source}:/workspace/node_modules:rw"),
                ["--volume", f"{source.resolve()}:/workspace/node_modules:rw"],
            )

    def test_extra_mount_rejects_relative_container_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            with self.assertRaisesRegex(RunnerError, "absolute container target"):
                extra_mount_arg(f"{source}:workspace/node_modules")

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

    def test_reasoning_is_passed_to_container_when_set(self):
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
                reasoning="high",
                agent="reviewer",
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

            self.assertIn("--env EVAL_REASONING=high", " ".join(command))

    def test_expected_plugin_is_passed_to_opencode_container(self):
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
                agent="general",
                skill=None,
                expected_plugin="loom",
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

            self.assertIn("--env EVAL_EXPECT_PLUGIN=loom", " ".join(command))

    def test_expected_plugin_is_rejected_for_copilot_transport(self):
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
                agent="general",
                skill=None,
                expected_plugin="loom",
                timeout_seconds=120,
                env=[],
                auth=None,
                config=None,
                models_catalog=None,
            )
            with self.assertRaisesRegex(RunnerError, "--expected-plugin is only supported"):
                build_container_command(args, input_dir, output_dir)

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

    def test_additional_mount_is_added_to_container_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            node_modules = root / "node_modules"
            for path in (workspace, input_dir, output_dir, node_modules):
                path.mkdir()
            args = argparse.Namespace(
                engine="podman",
                image="test-image",
                workspace=str(workspace),
                workspace_mode="ro",
                mount=[f"{node_modules}:/workspace/node_modules:ro"],
                output=str(root / "result.json"),
                transport="opencode",
                model="openai/test",
                agent="reviewer",
                skill=None,
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

            self.assertIn(f"{node_modules.resolve()}:/workspace/node_modules:ro", command)

    def test_explicit_network_is_forwarded_to_container_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            input_dir = root / "input"
            output_dir = root / "output"
            for path in (workspace, input_dir, output_dir):
                path.mkdir()
            args = argparse.Namespace(
                engine="podman",
                network="host",
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
            with patch("runner.cli.shutil.which", return_value="/usr/bin/podman"), patch.dict(
                os.environ, {}, clear=True
            ):
                command, _ = build_container_command(args, input_dir, output_dir)

            self.assertIn("--network", command)
            self.assertEqual(command[command.index("--network") + 1], "host")

    def test_default_network_does_not_override_engine_networking(self):
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

            self.assertNotIn("--network", command)

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
