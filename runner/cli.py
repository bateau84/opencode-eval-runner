#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from runner.observer import ObserverCapture, unavailable

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

RUNTIME_UID = 1000
RUNTIME_GID = 1000
OPENCODE_STATE_PROFILES = ("default", "disposable")
DISPOSABLE_STATE_CONTROL_ENVS = {
    "EVAL_OPENCODE_STATE_PROFILE",
    "EVAL_OPENCODE_AUTH_SOURCE",
    "EVAL_OPENCODE_DATABASE_SOURCE",
}
RUNNER_SEED_ENVS = (
    "OPENCODE_EVAL_RUNNER_AUTH",
    "OPENCODE_EVAL_RUNNER_CONFIG",
    "OPENCODE_EVAL_RUNNER_MODELS",
    "OPENCODE_EVAL_RUNNER_DB",
    "OPENCODE_EVAL_RUNNER_CONFIG_ROOT",
)


class RunnerError(RuntimeError):
    pass


def default_auth_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "opencode" / "auth.json"


def default_models_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "opencode" / "models.json"


def default_database_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "opencode" / "opencode.db"


def sanitize_database_seed(source: Path, destination: Path) -> Path:
    source = source.expanduser().resolve()
    destination = destination.resolve()
    if not source.is_file():
        raise RunnerError(f"OpenCode database file not found: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    def quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src_db, sqlite3.connect(destination) as dst_db:
            schema = src_db.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
                "ORDER BY CASE type "
                "WHEN 'table' THEN 0 WHEN 'index' THEN 1 "
                "WHEN 'view' THEN 2 WHEN 'trigger' THEN 3 ELSE 4 END, name"
            ).fetchall()

            tables = {name for object_type, name, _ in schema if object_type == "table"}
            if "credential" not in tables:
                raise RunnerError("OpenCode database has no credential table")
            if "session" not in tables:
                raise RunnerError("OpenCode database has no session table")

            dst_db.execute("PRAGMA foreign_keys=OFF")

            # Create all tables, but copy no application rows by default.
            for object_type, _, sql in schema:
                if object_type == "table":
                    dst_db.execute(sql)

            # Preserve only V2 credentials and migration journals. Everything
            # session/project/history related remains schema-only and empty.
            for table in ("credential", "migration", "__drizzle_migrations"):
                if table not in tables:
                    continue
                columns = [row[1] for row in src_db.execute(f"PRAGMA table_info({quote(table)})")]
                if not columns:
                    continue
                column_sql = ", ".join(quote(column) for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = src_db.execute(f"SELECT {column_sql} FROM {quote(table)}").fetchall()
                if rows:
                    dst_db.executemany(
                        f"INSERT INTO {quote(table)} ({column_sql}) VALUES ({placeholders})",
                        rows,
                    )

            # Add indexes/views/triggers after the retained rows are copied so
            # triggers cannot manufacture extra state while seeding.
            for object_type, _, sql in schema:
                if object_type != "table":
                    dst_db.execute(sql)

            dst_db.commit()
            dst_db.execute("PRAGMA journal_mode=DELETE")
            dst_db.execute("VACUUM")
    except sqlite3.Error as exc:
        destination.unlink(missing_ok=True)
        raise RunnerError(f"failed to prepare sanitized OpenCode database: {exc}") from exc
    except RunnerError:
        destination.unlink(missing_ok=True)
        raise

    destination.chmod(0o600)
    return destination


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


def extra_mount_arg(spec: str) -> list[str]:
    parts = spec.rsplit(":", 2)
    readonly = True
    if len(parts) == 2:
        source_raw, target = parts
    elif len(parts) == 3 and parts[2] in {"ro", "rw"}:
        source_raw, target, mode = parts
        readonly = mode == "ro"
    else:
        raise RunnerError("mount must be SOURCE:TARGET[:ro|rw]")

    if not source_raw or not target.startswith("/"):
        raise RunnerError("mount must use a non-empty source and absolute container target")
    source = Path(source_raw).expanduser()
    if not source.exists():
        raise RunnerError(f"mount source not found: {source}")
    return bind_arg(source, target, readonly=readonly)


def existing_seed(explicit: str | None, env_name: str, fallback: Path | None = None) -> Path | None:
    raw = explicit or os.environ.get(env_name)
    if raw:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise RunnerError(f"{env_name.lower().replace('_', ' ')} file not found: {path}")
        return path
    return fallback if fallback and fallback.is_file() else None


def existing_dir(explicit: str | None, env_name: str) -> Path | None:
    raw = explicit or os.environ.get(env_name)
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise RunnerError(f"{env_name.lower().replace('_', ' ')} directory not found: {path}")
    return path


def explicit_seed(explicit: str | None, label: str) -> Path | None:
    if not explicit:
        return None
    path = Path(explicit).expanduser()
    if not path.is_file():
        raise RunnerError(f"{label} file not found: {path}")
    return path


def explicit_dir(explicit: str | None, label: str) -> Path | None:
    if not explicit:
        return None
    path = Path(explicit).expanduser()
    if not path.is_dir():
        raise RunnerError(f"{label} directory not found: {path}")
    return path


def opencode_state_profile(args: argparse.Namespace, host_env: dict[str, str] | None = None) -> str:
    profile = getattr(args, "opencode_state_profile", "default") or "default"
    if profile not in OPENCODE_STATE_PROFILES:
        raise RunnerError(f"unsupported OpenCode state profile: {profile}")
    if profile == "disposable":
        if args.transport != "opencode":
            raise RunnerError("--opencode-state-profile disposable is only supported by the opencode transport")
        if getattr(args, "database", None):
            raise RunnerError("--database is incompatible with --opencode-state-profile disposable")
        env = dict(os.environ) if host_env is None else host_env
        selected = [name for name in RUNNER_SEED_ENVS if env.get(name)]
        if selected:
            raise RunnerError(
                "--opencode-state-profile disposable rejects implicit runner seed overrides: "
                + ", ".join(sorted(selected))
            )
    return profile


def resolve_database_seed(
    args: argparse.Namespace, destination: Path, host_env: dict[str, str] | None = None
) -> Path | None:
    if opencode_state_profile(args, host_env) == "disposable":
        return None
    source = existing_seed(args.database, "OPENCODE_EVAL_RUNNER_DB", default_database_path())
    return sanitize_database_seed(source, destination) if source else None


def host_environment_for_transport(transport: str) -> dict[str, str]:
    env = dict(os.environ)
    if transport != "github-copilot-cli" or any(env.get(name, "").strip() for name in COPILOT_AUTH_ENVS):
        return env

    gh = shutil.which("gh")
    if not gh:
        return env

    try:
        proc = subprocess.run(
            [gh, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return env

    token = proc.stdout.strip() if proc.returncode == 0 else ""
    if token:
        env["COPILOT_GITHUB_TOKEN"] = token
    return env


def pass_env(command: list[str], names: list[str], host_env: dict[str, str]) -> None:
    for name in names:
        if host_env.get(name):
            command += ["--env", name]


def build_container_command(
    args: argparse.Namespace,
    input_dir: Path,
    output_dir: Path,
    host_env: dict[str, str] | None = None,
    database_seed: Path | None = None,
) -> tuple[list[str], Path]:
    host_env = dict(os.environ) if host_env is None else host_env
    skill = getattr(args, "skill", None)
    expected_plugin = getattr(args, "expected_plugin", None)
    reasoning = getattr(args, "reasoning", None)
    if skill and args.transport != "opencode":
        raise RunnerError("--skill is only supported by the opencode transport")
    if expected_plugin and args.transport != "opencode":
        raise RunnerError("--expected-plugin is only supported by the opencode transport")
    engine = resolve_engine(args.engine)
    transport_env = (
        "OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE"
        if args.transport == "opencode"
        else "OPENCODE_EVAL_RUNNER_COPILOT_IMAGE"
    )
    image = (
        args.image
        or host_env.get(transport_env)
        or host_env.get("OPENCODE_EVAL_RUNNER_IMAGE")
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
    network = getattr(args, "network", None)
    if network:
        command += ["--network", network]
    if engine == "podman":
        # Map the invoking host user to the dedicated non-root runtime user so
        # private read-only seed files (for example auth.json mode 0600) remain
        # readable without running the container as root.
        command += ["--userns", f"keep-id:uid={RUNTIME_UID},gid={RUNTIME_GID}"]
        # Rootless Podman on SELinux hosts blocks bind mounts unless they are
        # relabeled (:z/:Z) or container labeling is disabled. Do not relabel
        # the user's repository or credential files; disable labeling for this
        # tightly scoped eval container instead.
        command += ["--security-opt", "label=disable"]
    elif hasattr(os, "getuid") and os.getuid() != 0:
        # Rootful Docker preserves numeric ownership on bind mounts. Match the
        # non-root host caller so mode-0600 seed files stay readable. A root
        # caller leaves the image's non-root USER intact.
        command += ["--user", f"{os.getuid()}:{os.getgid()}"]
    command += [
        "--workdir",
        "/workspace",
    ]
    command += bind_arg(workspace, "/workspace", readonly=args.workspace_mode == "ro")
    command += bind_arg(input_dir, "/input", readonly=True)
    for spec in getattr(args, "mount", []):
        command += extra_mount_arg(spec)

    state_profile = opencode_state_profile(args, host_env)
    if state_profile == "disposable":
        auth = explicit_seed(args.auth, "auth")
        config = explicit_seed(args.config, "config")
        models = explicit_seed(args.models_catalog, "models catalog")
    else:
        auth = existing_seed(args.auth, "OPENCODE_EVAL_RUNNER_AUTH", default_auth_path())
        config = existing_seed(args.config, "OPENCODE_EVAL_RUNNER_CONFIG")
        models = existing_seed(
            args.models_catalog,
            "OPENCODE_EVAL_RUNNER_MODELS",
            default_models_path(),
        )
    if auth:
        command += bind_arg(auth, "/seed/auth.json", readonly=True)
    if config:
        command += bind_arg(config, "/seed/opencode.json", readonly=True)
    if models:
        command += bind_arg(models, "/seed/models.json", readonly=True)
    if database_seed:
        command += bind_arg(database_seed, "/seed/opencode.db", readonly=True)
    config_root = (
        explicit_dir(getattr(args, "config_root", None), "config root")
        if state_profile == "disposable"
        else existing_dir(getattr(args, "config_root", None), "OPENCODE_EVAL_RUNNER_CONFIG_ROOT")
    )
    if config_root:
        command += bind_arg(config_root, "/seed/opencode-config", readonly=True)

    command += [
        "--env", f"EVAL_TRANSPORT={args.transport}",
        "--env", f"EVAL_MODEL={args.model}",
        "--env", f"EVAL_REASONING={reasoning or ''}",
        "--env", f"EVAL_AGENT={args.agent or ''}",
        "--env", f"EVAL_SKILL={skill or ''}",
        "--env", f"EVAL_EXPECT_PLUGIN={expected_plugin or ''}",
        "--env", "EVAL_PROMPT_FILE=/input/prompt.txt",
        "--env", "EVAL_SYSTEM_FILE=/input/system.txt",
        "--env", f"EVAL_TIMEOUT_SECONDS={args.timeout_seconds}",
        "--env", f"EVAL_OPENCODE_STATE_PROFILE={state_profile}",
        "--env", f"EVAL_OPENCODE_AUTH_SOURCE={'explicit' if auth else 'none' if state_profile == 'disposable' else 'implicit-or-none'}",
        "--env", f"EVAL_OPENCODE_DATABASE_SOURCE={'runtime-bootstrap' if state_profile == 'disposable' else 'seed-or-runtime'}",
    ]

    if state_profile == "disposable":
        forbidden = sorted(DISPOSABLE_STATE_CONTROL_ENVS.intersection(args.env))
        if forbidden:
            raise RunnerError(
                "--opencode-state-profile disposable reserves runner state environment names: "
                + ", ".join(forbidden)
            )
        env_names = list(dict.fromkeys(tuple(args.env)))
    else:
        env_names = list(dict.fromkeys(DEFAULT_ENV_ALLOWLIST + tuple(args.env)))
    if args.transport == "github-copilot-cli" and state_profile != "disposable":
        env_names.extend(COPILOT_AUTH_ENVS)
    pass_env(command, env_names, host_env)

    command.append(image)
    return command, result_host


def invoke(args: argparse.Namespace) -> int:
    if getattr(args, 'require_evidence_safety', False) or getattr(args, 'evidence_policy_file', None):
        from runner.safe_invoke import invoke as safe_invoke
        return safe_invoke(args)
    observer_key = getattr(args, "observer_key_file", None)
    if observer_key and args.transport != "opencode":
        raise RunnerError("--observer-key-file is only supported by the opencode transport")
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

        host_env = host_environment_for_transport(args.transport)
        database_seed = resolve_database_seed(
            args, root / "opencode-credentials.db", host_env
        )

        command, _ = build_container_command(
            args,
            input_dir,
            output_dir,
            host_env=host_env,
            database_seed=database_seed,
        )
        capture = None
        if observer_key:
            try:
                capture = ObserverCapture(Path(observer_key).expanduser(), root, command, host_env)
            except (OSError, ValueError) as exc:
                raise RunnerError("cannot configure isolated observer capture") from exc
        try:
            proc = subprocess.run(
                command,
                env=host_env,
                text=True,
                capture_output=True,
                timeout=args.container_timeout,
                check=False,
            )
            try:
                result = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                detail = " | ".join(part.strip() for part in (proc.stderr, proc.stdout) if part.strip())
                raise RunnerError(
                    f"container produced invalid result JSON (exit {proc.returncode}): {exc}"
                    + (f": {detail[:2000]}" if detail else "")
                ) from exc

            if not isinstance(result, dict):
                raise RunnerError("container result must be a JSON object")
            returncode = proc.returncode
        except (RunnerError, subprocess.TimeoutExpired, OSError):
            if capture is None:
                raise
            # Preserve an explicit non-evidence artifact even on interruption.
            # Never echo untrusted stdout/stderr into observer diagnostics.
            result = {"error": "observer_transport_failed", "exit_code": 2}
            returncode = 2

        # ALWAYS replace this field: container/script JSON cannot attest itself.
        result["observed_execution"] = (
            capture.finish(transport_ok=returncode == 0) if capture
            else unavailable("capture_not_requested")
        )
        if capture and not result["observed_execution"]["evidence_eligible"] and returncode == 0:
            returncode = 4
        result_host.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if args.print_result:
            sys.stdout.write(result_host.read_text(encoding="utf-8"))
        return returncode


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one isolated model invocation in an OCI container.")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("invoke", help="Run one isolated target or judge invocation.")
    run.add_argument("--transport", choices=("opencode", "github-copilot-cli"), default="opencode")
    run.add_argument("--engine", choices=("auto", "podman", "docker"), default="auto")
    run.add_argument(
        "--network",
        metavar="MODE",
        help="Optional OCI network mode/name (for example host, bridge, slirp4netns, or a custom network). Default keeps the engine's normal network isolation.",
    )
    run.add_argument("--image")
    run.add_argument("--workspace", default=".")
    run.add_argument("--workspace-mode", choices=("ro", "rw"), default="ro")
    run.add_argument(
        "--mount",
        action="append",
        default=[],
        metavar="SOURCE:TARGET[:ro|rw]",
        help="Additional explicit bind mount. May be repeated.",
    )
    run.add_argument("--model", required=True)
    run.add_argument(
        "--reasoning",
        metavar="LEVEL",
        help="Optional reasoning level. OpenCode maps this to the model #variant; Copilot maps it to --effort. Omit to use the transport/provider default.",
    )
    run.add_argument("--agent")
    run.add_argument(
        "--skill",
        help="Skill ID under test (OpenCode only; records intent but does not force the skill to load).",
    )
    run.add_argument(
        "--expected-plugin",
        help="Expected OpenCode plugin namespace. Fails before inference when the selected agent exposes no tools from that namespace.",
    )
    run.add_argument("--prompt-file", required=True)
    run.add_argument("--system-file")
    run.add_argument("--output", required=True)
    run.add_argument("--require-evidence-safety", action="store_true",
                     help="Require pre-output projection and matching image acknowledgement; missing policy omits payloads.")
    run.add_argument("--evidence-policy-file",
                     help="Private Loom credential inventory JSON (128000-byte maximum); implies --require-evidence-safety.")
    run.add_argument(
        "--observer-key-file",
        metavar="PATH",
        help="Require authenticated execution-observer evidence (OpenCode only). The trusted producer's verification key must remain outside every container mount. Missing or indeterminate capture exits 4; see docs/execution-observer.md.",
    )
    run.add_argument("--auth")
    run.add_argument("--config")
    run.add_argument("--models-catalog")
    run.add_argument("--database")
    run.add_argument(
        "--opencode-state-profile",
        choices=OPENCODE_STATE_PROFILES,
        default="default",
        help=(
            "OpenCode host-state lifecycle. 'default' preserves existing implicit auth/model/database seeds; "
            "'disposable' rejects implicit runner seed overrides, disables ambient provider auth forwarding, "
            "forbids database seeds, and lets OpenCode bootstrap a fresh migrated database in disposable XDG state."
        ),
    )
    run.add_argument("--config-root")
    run.add_argument("--env", action="append", default=[], metavar="NAME")
    run.add_argument("--timeout-seconds", type=int, default=240)
    run.add_argument("--container-timeout", type=int, default=300)
    run.add_argument("--print-result", action="store_true")
    return p


def main() -> int:
    # argparse accepts unambiguous long-option prefixes. Protect diagnostics
    # for every candidate safety prefix (including ambiguous ones), not only
    # the full spelling. Preserve normal option abbreviation behavior.
    safety_options = ('--require-evidence-safety', '--evidence-policy-file')
    requested_safety = any(
        name.startswith('--') and len(name) > 2 and
        any(option.startswith(name) for option in safety_options)
        for arg in sys.argv[1:] for name in (arg.partition('=')[0],)
    )
    if requested_safety:
        # argparse can echo invalid arguments (including accidental credential
        # values) before invoke has loaded policy. Emit only a fixed diagnostic.
        import contextlib
        import io
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                args = parser().parse_args()
        except SystemExit as exc:
            if exc.code:
                print('opencode-eval-runner: invalid safety invocation', file=sys.stderr)
            return int(exc.code or 0)
    else:
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
