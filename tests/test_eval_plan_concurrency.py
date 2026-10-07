from __future__ import annotations

import unittest

from runner.eval_plan import EvalPlanningError, build_run_plan, resolve_run_schedule
from runner.eval_types import EvalJob, NormalizedCase


def case(case_id: str, lane: str = "standard") -> NormalizedCase:
    return NormalizedCase(
        id=case_id,
        selectors=(case_id,),
        lane=lane,  # type: ignore[arg-type]
        project_data=None,
        metadata={},
    )


def job(case_id: str, lane: str, iteration: int = 1) -> EvalJob:
    normalized = case(case_id, lane)
    return EvalJob(case=normalized, iteration=iteration, label=case_id)


class EvalPlanConcurrencyTests(unittest.TestCase):
    def test_standard_defaults_to_sequential(self):
        jobs = [job("a", "standard"), job("b", "standard")]

        plan = resolve_run_schedule("run-1", jobs)

        self.assertEqual(plan.standard_parallelism, 1)
        self.assertEqual(plan.runtime_parallelism, 0)
        self.assertEqual([item.case.id for item in plan.jobs], ["a", "b"])

    def test_zero_standard_parallelism_means_full_parallel(self):
        jobs = [job("a", "standard"), job("b", "standard"), job("c", "standard")]

        plan = resolve_run_schedule("run-1", jobs, standard_parallelism=0)

        self.assertEqual(plan.standard_parallelism, 3)

    def test_standard_parallelism_is_capped_by_requested_limit_and_job_count(self):
        jobs = [job("a", "standard"), job("b", "standard"), job("c", "standard")]

        capped = resolve_run_schedule("run-1", jobs, standard_parallelism=2)
        oversized = resolve_run_schedule("run-1", jobs, standard_parallelism=20)

        self.assertEqual(capped.standard_parallelism, 2)
        self.assertEqual(oversized.standard_parallelism, 3)

    def test_runtime_defaults_to_serialization(self):
        jobs = [job("r1", "runtime"), job("r2", "runtime")]

        plan = resolve_run_schedule("run-1", jobs)

        self.assertEqual(plan.standard_parallelism, 0)
        self.assertEqual(plan.runtime_parallelism, 1)

    def test_runtime_parallelism_is_explicit_and_independently_capped(self):
        jobs = [job("r1", "runtime"), job("r2", "runtime"), job("r3", "runtime")]

        capped = resolve_run_schedule("run-1", jobs, runtime_parallelism=2)
        oversized = resolve_run_schedule("run-1", jobs, runtime_parallelism=20)

        self.assertEqual(capped.runtime_parallelism, 2)
        self.assertEqual(oversized.runtime_parallelism, 3)

    def test_mixed_jobs_keep_stable_order_with_standard_group_first(self):
        jobs = [
            job("r1", "runtime"),
            job("s1", "standard"),
            job("r2", "runtime"),
            job("s2", "standard"),
        ]

        plan = resolve_run_schedule(
            "run-1",
            jobs,
            standard_parallelism=0,
            runtime_parallelism=2,
        )

        self.assertEqual([item.case.id for item in plan.jobs], ["s1", "s2", "r1", "r2"])
        self.assertEqual(plan.standard_parallelism, 2)
        self.assertEqual(plan.runtime_parallelism, 2)

    def test_invalid_concurrency_values_are_rejected(self):
        jobs = [job("s1", "standard"), job("r1", "runtime")]

        for value in (-1, True, 1.5, "2"):
            with self.subTest(standard=value):
                with self.assertRaisesRegex(EvalPlanningError, "standard_parallelism"):
                    resolve_run_schedule(
                        "run-1", jobs, standard_parallelism=value  # type: ignore[arg-type]
                    )

        for value in (0, -1, False, 1.5, "2"):
            with self.subTest(runtime=value):
                with self.assertRaisesRegex(EvalPlanningError, "runtime_parallelism"):
                    resolve_run_schedule(
                        "run-1", jobs, runtime_parallelism=value  # type: ignore[arg-type]
                    )

    def test_resolved_plan_is_deterministic_for_same_inputs(self):
        jobs = [
            job("r1", "runtime"),
            job("s1", "standard"),
            job("s2", "standard", iteration=2),
        ]

        first = resolve_run_schedule(
            "fixed-run",
            jobs,
            standard_parallelism=0,
            runtime_parallelism=4,
        )
        second = resolve_run_schedule(
            "fixed-run",
            tuple(jobs),
            standard_parallelism=0,
            runtime_parallelism=4,
        )

        self.assertEqual(first, second)

    def test_invalid_lane_is_rejected(self):
        invalid = job("x", "other")

        with self.assertRaisesRegex(EvalPlanningError, "unsupported eval lane"):
            resolve_run_schedule("run-1", [invalid])

    def test_complete_planning_composes_selection_iterations_and_lanes(self):
        cases = (
            case("r1", "runtime"),
            case("s1", "standard"),
            case("s2", "standard"),
        )

        first = build_run_plan(
            "fixed-run",
            cases,
            select_all=True,
            iterations=2,
            standard_parallelism=0,
            runtime_parallelism=2,
        )
        second = build_run_plan(
            "fixed-run",
            cases,
            select_all=True,
            iterations=2,
            standard_parallelism=0,
            runtime_parallelism=2,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            [(item.case.id, item.iteration, item.label) for item in first.jobs],
            [
                ("s1", 1, "s1#1"),
                ("s1", 2, "s1#2"),
                ("s2", 1, "s2#1"),
                ("s2", 2, "s2#2"),
                ("r1", 1, "r1#1"),
                ("r1", 2, "r1#2"),
            ],
        )
        self.assertEqual(first.standard_parallelism, 4)
        self.assertEqual(first.runtime_parallelism, 2)

    def test_complete_planning_keeps_explicit_selection_safeguard(self):
        with self.assertRaisesRegex(EvalPlanningError, "explicit case selectors"):
            build_run_plan("run-1", (case("A"),))


if __name__ == "__main__":
    unittest.main()
