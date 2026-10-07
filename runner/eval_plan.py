"""Provider-free run planning for the generic eval engine."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from runner.eval_types import EvalJob, NormalizedCase, RunPlan


class EvalPlanningError(ValueError):
    """Raised when normalized planning input is invalid or unsafe."""


def validate_normalized_cases(cases: Iterable[NormalizedCase]) -> tuple[NormalizedCase, ...]:
    """Validate the identity contract for a normalized case suite.

    Case order is preserved because it is part of deterministic job expansion.
    Selector aliases may be shared by multiple cases; one selector can therefore
    intentionally select more than one case.
    """
    normalized = tuple(cases)
    seen_ids: set[str] = set()
    for case in normalized:
        if not isinstance(case.id, str) or not case.id:
            raise EvalPlanningError("normalized case id must be a non-empty string")
        if case.id in seen_ids:
            raise EvalPlanningError("duplicate normalized case id: {}".format(case.id))
        seen_ids.add(case.id)

        if not isinstance(case.selectors, tuple):
            raise EvalPlanningError("case {!r} selectors must be a tuple".format(case.id))
        if case.id not in case.selectors:
            raise EvalPlanningError(
                "case {!r} selectors must include its canonical id".format(case.id)
            )
        for selector in case.selectors:
            if not isinstance(selector, str) or not selector:
                raise EvalPlanningError(
                    "case {!r} selectors must be non-empty strings".format(case.id)
                )
    return normalized


def list_cases(cases: Iterable[NormalizedCase]) -> tuple[NormalizedCase, ...]:
    """Return validated normalized cases without provider/model access."""
    return validate_normalized_cases(cases)


def list_case_ids(cases: Iterable[NormalizedCase]) -> tuple[str, ...]:
    """Return canonical case IDs in normalized suite order."""
    return tuple(case.id for case in validate_normalized_cases(cases))


def list_selectors(cases: Iterable[NormalizedCase]) -> tuple[str, ...]:
    """Return unique selectable IDs/aliases in deterministic first-seen order."""
    ordered: list[str] = []
    seen: set[str] = set()
    for case in validate_normalized_cases(cases):
        for selector in case.selectors:
            if selector not in seen:
                seen.add(selector)
                ordered.append(selector)
    return tuple(ordered)


def select_cases(
    cases: Iterable[NormalizedCase],
    *,
    selectors: Sequence[str] = (),
    select_all: bool = False,
) -> tuple[NormalizedCase, ...]:
    """Resolve explicit selection intent without performing any execution.

    The safe default refuses an empty selector set unless select_all is
    explicitly requested. Returned cases always preserve suite order.
    """
    normalized = validate_normalized_cases(cases)
    requested = tuple(selectors)

    if not select_all and not requested:
        raise EvalPlanningError(
            "live execution requires explicit case selectors or select_all=True"
        )

    for selector in requested:
        if not isinstance(selector, str) or not selector:
            raise EvalPlanningError("selectors must be non-empty strings")

    known = {selector for case in normalized for selector in case.selectors}
    unknown = tuple(
        dict.fromkeys(selector for selector in requested if selector not in known)
    )
    if unknown:
        raise EvalPlanningError("unknown selector(s): {}".format(", ".join(unknown)))

    if select_all:
        return normalized

    requested_set = set(requested)
    return tuple(
        case
        for case in normalized
        if any(selector in requested_set for selector in case.selectors)
    )


def validate_iterations(iterations: int) -> int:
    """Require a positive integer iteration count."""
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise EvalPlanningError("iterations must be an integer >= 1")
    return iterations


def expand_jobs(
    cases: Iterable[NormalizedCase],
    *,
    iterations: int,
) -> tuple[EvalJob, ...]:
    """Deterministically expand selected cases into case x iteration jobs."""
    selected = validate_normalized_cases(cases)
    iteration_count = validate_iterations(iterations)
    repeated = iteration_count > 1

    return tuple(
        EvalJob(
            case=case,
            iteration=iteration,
            label="{}#{}".format(case.id, iteration) if repeated else case.id,
        )
        for case in selected
        for iteration in range(1, iteration_count + 1)
    )


def select_and_expand_jobs(
    cases: Iterable[NormalizedCase],
    *,
    selectors: Sequence[str] = (),
    select_all: bool = False,
    iterations: int = 1,
) -> tuple[EvalJob, ...]:
    """Compose safe selection with deterministic iteration expansion."""
    return expand_jobs(
        select_cases(cases, selectors=selectors, select_all=select_all),
        iterations=iterations,
    )


def _validate_standard_parallelism(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvalPlanningError("standard_parallelism must be an integer >= 0")
    return value


def _validate_runtime_parallelism(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EvalPlanningError("runtime_parallelism must be an integer >= 1")
    return value


def _resolved_standard_parallelism(job_count: int, requested: int) -> int:
    requested = _validate_standard_parallelism(requested)
    if job_count == 0:
        return 0
    if requested == 0:
        return job_count
    return min(requested, job_count)


def _resolved_runtime_parallelism(job_count: int, requested: int) -> int:
    requested = _validate_runtime_parallelism(requested)
    if job_count == 0:
        return 0
    return min(requested, job_count)


def resolve_run_schedule(
    run_id: str,
    jobs: Sequence[EvalJob],
    *,
    standard_parallelism: int = 1,
    runtime_parallelism: int = 1,
) -> RunPlan:
    """Resolve deterministic lane ordering and concurrency for expanded jobs.

    standard_parallelism=0 means all standard jobs may run concurrently.
    Runtime jobs are independently bounded and default to serialization.
    The returned order is stable within each lane and always places the
    standard group before the runtime group.
    """
    standard_jobs: list[EvalJob] = []
    runtime_jobs: list[EvalJob] = []

    for job in jobs:
        if job.case.lane == "standard":
            standard_jobs.append(job)
        elif job.case.lane == "runtime":
            runtime_jobs.append(job)
        else:
            raise EvalPlanningError(f"unsupported eval lane: {job.case.lane!r}")

    resolved_standard = _resolved_standard_parallelism(
        len(standard_jobs), standard_parallelism
    )
    resolved_runtime = _resolved_runtime_parallelism(
        len(runtime_jobs), runtime_parallelism
    )

    return RunPlan(
        run_id=run_id,
        jobs=tuple(standard_jobs + runtime_jobs),
        standard_parallelism=resolved_standard,
        runtime_parallelism=resolved_runtime,
    )


def build_run_plan(
    run_id: str,
    cases: Iterable[NormalizedCase],
    *,
    selectors: Sequence[str] = (),
    select_all: bool = False,
    iterations: int = 1,
    standard_parallelism: int = 1,
    runtime_parallelism: int = 1,
) -> RunPlan:
    """Build a complete provider-free run plan from normalized cases."""
    jobs = select_and_expand_jobs(
        cases,
        selectors=selectors,
        select_all=select_all,
        iterations=iterations,
    )
    return resolve_run_schedule(
        run_id,
        jobs,
        standard_parallelism=standard_parallelism,
        runtime_parallelism=runtime_parallelism,
    )
