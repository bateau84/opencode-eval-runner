#!/usr/bin/env python3
"""Provider-free acceptance gate for trusted-checkout runtime evidence.

The driver uses a local OpenAI-compatible HTTP fixture only to deterministically
select tools. Evidence assertions use the runner's public runtime_evidence
contract. Workspace oracle records are test-only comparison data and are never
accepted as evidence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("runtime_evidence_fixture.ts")
SECRET = "runtime-evidence-acceptance-secret-7f6e5d4c"
STATUSES = {"complete", "incomplete", "unsupported", "invalid"}

GENERAL = """---
description: Runtime evidence parent fixture
mode: primary
model: fixture/mock
permissions:
  - action: "*"
    resource: "*"
    effect: allow
---

Use the requested fixture tool.
"""

REVIEWER = """---
description: Runtime evidence delegated fixture
mode: subagent
model: fixture/mock
permissions:
  - action: "*"
    resource: "*"
    effect: allow
---

Complete the delegated fixture task.
"""


def canonical(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("state"), str) and "value" in value:
        return value.get("value")
    return value


def field_state(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("state"), str):
        return value["state"]
    return None


def evidence_of(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("runtime_evidence")
    return value if isinstance(value, dict) else {}


def coverage_count(evidence: dict[str, Any], key: str) -> int:
    coverage = evidence.get("coverage")
    if not isinstance(coverage, dict):
        return 0
    value = unwrap(coverage.get(key, 0))
    if type(value) is int:
        return value
    if isinstance(value, list):
        return len(value)
    return 0


def aggregate_invocations(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept the v1 aggregate shape and a start/end event shape during rollout."""
    observations = evidence.get("observations")
    if not isinstance(observations, list):
        return []
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    anonymous = 0
    for raw in observations:
        if not isinstance(raw, dict):
            continue
        iid = unwrap(raw.get("invocation_id"))
        if not isinstance(iid, str) or not iid:
            anonymous += 1
            iid = f"<anonymous-{anonymous}>"
        if iid not in grouped:
            grouped[iid] = {"invocation_id": iid}
            order.append(iid)
        item = grouped[iid]
        kind = canonical(unwrap(raw.get("kind")))
        for key, value in raw.items():
            if key not in item or value is not None:
                item[key] = value
        sequence = unwrap(raw.get("sequence"))
        if kind in {"callstart", "start"} and type(sequence) is int:
            item.setdefault("start_sequence", sequence)
        if kind in {"callend", "terminal", "end"} and type(sequence) is int:
            item.setdefault("terminal_sequence", sequence)
    return [grouped[iid] for iid in order]


def tool_name(item: dict[str, Any]) -> str:
    value = unwrap(item.get("tool"))
    return value if isinstance(value, str) else ""


def mode_name(item: dict[str, Any]) -> str:
    value = unwrap(item.get("mode"))
    return canonical(value)


def tool_matches(item: dict[str, Any], suffix: str) -> bool:
    return canonical(tool_name(item)).endswith(canonical(suffix))


def matching(evidence: dict[str, Any], suffix: str) -> list[dict[str, Any]]:
    return [item for item in aggregate_invocations(evidence) if tool_matches(item, suffix)]


def sequence(item: dict[str, Any], key: str) -> int | None:
    value = unwrap(item.get(key))
    return value if type(value) is int else None


def actor_value(item: dict[str, Any], key: str) -> Any:
    actor = unwrap(item.get("actor"))
    if isinstance(actor, dict):
        aliases = {
            "session_id": ("session_id", "sessionID", "sessionId"),
            "message_id": ("message_id", "messageID", "messageId"),
            "agent": ("agent",),
        }
        for name in aliases.get(key, (key,)):
            value = unwrap(actor.get(name))
            if value is not None:
                return value
    value = unwrap(item.get(key))
    if value is not None:
        return value
    camel = {"session_id": "sessionID", "message_id": "messageID"}.get(key)
    return unwrap(item.get(camel)) if camel else None


def parent_session(item: dict[str, Any]) -> str | None:
    for key in ("parent_session_id", "parentSessionID", "parentSessionId"):
        value = unwrap(item.get(key))
        if isinstance(value, str) and value:
            return value
    parent = unwrap(item.get("parent"))
    if isinstance(parent, dict):
        for key in ("session_id", "sessionID", "sessionId", "parent_session_id"):
            value = unwrap(parent.get(key))
            if isinstance(value, str) and value:
                return value
    return None


