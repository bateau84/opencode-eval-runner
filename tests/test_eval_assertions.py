import pytest

from runner.eval_assertions import deterministic_checks
from runner.eval_types import AttemptRecord


def attempt(observations, *, text="", input_available=True):
    return AttemptRecord(
        attempt=1,
        started_at="2025-01-01T00:00:00Z",
        duration_seconds=0,
        host_exit_code=0,
        result={
            "text": text,
            "runtime_evidence": {"observations": observations},
        },
        failure=None,
    )


def obs(tool=None, arguments=None):
    return {
        "tool": {"state": "available", "value": tool} if tool is not None else {"state": "omitted", "reason": "capture"},
        "input": {"state": "available", "value": arguments or {}},
        "start_sequence": 1,
        "terminal_sequence": 2,
        "outcome": "success",
        "result": {"state": "available", "value": "done"},
    }


def test_tool_only_action_assertions_retain_individual_require_forbid_and_any_of():
    case = {
        "id": "a",
        "execution": "runtime",
        "prompt": "",
        "actions": {
            "requires": [{"tool": "read"}],
            "forbids": [{"tool": "write"}],
            "any_of": [[{"tool": "read"}, {"tool": "search"}]],
        },
    }

    checks = deterministic_checks(case, attempt([obs("read")]), "ready")

    assert [check.status for check in checks] == ["pass", "pass", "pass"]


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        (obs("other"), "fail"),
        ({"tool": {"state": "omitted", "reason": "capture"}}, "non-evidence"),
        ({"tool": {"state": "unsupported", "reason": "capture"}}, "non-evidence"),
    ],
)
def test_tool_only_required_action_distinguishes_absence_from_unknown(observation, expected):
    case = {"id": "a", "execution": "runtime", "prompt": "", "actions": {"requires": [{"tool": "read"}]}}

    check = deterministic_checks(case, attempt([observation]), "ready")[0]

    assert check.status == expected


def test_conclusive_forbidden_match_wins_over_an_uncertain_observation():
    case = {"id": "a", "execution": "runtime", "prompt": "", "actions": {"forbids": [{"tool": "write"}]}}

    check = deterministic_checks(case, attempt([obs("write"), {"tool": {"state": "omitted", "reason": "capture"}}]), "ready")[0]

    assert check.status == "fail"


def test_conclusive_required_action_match_wins_over_an_uncertain_observation():
    case = {"id": "a", "execution": "runtime", "prompt": "", "actions": {"requires": [{"tool": "read"}]}}

    check = deterministic_checks(case, attempt([obs("read"), {"tool": {"state": "omitted", "reason": "capture"}}]), "ready")[0]

    assert check.status == "pass"


def test_action_args_subset_alias_and_extra_observed_arguments():
    case = {"id": "a", "execution": "runtime", "prompt": "", "actions": {"requires": [{"tool": "read", "args": {"filePath": "a.md"}}]}}

    check = deterministic_checks(case, attempt([obs("read", {"path": "a.md", "mode": "ro"})]), "ready")[0]

    assert check.status == "pass"


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [({"path": "prefix-first-middle-last"}, "pass"), ({"path": "first", "other": "last"}, "fail")],
)
def test_contains_all_requires_substrings_in_one_selected_argument(arguments, expected):
    case = {"id": "a", "execution": "runtime", "prompt": "", "actions": {"requires": [{"tool": "read", "arg": "path", "contains_all": ["first", "last"]}]}}

    check = deterministic_checks(case, attempt([obs("read", arguments)]), "ready")[0]

    assert check.status == expected


def test_min_source_urls_counts_unique_exact_prompt_answer_intersection():
    url = "https://example.test/a"
    case = {"id": "a", "execution": "conversation-response", "prompt": f"Use {url} and {url}", "output": {"min_source_urls": 1}}

    check = deterministic_checks(case, attempt([], text=f"{url} {url}"), "ready")[0]

    assert check.status == "pass"
    assert check.metadata["observed"] == [url]


def test_tool_result_occurrence_and_after_preserve_call_order_and_result_value():
    earlier = obs("open", {"path": "a.md"})
    earlier["start_sequence"] = 1
    later_first = obs("read", {"path": "a.md"})
    later_first["start_sequence"] = 3
    later_first["result"] = {"state": "available", "value": "old"}
    later_second = obs("read", {"path": "a.md"})
    later_second["start_sequence"] = 5
    later_second["result"] = {"state": "available", "value": "expected content"}
    case = {
        "id": "a", "execution": "runtime", "prompt": "",
        "tool_results": {"requires": [{
            "tool": "read", "args": {"path": "a.md"}, "occurrence": 2,
            "after": {"tool": "open", "args": {"path": "a.md"}},
            "output_contains": "expected",
        }]},
    }

    check = deterministic_checks(case, attempt([earlier, later_first, later_second]), "ready")[0]

    assert check.status == "pass"
