"""Public generic eval CLI orchestration over the frozen profile contract."""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from runner.eval_api import EvalProfile, EvalProfileError, load_eval_profile
from runner.eval_artifacts import (
    EVAL_RUN_SCHEMA,
    EvalArtifactError,
    EvalArtifactStorageError,
    RunArtifactStore,
    artifact_identity_for_job,
    claim_run_artifact_directory,
)
from runner.eval_builtin import (
    AgentRuntimeAdapter,
    SkillAblationAdapter,
    normalized_cases,
)
from runner.eval_engine import build_eval_artifact, run_evaluation_phase
from runner.eval_evidence import EvidenceRequirement
from runner.eval_execute import (
    InvokeAdapter,
    SleepFn,
    TransientProviderRetryPolicy,
    invoke_once,
)
from runner.eval_input import InputContractError, load_evaluation_input
from runner.eval_output import EvalOutputError, load_verified_output, write_output
from runner.eval_plan import EvalPlanningError, build_run_plan, list_cases
from runner.eval_types import EvalJob, InvocationSpec, JsonValue, RunPlan
from runner.oci_image import ImageSelectionError, validate_immutable_image_identity

EVAL_EXIT_PASS = 0
EVAL_EXIT_VERDICT = 1
EVAL_EXIT_ERROR = 2
MAX_TRANSPORT_RETRIES = 5


class EvalCommandError(RuntimeError):
    """Public eval command configuration or orchestration failure."""


