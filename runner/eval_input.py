"""Strict host-side readers for the built-in evaluation input contracts."""
from __future__ import annotations

import hashlib
import json
import math
import ntpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

Family = Literal["agent-runtime", "skill"]
JSONScalar = None | bool | int | float | str


class InputContractError(ValueError):
    """An input document does not conform to its explicitly selected family."""


@dataclass(frozen=True)
class InputCase:
    case_id: str
    source_index: int
    authored: dict[str, Any]
    skill: str | None = None
    source_id: str | int | None = None
    authored_id: str | int | None = None
    display_name: str | None = None
    negative_expectations: tuple[str, ...] = ()
    trap: str | None = None


@dataclass(frozen=True)
class EvaluationInput:
    family: Family
    contract: str
    sha256: str
    source_path: Path
    suite_name: str | None
    suite_default: bool | None
    skill: str | None
    cases: tuple[InputCase, ...]


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise InputContractError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise InputContractError(f"non-JSON numeric constant: {value}")


def _decode(path: Path) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputContractError(f"cannot read UTF-8 input {path}: {exc}") from exc
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except InputContractError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise InputContractError(f"invalid JSON input: {exc}") from exc
    return value, hashlib.sha256(raw).hexdigest()


def _object(value: Any, label: str, allowed: set[str], required: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputContractError(f"{label} must be an object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise InputContractError(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")
    if missing:
        raise InputContractError(f"{label} missing field(s): {', '.join(sorted(missing))}")
    return value


def _string(value: Any, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise InputContractError(f"{label} must be a {'non-empty ' if nonempty else ''}string")
    return value


def _strings(value: Any, label: str, *, minimum: int = 0, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise InputContractError(f"{label} must be an array with at least {minimum} item(s)")
    result = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{label}[{index}]", nonempty=not allow_empty))
    return tuple(result)


def _scalar(value: Any, label: str) -> JSONScalar:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise InputContractError(f"{label} must be a finite JSON scalar")


def _scalar_map(value: Any, label: str, *, nonempty: bool) -> dict[str, JSONScalar]:
    if not isinstance(value, dict) or (nonempty and not value):
        raise InputContractError(f"{label} must be a {'non-empty ' if nonempty else ''}object")
    result: dict[str, JSONScalar] = {}
    for key, item in value.items():
        if not key.strip():
            raise InputContractError(f"{label} argument names must not be empty")
        result[key] = _scalar(item, f"{label}.{key}")
    return result


def _fixture_files(value: Any, label: str) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        raise InputContractError(f"{label} must be an array")
    seen: set[str] = set()
    fixtures: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        item = _object(raw, f"{label}[{index}]", {"path", "content"}, {"path", "content"})
        path = _string(item["path"], f"{label}[{index}].path")
        posix = PurePosixPath(path)
        if (posix.is_absolute() or ntpath.isabs(path) or ".." in posix.parts
                or "\\" in path or "\x00" in path or not posix.parts):
            raise InputContractError(f"unsafe fixture path: {path!r}")
        normalized = posix.as_posix()
        if normalized in seen:
            raise InputContractError(f"duplicate fixture destination: {normalized!r}")
        seen.add(normalized)
        fixtures.append({"path": path, "content": _string(item["content"], f"{label}[{index}].content", nonempty=False)})
    return tuple(fixtures)


def _validate_action(value: Any, label: str) -> None:
    item = _object(value, label,
                   {"tool", "arg", "equals", "args", "ends_with", "contains", "contains_all"},
                   {"tool"})
    _string(item["tool"], f"{label}.tool")
    comparator_keys = {"equals", "ends_with", "contains", "contains_all"} & set(item)
    if "args" in item:
        if "arg" in item or comparator_keys:
            raise InputContractError(f"{label}: args cannot be combined with arg/comparators")
        _scalar_map(item["args"], f"{label}.args", nonempty=True)
    elif "arg" in item:
        _string(item["arg"], f"{label}.arg")
        if len(comparator_keys) != 1:
            raise InputContractError(f"{label}: arg requires exactly one comparator")
        if "equals" in item:
            _scalar(item["equals"], f"{label}.equals")
        elif "contains_all" in item:
            _strings(item["contains_all"], f"{label}.contains_all", minimum=1)
        else:
            _string(item[next(iter(comparator_keys))], f"{label}.{next(iter(comparator_keys))}", nonempty=False)
    elif comparator_keys:
        raise InputContractError(f"{label}: comparators require arg")


def _validate_actions(value: Any, label: str) -> None:
    item = _object(value, label, {"requires", "forbids", "any_of"})
    for key in ("requires", "forbids"):
        if key in item:
            if not isinstance(item[key], list):
                raise InputContractError(f"{label}.{key} must be an array")
            for i, assertion in enumerate(item[key]):
                _validate_action(assertion, f"{label}.{key}[{i}]")
    if "any_of" in item:
        groups = item["any_of"]
        if not isinstance(groups, list) or not groups:
            raise InputContractError(f"{label}.any_of must be a non-empty array")
        for i, group in enumerate(groups):
            if not isinstance(group, list) or not group:
                raise InputContractError(f"{label}.any_of[{i}] must be a non-empty array")
            for j, assertion in enumerate(group):
                _validate_action(assertion, f"{label}.any_of[{i}][{j}]")


def _validate_tool_results(value: Any, label: str) -> None:
    item = _object(value, label, {"requires", "forbids"})
    for key in ("requires", "forbids"):
        if key not in item:
            continue
        if not isinstance(item[key], list):
            raise InputContractError(f"{label}.{key} must be an array")
        for index, raw in enumerate(item[key]):
            name = f"{label}.{key}[{index}]"
            assertion = _object(raw, name, {"tool", "args", "occurrence", "after", "status", "output_contains", "output_contains_all", "json_path", "equals"}, {"tool", "args"})
            _string(assertion["tool"], f"{name}.tool")
            _scalar_map(assertion["args"], f"{name}.args", nonempty=True)
            if "occurrence" in assertion and (type(assertion["occurrence"]) is not int or assertion["occurrence"] < 1):
                raise InputContractError(f"{name}.occurrence must be an integer >= 1")
            if "after" in assertion:
                after = _object(assertion["after"], f"{name}.after", {"tool", "args"}, {"tool", "args"})
                _string(after["tool"], f"{name}.after.tool")
                _scalar_map(after["args"], f"{name}.after.args", nonempty=True)
            if "status" in assertion:
                _string(assertion["status"], f"{name}.status")
            if "output_contains" in assertion:
                _string(assertion["output_contains"], f"{name}.output_contains")
            if "output_contains_all" in assertion:
                _strings(assertion["output_contains_all"], f"{name}.output_contains_all", minimum=1)
            has_path, has_equals = "json_path" in assertion, "equals" in assertion
            if has_path != has_equals:
                raise InputContractError(f"{name}: json_path and equals must be supplied together")
            if has_path:
                dotted = _string(assertion["json_path"], f"{name}.json_path")
                if any(not part for part in dotted.split(".")):
                    raise InputContractError(f"{name}.json_path must be a non-empty dotted path")
                _scalar(assertion["equals"], f"{name}.equals")
            if not any(k in assertion for k in ("output_contains", "output_contains_all", "json_path")):
                raise InputContractError(f"{name} must include at least one result test")


def _agent_case(raw: Any, index: int, ids: set[str]) -> InputCase:
    name = f"case[{index}]"
    allowed = {"id", "default", "agent", "skill", "execution", "target_timeout_seconds", "requirements", "prompt", "trap", "expectations", "must_not", "tools", "actions", "tool_results", "output", "fixture_files"}
    item = _object(raw, name, allowed, {"id", "agent", "execution", "requirements", "prompt", "trap", "expectations", "must_not"})
    case_id = _string(item["id"], f"{name}.id")
    if case_id in ids:
        raise InputContractError(f"duplicate case id: {case_id!r}")
    ids.add(case_id)
    _string(item["agent"], f"{name}.agent")
    if "skill" in item:
        _string(item["skill"], f"{name}.skill")
    if not isinstance(item["execution"], str) or item["execution"] not in {
        "runtime", "role-decision", "conversation-response"
    }:
        raise InputContractError(f"{name}.execution is unsupported")
    if "skill" in item and item["execution"] != "runtime":
        raise InputContractError(f"{name}: skill requires runtime execution")
    if "target_timeout_seconds" in item and (type(item["target_timeout_seconds"]) is not int or not 30 <= item["target_timeout_seconds"] <= 600):
        raise InputContractError(f"{name}.target_timeout_seconds must be an integer in [30, 600]")
    for field in ("default",):
        if field in item and type(item[field]) is not bool:
            raise InputContractError(f"{name}.{field} must be a boolean")
    _strings(item["requirements"], f"{name}.requirements", minimum=1)
    _string(item["prompt"], f"{name}.prompt")
    _string(item["trap"], f"{name}.trap")
    _strings(item["expectations"], f"{name}.expectations", minimum=2)
    _strings(item["must_not"], f"{name}.must_not", minimum=1)
    for key in ("tools", "actions", "tool_results"):
        if key in item and item["execution"] != "runtime":
            raise InputContractError(f"{name}.{key} requires runtime execution")
    if "tools" in item:
        tools = _object(item["tools"], f"{name}.tools", {"requires", "forbids"})
        for key, values in tools.items():
            _strings(values, f"{name}.tools.{key}")
    if "actions" in item:
        _validate_actions(item["actions"], f"{name}.actions")
    if "tool_results" in item:
        _validate_tool_results(item["tool_results"], f"{name}.tool_results")
    if "output" in item:
        output = _object(item["output"], f"{name}.output", {"min_source_urls", "contains", "forbids"})
        if "min_source_urls" in output and (type(output["min_source_urls"]) is not int or not 1 <= output["min_source_urls"] <= 100):
            raise InputContractError(f"{name}.output.min_source_urls must be an integer in [1, 100]")
        for key in ("contains", "forbids"):
            if key in output:
                _strings(output[key], f"{name}.output.{key}")
    fixtures = _fixture_files(item["fixture_files"], f"{name}.fixture_files") if "fixture_files" in item else ()
    normalized = dict(item)
    if fixtures:
        normalized["fixture_files"] = list(fixtures)
    return InputCase(case_id, index, normalized)


def _agent_input(raw: Any) -> tuple[str, bool | None, tuple[InputCase, ...]]:
    suite = _object(raw, "agent-runtime suite", {"version", "name", "default", "cases"}, {"version", "name", "cases"})
    if type(suite["version"]) is not int or suite["version"] != 1:
        raise InputContractError("agent-runtime suite version must be integer 1")
    name = _string(suite["name"], "suite.name")
    if "default" in suite and type(suite["default"]) is not bool:
        raise InputContractError("suite.default must be a boolean")
    cases = suite["cases"]
    if not isinstance(cases, list) or not cases:
        raise InputContractError("suite.cases must be a non-empty array")
    ids: set[str] = set()
    return name, suite.get("default"), tuple(_agent_case(case, i + 1, ids) for i, case in enumerate(cases))


def _skill_input(raw: Any, supplied_skill: str | None) -> tuple[str, tuple[InputCase, ...]]:
    if isinstance(raw, list):
        skill = supplied_skill
        cases = raw
        if not skill or not skill.strip():
            raise InputContractError("--skill NAME is required for a top-level skill array")
    else:
        wrapper = _object(raw, "skill input", {"skill", "cases", "skill_name", "evals"})
        if ("skill" in wrapper) == ("skill_name" in wrapper):
            raise InputContractError("skill input must use exactly one skill/cases or skill_name/evals wrapper")
        if "skill" in wrapper:
            if "evals" in wrapper:
                raise InputContractError("skill/cases wrapper cannot contain evals")
            skill = _string(wrapper["skill"], "skill")
            if "cases" not in wrapper:
                raise InputContractError("skill/cases wrapper requires cases")
            cases = wrapper["cases"]
        else:
            if "cases" in wrapper:
                raise InputContractError("skill_name/evals wrapper cannot contain cases")
            skill = _string(wrapper["skill_name"], "skill_name")
            if "evals" not in wrapper:
                raise InputContractError("skill_name/evals wrapper requires evals")
            cases = wrapper["evals"]
        if supplied_skill is not None and supplied_skill != skill:
            raise InputContractError("--skill does not match wrapper skill identity")
    if not isinstance(cases, list) or not cases:
        raise InputContractError("skill cases must be a non-empty array")
    result: list[InputCase] = []
    identities: set[str] = set()
    for i, raw_case in enumerate(cases, 1):
        label = f"skill case[{i}]"
        item = _object(raw_case, label, {"id", "name", "prompt", "expectations", "negative_expectations", "must_not", "trap", "fixture_files"}, {"prompt", "expectations"})
        authored_id = item.get("id")
        if "id" in item and (isinstance(authored_id, bool) or not isinstance(authored_id, (str, int)) or (isinstance(authored_id, str) and not authored_id.strip())):
            raise InputContractError(f"{label}.id must be a non-empty string or integer")
        source_id: str | int = authored_id if authored_id is not None else i
        source_id_text = str(source_id)
        case_id = f"skill:{skill}:{source_id_text}"
        if case_id in identities:
            raise InputContractError(f"duplicate canonical skill case id: {case_id!r}")
        identities.add(case_id)
        display_name = _string(item["name"], f"{label}.name") if "name" in item else None
        prompt = _string(item["prompt"], f"{label}.prompt")
        expectations = _strings(item["expectations"], f"{label}.expectations", minimum=1)
        if "negative_expectations" in item and "must_not" in item:
            left = _strings(item["negative_expectations"], f"{label}.negative_expectations")
            right = _strings(item["must_not"], f"{label}.must_not")
            if left != right:
                raise InputContractError(f"{label}: negative_expectations and must_not differ")
            negative = left
        elif "negative_expectations" in item:
            negative = _strings(item["negative_expectations"], f"{label}.negative_expectations")
        else:
            negative = _strings(item.get("must_not", []), f"{label}.must_not")
        trap_value = item.get("trap")
        if trap_value is not None and not isinstance(trap_value, str):
            raise InputContractError(f"{label}.trap must be a string or null")
        trap = trap_value.strip() if isinstance(trap_value, str) and trap_value.strip() else None
        fixtures = _fixture_files(item["fixture_files"], f"{label}.fixture_files") if "fixture_files" in item else ()
        normalized = dict(item)
        normalized["prompt"] = prompt
        normalized["expectations"] = list(expectations)
        normalized["negative_expectations"] = list(negative)
        normalized["trap"] = trap
        normalized["fixture_files"] = list(fixtures)
        result.append(InputCase(case_id, i, normalized, skill=skill, source_id=source_id,
                                authored_id=authored_id, display_name=display_name,
                                negative_expectations=negative, trap=trap))
    return skill, tuple(result)


def load_evaluation_input(path: str | Path, *, family: Family, skill: str | None = None) -> EvaluationInput:
    """Read and validate the complete explicitly selected input family."""
    if not isinstance(family, str) or family not in {"agent-runtime", "skill"}:
        raise InputContractError(f"unsupported input family: {family!r}")
    source = Path(path)
    raw, digest = _decode(source)
    if family == "agent-runtime":
        if skill is not None:
            raise InputContractError("--skill is only valid with --family skill")
        name, default, cases = _agent_input(raw)
        return EvaluationInput(family, "agent-runtime/v1", digest, source, name, default, None, cases)
    skill_name, cases = _skill_input(raw, skill)
    return EvaluationInput(family, "skill-cases/v1", digest, source, None, None, skill_name, cases)
