from __future__ import annotations

import unittest

from runner.eval_plan import (
    EvalPlanningError,
    expand_jobs,
    list_case_ids,
    list_selectors,
    select_and_expand_jobs,
    select_cases,
    validate_iterations,
    validate_normalized_cases,
)
from runner.eval_types import NormalizedCase


def make_case(
    case_id: str,
    *aliases: str,
    lane: str = "standard",
) -> NormalizedCase:
    return NormalizedCase(
        id=case_id,
        selectors=(case_id, *aliases),
        lane=lane,  # type: ignore[arg-type]
        project_data=None,
        metadata={},
    )


class EvalPlanSelectionTests(unittest.TestCase):
    def test_one_case_one_iteration(self):
        case = make_case("CASE-1")

        jobs = select_and_expand_jobs(
            (case,), selectors=("CASE-1",), iterations=1
        )

        self.assertEqual(len(jobs), 1)
        self.assertIs(jobs[0].case, case)
        self.assertEqual(jobs[0].iteration, 1)
        self.assertEqual(jobs[0].label, "CASE-1")

    def test_n_cases_m_iterations_are_deterministic(self):
        cases = (make_case("A"), make_case("B"), make_case("C"))

        first = expand_jobs(cases, iterations=2)
        second = expand_jobs(cases, iterations=2)

        expected = [
            ("A", 1, "A#1"),
            ("A", 2, "A#2"),
            ("B", 1, "B#1"),
            ("B", 2, "B#2"),
            ("C", 1, "C#1"),
            ("C", 2, "C#2"),
        ]
        self.assertEqual(
            [(job.case.id, job.iteration, job.label) for job in first], expected
        )
        self.assertEqual(first, second)

    def test_selectors_and_aliases_preserve_suite_order(self):
        cases = (
            make_case("A", "smoke"),
            make_case("B", "runtime", "smoke"),
            make_case("C", "slow"),
        )

        selected = select_cases(cases, selectors=("smoke",))

        self.assertEqual([case.id for case in selected], ["A", "B"])
        self.assertEqual(list_case_ids(cases), ("A", "B", "C"))
        self.assertEqual(
            list_selectors(cases),
            ("A", "smoke", "B", "runtime", "C", "slow"),
        )

    def test_unknown_selector_is_rejected(self):
        with self.assertRaisesRegex(EvalPlanningError, "unknown selector"):
            select_cases((make_case("A"),), selectors=("missing",))

    def test_no_selection_is_rejected_for_live_planning(self):
        with self.assertRaisesRegex(EvalPlanningError, "explicit case selectors"):
            select_cases((make_case("A"),))

    def test_explicit_all_selects_every_case(self):
        cases = (make_case("A"), make_case("B"))
        self.assertEqual(select_cases(cases, select_all=True), cases)

    def test_duplicate_normalized_ids_are_rejected(self):
        with self.assertRaisesRegex(EvalPlanningError, "duplicate normalized case id"):
            validate_normalized_cases((make_case("A"), make_case("A", "other")))

    def test_canonical_id_must_be_selectable(self):
        invalid = NormalizedCase(
            id="A",
            selectors=("alias",),
            lane="standard",
            project_data=None,
            metadata={},
        )
        with self.assertRaisesRegex(EvalPlanningError, "canonical id"):
            validate_normalized_cases((invalid,))

    def test_invalid_iterations_are_rejected(self):
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(EvalPlanningError, "iterations"):
                    validate_iterations(value)  # type: ignore[arg-type]

    def test_single_iteration_labels_do_not_add_suffix(self):
        jobs = expand_jobs((make_case("A"), make_case("B")), iterations=1)
        self.assertEqual([job.label for job in jobs], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
