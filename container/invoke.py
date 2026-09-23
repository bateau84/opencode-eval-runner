#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import selectors
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

RESULT_SCHEMA = "opencode-eval-runner/v1"
OPENCODE_EVAL_TITLE = "opencode-eval-runner"
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


def timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def last_event_summary(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    event = events[-1]
    part = event.get("part")
    result: dict[str, Any] = {}
    for key in ("type", "timestamp", "sessionID", "sessionId"):
        value = event.get(key)
        if value is not None:
            result[key] = value
    if isinstance(part, dict):
        for key in ("type", "tool"):
            value = part.get(key)
            if value is not None:
                result["part_" + key] = value
        state = part.get("state")
        if isinstance(state, dict) and state.get("status") is not None:
            result["part_status"] = state.get("status")
    return result


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


TOOL_RESULT_FIELD_LIMIT = 6000
TOOL_RESULT_EVENT_LIMIT = 64
TOOL_RESULT_TOTAL_LIMIT = 48000
STDOUT_CAPTURE_LIMIT = 200000


def _tool_result_text(value: Any, limit: int) -> tuple[str, bool]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return text, False
    marker = "\n[... tool-result field truncated ...]\n"
    retained = limit - len(marker)
    head = retained // 2
    return text[:head] + marker + text[-(retained - head):], True


def extract_tool_result_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Bound tool results from the full structured event stream before stdout clipping."""
    evidence: dict[str, Any] = {
        "schema": "opencode-eval-runner/tool-results/v1",
        "source": "opencode.event-stream.full",
        "observed_events": 0,
        "omitted_events": 0,
        "events": [],
    }
    recent: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "tool_use":
            continue
        part = event.get("part")
        if not isinstance(part, dict) or part.get("type") != "tool" or not isinstance(part.get("tool"), str):
            continue
        state = part.get("state")
        if not isinstance(state, dict):
            continue
        evidence["observed_events"] += 1
        item: dict[str, Any] = {
            "sequence": evidence["observed_events"],
            "truncated_fields": [],
        }
        fields: dict[str, tuple[Any, int]] = {
            "tool": (part["tool"], 256),
            "status": (state.get("status", "unknown"), 256),
            "input": (state.get("input", {}), 2000),
        }
        for key, value in (("call_id", part.get("callID")), ("session_id", event.get("sessionID"))):
            if value is not None:
                fields[key] = (value, 256)
        for key in ("output", "error"):
            if key in state:
                fields[key] = (state[key], TOOL_RESULT_FIELD_LIMIT)
        for key, (value, limit) in fields.items():
            item[key], clipped = _tool_result_text(value, limit)
            if clipped:
                item["truncated_fields"].append(key)
        recent.append(item)
        if len(recent) > TOOL_RESULT_EVENT_LIMIT:
            recent.pop(0)

    evidence["events"] = recent
    evidence["omitted_events"] = evidence["observed_events"] - len(recent)
    while len(json.dumps(evidence, ensure_ascii=False)) > TOOL_RESULT_TOTAL_LIMIT and evidence["events"]:
        evidence["events"].pop(0)
        evidence["omitted_events"] += 1
    return evidence


def completed_skill_from_part(part: dict[str, Any]) -> str | None:
    if part.get("type") != "tool" or part.get("tool") != "skill":
        return None
    state = part.get("state")
    if not isinstance(state, dict) or state.get("status") != "completed":
        return None
    args = state.get("input")
    if not isinstance(args, dict):
        return None
    skill = args.get("id") or args.get("name")
    return skill if isinstance(skill, str) and skill else None


def extract_loaded_skills(events: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for event in events:
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        skill = completed_skill_from_part(part)
        if skill and skill not in found:
            found.append(skill)
    return found


def loaded_skills_from_export(exported: Any) -> list[str]:
    found: list[str] = []
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
            skill = completed_skill_from_part(part)
            if skill and skill not in found:
                found.append(skill)
    return found


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

            # OpenCode V2 resolves package imports for config-root local
            # plugins from the config-root dependency context. Runtime evals
            # mount the repository dependencies at /workspace/node_modules, so
            # bridge that dependency tree into the isolated config root. This
            # keeps the plugin source isolated while making imports such as
            # @opencode/plugin/rpc resolvable from the materialized module tree.
            workspace_node_modules = Path("/workspace/node_modules")
            config_node_modules = config / "node_modules"
            if workspace_node_modules.is_dir() and not config_node_modules.exists():
                config_node_modules.symlink_to(workspace_node_modules, target_is_directory=True)
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


def ensure_model_config(env: dict[str, str], model: str) -> None:
    config_root = Path(
        env.get("OPENCODE_CONFIG_DIR")
        or Path(env.get("XDG_CONFIG_HOME", "/tmp/runtime/config")) / "opencode"
    )
    config_file = config_root / "opencode.json"
    data: dict[str, Any] = {}
    if config_file.is_file():
        try:
            parsed = json.loads(config_file.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            pass
    data["$schema"] = data.get("$schema") or "https://opencode.ai/config.json"
    data["model"] = model
    config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def unwrap_api_data(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def _standalone_json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
    authorization: str | None = None,
) -> Any:
    data = None
    headers: dict[str, str] = {}
    if authorization:
        headers["authorization"] = authorization
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenCode preflight request {method} {path} failed: HTTP {exc.code}: {body[:2000]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"OpenCode preflight request {method} {path} failed: {exc}"
        ) from exc
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"OpenCode preflight request {method} {path} returned non-JSON: {body[:2000]}"
        ) from exc


def _start_preflight_server(
    env: dict[str, str],
    timeout: float,
) -> tuple[subprocess.Popen[str], str, str]:
    server_env = dict(env)
    server_env["OPENCODE_PRINT_LOGS"] = "1"
    password = secrets.token_urlsafe(32)
    server_env["OPENCODE_PASSWORD"] = password
    authorization = "Basic " + base64.b64encode(
        f"opencode:{password}".encode("utf-8")
    ).decode("ascii")
    proc = subprocess.Popen(
        ["opencode", "serve", "--stdio", "--port", "0"],
        cwd="/workspace",
        env=server_env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:
        proc.kill()
        raise RuntimeError("OpenCode preflight server has no stdout pipe")
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    events = selector.select(timeout=max(timeout, 0.1))
    selector.close()
    if not events:
        proc.kill()
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise RuntimeError(
            "OpenCode preflight server did not report readiness"
            + (f": {stderr[:3000]}" if stderr.strip() else "")
        )
    line = proc.stdout.readline()
    try:
        ready = json.loads(line)
    except json.JSONDecodeError as exc:
        proc.kill()
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise RuntimeError(
            f"OpenCode preflight server returned invalid readiness JSON: {line!r}"
            + (f"; logs: {stderr[:3000]}" if stderr.strip() else "")
        ) from exc
    url = ready.get("url") if isinstance(ready, dict) else None
    if not isinstance(url, str) or not url:
        proc.kill()
        raise RuntimeError(f"OpenCode preflight server readiness payload has no URL: {ready!r}")
    return proc, url, authorization


def _stop_preflight_server(proc: subprocess.Popen[str]) -> str:
    try:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    return proc.stderr.read() if proc.stderr is not None else ""


def verify_expected_plugin(
    env: dict[str, str],
    agent: str,
    model: str,
    expected_plugin: str,
    timeout: int,
) -> dict[str, Any]:
    if not expected_plugin:
        return {"expected": None, "agent": None, "entrypoints": []}
    if not agent:
        raise RuntimeError("expected plugin preflight requires an agent")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", expected_plugin):
        raise RuntimeError(f"invalid expected plugin name: {expected_plugin!r}")

    ensure_model_config(env, model)
    config_root = Path(
        env.get("OPENCODE_CONFIG_DIR")
        or Path(env.get("XDG_CONFIG_HOME", "/tmp/runtime/config")) / "opencode"
    )
    plugins_root = config_root / "plugins"
    candidates = [
        plugins_root / expected_plugin,
        plugins_root / f"{expected_plugin}.ts",
        plugins_root / f"{expected_plugin}.js",
        plugins_root / f"{expected_plugin}.mjs",
    ]
    entrypoints = sorted(
        str(path.relative_to(config_root))
        for path in candidates
        if path.is_dir() or path.is_file()
    )
    if not entrypoints:
        available = (
            sorted(item.name for item in plugins_root.iterdir())
            if plugins_root.is_dir()
            else []
        )
        raise RuntimeError(
            f"expected plugin {expected_plugin!r} is not materialized in {plugins_root}; "
            f"available entries: {available[:80]}"
        )

    # Agent resolution is intentionally left to the real `opencode run --agent`
    # invocation. OpenCode V2 activates plugins asynchronously for a cold
    # Location. The raw plugin.list endpoint can therefore observe an empty
    # inventory before activation settles. Start one private server, submit a
    # non-resuming Session prompt (SessionPrompt.prepare waits on
    # Plugin.awaitActivation without starting model inference), then inspect
    # the plugin inventory on that same server.
    preflight_timeout = min(timeout, 30)
    started = time.monotonic()
    server, base_url, authorization = _start_preflight_server(
        inventory_env := dict(env),
        preflight_timeout,
    )
    logs = ""
    try:
        remaining = lambda: max(0.5, preflight_timeout - (time.monotonic() - started))
        created = _standalone_json_request(
            base_url,
            "/api/session",
            method="POST",
            payload={
                "title": "opencode-eval-runner plugin preflight",
                "agent": agent,
                "location": {"directory": "/workspace"},
            },
            timeout=remaining(),
            authorization=authorization,
        )
        session_payload = unwrap_api_data(created)
        if not isinstance(session_payload, dict) or not isinstance(session_payload.get("id"), str):
            raise RuntimeError(
                f"OpenCode preflight session.create returned invalid payload: {created!r}"
            )
        session_id = session_payload["id"]
        _standalone_json_request(
            base_url,
            f"/api/session/{session_id}/prompt",
            method="POST",
            payload={
                "text": "plugin activation preflight",
                "resume": False,
            },
            timeout=remaining(),
            authorization=authorization,
        )
        inventory = _standalone_json_request(
            base_url,
            "/api/plugin?location%5Bdirectory%5D=%2Fworkspace",
            timeout=remaining(),
            authorization=authorization,
        )
        inventory_payload = unwrap_api_data(inventory)
        if not isinstance(inventory_payload, list):
            raise RuntimeError(
                f"expected plugin inventory preflight returned invalid payload for {expected_plugin!r}: "
                f"{inventory_payload!r}"
            )
        plugin = next(
            (
                value
                for value in inventory_payload
                if isinstance(value, dict) and value.get("id") == expected_plugin
            ),
            None,
        )
        if plugin is None:
            available = sorted(
                str(value.get("id"))
                for value in inventory_payload
                if isinstance(value, dict) and value.get("id")
            )
            raise RuntimeError(
                f"expected plugin {expected_plugin!r} is not present in OpenCode plugin inventory "
                f"after activation; available plugins: {available[:120]}"
            )
        state = plugin.get("state")
        status = state.get("status") if isinstance(state, dict) else None
        if status != "active":
            error = state.get("error") if isinstance(state, dict) else None
            ref = state.get("ref") if isinstance(state, dict) else None
            raise RuntimeError(
                f"expected plugin {expected_plugin!r} is not active"
                + (f": {error}" if error else f"; state={state!r}")
                + (f" ({ref})" if ref else "")
            )
    except Exception as exc:
        logs = _stop_preflight_server(server)
        raise RuntimeError(
            str(exc)
            + (f"; server logs: {logs.strip()[:4000]}" if logs.strip() else "")
        ) from exc
    else:
        logs = _stop_preflight_server(server)

    return {
        "expected": expected_plugin,
        "agent": agent,
        "entrypoints": entrypoints,
        "plugin": plugin,
        "verification": "plugin-entrypoint+activation-barrier+plugin-inventory",
    }


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


def invoke_opencode(
    model: str,
    agent: str,
    prompt: str,
    timeout: int,
    skill: str = "",
) -> dict[str, Any]:
    env = prepare_opencode_env()
    plugins = plugin_diagnostic(env)
    expected_plugin = os.environ.get("EVAL_EXPECT_PLUGIN", "").strip()
    plugin_preflight = verify_expected_plugin(env, agent, model, expected_plugin, timeout)

    # OpenCode V2 has no documented force-refresh command for the model
    # catalog. A fresh isolated process owns a fresh cache and resolves the
    # requested model through its normal provider/catalog startup path.
    # The real model invocation is authoritative; provider/model resolution
    # failures are reported as transport failures instead of preflight guesses.
    # Every eval invocation uses a fresh OpenCode session. Supplying a fixed
    # title prevents OpenCode from launching its automatic title agent, which
    # otherwise adds an unrelated model call (and any title-model retries) to
    # every target and judge invocation.
    command = [
        "opencode",
        "run",
        "--standalone",
        "--format",
        "json",
        "--auto",
        "--title",
        OPENCODE_EVAL_TITLE,
    ]
    if agent:
        command += ["--agent", agent]
    command += ["--model", model, prompt]
    run_started = time.perf_counter()
    try:
        proc = run(command, Path("/workspace"), env, timeout)
    except subprocess.TimeoutExpired as exc:
        run_seconds = time.perf_counter() - run_started
        stdout = timeout_output(exc.stdout)
        stderr = timeout_output(exc.stderr)
        events = parse_events(stdout)
        sid = session_id(events)
        summary = last_event_summary(events)
        detail = (
            f"opencode run timed out after {timeout}s; "
            f"partial_events={len(events)}"
            + (f"; last_event={json.dumps(summary, sort_keys=True)}" if summary else "")
        )
        if stderr.strip():
            detail += "\n" + stderr.strip()
        return {
            "schema": RESULT_SCHEMA,
            "transport": "opencode",
            "model": model,
            "agent": agent or None,
            "skill": skill or None,
            "exit_code": 124,
            "timed_out": True,
            "session_id": sid,
            "text": extract_text(events),
            "tools": extract_tools(events),
            "actions": extract_actions(events),
            "skills_loaded": extract_loaded_skills(events),
            "timing": {
                "run_seconds": round(run_seconds, 3),
                "export_seconds": 0.0,
                "export_exit_code": None,
                "total_seconds": round(run_seconds, 3),
            },
            "stderr": detail[:20000],
            "stdout": stdout[:STDOUT_CAPTURE_LIMIT],
            "stdout_truncated": len(stdout) > STDOUT_CAPTURE_LIMIT,
            "stdout_total_chars": len(stdout),
            "tool_result_evidence": extract_tool_result_evidence(events),
            "plugin_diagnostic": plugins,
            "plugin_preflight": plugin_preflight,
        }

    run_seconds = time.perf_counter() - run_started
    events = parse_events(proc.stdout)
    sid = session_id(events)

    # The structured `opencode run --format json` event stream is the
    # authoritative evidence source. Starting a second OpenCode process to
    # export the just-created session is redundant and can add a full timeout
    # per invocation when export/session bootstrap fails. Keep eval latency
    # bound to the requested target/judge execution only.
    text = extract_text(events)
    tools = extract_tools(events)
    actions = extract_actions(events)
    skills_loaded = extract_loaded_skills(events)
    export_seconds = 0.0
    export_exit_code: int | None = None

    return {
        "schema": RESULT_SCHEMA,
        "transport": "opencode",
        "model": model,
        "agent": agent or None,
        "skill": skill or None,
        "exit_code": proc.returncode,
        "session_id": sid,
        "text": text,
        "tools": tools,
        "actions": actions,
        "skills_loaded": skills_loaded,
        "timing": {
            "run_seconds": round(run_seconds, 3),
            "export_seconds": round(export_seconds, 3),
            "export_exit_code": export_exit_code,
            "total_seconds": round(run_seconds + export_seconds, 3),
        },
        "stderr": proc.stderr[:20000],
        "stdout": proc.stdout[:STDOUT_CAPTURE_LIMIT],
        "stdout_truncated": len(proc.stdout) > STDOUT_CAPTURE_LIMIT,
        "stdout_total_chars": len(proc.stdout),
        "tool_result_evidence": extract_tool_result_evidence(events),
        "plugin_diagnostic": plugins,
        "plugin_preflight": plugin_preflight,
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
            "skill": None,
            "exit_code": 2,
            "session_id": None,
            "text": "",
            "tools": [],
            "actions": [],
            "skills_loaded": [],
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
        "skill": None,
        "credential_source": auth_source,
        "exit_code": proc.returncode,
        "session_id": None,
        "text": proc.stdout.strip() if proc.returncode == 0 else "",
        "tools": [],
        "actions": [],
        "skills_loaded": [],
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
        skill = os.environ.get("EVAL_SKILL", "")
        timeout = int(os.environ.get("EVAL_TIMEOUT_SECONDS", "240"))
        prompt = Path(os.environ.get("EVAL_PROMPT_FILE", "/input/prompt.txt")).read_text(encoding="utf-8")
        system_path = Path(os.environ.get("EVAL_SYSTEM_FILE", "/input/system.txt"))
        system = system_path.read_text(encoding="utf-8") if system_path.is_file() else ""

        if transport == "opencode":
            result = invoke_opencode(model, agent, prompt, timeout, skill)
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
            "skill": os.environ.get("EVAL_SKILL") or None,
            "exit_code": 2,
            "session_id": None,
            "text": "",
            "tools": [],
            "actions": [],
            "skills_loaded": [],
            "stderr": f"{type(exc).__name__}: {exc}",
            "stdout": "",
            "infrastructure_error": True,
        }
        emit_result(result)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