def add_eval_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Register the public eval command without changing invoke semantics."""
    run = subparsers.add_parser(
        "eval",
        help="Run a generic eval profile over one or more isolated invocations.",
        description=(
            "Run project-supplied eval cases through the generic eval engine. "
            "Live runs require --all or explicit --cases selection."
        ),
    )
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument("--profile", metavar="MODULE:ATTRIBUTE", help="Initialized EvalProfile export to load.")
    mode.add_argument("--input", metavar="PATH", help="JSON input file for a built-in evaluation family.")
    mode.add_argument("--render-run", metavar="RUN_DIRECTORY", help="Render a completed verified run without invoking a model.")
    run.add_argument("--family", choices=("agent-runtime", "skill"), help="Input contract family for --input.")
    run.add_argument("--skill", metavar="NAME", help="Skill identity for top-level skill-case arrays.")
    run.add_argument("--ablation", action="store_true", help="Run the skill baseline/candidate paired lifecycle.")
    run.add_argument(
        "--list",
        action="store_true",
        help="List normalized cases without running target or judge invocations.",
    )
    run.add_argument(
        "--all",
        action="store_true",
        help="Explicitly select every discovered case for live execution.",
    )
    run.add_argument(
        "--cases",
        action="append",
        default=[],
        metavar="SELECTOR[,SELECTOR...]",
        help="Select canonical case IDs or profile aliases. May be repeated.",
    )
    run.add_argument(
        "--iterations",
        type=int,
        default=1,
        metavar="N",
        help="Run each selected case N times (default: 1).",
    )
    run.add_argument(
        "--parallel",
        nargs="?",
        const=0,
        type=int,
        default=1,
        metavar="N",
        help=(
            "Standard-lane concurrency. Default: 1. Without N, allow all "
            "standard jobs to run concurrently."
        ),
    )
    run.add_argument(
        "--runtime-parallel",
        type=int,
        default=1,
        metavar="N",
        help="Runtime-lane concurrency (default: 1).",
    )
    run.add_argument(
        "--target-transport",
        choices=("opencode", "github-copilot-cli"),
        help="Override the target InvocationSpec transport.",
    )
    run.add_argument(
        "--judge-transport",
        choices=("opencode", "github-copilot-cli"),
        help="Override the judge InvocationSpec transport.",
    )
    run.add_argument(
        "--target-model",
        metavar="MODEL",
        help="Override the target InvocationSpec model.",
    )
    run.add_argument(
        "--judge-model",
        metavar="MODEL",
        help="Override the judge InvocationSpec model.",
    )
    run.add_argument(
        "--reasoning",
        metavar="LEVEL",
        help="Override reasoning for both target and judge unless phase-specific.",
    )
    run.add_argument(
        "--target-reasoning",
        metavar="LEVEL",
        help="Override --reasoning for target invocations.",
    )
    run.add_argument(
        "--judge-reasoning",
        metavar="LEVEL",
        help="Override --reasoning for judge invocations.",
    )
    run.add_argument(
        "--engine",
        choices=("auto", "podman", "docker"),
        help="Override the OCI engine in target and judge InvocationSpec values.",
    )
    run.add_argument(
        "--network",
        metavar="MODE",
        help="Override the OCI network mode/name for target and judge.",
    )
    run.add_argument(
        "--artifact-dir",
        metavar="PATH",
        help="Single-run artifact directory. Default: .opencode-evals/<run-id>.",
    )
    run.add_argument(
        "--timeout-seconds",
        type=int,
        metavar="N",
        help="Override the inner invocation timeout for target and judge.",
    )
    run.add_argument(
        "--container-timeout",
        type=int,
        metavar="N",
        help="Override the outer OCI process timeout for target and judge.",
    )
    run.add_argument(
        "--transport-retries",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Opt in to replay-safe transient provider retries for target and judge "
            f"(default: 0; range: 0-{MAX_TRANSPORT_RETRIES})."
        ),
    )
    run.add_argument("--format", choices=("json", "yaml", "markdown", "html"), help="Built-in result format (default: json).")
    run.add_argument("--output", metavar="PATH", help="Write the selected built-in representation atomically to PATH.")
    return run


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _selectors(values: Sequence[str]) -> tuple[str, ...]:
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in value.split(","):
            selector = item.strip()
            if not selector:
                continue
            if selector not in seen:
                seen.add(selector)
                selected.append(selector)
    return tuple(selected)


def _validate_positive_override(name: str, value: int | None) -> None:
    if value is not None and value < 1:
        raise EvalCommandError(f"{name} must be >= 1")


def _validate_cli_values(args: argparse.Namespace) -> None:
    if args.transport_retries < 0 or args.transport_retries > MAX_TRANSPORT_RETRIES:
        raise EvalCommandError(
            f"--transport-retries must be between 0 and {MAX_TRANSPORT_RETRIES}"
        )
    _validate_positive_override("--timeout-seconds", args.timeout_seconds)
    _validate_positive_override("--container-timeout", args.container_timeout)
    for name in (
        "target_model",
        "judge_model",
        "reasoning",
        "target_reasoning",
        "judge_reasoning",
        "network",
    ):
        value = getattr(args, name)
        if value is not None and not value.strip():
            raise EvalCommandError(f"--{name.replace('_', '-')} must not be empty")


def _phase_reasoning(
    args: argparse.Namespace,
    phase: str,
    current: str | None,
) -> str | None:
    specific = getattr(args, f"{phase}_reasoning")
    if specific is not None:
        return specific
    if args.reasoning is not None:
        return args.reasoning
    return current


def apply_invocation_overrides(
    spec: InvocationSpec,
    args: argparse.Namespace,
    phase: str,
) -> InvocationSpec:
    """Apply explicit public CLI controls without changing the profile contract."""
    if not isinstance(spec, InvocationSpec):
        raise EvalCommandError(
            f"profile {phase}_spec must return InvocationSpec"
        )
    if phase not in {"target", "judge"}:
        raise ValueError(f"unsupported eval phase: {phase!r}")

    transport = getattr(args, f"{phase}_transport")
    model = getattr(args, f"{phase}_model")
    return replace(
        spec,
        transport=transport if transport is not None else spec.transport,
        model=model if model is not None else spec.model,
        reasoning=_phase_reasoning(args, phase, spec.reasoning),
        engine=args.engine if args.engine is not None else spec.engine,
        network=args.network if args.network is not None else spec.network,
        timeout_seconds=(
            args.timeout_seconds
            if args.timeout_seconds is not None
            else spec.timeout_seconds
        ),
        container_timeout=(
            args.container_timeout
            if args.container_timeout is not None
            else spec.container_timeout
        ),
    )


class _ProfileWithJudgeOverrides:
    """Delegate project meaning while applying only public judge CLI overrides."""

    def __init__(self, profile: EvalProfile, args: argparse.Namespace):
        self._profile = profile
        self._args = args

    def deterministic_checks(self, case, prepared, target, readiness):
        return self._profile.deterministic_checks(
            case,
            prepared,
            target,
            readiness,
        )

    def judge_spec(self, case, prepared, target, checks):
        spec = self._profile.judge_spec(
            case,
            prepared,
            target,
            checks,
        )
        if spec is None:
            return None
        return apply_invocation_overrides(spec, self._args, "judge")

    def parse_judge(self, case, prepared, judge):
        return self._profile.parse_judge(case, prepared, judge)


def _metadata(
    profile: EvalProfile,
    case: Any,
    prepared: Any,
) -> dict[str, JsonValue]:
    value = profile.artifact_metadata(case, prepared)
    if not isinstance(value, Mapping):
        raise EvalCommandError(
            "profile artifact_metadata must return a mapping"
        )
    return dict(value)


def _execute_job(
    job: EvalJob,
    *,
    profile: EvalProfile,
    args: argparse.Namespace,
    retry_policy: TransientProviderRetryPolicy | None,
    max_attempts: int,
    invoker: InvokeAdapter,
    sleep: SleepFn,
    run_id: str,
    store: RunArtifactStore | None = None,
) -> dict[str, Any]:
    paired_executor = getattr(profile, "execute_paired_job", None)
    if callable(paired_executor):
        if store is None:
            raise EvalCommandError("paired built-in eval requires artifact storage")
        return paired_executor(
            job, run_id=run_id, retry_policy=retry_policy,
            max_attempts=max_attempts, invoker=invoker, sleep=sleep, store=store,
        )
    context = profile.prepare(job.case, job.iteration)
    if not hasattr(context, "__enter__") or not hasattr(context, "__exit__"):
        raise EvalCommandError(
            f"profile prepare for {job.case.id!r} must return a context manager"
        )

    with context as prepared:
        project_metadata = _metadata(profile, job.case, prepared)

        target_spec = apply_invocation_overrides(
            profile.target_spec(job.case, prepared),
            args,
            "target",
        )
        evidence_requirement = profile.target_evidence_requirement(
            job.case,
            prepared,
        )
        if not isinstance(evidence_requirement, EvidenceRequirement):
            raise EvalCommandError(
                "profile target_evidence_requirement must return EvidenceRequirement"
            )

        result = run_evaluation_phase(
            case=job.case,
            prepared=prepared,
            target_spec=target_spec,
            evidence_requirement=evidence_requirement,
            profile=_ProfileWithJudgeOverrides(profile, args),
            project_metadata=project_metadata,
            target_retry_policy=retry_policy,
            target_max_attempts=max_attempts,
            target_invoker=invoker,
            target_sleep=sleep,
            judge_retry_policy=retry_policy,
            judge_max_attempts=max_attempts,
            judge_invoker=invoker,
            judge_sleep=sleep,
        )
        completed_metadata = (
            getattr(profile, "completed_artifact_metadata", None)
            if getattr(profile, "runner_builtin_family", False)
            else None
        )
        if callable(completed_metadata):
            value = completed_metadata(job.case, prepared, result)
            if not isinstance(value, Mapping):
                raise EvalCommandError(
                    "profile completed_artifact_metadata must return a mapping"
                )
            result = replace(result, project_metadata=dict(value))
        return build_eval_artifact(
            result,
            run_id=run_id,
            iteration=job.iteration,
        )


def _job_key(job: EvalJob) -> tuple[str, int]:
    return (job.case.id, job.iteration)


def _run_lane(
    jobs: Sequence[EvalJob],
    *,
    parallelism: int,
    execute: Callable[[EvalJob], dict[str, Any]],
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[tuple[str, int], str]]:
    artifacts: dict[tuple[str, int], dict[str, Any]] = {}
    errors: dict[tuple[str, int], str] = {}
    if not jobs:
        return artifacts, errors

    def capture(job: EvalJob) -> None:
        try:
            artifacts[_job_key(job)] = execute(job)
        except Exception as exc:  # noqa: BLE001 - each job failure is a terminal run outcome
            errors[_job_key(job)] = f"{type(exc).__name__}: {exc}"

    if parallelism <= 1:
        for job in jobs:
            capture(job)
        return artifacts, errors

    with ThreadPoolExecutor(max_workers=parallelism) as pool:
        futures = {pool.submit(execute, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                artifacts[_job_key(job)] = future.result()
            except Exception as exc:  # noqa: BLE001 - each job failure is a terminal run outcome
                errors[_job_key(job)] = f"{type(exc).__name__}: {exc}"
    return artifacts, errors


def _manifest_jobs(
    plan: RunPlan,
    store: RunArtifactStore,
    statuses: Mapping[tuple[str, int], str] | None = None,
    paired: bool = False,
) -> list[dict[str, JsonValue]]:
    statuses = {} if statuses is None else statuses
    values: list[dict[str, JsonValue]] = []
    for job in plan.jobs:
        identity = artifact_identity_for_job(plan.run_id, job)
        values.append(
            {
                "case": job.case.id,
                "iteration": job.iteration,
                "label": job.label,
                "lane": job.case.lane,
                "artifact": (
                    store.paired_job_relative_path(identity)
                    if paired else store.job_relative_path(identity)
                ).as_posix(),
                "status": statuses.get(_job_key(job), "planned"),
            }
        )
    return values


def _run_manifest(
    *,
    plan: RunPlan,
    store: RunArtifactStore,
    created_at: str,
    profile_reference: str,
    selectors: Sequence[str],
    select_all: bool,
    iterations: int,
    statuses: Mapping[tuple[str, int], str] | None = None,
    summary: Mapping[str, JsonValue] | None = None,
    paired: bool = False,
    project_metadata: Mapping[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    manifest: dict[str, JsonValue] = {
        "schema": EVAL_RUN_SCHEMA,
        "run_id": plan.run_id,
        "created_at": created_at,
        "selection": {
            "profile": profile_reference,
            "all": select_all,
            "selectors": list(selectors),
            "cases": list(dict.fromkeys(job.case.id for job in plan.jobs)),
        },
        "iterations": iterations,
        "concurrency": {
            "standard": plan.standard_parallelism,
            "runtime": plan.runtime_parallelism,
        },
        "jobs": _manifest_jobs(plan, store, statuses, paired=paired),
        "summary": dict(summary or {"status": "running"}),
    }
    if project_metadata is not None:
        manifest["project_metadata"] = dict(project_metadata)
    return manifest


def _list_profile_cases(profile: EvalProfile, stdout: TextIO) -> int:
    cases = list_cases(profile.discover_cases())
    for case in cases:
        aliases = ",".join(
            selector for selector in case.selectors if selector != case.id
        )
        print(
            f"{case.id}\t{case.lane}\t{aliases}",
            file=stdout,
        )
    return EVAL_EXIT_PASS


def _persist_lane(
    *,
    jobs: Sequence[EvalJob],
    artifacts: Mapping[tuple[str, int], dict[str, Any]],
    store: RunArtifactStore,
    stdout: TextIO,
    statuses: dict[tuple[str, int], str],
) -> None:
    for job in jobs:
        key = _job_key(job)
        artifact = artifacts.get(key)
        if artifact is None:
            continue
        identity = artifact_identity_for_job(store.run_id, job)
        if artifact.get("schema") == "opencode-eval-runner/eval-paired-artifact/v1":
            store.write_paired_job_artifact(identity, artifact)
            verified = store.read_paired_job_artifact(identity)
            comparison = verified.get("comparison", {})
            if comparison.get("status") == "compared":
                classification = str(comparison["decision"]["classification"])
            elif comparison.get("status") == "non-evidence":
                classification = "non-evidence"
            else:
                classification = "error"
        else:
            store.write_job_artifact(identity, artifact)
            verified = store.read_job_artifact(identity)
            classification = str(verified["classification"])
        statuses[key] = classification
        print(f"{job.label} ... {classification.upper()}", file=stdout)


def _error_report(
    jobs: Sequence[EvalJob],
    errors: Mapping[tuple[str, int], str],
    *,
    stderr: TextIO,
    statuses: dict[tuple[str, int], str],
) -> None:
    for job in jobs:
        key = _job_key(job)
        message = errors.get(key)
        if message is None:
            continue
        statuses[key] = "error"
        print(f"{job.label} ... ERROR", file=stderr)
        print(f"  - {message}", file=stderr)


def _summary_from_store(
    plan: RunPlan,
    store: RunArtifactStore,
    statuses: Mapping[tuple[str, int], str],
) -> dict[str, JsonValue]:
    counts = {"pass": 0, "fail": 0, "non-evidence": 0}
    errors = 0
    skipped = 0
    for job in plan.jobs:
        status = statuses.get(_job_key(job), "not-run")
        if status in counts:
            identity = artifact_identity_for_job(plan.run_id, job)
            if store.paired_job_path(identity).exists():
                verified = store.read_paired_job_artifact(identity)
                comparison = verified.get("comparison", {})
                if comparison.get("status") == "compared":
                    classification = str(comparison["decision"]["classification"])
                elif comparison.get("status") == "non-evidence":
                    classification = "non-evidence"
                else:
                    classification = "error"
            else:
                verified = store.read_job_artifact(identity)
                classification = str(verified["classification"])
            if classification != status:
                raise EvalCommandError(
                    f"artifact classification changed after persistence for {job.label}"
                )
            counts[classification] += 1
        elif status == "error":
            errors += 1
        else:
            skipped += 1

    if errors or skipped:
        state = "error"
    elif counts["fail"] or counts["non-evidence"]:
        state = "verdict"
    else:
        state = "pass"

    return {
        "status": state,
        "pass": counts["pass"],
        "fail": counts["fail"],
        "non-evidence": counts["non-evidence"],
        "errors": errors,
        "not_run": skipped,
        "total": len(plan.jobs),
    }


def run_eval(
    args: argparse.Namespace,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    invoker: InvokeAdapter = invoke_once,
    sleep: SleepFn = time.sleep,
) -> int:
    """Run one public eval command. Provider calls occur only after safe selection."""
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    progress_stdout = stderr if getattr(args, "input", None) else stdout

    try:
        _validate_cli_values(args)
        if getattr(args, "render_run", None) is not None:
            prohibited = (
                args.profile is not None or args.input is not None or args.family is not None
                or args.skill is not None or args.ablation or args.list or args.all or bool(args.cases)
                or args.target_model is not None or args.judge_model is not None
                or args.target_transport is not None or args.judge_transport is not None
                or args.reasoning is not None or args.target_reasoning is not None or args.judge_reasoning is not None
                or args.engine is not None or args.network is not None or args.artifact_dir is not None
                or args.timeout_seconds is not None or args.container_timeout is not None
                or args.transport_retries != 0 or args.iterations != 1 or args.parallel != 1
                or args.runtime_parallel != 1
            )
            if prohibited:
                raise EvalCommandError("--render-run cannot be combined with input, selection, invocation, profile, or artifact options")
            model = load_verified_output(args.render_run)
            write_output(model, args.format or "json", args.output, stdout, run_directory=args.render_run)
            return EVAL_EXIT_PASS
        input_metadata: dict[str, JsonValue] | None = None
        if args.input is None:
            built_in_controls = (
                args.family is not None
                or args.skill is not None
                or args.ablation
                or args.format is not None
                or args.output is not None
            )
            if built_in_controls:
                raise EvalCommandError("built-in eval controls cannot be combined with --profile")
            if not args.profile:
                raise EvalCommandError("pass --profile or --input")
            profile = load_eval_profile(args.profile)
            profile_reference = args.profile
        else:
            if args.family is None:
                raise EvalCommandError("--family is required with --input")
            if args.list:
                raise EvalCommandError("--list is available only with --profile")
            if args.skill is not None and args.family != "skill":
                raise EvalCommandError("--skill is only valid with --family skill")
            if args.ablation and args.family != "skill":
                raise EvalCommandError("--ablation is only valid with --family skill")
            if args.target_model is None or not args.target_model.strip():
                raise EvalCommandError("--target-model is required for built-in eval")
            target_transport = args.target_transport or "opencode"
            judge_transport = args.judge_transport or "opencode"
            if target_transport != "opencode" or judge_transport != "opencode":
                raise EvalCommandError("built-in evaluations support only the opencode transport")
            args.target_transport = target_transport
            args.judge_transport = judge_transport
            try:
                args.opencode_image = validate_immutable_image_identity(
                    os.environ.get("OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE")
                )
            except ImageSelectionError as exc:
                raise EvalCommandError(str(exc)) from exc
            args.judge_model = args.judge_model or args.target_model
            source = load_evaluation_input(args.input, family=args.family, skill=args.skill)
            input_metadata = {
                "runner_eval_input": {
                    "family": source.family,
                    "contract": source.contract,
                    "sha256": source.sha256,
                }
            }
            cases = normalized_cases(source)
            profile = (
                AgentRuntimeAdapter(cases, args, Path.cwd())
                if source.family == "agent-runtime"
                else SkillAblationAdapter(cases, args, Path.cwd())
            )
            validate_inputs = getattr(profile, "validate_inputs", None)
            if callable(validate_inputs):
                validate_inputs()
            profile_reference = f"builtin:{source.family}:{source.contract}"
        if args.list:
            return _list_profile_cases(profile, stdout)

        selectors = _selectors(args.cases)
        if args.input is not None and args.all == bool(selectors):
            raise EvalCommandError("built-in eval requires exactly one of --all or --cases")
        if not args.all and not selectors:
            raise EvalCommandError(
                "live evals spend model inference; pass --cases or --all explicitly"
            )

        cases = tuple(profile.discover_cases())
        run_id = uuid.uuid4().hex
        plan = build_run_plan(
            run_id,
            cases,
            selectors=selectors,
            select_all=args.all,
            iterations=args.iterations,
            standard_parallelism=args.parallel,
            runtime_parallelism=args.runtime_parallel,
        )
        if not plan.jobs:
            raise EvalCommandError("selection matched no eval cases")

        artifact_dir = (
            Path(args.artifact_dir)
            if args.artifact_dir
            else Path(".opencode-evals") / run_id
        )
        store = claim_run_artifact_directory(artifact_dir, run_id)
        created_at = _utc_now()
        store.write_run_manifest(
            _run_manifest(
                plan=plan,
                store=store,
                created_at=created_at,
                profile_reference=profile_reference,
                selectors=selectors,
                select_all=args.all,
                iterations=args.iterations,
                paired=isinstance(profile, SkillAblationAdapter),
                project_metadata=input_metadata,
            )
        )

        retry_policy = (
            TransientProviderRetryPolicy()
            if args.transport_retries > 0
            else None
        )
        max_attempts = args.transport_retries + 1

        standard_jobs = tuple(
            job for job in plan.jobs if job.case.lane == "standard"
        )
        runtime_jobs = tuple(
            job for job in plan.jobs if job.case.lane == "runtime"
        )
        statuses: dict[tuple[str, int], str] = {}

        def execute(job: EvalJob) -> dict[str, Any]:
            return _execute_job(
                job,
                profile=profile,
                args=args,
                retry_policy=retry_policy,
                max_attempts=max_attempts,
                invoker=invoker,
                sleep=sleep,
                run_id=run_id,
                store=store,
            )

        standard_artifacts, standard_errors = _run_lane(
            standard_jobs,
            parallelism=plan.standard_parallelism,
            execute=execute,
        )
        _persist_lane(
            jobs=standard_jobs,
            artifacts=standard_artifacts,
            store=store,
            stdout=progress_stdout,
            statuses=statuses,
        )
        _error_report(
            standard_jobs,
            standard_errors,
            stderr=stderr,
            statuses=statuses,
        )

        # A profile/orchestration exception means the run did not complete
        # reliably. Avoid starting the independent runtime lane after that
        # failure so a broken profile does not trigger additional inference.
        runtime_errors: dict[tuple[str, int], str] = {}
        if standard_errors:
            for job in runtime_jobs:
                statuses[_job_key(job)] = "not-run"
        else:
            runtime_artifacts, runtime_errors = _run_lane(
                runtime_jobs,
                parallelism=plan.runtime_parallelism,
                execute=execute,
            )
            _persist_lane(
                jobs=runtime_jobs,
                artifacts=runtime_artifacts,
                store=store,
                stdout=progress_stdout,
                statuses=statuses,
            )
            _error_report(
                runtime_jobs,
                runtime_errors,
                stderr=stderr,
                statuses=statuses,
            )

        summary = _summary_from_store(plan, store, statuses)
        store.write_run_manifest(
            _run_manifest(
                plan=plan,
                store=store,
                created_at=created_at,
                profile_reference=profile_reference,
                selectors=selectors,
                select_all=args.all,
                iterations=args.iterations,
                statuses=statuses,
                summary=summary,
                paired=isinstance(profile, SkillAblationAdapter),
                project_metadata=input_metadata,
            )
        )

        if args.input is not None:
            model = load_verified_output(store.root)
            write_output(model, args.format or "json", args.output, stdout, run_directory=store.root)

        print(
            "Run {run_id}: {passed} pass, {failed} fail, "
            "{non_evidence} non-evidence, {errors} error, {not_run} not-run. "
            "Artifacts: {artifact_dir}".format(
                run_id=run_id,
                passed=summary["pass"],
                failed=summary["fail"],
                non_evidence=summary["non-evidence"],
                errors=summary["errors"],
                not_run=summary["not_run"],
                artifact_dir=store.root,
            ),
            file=progress_stdout,
        )

        if summary["errors"] or summary["not_run"]:
            return EVAL_EXIT_ERROR
        if summary["fail"] or summary["non-evidence"]:
            return EVAL_EXIT_VERDICT
        return EVAL_EXIT_PASS
    except (
        EvalProfileError,
        EvalPlanningError,
        EvalArtifactError,
        EvalArtifactStorageError,
        InputContractError,
        EvalCommandError,
        EvalOutputError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"opencode-eval-runner eval: {exc}", file=stderr)
        return EVAL_EXIT_ERROR
