"""Project/profile callbacks and generic final eval classification.

Project code owns deterministic and semantic meaning. This module only defines
that extension surface and the architecture-approved pass/fail/non-evidence
precedence. It performs no provider execution and defines no assertion DSL.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from runner.eval_evidence import EvidenceReadiness
from runner.eval_types import (
    AttemptFailure,
    AttemptRecord,
    CheckOutcome,
    EvalClassification,
    InvocationSpec,
    NormalizedCase,
    SemanticDecision,
)


class EvalProfileCallbacks(Protocol):
    """Task-5 project callbacks consumed by generic orchestration.

    ``parse_judge`` owns project-specific judge schema/contract validation.
    Callers must normalize a parse/contract exception as a required judge
    failure rather than converting it into a semantic FAIL.
    """

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


def classify_evaluation(
    *,
    target_failure: AttemptFailure | None,
    target_readiness: EvidenceReadiness | None,
    deterministic_checks: Sequence[CheckOutcome],
    judge_required: bool,
    judge_failure: AttemptFailure | None,
    semantic: SemanticDecision | None,
) -> EvalClassification:
    """Return the final generic classification using fixed precedence.

    Inputs are already-normalized engine/profile outcomes. ``judge_failure``
    covers both execution failure and a profile parse/contract failure. Missing
    required readiness or a missing required semantic decision fails closed as
    non-evidence.
    """

    # 1. A required target that did not produce a usable execution result cannot
    # authorize a behavioral verdict. Product/timeout failures are likewise not
    # reinterpreted as behavioral FAIL here.
    if target_failure is not None:
        return "non-evidence"

    # 2. Required authoritative target evidence must be ready.
    if target_readiness is None or target_readiness.status != "ready":
        return "non-evidence"

    # 3. A required judge must both execute and satisfy the profile-owned output
    # contract before downstream behavioral outcomes may classify the case.
    if judge_required and (judge_failure is not None or semantic is None):
        return "non-evidence"

    # 4. Valid deterministic behavioral failure is stronger than downstream
    # semantic evidence.
    if any(check.status == "fail" for check in deterministic_checks):
        return "fail"

    # 5. Otherwise inability to prove a deterministic requirement is
    # non-evidence. Unknown statuses also fail closed at this boundary.
    if any(check.status != "pass" for check in deterministic_checks):
        return "non-evidence"

    # 6-7. Semantic meaning is project-owned but normalized to pass/fail. A
    # deterministic-only case passes when every required deterministic check did.
    if semantic is not None:
        if semantic.status == "fail":
            return "fail"
        if semantic.status == "pass":
            return "pass"
        return "non-evidence"

    if not judge_required:
        return "pass"

    # Defensive fail-closed fallback; the missing required semantic case is
    # handled above but keeping the total function explicit avoids accidental PASS.
    return "non-evidence"
