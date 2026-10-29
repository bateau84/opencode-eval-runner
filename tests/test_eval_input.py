import json

import pytest

from runner.eval_input import (
    InputContractError,
    load_evaluation_input,
    load_evaluation_inputs,
)


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


def test_combined_skill_inputs_bind_each_occurrence_and_encode_composite_ids(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"skill": "same", "cases": [{"id": "a,b", "prompt": "do", "expectations": ["yes"]}]}))
    second.write_text(json.dumps({"skill_name": "same", "evals": [{"id": "c", "prompt": "do", "expectations": ["yes"]}]}))

    result = load_evaluation_inputs([first, second], family="skill", skills=["same", "same"])

    assert [case.source_input for case in result.cases] == [1, 2]
    assert [case.case_id for case in result.cases] == [
        "sk1_BABzAGEAbQBlAwBhACwAYg", "sk1_BABzAGEAbQBlAQBj"
    ]
    assert [item.source_path for item in result.inputs] == [first, second]
    assert result.inputs[0].sha256 != result.inputs[1].sha256


def test_combined_skill_inputs_reject_duplicate_pairs_and_binding_mismatch(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    payload = {"skill": "same", "cases": [{"id": "duplicate", "prompt": "do", "expectations": ["yes"]}]}
    first.write_text(json.dumps(payload))
    second.write_text(json.dumps(payload))

    with pytest.raises(InputContractError, match="duplicate composite"):
        load_evaluation_inputs([first, second], family="skill", skills=["same", "same"])
    with pytest.raises(InputContractError, match="does not match"):
        load_evaluation_inputs([first, second], family="skill", skills=["same", "other"])


def test_combined_raw_arrays_use_each_explicit_binding(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    case = {"id": "same", "prompt": "do", "expectations": ["yes"]}
    first.write_text(json.dumps([case]))
    second.write_text(json.dumps([case]))

    result = load_evaluation_inputs([first, second], family="skill", skills=["alpha", "beta"])

    assert [(case.skill, case.source_input) for case in result.cases] == [("alpha", 1), ("beta", 2)]
    assert result.cases[0].case_id != result.cases[1].case_id
