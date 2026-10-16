import json

import pytest

from runner.eval_input import InputContractError, load_evaluation_input


def test_loads_agent_suite_and_preserves_source_identity(tmp_path):
    source = tmp_path / "suite.json"
    payload = {
        "version": 1,
        "name": "suite",
        "default": False,
        "cases": [
            {
                "id": "case-a",
                "agent": "reviewer",
                "execution": "runtime",
                "requirements": ["BR-1"],
                "prompt": "Do the task",
                "trap": "Do not leak",
                "expectations": ["One", "Two"],
                "must_not": ["Leak"],
                "actions": {"requires": [{"tool": "read"}]},
            }
        ],
    }
    source.write_text(json.dumps(payload))

    result = load_evaluation_input(source, family="agent-runtime")

    assert result.family == "agent-runtime"
    assert result.contract == "agent-runtime/v1"
    assert result.cases[0].case_id == "case-a"
    assert result.cases[0].authored == payload["cases"][0]
    assert result.sha256 == __import__("hashlib").sha256(source.read_bytes()).hexdigest()


def test_loads_skill_array_and_assigns_stable_identity(tmp_path):
    source = tmp_path / "skill.json"
    source.write_text(json.dumps([{
        "id": 7,
        "name": "example",
        "prompt": "Do it",
        "expectations": ["Works"],
        "must_not": ["Leaks"],
        "trap": "  hidden trap  ",
    }]))

    result = load_evaluation_input(source, family="skill", skill="helper")

    case = result.cases[0]
    assert case.case_id == "skill:helper:7"
    assert case.source_id == 7
    assert case.authored_id == 7
    assert case.source_index == 1
    assert case.skill == "helper"
    assert case.negative_expectations == ("Leaks",)
    assert case.trap == "hidden trap"


@pytest.mark.parametrize(
    ("wrapper", "expected_skill"),
    [
        ({"skill": "helper", "cases": [{"prompt": "do", "expectations": ["yes"]}]}, "helper"),
        ({"skill_name": "helper", "evals": [{"id": "authored", "prompt": "do", "expectations": ["yes"]}]}, "helper"),
    ],
)
def test_loads_both_skill_wrappers_and_negative_alias(tmp_path, wrapper, expected_skill):
    wrapper[next(iter(wrapper.keys() - {"skill", "skill_name"}))][0]["must_not"] = ["no"]
    source = tmp_path / "skill.json"
    source.write_text(json.dumps(wrapper))

    result = load_evaluation_input(source, family="skill")

    assert result.skill == expected_skill
    assert result.cases[0].negative_expectations == ("no",)
    assert result.cases[0].case_id.startswith("skill:helper:")


@pytest.mark.parametrize("raw", [
    '{"version":1,"version":1,"name":"s","cases":[]}',
    '{"version":1,"name":"s","cases":[],"extra":true}',
    '{"version":1,"name":"s","cases":[],"x":NaN}',
])
def test_rejects_duplicate_keys_unknown_fields_and_nonfinite_numbers(tmp_path, raw):
    source = tmp_path / "input.json"
    source.write_text(raw)

    with pytest.raises(InputContractError):
        load_evaluation_input(source, family="agent-runtime")


def test_rejects_unsafe_fixture_path_before_execution(tmp_path):
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1,
        "name": "suite",
        "cases": [{
            "id": "case-a", "agent": "reviewer", "execution": "runtime",
            "requirements": ["BR-1"], "prompt": "Do", "trap": "Trap",
            "expectations": ["Works", "Fine"], "must_not": ["Leak"],
            "fixture_files": [{"path": "../outside", "content": "x"}],
        }],
    }))

    with pytest.raises(InputContractError, match="unsafe fixture"):
        load_evaluation_input(source, family="agent-runtime")


@pytest.mark.parametrize(
    "payload",
    [
        {"skill": "helper", "cases": [], "evals": []},
        {"skill": "helper", "cases": [{"prompt": "do", "expectations": ["yes"], "extra": 1}]},
        {"skill": "helper", "cases": [{"id": 1, "prompt": "do", "expectations": ["yes"]}, {"id": "1", "prompt": "do", "expectations": ["yes"]}]},
    ],
)
def test_rejects_ambiguous_or_unknown_skill_input(tmp_path, payload):
    source = tmp_path / "skill.json"
    source.write_text(json.dumps(payload))

    with pytest.raises(InputContractError):
        load_evaluation_input(source, family="skill")


def test_rejects_malformed_execution_type_as_contract_error(tmp_path):
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({"version": 1, "name": "suite", "cases": [{
        "id": "case-a", "agent": "reviewer", "execution": [],
        "requirements": ["BR-1"], "prompt": "Do", "trap": "Trap",
        "expectations": ["Works", "Fine"], "must_not": ["Leak"],
    }]}))

    with pytest.raises(InputContractError, match="execution"):
        load_evaluation_input(source, family="agent-runtime")


def test_rejects_tool_result_assertion_without_a_result_test(tmp_path):
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1, "name": "suite", "cases": [{
            "id": "case-a", "agent": "reviewer", "execution": "runtime",
            "requirements": ["BR-1"], "prompt": "Do", "trap": "Trap",
            "expectations": ["Works", "Fine"], "must_not": ["Leak"],
            "tool_results": {"requires": [{"tool": "read", "args": {"path": "a.md"}}]},
        }],
    }))

    with pytest.raises(InputContractError, match="result test"):
        load_evaluation_input(source, family="agent-runtime")
