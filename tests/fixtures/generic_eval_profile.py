"""Provider-free generic eval profile used by Task-6 acceptance tests.

The fixture intentionally imports only the frozen public profile surface. It has
no Loom concepts and never performs provider or network access itself.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from runner.eval_api import (
    AttemptRecord,
    CheckOutcome,
    EvidenceReadiness,
    EvidenceRequirement,
    InvocationSpec,
    JsonValue,
    NormalizedCase,
    SemanticDecision,
)


_CASES = (
    NormalizedCase(
        id="PF-PASS",
        selectors=("PF-PASS", "pass", "standard"),
        lane="standard",
        project_data={
            "check": "pass",
            "judge": "pass",
            "evidence_boundaries": [],
            "retry_target": False,
        },
        metadata={"fixture": "provider-free", "expected": "pass"},
    ),
    NormalizedCase(
        id="PF-FAIL",
        selectors=("PF-FAIL", "fail", "standard"),
        lane="standard",
        project_data={
            "check": "pass",
            "judge": "fail",
            "evidence_boundaries": [],
            "retry_target": False,
        },
        metadata={"fixture": "provider-free", "expected": "fail"},
    ),
    NormalizedCase(
        id="PF-DETERMINISTIC",
        selectors=("PF-DETERMINISTIC", "deterministic", "standard"),
        lane="standard",
        project_data={
            "check": "pass",
            "judge": None,
            "evidence_boundaries": [],
            "retry_target": False,
        },
        metadata={"fixture": "provider-free", "expected": "pass"},
    ),
    NormalizedCase(
        id="PF-NON-EVIDENCE",
        selectors=("PF-NON-EVIDENCE", "non-evidence", "runtime"),
        lane="runtime",
        project_data={
            "check": "pass",
            "judge": "pass",
            "evidence_boundaries": ["native"],
            "retry_target": False,
        },
        metadata={"fixture": "provider-free", "expected": "non-evidence"},
    ),
    NormalizedCase(
        id="PF-RETRY",
        selectors=("PF-RETRY", "retry", "runtime"),
        lane="runtime",
        project_data={
            "check": "pass",
            "judge": None,
            "evidence_boundaries": [],
            "retry_target": True,
        },
        metadata={"fixture": "provider-free", "expected": "pass"},
    ),
)


def _data(case: NormalizedCase) -> dict[str, JsonValue]:
    data = case.project_data
    if not isinstance(data, dict):
        raise TypeError("provider-free fixture case data must be an object")
    return data


def _workspace(prepared: Any) -> Path:
    if not isinstance(prepared, dict) or not isinstance(prepared.get("workspace"), Path):
        raise TypeError("provider-free fixture prepare payload is invalid")
    return prepared["workspace"]


def _iteration(prepared: Any) -> int:
    if not isinstance(prepared, dict) or type(prepared.get("iteration")) is not int:
        raise TypeError("provider-free fixture prepare payload has no iteration")
    return prepared["iteration"]


def _spec(
    *,
    workspace: Path,
    model: str,
    prompt: str,
) -> InvocationSpec:
    return InvocationSpec(
        transport="opencode",
        model=model,
        reasoning="low",
        agent=None,
        skill=None,
        workspace=workspace,
        workspace_mode="ro",
        prompt=prompt,
        system=None,
        expected_plugin=None,
        engine="auto",
        network=None,
        image=None,
        auth=None,
        database=None,
        models_catalog=None,
        config=None,
        config_root=None,
        env_names=(),
        timeout_seconds=5,
        container_timeout=10,
    )


class ProviderFreeGenericProfile:
    def discover_cases(self):
        return _CASES

    @contextmanager
    def prepare(
        self,
        case: NormalizedCase,
        iteration: int,
    ) -> Iterator[dict[str, Any]]:
        with TemporaryDirectory(prefix="opencode-eval-provider-free-") as temp:
            workspace = Path(temp)
            (workspace / "fixture.txt").write_text(
                f"{case.id}#{iteration}\n",
                encoding="utf-8",
            )
            yield {
                "workspace": workspace,
                "iteration": iteration,
            }

    def target_spec(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> InvocationSpec:
        return _spec(
            workspace=_workspace(prepared),
            model=f"fixture/target/{case.id}",
            prompt=f"target:{case.id}:{_iteration(prepared)}",
        )

    def target_evidence_requirement(
        self,
        case: NormalizedCase,
        prepared: Any,
    ) -> EvidenceRequirement:
        del prepared
        raw = _data(case).get("evidence_boundaries", [])
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise TypeError("fixture evidence_boundaries must be a string list")
        return EvidenceRequirement(tuple(raw))

    def deterministic_checks(
        self,
        case: NormalizedCase,
        prepared: Any,
        target: AttemptRecord,
        readiness: EvidenceReadiness,
    ):
        del prepared, target
        if readiness.status != "ready":
            raise ValueError("deterministic checks require ready evidence")
        status = _data(case).get("check")
        if status not in {"pass", "fail", "non-evidence"}:
            raise ValueError("fixture check status is invalid")
        return (
            CheckOutcome(
                name="provider-free-check",
                status=status,
                reason=f"fixture deterministic result: {status}",
                metadata={"case": case.id},
            ),
        )

    def judge_spec(
        self,
        case: NormalizedCase,
        prepared: Any,
        target: AttemptRecord,
        checks,
    ) -> InvocationSpec | None:
        del target, checks
        judge = _data(case).get("judge")
        if judge is None:
            return None
        if judge not in {"pass", "fail"}:
            raise ValueError("fixture judge result is invalid")
        return _spec(
            workspace=_workspace(prepared),
            model=f"fixture/judge/{case.id}",
            prompt=f"judge:{case.id}:{_iteration(prepared)}",
        )

    def parse_judge(
        self,
        case: NormalizedCase,
        prepared: Any,
        judge: AttemptRecord,
    ) -> SemanticDecision:
        del prepared
        if not isinstance(judge.result, dict):
            raise ValueError("fixture judge result is missing")
        stdout = judge.result.get("stdout")
        if not isinstance(stdout, str):
            raise ValueError("fixture judge stdout is missing")
        payload = json.loads(stdout)
        if not isinstance(payload, dict) or payload.get("case") != case.id:
            raise ValueError("fixture judge output case does not match")
        status = payload.get("status")
        if status not in {"pass", "fail"}:
            raise ValueError("fixture judge status is invalid")
        return SemanticDecision(
            status=status,
            summary=f"fixture judge: {status}",
            data={"case": case.id},
        )

    def artifact_metadata(
        self,
        case: NormalizedCase,
        prepared: Any,
    ):
        return {
            "fixture": "provider-free",
            "case": case.id,
            "iteration": _iteration(prepared),
        }


profile = ProviderFreeGenericProfile()
