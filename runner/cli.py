#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_IMAGES = {
    "opencode": "ghcr.io/bateau84/opencode-eval-runner:opencode-edge",
    "github-copilot-cli": "ghcr.io/bateau84/opencode-eval-runner:copilot-edge",
}
DEFAULT_ENV_ALLOWLIST = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
)
COPILOT_AUTH_ENVS = (
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)


class RunnerError(RuntimeError):
    pass


def default_auth_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "opencode" / "auth.json"


def resolve_engine(requested: str) -> str:
    if requested != "auto":
        if not shutil.which(requested):
            raise RunnerError(f"container engine not found: {requested}")
        return requested
    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    raise RunnerError("no supported container engine found; install podman or docker")


def bind_arg(source: Path, target: str, *, readonly: bool = True) -> list[str]:
    source = source.resolve()
    mode = "ro" if readonly else "rw"
    return ["--volume", f"{source}:{target}:{mode}"]


def existing_seed(explicit: str | None, env_name: str, fallback: Path | None = None) -> Path | None:
    raw = explicit or os.environ.get(env_name)
    if raw:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise RunnerError(f"{env_name.lower().replace('_', ' ')} file not found: {path}")
        return path
    return fallback if fallback and fallback.is_file() else None


def pass_env(command: list[str], names: list[str]) -> None:
    for name in names:
        if os.environ.get(name):
            command += ["--env", name]


def build_container_command(args: argparse.Namespace, input_dir: Path, output_dir: Path) -> tuple[list[str], Path]:
    engine = resolve_engine(args.engine)
    transport_env = (
        "OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE"
        if args.transport == "opencode"
        else "OPENCODE_EVAL_RUNNER_COPILOT_IMAGE"
    )
    image = (
        args.image
        or os.environ.get(transport_env)
        or os.environ.get("OPENCODE_EVAL_RUNNER_IMAGE")
        or DEFAULT_IMAGES[args.transport]
    )
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        raise RunnerError(f"workspace not found: {workspace}")

    result_host = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        engine,
        "run",
        "--rm",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,size=1g",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
    ]
    if engine == "podman":
        # Rootless Podman on SELinux hosts blocks bind mounts unless they are
        # relabeled (:z/:Z) or container labeling is disabled. Do not relabel
        # the user's repository or credential files; disable labeling for this
        # tightly scoped eval container instead.
        command += ["--security-opt", "label=disable"]
    command += [
        "--workdir",
        "/workspace",
    ]
    command += bind_arg(workspace, "/workspace", readonly=args.workspace_mode == "ro")
    command += bind_arg(input_dir, "/input", readonly=True)
    command += bind_arg(output_dir, "/output", readonly=False)

    auth = existing_seed(args.auth, "OPENCODE_EVAL_RUNNER_AUTH", default_auth_path())
    config = existing_seed(args.config, "OPENCODE_EVAL_RUNNER_CONFIG")
    models = existing_seed(args.models_catalog, "OPENCODE_EVAL_RUNNER_MODELS")
    if auth:
        command += bind_arg(auth, "/seed/auth.json", readonly=True)
    if config:
        command += bind_arg(config, "/seed/opencode.json", readonly=True)
    if models:
        command += bind_arg(models, "/seed/models.json", readonly=True)

    command += [
        "--env", f"EVAL_TRANSPORT={args.transport}",
        "--env", f"EVAL_MODEL={args.model}",
        "--env", f"EVAL_AGENT={args.agent or ''}",
        "--env", "EVAL_PROMPT_FILE=/input/prompt.txt",
        "--env", "EVAL_SYSTEM_FILE=/input/system.txt",
        "--env", "EVAL_RESULT_FILE=/output/result.json",
        "--env", f"EVAL_TIMEOUT_SECONDS={args.timeout_seconds}",
    ]

    env_names = list(dict.fromkeys(DEFAULT_ENV_ALLOWLIST + tuple(args.env)))
    if args.transport == "github-copilot-cli":
        env_names.extend(COPILOT_AUTH_ENVS)
    pass_env(command, env_names)

    command.append(image)
    return command, result_host


def invoke(args: argparse.Namespace) -> int:
    prompt_path = Path(args.prompt_file).resolve()
    if not prompt_path.is_file():
        raise RunnerError(f"prompt file not found: {prompt_path}")
    system_path = Path(args.system_file).resolve() if args.system_file else None
    if system_path and not system_path.is_file():
        raise RunnerError(f"system file not found: {system_path}")

    result_host = Path(args.output).resolve()
    result_host.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="opencode-eval-runner-") as tmp:
        root = Path(tmp)
        input_dir = root / "input"
        output_dir = root / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        shutil.copyfile(prompt_path, input_dir / "prompt.txt")
        if system_path:
            shutil.copyfile(system_path, input_dir / "system.txt")
        else:
            (input_dir / "system.txt").write_text("", encoding="utf-8")

        command, _ = build_container_command(args, input_dir, output_dir)
        proc = subprocess.run(command, text=True, capture_output=True, timeout=args.container_timeout, check=False)
        produced = output_dir / "result.json"

        if produced.is_file():
            shutil.copyfile(produced, result_host)
            if args.print_result:
                sys.stdout.write(result_host.read_text(encoding="utf-8"))
            return 0 if proc.returncode == 0 else proc.returncode

        detail = " | ".join(part.strip() for part in (proc.stderr, proc.stdout) if part.strip())
        raise RunnerError(
            f"container produced no result (exit {proc.returncode})"
            + (f": {detail[:2000]}" if detail else "")
        )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one isolated model invocation in an OCI container.")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("invoke", help="Run one isolated target or judge invocation.")
    run.add_argument("--transport", choices=("opencode", "github-copilot-cli"), default="opencode")
    run.add_argument("--engine", choices=("auto", "podman", "docker"), default="auto")
    run.add_argument("--image")
    run.add_argument("--workspace", default=".")
    run.add_argument("--workspace-mode", choices=("ro", "rw"), default="ro")
    run.add_argument("--model", required=True)
    run.add_argument("--agent")
    run.add_argument("--prompt-file", required=True)
    run.add_argument("--system-file")
    run.add_argument("--output", required=True)
    run.add_argument("--auth")
    run.add_argument("--config")
    run.add_argument("--models-catalog")
    run.add_argument("--env", action="append", default=[], metavar="NAME")
    run.add_argument("--timeout-seconds", type=int, default=240)
    run.add_argument("--container-timeout", type=int, default=300)
    run.add_argument("--print-result", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "invoke":
            return invoke(args)
        raise RunnerError(f"unsupported command: {args.command}")
    except (RunnerError, subprocess.TimeoutExpired) as exc:
        print(f"opencode-eval-runner: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
