"""Shared internal types for the generic eval engine.

These are data envelopes only. Validation, selection, expansion, scheduling,
artifact storage, and artifact integrity policy live in their owning modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias, Union


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