def evidence_has_ancestry(evidence: dict[str, Any], child: str, parent: str) -> bool:
    for key in ("sessions", "ancestry", "session_ancestry"):
        values = evidence.get(key)
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, dict):
                continue
            child_value = unwrap(raw.get("session_id") or raw.get("child_session_id") or raw.get("child"))
            parent_value = unwrap(raw.get("parent_session_id") or raw.get("parent_id") or raw.get("parent"))
            if child_value == child and parent_value == parent:
                return True
    return any(
        actor_value(item, "session_id") == child and parent_session(item) == parent
        for item in aggregate_invocations(evidence)
    )


def terminal_present(item: dict[str, Any]) -> bool:
    if sequence(item, "terminal_sequence") is not None:
        return True
    kind = canonical(unwrap(item.get("kind")))
    if kind in {"callend", "terminal", "end"}:
        return True
    return any(key in item for key in ("outcome", "result", "error"))


def explicit_unsupported(evidence: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    if evidence.get("status") == "unsupported" and evidence.get("evidence_eligible") is False:
        return True
    if coverage_count(evidence, "unsupported") > 0:
        return True
    for item in items:
        if unwrap(item.get("status")) == "unsupported" or item.get("evidence_eligible") is False:
            return True
        for key in ("result", "error", "terminal"):
            if field_state(item.get(key)) == "unsupported":
                return True
    return False


def json_contains(value: Any, needle: str) -> bool:
    return needle in json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_oracle(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def actual_tool_name(body: dict[str, Any], suffix: str) -> str | None:
    target = canonical(suffix)
    for item in body.get("tools", []):
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        if isinstance(name, str) and canonical(name).endswith(target):
            return name
    return None


def provider_message(body: dict[str, Any], call_id: str | None, tool: tuple[str, dict[str, Any]] | None, text: str | None) -> bytes:
    common = {"id": "chatcmpl-runtime-evidence", "created": 1, "model": body.get("model", "fixture/mock")}
    if tool is not None:
        call = {
            "index": 0,
            "id": call_id or "fixture-call",
            "type": "function",
            "function": {"name": tool[0], "arguments": json.dumps(tool[1], separators=(",", ":"))},
        }
        delta: dict[str, Any] = {"role": "assistant", "tool_calls": [call]}
        finish = "tool_calls"
    else:
        call = None
        delta = {"role": "assistant", "content": text or ""}
        finish = "stop"
    if body.get("stream"):
        chunks = [
            {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
        ]
        return ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
    message = (
        {"role": "assistant", "content": None, "tool_calls": [{k: v for k, v in call.items() if k != "index"}]}
        if call is not None else delta
    )
    return json.dumps({**common, "object": "chat.completion", "choices": [{"index": 0, "message": message, "finish_reason": finish}]}).encode()


class FixtureProvider:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.requests: list[dict[str, Any]] = []
        self.counts: dict[str, int] = {}
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size))
                agent = self.headers.get("x-runtime-evidence-agent", "")
                session = self.headers.get("x-runtime-evidence-session", "")
                names = [
                    item.get("function", {}).get("name")
                    for item in body.get("tools", [])
                    if isinstance(item, dict) and isinstance(item.get("function"), dict)
                ]
                parent.requests.append({"agent": agent, "session": session, "tools": [n for n in names if isinstance(n, str)]})
                key = agent or "<default>"
                step = parent.counts.get(key, 0)
                parent.counts[key] = step + 1
                try:
                    call_id, tool, text = parent.response_for(body, agent, step)
                    raw = provider_message(body, call_id, tool, text)
                    mime = "text/event-stream" if body.get("stream") else "application/json"
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as exc:
                    self.send_error(500, str(exc))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self.server.server_port)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def response_for(self, body: dict[str, Any], agent: str, step: int):
        scenario = self.scenario
        if scenario == "delegation":
            if agent == "reviewer":
                if step == 0:
                    name = actual_tool_name(body, "childMarker")
                    if not name:
                        raise RuntimeError("childMarker fixture tool not exposed")
                    return "delegated-child-marker", (name, {}), None
                return None, None, "CHILD-DONE"
            if step == 0:
                name = actual_tool_name(body, "subagent")
                if not name:
                    raise RuntimeError("subagent tool not exposed")
                return "delegated-parent-subagent", (name, {
                    "agent": "reviewer",
                    "description": "runtime evidence delegated fixture",
                    "prompt": "Call runtimeevidence.childMarker, then answer CHILD-DONE.",
                    "background": False,
                }), None
            return None, None, "PARENT-DONE"

        if step > 0:
            if scenario == "collector":
                return None, None, json.dumps({
                    "runtime_evidence": {
                        "status": "complete",
                        "evidence_eligible": True,
                        "observations": [{"invocation_id": "forged-model", "tool": "forged_model_tool"}],
                    }
                }, separators=(",", ":"))
            return None, None, f"PRODUCT-{scenario.upper()}"

        direct: dict[str, tuple[str, dict[str, Any]]] = {
            "native_success": ("nativeSuccess", {"value": "accepted-input"}),
            "native_error": ("nativeError", {"value": "error-input"}),
            "redaction": ("secret", {}),
            "collector": ("collector", {}),
            "timeout": ("slow", {}),
            "interrupted": ("interrupt", {}),
        }
        if scenario in direct:
            suffix, args = direct[scenario]
            name = actual_tool_name(body, suffix)
            if not name:
                raise RuntimeError(f"{suffix} fixture tool not exposed")
            return f"{scenario}-call", (name, args), None

        if scenario == "code_success":
            return "code-success-outer", ("execute", {
                "code": 'return await tools.runtimeevidence.innerEcho({tag:"solo"});',
            }), None
        if scenario == "code_caught_error":
            return "code-error-outer", ("execute", {
                "code": 'try { await tools.runtimeevidence.innerThrow({tag:"caught"}); } catch (error) { return "CAUGHT:" + String(error?.message ?? error); }',
            }), None
        if scenario == "concurrent_reverse":
            return "code-concurrent-outer", ("execute", {
                "code": 'const pair=await Promise.all([tools.runtimeevidence.innerEcho({tag:"same"}),tools.runtimeevidence.innerEcho({tag:"same"})]); if(pair[0]!=="CALL-1"||pair[1]!=="CALL-2") throw Error("pair"); return JSON.stringify(pair);',
            }), None
        raise RuntimeError(f"unknown scenario: {scenario}")


