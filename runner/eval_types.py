"""Shared internal types for the generic eval engine.

These are data envelopes only. Validation, selection, expansion, scheduling,
artifact storage, and artifact integrity policy live in their owning modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeAlias, Union


JsonValue: TypeAlias = Union[
    None,
    bool,
    int,
    float,
    str,
    list["JsonValue"],
    dict[str, "JsonValue"],
]

ExecutionLane: TypeAlias = Literal["standard", "runtime"]
FailurePlane: TypeAlias = Literal["infrastructure", "product", "evidence"]
InvocationTransport: TypeAlias = Literal["opencode", "github-copilot-cli"]
WorkspaceMode: TypeAlias = Literal["ro", "rw"]
CheckStatus: TypeAlias = Literal["pass", "fail", "non-evidence"]
SemanticStatus: TypeAlias = Literal["pass", "fail"]
EvalClassification: TypeAlias = Literal["pass", "fail", "non-evidence"]


@dataclass(frozen=True)
class NormalizedCase:
    """Project-normalized case envelope consumed by generic planning."""

    id: str
    selectors: tuple[str, ...]
    lane: ExecutionLane
    project_data: JsonValue
    metadata: dict[str, JsonValue]


@dataclass(frozen=True)
class EvalJob:
    """One case iteration scheduled by the generic eval engine."""

    case: NormalizedCase
    iteration: int
    label: str


@dataclass(frozen=True)
class RunPlan:
    """Resolved generic run plan.

    Task 2 planning code may add normalized selector/planning metadata later
    if needed, while preserving these core fields.
    """

    run_id: str
    jobs: tuple[EvalJob, ...]
    standard_parallelism: int
    runtime_parallelism: int


@dataclass(frozen=True)
class ArtifactIdentity:
    """Stable identity for one durable case/iteration artifact."""

    run_id: str
    case_id: str
    iteration: int


@dataclass(frozen=True)
class InvocationSpec:
    """Logical invocation request consumed by eval orchestration."""

    transport: InvocationTransport
    model: str
    reasoning: str | None
    agent: str | None
    skill: str | None
    workspace: Path
    workspace_mode: WorkspaceMode
    prompt: str
    system: str | None
    expected_plugin: str | None
    engine: str
    network: str | None
    image: str | None
    auth: Path | None
    database: Path | None
    models_catalog: Path | None
    config: Path | None
    config_root: Path | None
    env_names: tuple[str, ...]
    timeout_seconds: int
    container_timeout: int


@dataclass(frozen=True)
class AttemptFailure:
    """One attempt failure, separated by infrastructure/product/evidence plane."""

    plane: FailurePlane
    code: str
    message: str
    retry_safe: bool


@dataclass(frozen=True)
class AttemptRecord:
    """Durable record for exactly one actual low-level invoke call."""

    attempt: int
    started_at: str
    duration_seconds: float
    host_exit_code: int | None
    result: dict[str, JsonValue] | None
    failure: AttemptFailure | None


@dataclass(frozen=True)
class CheckOutcome:
    """Project-owned deterministic check normalized for generic classification."""

    name: str
    status: CheckStatus
    reason: str
    metadata: dict[str, JsonValue]


@dataclass(frozen=True)
class SemanticDecision:
    """Project-owned semantic judgment normalized to pass/fail."""

    status: SemanticStatus
    summary: str
    data: JsonValue


@dataclass(frozen=True)
class RetryDecision:
    """Explicit orchestration decision made after a failed attempt."""

    retry: bool
    reason: str
    delay_seconds: float


class RetryPolicy(Protocol):
    """Policy decides permission to retry; orchestration enforces safety/bounds."""

    def decide(
        self,
        attempts: tuple[AttemptRecord, ...],
        latest: AttemptRecord,
    ) -> RetryDecision: ...
