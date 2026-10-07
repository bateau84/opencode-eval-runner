"""Stable public profile contract for generic eval orchestration.

External projects implement EvalProfile and export one initialized profile
object. The public eval command resolves that object explicitly from a
module:attribute reference. This module is the stable import surface for the
project-owned hooks and normalized values needed by that contract.

The contract is intentionally imperative. It does not define project semantics
or a universal assertion DSL.
"""
from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, Protocol, cast, runtime_checkable

from runner.eval_compare import (
    COMPARISON_RESULT_SCHEMA,
    ComparisonDecision,
    ComparisonFailure,
    ComparisonResult,
    ComparisonStatus,
    CompletedEvaluationOutcome,
    EvalComparisonExtension,
    compare_completed_outcomes,
    comparison_result_envelope,
)
from runner.eval_evidence import EvidenceReadiness, EvidenceRequirement
from runner.eval_types import (
    AttemptRecord,
    CheckOutcome,
    InvocationSpec,
    JsonValue,
    NormalizedCase,
    SemanticDecision,
)

EVAL_COMMAND = "eval"
EVAL_PROFILE_API = "opencode-eval-runner/eval-profile/v1"
EVAL_PROFILE_OPTION = "--profile"
EVAL_PROFILE_REFERENCE_SYNTAX = "module:attribute"

_REQUIRED_PROFILE_METHODS = (
    "discover_cases",
    "prepare",
    "target_spec",
    "target_evidence_requirement",
    "deterministic_checks",
    "judge_spec",
    "parse_judge",
    "artifact_metadata",
)


class EvalProfileError(RuntimeError):
    """Invalid external eval-profile reference or contract implementation."""


@runtime_checkable
class EvalProfile(Protocol):
    """Project-owned hooks consumed by the generic eval engine.

    Generic orchestration owns selection, scheduling, attempts, retries,
    evidence-readiness mechanics, classification, artifacts, and summaries.
    The profile owns project discovery, fixtures, invocation construction,
    behavioral checks, semantic judge meaning, and opaque metadata.
    """

    def discover_cases(self) -> Sequence[NormalizedCase]: ...

    def prepare(
        self,
        case: NormalizedCase,
        iteration: int,
    ) -> AbstractContextManager[Any]: ...

    def target_spec(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> InvocationSpec: ...

    def target_evidence_requirement(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> EvidenceRequirement: ...

    def deterministic_checks(
        self,
        case: NormalizedCase,
        prepared: Any,
        target: AttemptRecord,
        readiness: EvidenceReadiness,
    ) -> Sequence[CheckOutcome]: ...

    def judge_spec(
        self,
        case: NormalizedCase,
        prepared: Any,
        target: AttemptRecord,
        checks: Sequence[CheckOutcome],
    ) -> InvocationSpec | None: ...

    def parse_judge(
        self,
        case: NormalizedCase,
        prepared: Any,
        judge: AttemptRecord,
    ) -> SemanticDecision: ...

    def artifact_metadata(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> Mapping[str, JsonValue]: ...


def validate_eval_profile(profile: object) -> EvalProfile:
    """Validate only the stable hook surface; semantics remain project-owned."""

    if isinstance(profile, type):
        raise EvalProfileError(
            "eval profile export must be an initialized object, not a class"
        )

    missing = tuple(
        name
        for name in _REQUIRED_PROFILE_METHODS
        if not callable(getattr(profile, name, None))
    )
    if missing:
        raise EvalProfileError(
            "eval profile is missing required callable hook(s): "
            + ", ".join(missing)
        )

    return cast(EvalProfile, profile)


def load_eval_profile(reference: str) -> EvalProfile:
    """Resolve the public eval command profile from module:attribute.

    The referenced attribute must already be an initialized profile object.
    Loader-side factories, file execution, and implicit discovery are excluded
    so the public command has one deterministic external extension mechanism.
    """

    if not isinstance(reference, str) or reference != reference.strip():
        raise EvalProfileError(
            f"profile reference must use {EVAL_PROFILE_REFERENCE_SYNTAX}"
        )
    if reference.count(":") != 1:
        raise EvalProfileError(
            f"profile reference must use {EVAL_PROFILE_REFERENCE_SYNTAX}"
        )

    module_name, attribute_name = reference.split(":", 1)
    if not module_name or not attribute_name or not attribute_name.isidentifier():
        raise EvalProfileError(
            f"profile reference must use {EVAL_PROFILE_REFERENCE_SYNTAX}"
        )

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise EvalProfileError(
            f"could not import eval profile module {module_name!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    try:
        profile = getattr(module, attribute_name)
    except AttributeError as exc:
        raise EvalProfileError(
            f"eval profile module {module_name!r} has no export "
            f"{attribute_name!r}"
        ) from exc

    return validate_eval_profile(profile)


__all__ = [
    "COMPARISON_RESULT_SCHEMA",
    "ComparisonDecision",
    "ComparisonFailure",
    "ComparisonResult",
    "ComparisonStatus",
    "CompletedEvaluationOutcome",
    "EvalComparisonExtension",
    "AttemptRecord",
    "CheckOutcome",
    "EVAL_COMMAND",
    "EVAL_PROFILE_API",
    "EVAL_PROFILE_OPTION",
    "EVAL_PROFILE_REFERENCE_SYNTAX",
    "EvalProfile",
    "EvalProfileError",
    "EvidenceReadiness",
    "EvidenceRequirement",
    "InvocationSpec",
    "JsonValue",
    "NormalizedCase",
    "SemanticDecision",
    "compare_completed_outcomes",
    "comparison_result_envelope",
    "load_eval_profile",
    "validate_eval_profile",
]