def scenario_outcomes(result: dict[str, Any]) -> dict[str, Any]:
    evidence = evidence_of(result)
    return {
        "product": {
            "exit_code": result.get("exit_code"),
            "timed_out": result.get("timed_out", False),
            "text": result.get("text"),
        },
        "observation": {
            "status": evidence.get("status"),
            "coverage": evidence.get("coverage"),
        },
        "evidence": {"eligible": evidence.get("evidence_eligible")},
    }


def validate_contract(evidence: dict[str, Any]) -> dict[str, bool]:
    return {
        "runtime_evidence_present": bool(evidence),
        "status_explicit": evidence.get("status") in STATUSES,
        "eligibility_explicit": type(evidence.get("evidence_eligible")) is bool,
        "observations_explicit": isinstance(evidence.get("observations"), list),
        "coverage_explicit": isinstance(evidence.get("coverage"), dict),
    }


def oracle_for(oracle: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in oracle if item.get("kind") == "executed" and item.get("tool") == name), None)


def validate_native_success(result: dict[str, Any], oracle: list[dict[str, Any]]) -> dict[str, bool]:
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    items = matching(evidence, "nativeSuccess")
    item = items[0] if len(items) == 1 else {}
    actual = oracle_for(oracle, "nativeSuccess") or {}
    start, terminal = sequence(item, "start_sequence"), sequence(item, "terminal_sequence")
    checks.update({
        "product_success": result.get("exit_code") == 0 and result.get("text") == "PRODUCT-NATIVE_SUCCESS",
        "observation_complete": evidence.get("status") == "complete",
        "evidence_eligible": evidence.get("evidence_eligible") is True,
        "one_actual_native_call": len(items) == 1,
        "actual_executable_input": unwrap(item.get("input")) == actual.get("input") == {"value": "accepted-input"},
        "actual_session_identity": actor_value(item, "session_id") == actual.get("session_id") and bool(actual.get("session_id")),
        "actual_message_identity": actor_value(item, "message_id") == actual.get("message_id") and bool(actual.get("message_id")),
        "actual_agent_identity": actor_value(item, "agent") == actual.get("agent") == "general",
        "actual_call_identity": unwrap(item.get("call_id")) == actual.get("call_id") and bool(actual.get("call_id")),
        "ordered_start_terminal": type(start) is int and type(terminal) is int and start < terminal,
        "terminal_result_is_actual": terminal_present(item) and json_contains(unwrap(item.get("result")), "NATIVE:accepted-input"),
    })
    return checks


