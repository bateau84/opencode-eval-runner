"""Agent/runtime deterministic assertions over authoritative runtime evidence."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from runner.eval_types import AttemptRecord, CheckOutcome

_ALIASES = {
    "skill": {"name": ("name", "id"), "id": ("id", "name")},
    "read": {"filePath": ("filePath", "path"), "path": ("path", "filePath")},
}
_MISSING = object()


def normalize_tool(value: str) -> str:
    value = re.sub(r"^mcp__([^_]+)__(.+)$", r"\1_\2", value)
    value = re.sub(r"^loom\.code\.([A-Za-z0-9_-]+)$", r"loom_\1", value)
    return value.replace(".", "_")


def _field(raw: object) -> tuple[str, Any, str]:
    if not isinstance(raw, Mapping):
        return "invalid", None, "field is not an object"
    state = raw.get("state")
    if state == "available":
        if set(raw) != {"state", "value"}:
            return "invalid", None, "available field has invalid shape"
        try:
            json.dumps(raw["value"], ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            return "invalid", None, "available field is not strict JSON"
        return "ready", raw["value"], ""
    if state in {"redacted", "omitted", "unsupported"}:
        if set(raw) != {"state", "reason"} or not isinstance(raw.get("reason"), str):
            return "invalid", None, f"{state} field has invalid shape"
        return ("unsupported" if state == "unsupported" else "incomplete"), None, f"field_{state}:{raw['reason']}"
    return "invalid", None, "field has invalid state"


def _observations(target: AttemptRecord) -> tuple[list[Mapping[str, Any]] | None, str]:
    if not isinstance(target.result, Mapping):
        return None, "target result unavailable"
    evidence = target.result.get("runtime_evidence")
    if not isinstance(evidence, Mapping):
        return None, "authoritative runtime_evidence/v1 unavailable"
    observations = evidence.get("observations")
    if not isinstance(observations, list) or not all(isinstance(v, Mapping) for v in observations):
        return None, "runtime_evidence observations invalid"
    return list(observations), ""


def _target_text(target: AttemptRecord) -> tuple[str | None, str]:
    if not isinstance(target.result, Mapping) or not isinstance(target.result.get("text"), str):
        return None, "complete assistant text unavailable"
    return str(target.result["text"]), ""


def _outcome(name: str, status: str, reason: str, family: str, assertion: object = None, observed: Any = None) -> CheckOutcome:
    metadata: dict[str, Any] = {"family": family}
    if assertion is not None:
        metadata["assertion"] = assertion
    if observed is not None:
        metadata["observed"] = observed
    return CheckOutcome(name, status, reason, metadata)


def _normalized_observations(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for observation in observations:
        item = dict(observation)
        state, tool, _ = _field(observation.get("tool"))
        if state == "ready" and isinstance(tool, str):
            item["tool"] = {"state": "available", "value": normalize_tool(tool)}
        normalized.append(item)
    return normalized


def _tool_state(observation: Mapping[str, Any], expected: str) -> tuple[bool | None, str]:
    state, actual, reason = _field(observation.get("tool"))
    if state != "ready":
        return None, reason
    if not isinstance(actual, str):
        return None, "tool identity is not a string"
    return normalize_tool(actual) == normalize_tool(expected), ""


def _arg(tool: str, args: Mapping[str, Any], dotted: str) -> Any:
    value: Any = args
    for index, part in enumerate(dotted.split(".")):
        if not isinstance(value, Mapping):
            return _MISSING
        names = (part,)
        if index == 0:
            names = _ALIASES.get(normalize_tool(tool), {}).get(part, names)
        for name in names:
            if name in value:
                value = value[name]
                break
        else:
            return _MISSING
    return value


def _equal(actual: Any, expected: Any) -> bool:
    if actual is _MISSING:
        return False
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is bool and type(expected) is bool and actual == expected
    return actual == expected


def _args_match(tool: str, args: Mapping[str, Any], assertion: Mapping[str, Any]) -> bool:
    if "args" in assertion:
        expected = assertion["args"]
        return isinstance(expected, Mapping) and all(_equal(_arg(tool, args, key), value) for key, value in expected.items())
    if "arg" not in assertion:
        return True
    value = _arg(tool, args, assertion["arg"])
    if "equals" in assertion:
        return _equal(value, assertion["equals"])
    if "ends_with" in assertion:
        return isinstance(value, str) and value.endswith(assertion["ends_with"])
    if "contains" in assertion:
        return isinstance(value, str) and assertion["contains"] in value
    if "contains_all" in assertion:
        return isinstance(value, str) and all(part in value for part in assertion["contains_all"])
    return False


def _call_state(observation: Mapping[str, Any], assertion: Mapping[str, Any]) -> tuple[bool | None, str]:
    matched, reason = _tool_state(observation, assertion["tool"])
    if matched is not True or ("args" not in assertion and "arg" not in assertion):
        return matched, reason
    state, args, reason = _field(observation.get("input"))
    if state != "ready":
        return None, reason
    if not isinstance(args, Mapping):
        return None, "tool input is not an object"
    return _args_match(assertion["tool"], args, assertion), ""


def _existence(observations: Sequence[Mapping[str, Any]], assertion: Any, *, forbidden: bool, family: str, name: str) -> CheckOutcome:
    if family == "tools":
        states = [_tool_state(obs, assertion) for obs in observations]
    else:
        states = [_call_state(obs, assertion) for obs in observations]
    matched = any(state is True for state, _ in states)
    unknown = next((reason for state, reason in states if state is None), None)
    status = ("fail" if matched else "non-evidence" if unknown else "pass") if forbidden else ("pass" if matched else "non-evidence" if unknown else "fail")
    return _outcome(name, status, ("forbidden" if forbidden else "required") + f" {family[:-1]} {'observed' if matched else 'not observed'}", family, assertion, _normalized_observations(observations))


def _any_of(observations: Sequence[Mapping[str, Any]], group: list[Mapping[str, Any]], name: str) -> CheckOutcome:
    states = [_call_state(obs, assertion) for assertion in group for obs in observations]
    matched = any(state is True for state, _ in states)
    unknown = next((reason for state, reason in states if state is None), None)
    status = "pass" if matched else "non-evidence" if unknown else "fail"
    return _outcome(name, status, "action alternative observed" if matched else "cannot establish action alternatives" if unknown else "no required action alternative observed", "actions", group, _normalized_observations(observations))


def _before(candidate: Mapping[str, Any], earlier: Mapping[str, Any]) -> bool:
    a, b = earlier.get("start_sequence"), candidate.get("start_sequence")
    return type(a) is int and type(b) is int and a < b


def _path(value: Any, dotted: str) -> tuple[bool, Any]:
    for part in dotted.split("."):
        if isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, Mapping) and part in value:
            value = value[part]
        else:
            return False, None
    return True, value


def _result_candidates(value: Any) -> list[Any]:
    result = [value]
    if isinstance(value, str):
        try:
            result.append(json.loads(value))
        except (ValueError, TypeError, RecursionError):
            pass
    for item in tuple(result):
        if isinstance(item, Mapping):
            for key in ("output", "content", "result"):
                if key in item:
                    result.append(item[key])
                    if isinstance(item[key], str):
                        try:
                            result.append(json.loads(item[key]))
                        except (ValueError, TypeError, RecursionError):
                            pass
    return result


def _result_value_matches(value: Any, assertion: Mapping[str, Any]) -> bool:
    if "json_path" in assertion:
        for candidate in _result_candidates(value):
            found, actual = _path(candidate, assertion["json_path"])
            if found:
                return _equal(actual, assertion["equals"])
        return False
    rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return ("output_contains" not in assertion or assertion["output_contains"] in rendered) and all(part in rendered for part in assertion.get("output_contains_all", []))


def _result_match(observations: Sequence[Mapping[str, Any]], assertion: Mapping[str, Any]) -> tuple[bool | None, str]:
    matching: list[Mapping[str, Any]] = []
    unknown = None
    for observation in observations:
        state, reason = _call_state(observation, assertion)
        if state is True:
            matching.append(observation)
        elif state is None and unknown is None:
            unknown = reason
    occurrence = assertion.get("occurrence")
    if occurrence is not None:
        if unknown:
            return None, "occurrence ambiguous; " + unknown
        matching = [matching[occurrence - 1]] if len(matching) >= occurrence else []
    if "after" in assertion:
        selected = []
        for candidate in matching:
            preceding = [o for o in observations if _before(candidate, o)]
            states = [_call_state(o, assertion["after"]) for o in preceding]
            if any(s is True for s, _ in states):
                selected.append(candidate)
            elif any(s is None for s, _ in states):
                unknown = unknown or next(r for s, r in states if s is None)
        matching = selected
    if not matching:
        return (None, unknown) if unknown else (False, "matching tool call not observed")
    for obs in matching:
        outcome = obs.get("outcome")
        if outcome not in {"success", "error"}:
            unknown = unknown or "terminal outcome missing or invalid"
            continue
        if "status" in assertion and assertion["status"] not in {outcome, "completed" if outcome == "success" else "error"}:
            continue
        field_name = "result" if outcome == "success" else "error"
        state, value, reason = _field(obs.get(field_name))
        if state != "ready":
            unknown = unknown or reason
            continue
        if _result_value_matches(value, assertion):
            return True, ""
    return (None, unknown) if unknown else (False, "tool result did not match")


def _tool_result(observations: Sequence[Mapping[str, Any]], assertion: Mapping[str, Any], *, forbidden: bool, name: str) -> CheckOutcome:
    state, reason = _result_match(observations, assertion)
    status = ("fail" if state is True else "non-evidence" if state is None else "pass") if forbidden else ("pass" if state is True else "non-evidence" if state is None else "fail")
    return _outcome(name, status, reason or ("forbidden tool result observed" if forbidden else "required tool result observed"), "tool_results", assertion, _normalized_observations(observations))


def _urls(text: str) -> set[str]:
    return {value.rstrip(".,;:") for value in re.findall(r'https?://[^\s<>"\[\]()]+', text)}


def source_urls_in_answer(prompt: str, text: str) -> list[str]:
    """Return unique exact URL tokens shared by the prompt and final answer."""
    return sorted(_urls(prompt) & _urls(text))


def deterministic_checks(case: Mapping[str, Any], target: AttemptRecord, readiness: str) -> tuple[CheckOutcome, ...]:
    """Evaluate authored assertions; evidence readiness is handled separately."""
    families = any(key in case for key in ("tools", "actions", "tool_results")) or case["execution"] == "runtime"
    observations, error = _observations(target) if families else ([], "")
    if observations is None:
        return (CheckOutcome("runtime_evidence", "non-evidence", error, {"family": "runtime_evidence"}),)
    checks: list[CheckOutcome] = []
    tools = case.get("tools", {})
    for i, tool in enumerate(tools.get("requires", [])):
        checks.append(_existence(observations, tool, forbidden=False, family="tools", name=f"tools.requires[{i}]"))
    for i, tool in enumerate(tools.get("forbids", [])):
        checks.append(_existence(observations, tool, forbidden=True, family="tools", name=f"tools.forbids[{i}]"))
    actions = case.get("actions", {})
    for key, forbidden in (("requires", False), ("forbids", True)):
        for i, assertion in enumerate(actions.get(key, [])):
            checks.append(_existence(observations, assertion, forbidden=forbidden, family="actions", name=f"actions.{key}[{i}]"))
    for i, group in enumerate(actions.get("any_of", [])):
        checks.append(_any_of(observations, group, f"actions.any_of[{i}]"))
    results = case.get("tool_results", {})
    for key, forbidden in (("requires", False), ("forbids", True)):
        for i, assertion in enumerate(results.get(key, [])):
            checks.append(_tool_result(observations, assertion, forbidden=forbidden, name=f"tool_results.{key}[{i}]"))
    output = case.get("output", {})
    if output:
        text, text_error = _target_text(target)
        if text is None:
            return tuple(checks + [CheckOutcome("output.text", "non-evidence", text_error, {"family": "output"})])
        for i, value in enumerate(output.get("contains", [])):
            checks.append(CheckOutcome(f"output.contains[{i}]", "pass" if value in text else "fail", "literal substring presence", {"family": "output", "assertion": value, "observed": text}))
        for i, value in enumerate(output.get("forbids", [])):
            checks.append(CheckOutcome(f"output.forbids[{i}]", "fail" if value in text else "pass", "literal substring absence", {"family": "output", "assertion": value, "observed": text}))
        minimum = output.get("min_source_urls")
        if minimum is not None:
            matched_urls = source_urls_in_answer(case["prompt"], text)
            count = len(matched_urls)
            checks.append(CheckOutcome("output.min_source_urls", "pass" if count >= minimum else "fail", f"prompt/answer URL intersection: {count}/{minimum}", {"family": "output", "assertion": minimum, "observed": matched_urls}))
    del readiness
    return tuple(checks)
