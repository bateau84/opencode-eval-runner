#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

RESULT_SCHEMA = "opencode-eval-runner/v1"
COPILOT_AGENT_NAME = "eval-runner"
COPILOT_AUTH_ENVS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
COPILOT_EXCLUDED_TOOLS = (
    "bash", "powershell", "list_bash", "list_powershell", "read_bash",
    "read_powershell", "stop_bash", "stop_powershell", "write_bash",
    "write_powershell", "apply_patch", "create", "edit", "view",
    "list_agents", "read_agent", "task", "write_agent", "ask_user",
    "glob", "grep", "rg", "skill", "web_fetch", "web_search",
)
COPILOT_DENIED_PERMISSIONS = ("read", "shell", "write", "url", "memory")


def run(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=max(timeout, 1),
        check=False,
    )


def parse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def session_id(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        value = event.get("sessionID") or event.get("sessionId")
        if isinstance(value, str) and value:
            return value
    return None


def extract_text(events: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for event in events:
        part = event.get("part")
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            if event.get("type") == "text" or part.get("type") == "text":
                value = part["text"].strip()
                if value:
                    parts.append(value)
        elif event.get("type") == "text" and isinstance(event.get("text"), str):
            value = event["text"].strip()
            if value:
                parts.append(value)
    return "\n\n".join(parts)


def extract_tools(events: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for event in events:
        part = event.get("part")
        candidates = (event, part if isinstance(part, dict) else {})
        for value in candidates:
            tool = value.get("tool")
            if isinstance(tool, str) and (
                value.get("type") in {"tool", "tool_use", "tool-call", "tool_call"}
                or event.get("type") in {"tool", "tool_use", "tool-call", "tool_call"}
            ):
                found.append(tool)
    return list(dict.fromkeys(found))


def tool_action(part: dict[str, Any]) -> dict[str, Any] | None:
    tool = part.get("tool")
    if part.get("type") != "tool" or not isinstance(tool, str):
        return None
    state = part.get("state")
    args = state.get("input") if isinstance(state, dict) and isinstance(state.get("input"), dict) else {}
    return {"tool": tool, "args": args}


def extract_actions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for event in events:
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        action = tool_action(part)
        if action:
            actions.append(action)
    return actions


def assistant_from_export(exported: Any) -> tuple[str, list[str], list[dict[str, Any]]]:
    parts: list[str] = []
    tools: list[str] = []
    actions: list[dict[str, Any]] = []
    messages = exported if isinstance(exported, list) else exported.get("messages", []) if isinstance(exported, dict) else []
    for message in messages:
        if not isinstance(message, dict):
            continue
        info = message.get("info")
        if not isinstance(info, dict) or info.get("role") != "assistant":
            continue
        for part in message.get("parts", []):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                value = part["text"].strip()
                if value and part.get("synthetic") is not True and part.get("ignored") is not True:
                    parts.append(value)
            if part.get("type") == "tool" and isinstance(part.get("tool"), str):
                tools.append(part["tool"])
                action = tool_action(part)
                if action:
                    actions.append(action)
    return "\n\n".join(parts), list(dict.fromkeys(tools)), actions


def prepare_opencode_env() -> dict[str, str]:
    env = dict(os.environ)
    root = Path("/tmp/runtime")
    home = root / "home"
    config = root / "config" / "opencode"
    data = root / "data" / "opencode"
    cache = root / "cache"
    cache_opencode = cache / "opencode"
    state = root / "state"
    for path in (home, config, data, cache_opencode, state):
        path.mkdir(parents=True, exist_ok=True)

    seed_config = Path("/seed/opencode.json")
    seed_auth = Path("/seed/auth.json")
    seed_models = Path("/seed/models.json")
    seed_database = Path("/seed/opencode.db")
    seed_config_root = Path("/seed/opencode-config")
    if seed_config.is_file():
        shutil.copyfile(seed_config, config / "opencode.json")
    else:
        (config / "opencode.json").write_text(
            json.dumps({"$schema": "https://opencode.ai/config.json"}) + "\n",
            encoding="utf-8",
        )
    if seed_config_root.is_dir():
        # Loom itself can be an OpenCode global config root. OpenCode 2.0.11's
        # packaged runtime can fail to register directory plugins even when
        # plugins/<name>/index.ts is present. Materialize a direct plugins/*.ts
        # entrypoint instead, which bypasses Host.resolve/Bun.resolveSync for
        # the plugin root while preserving Loom's local module tree.
        loom_source = seed_config_root / "plugins" / "loom"
        if loom_source.is_dir():
            module_root = config / "loom-plugin"
            plugin_root = config / "plugins"
            shutil.copytree(loom_source, module_root, dirs_exist_ok=True)
            plugin_root.mkdir(parents=True, exist_ok=True)
            (plugin_root / "loom.ts").write_text(
                'export { default } from "../loom-plugin/index.ts"\n',
                encoding="utf-8",
            )
    if seed_auth.is_file():
        shutil.copyfile(seed_auth, data / "auth.json")
    if seed_models.is_file():
        shutil.copyfile(seed_models, cache_opencode / "models.json")
    if seed_database.is_file():
        shutil.copyfile(seed_database, data / "opencode.db")

    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(cache),
        "XDG_STATE_HOME": str(state),
        "OPENCODE_CONFIG_DIR": str(config),
        "OPENCODE_DB": "opencode.db",
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
    })
    return env


def plugin_diagnostic(env: dict[str, str]) -> dict[str, Any]:
    config_root = Path(
        env.get("OPENCODE_CONFIG_DIR")
        or Path(env.get("XDG_CONFIG_HOME", "/tmp/runtime/config")) / "opencode"
    )
    plugins_root = config_root / "plugins"
    loom_root = plugins_root / "loom"
    loom_flat = plugins_root / "loom.ts"
    loom_module_root = config_root / "loom-plugin"
    return {
        "config_root": str(config_root),
        "config_root_exists": config_root.exists(),
        "plugins_root": str(plugins_root),
        "plugins_exists": plugins_root.exists(),
        "plugins_is_dir": plugins_root.is_dir(),
        "plugins_resolved": str(plugins_root.resolve()) if plugins_root.exists() else None,
        "plugins_entries": sorted(item.name for item in plugins_root.iterdir()) if plugins_root.is_dir() else [],
        "loom_exists": loom_root.exists(),
        "loom_is_dir": loom_root.is_dir(),
        "loom_index_exists": (loom_root / "index.ts").is_file(),
        "loom_flat_exists": loom_flat.is_file(),
        "loom_module_index_exists": (loom_module_root / "index.ts").is_file(),
    }


def invoke_opencode(model: str, agent: str, prompt: str, timeout: int) -> dict[str, Any]:
    env = prepare_opencode_env()
    plugins = plugin_diagnostic(env)

    # OpenCode V2 has no documented force-refresh command for the model
    # catalog. A fresh isolated process owns a fresh cache and resolves the
    # requested model through its normal provider/catalog startup path.
    # The real model invocation is authoritative; provider/model resolution
    # failures are reported as transport failures instead of preflight guesses.
    command = ["opencode", "run", "--standalone", "--format", "json", "--auto"]
    if agent:
        command += ["--agent", agent]
    command += ["--model", model, prompt]
    proc = run(command, Path("/workspace"), env, timeout)
    events = parse_events(proc.stdout)
    sid = session_id(events)
    exported: Any = None

    if sid:
        exp = run(["opencode", "session", "export", sid, "--sanitize"], Path("/workspace"), env, timeout)
        if exp.returncode == 0:
            try:
                exported = json.loads(exp.stdout)
            except json.JSONDecodeError:
                exported = None

    exported_text, exported_tools, exported_actions = assistant_from_export(exported)
    text = exported_text or extract_text(events)
    tools = exported_tools or extract_tools(events)
    actions = exported_actions or extract_actions(events)

    return {
        "schema": RESULT_SCHEMA,
        "transport": "opencode",
        "model": model,
        "agent": agent or None,
        "exit_code": proc.returncode,
        "session_id": sid,
        "text": text,
        "tools": tools,
        "actions": actions,
        "stderr": proc.stderr[:20000],
        "stdout": proc.stdout[:200000],
        "plugin_diagnostic": plugins,
    }


def copilot_auth_source(env: dict[str, str]) -> str | None:
    for name in COPILOT_AUTH_ENVS:
        if env.get(name, "").strip():
            return name
    return None


def copilot_profile(system: str) -> str:
    return (
        "---\n"
        f"name: {COPILOT_AGENT_NAME}\n"
        "description: Isolated behavioral-eval model transport.\n"
        "tools: []\n"
        "---\n\n"
        + system.strip()
        + "\n"
    )


def invoke_copilot(model: str, prompt: str, system: str, timeout: int) -> dict[str, Any]:
    env = dict(os.environ)
    auth_source = copilot_auth_source(env)
    if not auth_source:
        return {
            "schema": RESULT_SCHEMA,
            "transport": "github-copilot-cli",
            "model": model,
            "agent": COPILOT_AGENT_NAME,
            "exit_code": 2,
            "session_id": None,
            "text": "",
            "tools": [],
            "actions": [],
            "stderr": "github-copilot-cli requires COPILOT_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN",
            "stdout": "",
        }

    root = Path("/tmp/copilot")
    work = root / "work"
    home = root / "home"
    cache = root / "cache"
    agent_dir = work / ".github" / "agents"
    for path in (agent_dir, home, cache):
        path.mkdir(parents=True, exist_ok=True)

    (agent_dir / f"{COPILOT_AGENT_NAME}.agent.md").write_text(copilot_profile(system), encoding="utf-8")
    env["COPILOT_HOME"] = str(home)
    env["COPILOT_CACHE_HOME"] = str(cache)
    env["COPILOT_AUTO_UPDATE"] = "false"
    env["GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS"] = "false"
    env["GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS"] = "false"

    command = [
        "copilot",
        "-C", str(work),
        "--agent", COPILOT_AGENT_NAME,
        "-p", prompt,
        "-s",
        "--model", model,
        "--disable-builtin-mcps",
        "--no-experimental",
        "--no-remote",
        "--no-remote-export",
        "--excluded-tools", ",".join(COPILOT_EXCLUDED_TOOLS),
        "--deny-tool", ",".join(COPILOT_DENIED_PERMISSIONS),
    ]
    proc = run(command, work, env, timeout)
    return {
        "schema": RESULT_SCHEMA,
        "transport": "github-copilot-cli",
        "model": model,
        "agent": COPILOT_AGENT_NAME,
        "credential_source": auth_source,
        "exit_code": proc.returncode,
        "session_id": None,
        "text": proc.stdout.strip() if proc.returncode == 0 else "",
        "tools": [],
        "actions": [],
        "stderr": proc.stderr[:20000],
        "stdout": proc.stdout[:200000],
    }


def emit_result(result: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        transport = os.environ.get("EVAL_TRANSPORT", "opencode")
        model = os.environ["EVAL_MODEL"]
        agent = os.environ.get("EVAL_AGENT", "")
        timeout = int(os.environ.get("EVAL_TIMEOUT_SECONDS", "240"))
        prompt = Path(os.environ.get("EVAL_PROMPT_FILE", "/input/prompt.txt")).read_text(encoding="utf-8")
        system_path = Path(os.environ.get("EVAL_SYSTEM_FILE", "/input/system.txt"))
        system = system_path.read_text(encoding="utf-8") if system_path.is_file() else ""

        if transport == "opencode":
            result = invoke_opencode(model, agent, prompt, timeout)
        elif transport == "github-copilot-cli":
            result = invoke_copilot(model, prompt, system, timeout)
        else:
            raise RuntimeError(f"unsupported transport: {transport}")

        emit_result(result)
        return 0
    except Exception as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "transport": os.environ.get("EVAL_TRANSPORT"),
            "model": os.environ.get("EVAL_MODEL"),
            "exit_code": 2,
            "session_id": None,
            "text": "",
            "tools": [],
            "actions": [],
            "stderr": f"{type(exc).__name__}: {exc}",
            "stdout": "",
            "infrastructure_error": True,
        }
        emit_result(result)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