def validate_native_error(result: dict[str, Any]) -> dict[str, bool]:
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    items = matching(evidence, "nativeError")
    item = items[0] if len(items) == 1 else {}
    outcome = canonical(unwrap(item.get("outcome")))
    checks.update({
        "product_continues_after_tool_error": result.get("exit_code") == 0 and result.get("text") == "PRODUCT-NATIVE_ERROR",
        "observation_complete_despite_product_tool_error": evidence.get("status") == "complete",
        "evidence_eligible": evidence.get("evidence_eligible") is True,
        "one_actual_error_call": len(items) == 1,
        "terminal_is_error": terminal_present(item) and outcome in {"threw", "failed", "error", "errored"},
        "actual_error_preserved": json_contains(unwrap(item.get("error")), "NATIVE-FIXTURE-ERROR"),
    })
    return checks


def validate_code(result: dict[str, Any], suffix: str, expected: str, *, error: bool = False) -> dict[str, bool]:
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    items = matching(evidence, suffix)
    supported = bool(items) and all(terminal_present(item) for item in items) and not explicit_unsupported(evidence, items)
    checks["product_success"] = result.get("exit_code") == 0 and result.get("text") == expected
    if supported:
        item = items[0]
        outcome = canonical(unwrap(item.get("outcome")))
        checks.update({
            "code_mode_result_supported_or_explicit_unsupported": True,
            "inner_mode_explicit": mode_name(item) in {"code", "codemode", "inner", "codemodeinner"},
            "inner_parent_bound": unwrap(item.get("parent")) is not None,
            "inner_terminal_exact": (
                json_contains(unwrap(item.get("error")), "INNER-FIXTURE-ERROR") and outcome in {"threw", "failed", "error", "errored"}
                if error else json_contains(unwrap(item.get("result")), "CALL-1")
            ),
        })
    else:
        checks.update({
            "code_mode_result_supported_or_explicit_unsupported": explicit_unsupported(evidence, items),
            "inner_mode_explicit": True,
            "inner_parent_bound": True,
            "inner_terminal_exact": True,
        })
    return checks


def validate_concurrent(result: dict[str, Any]) -> dict[str, bool]:
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    items = matching(evidence, "innerEcho")
    supported = len(items) == 2 and all(terminal_present(item) for item in items) and not explicit_unsupported(evidence, items)
    checks["product_success"] = result.get("exit_code") == 0 and result.get("text") == "PRODUCT-CONCURRENT_REVERSE"
    if not supported:
        checks["concurrency_supported_or_explicit_unsupported"] = explicit_unsupported(evidence, items)
        return checks
    ordered = sorted(items, key=lambda item: sequence(item, "start_sequence") or 10**9)
    starts = [sequence(item, "start_sequence") for item in ordered]
    terminals = [sequence(item, "terminal_sequence") for item in ordered]
    parents = [json.dumps(unwrap(item.get("parent")), sort_keys=True) for item in ordered]
    checks.update({
        "concurrency_supported_or_explicit_unsupported": True,
        "unique_invocation_identity": len({item.get("invocation_id") for item in ordered}) == 2,
        "identical_executable_input": unwrap(ordered[0].get("input")) == unwrap(ordered[1].get("input")) == {"tag": "same"},
        "reverse_completion_not_fifo": all(type(x) is int for x in starts + terminals) and starts[0] < starts[1] < terminals[1] < terminals[0],
        "results_bound_to_identity": json_contains(unwrap(ordered[0].get("result")), "CALL-1") and json_contains(unwrap(ordered[1].get("result")), "CALL-2"),
        "same_actual_outer_parent": parents[0] == parents[1] and parents[0] not in {"null", "{}"},
    })
    return checks


def validate_delegation(result: dict[str, Any], oracle: list[dict[str, Any]], requests: list[dict[str, Any]]) -> dict[str, bool]:
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    child_oracle = oracle_for(oracle, "childMarker") or {}
    child_session = child_oracle.get("session_id")
    parent_session = child_oracle.get("parent_session_id")
    child_items = matching(evidence, "childMarker")
    child = child_items[0] if len(child_items) == 1 else {}
    subagents = matching(evidence, "subagent")
    checks.update({
        "product_success": result.get("exit_code") == 0 and result.get("text") == "PARENT-DONE",
        "observation_complete": evidence.get("status") == "complete",
        "evidence_eligible": evidence.get("evidence_eligible") is True,
        "foreground_subagent_observed": len(subagents) == 1 and terminal_present(subagents[0]),
        "child_native_call_observed": len(child_items) == 1 and terminal_present(child),
        "child_actor_identity": actor_value(child, "session_id") == child_session and actor_value(child, "agent") == "reviewer",
        "sessions_are_distinct": isinstance(child_session, str) and isinstance(parent_session, str) and child_session != parent_session,
        "runtime_ancestry_present": isinstance(child_session, str) and isinstance(parent_session, str) and evidence_has_ancestry(evidence, child_session, parent_session),
        "provider_saw_child_session": any(r.get("agent") == "reviewer" and r.get("session") == child_session for r in requests),
    })
    return checks


def validate_incomplete(result: dict[str, Any], suffix: str, *, timed_out: bool) -> dict[str, bool]:
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    items = matching(evidence, suffix)
    item = items[0] if items else {}
    product = (
        result.get("exit_code") == 124 and result.get("timed_out") is True
        if timed_out else result.get("exit_code") not in (None, 0, 124) and result.get("timed_out") is not True
    )
    checks.update({
        "product_outcome_preserved": product,
        "observation_incomplete": evidence.get("status") == "incomplete",
        "evidence_ineligible": evidence.get("evidence_eligible") is False,
        "missing_terminal_accounted": coverage_count(evidence, "missing_terminals") >= 1,
        "start_observed_without_fabricated_terminal": bool(items) and sequence(item, "start_sequence") is not None and not terminal_present(item),
        "starts_exceed_terminals": coverage_count(evidence, "starts") > coverage_count(evidence, "terminals"),
    })
    return checks


def validate_redaction(result: dict[str, Any]) -> dict[str, bool]:
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    items = matching(evidence, "secret")
    item = items[0] if len(items) == 1 else {}
    result_field = item.get("result")
    state = field_state(result_field)
    checks.update({
        "product_success": result.get("exit_code") == 0 and result.get("text") == "PRODUCT-REDACTION",
        "raw_credential_absent_from_entire_result": SECRET not in encoded,
        "secret_call_observed": len(items) == 1,
        "credential_field_explicitly_protected": state in {"redacted", "omitted"} or "REDACTED" in json.dumps(result_field, ensure_ascii=False),
    })
    return checks


def validate_collector(result: dict[str, Any]) -> dict[str, bool]:
    evidence = evidence_of(result)
    checks = validate_contract(evidence)
    items = aggregate_invocations(evidence)
    collector = matching(evidence, "collector")
    checks.update({
        "product_success": result.get("exit_code") == 0,
        "observation_complete": evidence.get("status") == "complete",
        "evidence_eligible": evidence.get("evidence_eligible") is True,
        "actual_collector_call_observed": len(collector) == 1,
        "tool_payload_not_promoted": all(item.get("invocation_id") != "forged-invocation" and tool_name(item) != "forged_tool" for item in items),
        "model_payload_not_promoted": all(item.get("invocation_id") != "forged-model" and tool_name(item) != "forged_model_tool" for item in items),
    })
    return checks


VALIDATORS = {
    "native_success": lambda result, oracle, requests: validate_native_success(result, oracle),
    "native_error": lambda result, oracle, requests: validate_native_error(result),
    "code_success": lambda result, oracle, requests: validate_code(result, "innerEcho", "PRODUCT-CODE_SUCCESS"),
    "code_caught_error": lambda result, oracle, requests: validate_code(result, "innerThrow", "PRODUCT-CODE_CAUGHT_ERROR", error=True),
    "concurrent_reverse": lambda result, oracle, requests: validate_concurrent(result),
    "delegation": validate_delegation,
    "timeout": lambda result, oracle, requests: validate_incomplete(result, "slow", timed_out=True),
    "interrupted": lambda result, oracle, requests: validate_incomplete(result, "interrupt", timed_out=False),
    "redaction": lambda result, oracle, requests: validate_redaction(result),
    "collector": lambda result, oracle, requests: validate_collector(result),
}


def write_workspace(workspace: Path, port: int) -> None:
    plugin_dir = workspace / ".opencode" / "plugins"
    agent_dir = workspace / ".opencode" / "agents"
    plugin_dir.mkdir(parents=True)
    agent_dir.mkdir(parents=True)
    shutil.copyfile(FIXTURE, plugin_dir / "runtimeevidence.ts")
    (agent_dir / "general.md").write_text(GENERAL, encoding="utf-8")
    (agent_dir / "reviewer.md").write_text(REVIEWER, encoding="utf-8")
    (workspace / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "default_agent": "general",
        "model": "fixture/mock",
        "enabled_providers": ["fixture"],
        "provider": {"fixture": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Provider-free runtime evidence fixture",
            "options": {"baseURL": f"http://127.0.0.1:{port}/v1", "apiKey": "fixture-api-key"},
            "models": {"mock": {"name": "Mock", "limit": {"context": 1000000, "output": 32768}}},
        }},
    }, indent=2) + "\n", encoding="utf-8")


def clean_env(scenario: str, xdg: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in list(env):
        if name.startswith("OPENCODE_EVAL_RUNNER_") or name in {
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENCODE_API_KEY",
            "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "OPENCODE_CONFIG_DIR",
        }:
            env.pop(name, None)
    for name in ("home", "config", "data", "state", "cache"):
        path = xdg / name
        path.mkdir(parents=True, exist_ok=True)
    env.update({
        "HOME": str(xdg / "home"),
        "XDG_CONFIG_HOME": str(xdg / "config"),
        "XDG_DATA_HOME": str(xdg / "data"),
        "XDG_STATE_HOME": str(xdg / "state"),
        "XDG_CACHE_HOME": str(xdg / "cache"),
    })
    if scenario == "redaction":
        env["OPENAI_API_KEY"] = SECRET
    return env


def run_scenario(image: str, scenario: str, output: Path) -> dict[str, Any]:
    with FixtureProvider(scenario) as provider, tempfile.TemporaryDirectory(prefix=f"runtime-evidence-{scenario}-") as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir()
        write_workspace(workspace, provider.port)
        prompt = root / "prompt.txt"
        prompt.write_text(f"Run the deterministic {scenario} fixture.", encoding="utf-8")
        result_path = root / "result.json"
        timeout = 2 if scenario == "timeout" else 30
        command = [
            os.environ.get("PYTHON", "python3"), str(ROOT / "bin" / "opencode-eval-runner"), "invoke",
            "--engine", "docker", "--network", "host", "--image", image,
            "--transport", "opencode", "--workspace", str(workspace), "--workspace-mode", "rw",
            "--model", "fixture/mock", "--agent", "general",
            "--config", str(workspace / "opencode.json"), "--prompt-file", str(prompt),
            "--output", str(result_path), "--timeout-seconds", str(timeout), "--container-timeout", "45",
        ]
        proc = subprocess.run(
            command, cwd=ROOT, env=clean_env(scenario, root / "xdg"),
            capture_output=True, text=True, timeout=60, check=False,
        )
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
        oracle = read_oracle(workspace / "runtime-evidence-oracle.jsonl")
        checks = VALIDATORS[scenario](result, oracle, provider.requests)
        report = {
            "scenario": scenario,
            "runner_exit_code": proc.returncode,
            "outcomes": scenario_outcomes(result),
            "checks": checks,
            "passed": all(checks.values()),
            "request_metadata": provider.requests,
            "oracle_metadata": [
                {k: v for k, v in item.items() if k not in {"input"}}
                for item in oracle
            ],
        }
        # Never copy the raw result into CI artifacts. In particular, a broken
        # redaction implementation must not turn the acceptance artifact into a
        # second credential sink.
        (output / f"{scenario}.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    version = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "opencode", args.image, "--version"],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout.strip()
    runtime_ok = version in {"2.0.23", "opencode v2.0.23"}

    reports = {}
    for scenario in VALIDATORS:
        reports[scenario] = run_scenario(args.image, scenario, args.output)
        print(f"{scenario}: {'PASS' if reports[scenario]['passed'] else 'FAIL'}", flush=True)

    summary = {
        "kind": "provider-free-runtime-evidence-acceptance",
        "version": 1,
        "image": args.image,
        "opencode_version": version,
        "stock_opencode_2_0_23": runtime_ok,
        "provider_inference": False,
        "cases": {name: report["passed"] for name, report in reports.items()},
        "passed": runtime_ok and all(report["passed"] for report in reports.values()),
        "notes": {
            "code_mode": "Exact inner finality may be complete or explicitly unsupported; silent skip/missing evidence fails.",
            "authority": "Workspace oracle records are comparison fixtures only and never evidence authority.",
            "outcomes": "Each case records product outcome, observation outcome, and evidence eligibility separately.",
        },
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
