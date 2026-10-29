"""Verified public projections of durable eval/v1 records."""

from __future__ import annotations

import html
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from runner.eval_artifacts import (
    EVAL_ARTIFACT_SCHEMA,
    EVAL_PAIRED_ARTIFACT_SCHEMA,
    EvalArtifactError,
    RunArtifactStore,
)
from runner.eval_types import ArtifactIdentity

EVAL_OUTPUT_SCHEMA = "opencode-eval-runner/eval-output/v1"
EVAL_OUTPUT_SCHEMA_V2 = "opencode-eval-runner/eval-output/v2"
FORMATS = ("json", "yaml", "markdown", "html")


class EvalOutputError(RuntimeError):
    """A durable run cannot safely be projected or written."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalOutputError(message)


def _artifact_ref(schema: str, path: str, evidence_id: str) -> dict[str, str]:
    return {"schema": schema, "relative_path": path, "evidence_id": evidence_id}


def _invocation(metadata: dict[str, Any]) -> dict[str, Any]:
    required = {
        "transport",
        "model",
        "reasoning",
        "agent",
        "skill",
        "workspace_mode",
        "timeout_seconds",
        "container_timeout",
        "engine",
        "network",
        "image",
        "expected_plugin",
    }
    _exact_keys(metadata, required, "invocation provenance")
    _require(
        metadata["transport"] == "opencode"
        and type(metadata["model"]) is str
        and bool(metadata["model"]),
        "invocation transport/model provenance is invalid",
    )
    _require(
        metadata["reasoning"] is None or type(metadata["reasoning"]) is str,
        "invocation reasoning is invalid",
    )
    _require(
        all(
            metadata[key] is None or type(metadata[key]) is str
            for key in ("agent", "skill", "network", "image", "expected_plugin")
        ),
        "invocation optional provenance is invalid",
    )
    _require(
        metadata["workspace_mode"] in {"ro", "rw"}
        and all(
            type(metadata[key]) is int and metadata[key] >= 1
            for key in ("timeout_seconds", "container_timeout")
        ),
        "invocation workspace/timeout provenance is invalid",
    )
    _require(
        metadata["engine"] in {"auto", "podman", "docker"},
        "invocation engine provenance is invalid",
    )
    return {
        "transport": metadata["transport"],
        "model": metadata["model"],
        "reasoning": metadata["reasoning"],
        "agent": metadata["agent"],
        "skill": metadata["skill"],
        "workspace_mode": metadata["workspace_mode"],
        "timeout_seconds": metadata["timeout_seconds"],
        "container_timeout": metadata["container_timeout"],
        "engine": metadata["engine"],
        "network": metadata["network"],
        "image": metadata["image"],
        "expected_plugin": metadata["expected_plugin"],
    }


def _attempts(
    attempts: list[dict[str, Any]], invocations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    _require(
        len(attempts) == len(invocations),
        "artifact attempts lack complete invocation provenance",
    )
    values = []
    for expected, item in enumerate(attempts, 1):
        _require(
            item.get("attempt") == expected,
            "artifact attempt numbering is not contiguous",
        )
        values.append(
            {
                "number": item["attempt"],
                "started_at": item["started_at"],
                "duration_seconds": item["duration_seconds"],
                "invocation": _invocation(invocations[expected - 1]),
                "host_exit_code": item["host_exit_code"],
                "result": item["result"],
                "failure": item["failure"],
                "retry_decision": item.get("retry_decision"),
            }
        )
    return values


def _readiness(artifact: dict[str, Any]) -> dict[str, Any]:
    value = artifact["target"]["evidence_readiness"]
    attempts = artifact["target"]["attempts"]
    runtime = []
    for attempt in attempts:
        result = attempt.get("result")
        evidence = result.get("runtime_evidence") if isinstance(result, dict) else None
        if isinstance(evidence, dict):
            runtime.append(evidence)
    return {
        "status": value.get("status"),
        "reasons": value.get("reasons", []),
        "required_boundaries": value.get("required_boundaries", []),
        "runtime_evidence": runtime,
    }


def _groups(
    artifact: dict[str, Any], paired_side: str | None = None
) -> list[dict[str, Any]]:
    phases = []
    target_name = f"{paired_side}-target" if paired_side else "target"
    judge_name = f"{paired_side}-judge" if paired_side else "judge"
    specs = artifact["project_metadata"].get("runner_eval_invocations", [])
    target_count = len(artifact["target"]["attempts"])
    judge_count = len(artifact["judge"]["attempts"])
    _require(isinstance(specs, list), "artifact lacks invocation provenance")
    _require(
        len(specs) == target_count + judge_count,
        "artifact invocation provenance count does not match attempts",
    )
    target_specs = specs[:target_count]
    judge_specs = specs[target_count:]
    phases.append(
        {
            "phase": target_name,
            "attempts": _attempts(artifact["target"]["attempts"], target_specs),
        }
    )
    phases.append(
        {
            "phase": judge_name,
            "attempts": _attempts(artifact["judge"]["attempts"], judge_specs),
        }
    )
    return phases


def _agent_result(artifact: dict[str, Any], ref: dict[str, str]) -> dict[str, Any]:
    meta = artifact["project_metadata"].get("runner_eval")
    _require(
        isinstance(meta, dict) and isinstance(meta.get("family_result"), dict),
        "agent artifact lacks runner family result",
    )
    family_result = meta["family_result"]
    _exact_keys(
        family_result,
        {"kind", "suite", "case", "assertions", "semantic_judge"},
        "agent family result",
    )
    _require(
        family_result["kind"] == "agent-runtime/v1", "agent family result kind mismatch"
    )
    _exact_keys(
        family_result["suite"], {"name", "version", "default"}, "agent suite result"
    )
    _exact_keys(
        family_result["case"],
        {
            "default",
            "agent",
            "skill",
            "execution",
            "target_timeout_seconds",
            "requirements",
            "prompt",
            "trap",
            "expectations",
            "must_not",
            "fixture_files",
        },
        "agent case result",
    )
    _require(type(family_result["assertions"]) is list, "agent assertions are invalid")
    for assertion in family_result["assertions"]:
        _exact_keys(
            assertion,
            {"kind", "authored", "status", "reason", "observed", "evidence_refs"},
            "agent assertion result",
        )
        _require(
            assertion["kind"] in {"tools", "actions", "tool_results", "output"}
            and assertion["status"] in {"pass", "fail", "non-evidence"},
            "agent assertion kind/status is invalid",
        )
    if family_result["semantic_judge"] is not None:
        _exact_keys(
            family_result["semantic_judge"],
            {
                "passed",
                "expectations",
                "violations",
                "trap_observed",
                "trap_evidence",
                "summary",
            },
            "agent semantic judge",
        )
    return {
        "id": artifact["case"],
        "family": "agent-runtime",
        "contract": meta["contract"],
        "iteration": artifact["iteration"],
        "execution_status": "complete",
        "classification": artifact["classification"],
        "error": None,
        "attempts": _groups(artifact),
        "evidence": _readiness(artifact),
        "checks": artifact["deterministic_checks"],
        "semantic": artifact["judge"]["semantic"],
        "family_result": family_result,
        "source_artifacts": [ref],
    }


def _skill_result(
    pair: dict[str, Any], ref: dict[str, str], *, source_input: int | None = None
) -> dict[str, Any]:
    meta = pair["project_metadata"].get("runner_eval")
    _require(isinstance(meta, dict), "paired artifact lacks runner family result")
    family_result = meta["family_result"]
    _require(
        isinstance(family_result, dict) and family_result.get("kind") == "skill/v1",
        "paired artifact lacks complete skill payload",
    )
    _exact_keys(
        family_result,
        {
            "kind",
            "skill",
            "case_identity",
            "prompt",
            "fixture_files",
            "expectations",
            "negative_expectations",
            "trap",
            "ablation",
        },
        "skill family result",
    )
    identity_keys = {
        "case_id",
        "source_id",
        "authored_id",
        "source_index",
        "display_name",
    }
    _exact_keys(family_result["case_identity"], identity_keys, "skill case identity")
    _exact_keys(family_result["trap"], {"declared", "text"}, "skill trap")
    _exact_keys(
        family_result["ablation"],
        {"baseline", "candidate", "comparison"},
        "skill ablation",
    )
    _require(
        type(family_result["expectations"]) is list
        and type(family_result["negative_expectations"]) is list,
        "skill expectation payload is invalid",
    )
    _require(
        family_result["ablation"]["comparison"] == pair.get("comparison"),
        "paired family comparison does not match verified pair envelope",
    )
    attempts = []
    refs = [ref]
    for name in ("baseline", "candidate"):
        side = family_result["ablation"][name]
        _exact_keys(
            side,
            {
                "case_id",
                "run_id",
                "iteration",
                "classification",
                "attempts",
                "evidence",
                "checks",
                "skill_outcome",
                "source_artifact",
            },
            f"skill {name} result",
        )
        _exact_keys(
            side["skill_outcome"],
            {"expectations", "negative_expectations", "trap", "semantic_judge"},
            f"skill {name} outcome",
        )
        _exact_keys(
            side["evidence"],
            {"status", "reasons", "required_boundaries", "runtime_evidence"},
            f"skill {name} evidence",
        )
        _require(
            type(side["checks"]) is list and type(side["attempts"]) is list,
            f"skill {name} outcomes are invalid",
        )
        for check in side["checks"]:
            _exact_keys(
                check, {"name", "status", "reason", "metadata"}, f"skill {name} check"
            )
        for group in side["attempts"]:
            _exact_keys(group, {"phase", "attempts"}, f"skill {name} attempt group")
            for attempt in group["attempts"]:
                _exact_keys(
                    attempt,
                    {
                        "number",
                        "started_at",
                        "duration_seconds",
                        "invocation",
                        "host_exit_code",
                        "result",
                        "failure",
                        "retry_decision",
                    },
                    f"skill {name} attempt",
                )
                _invocation(attempt["invocation"])
        for result in side["skill_outcome"]["expectations"]:
            _exact_keys(result, {"text", "met", "reason"}, f"skill {name} expectation")
        for result in side["skill_outcome"]["negative_expectations"]:
            _exact_keys(
                result,
                {"text", "violated", "reason"},
                f"skill {name} negative expectation",
            )
        _exact_keys(
            side["skill_outcome"]["trap"],
            {"declared", "text", "observed", "evidence"},
            f"skill {name} trap outcome",
        )
        if side["skill_outcome"]["semantic_judge"] is not None:
            _exact_keys(
                side["skill_outcome"]["semantic_judge"],
                {"passed", "summary", "behavior_score"},
                f"skill {name} semantic judge",
            )
        _exact_keys(
            side["source_artifact"],
            {"schema", "relative_path", "evidence_id"},
            f"skill {name} artifact reference",
        )
        attempts.extend(side["attempts"])
        side_ref = side["source_artifact"]
        paired_side = pair["sides"][name]
        _require(
            side["case_id"] == pair["case"]
            and side["run_id"] == pair["run_id"]
            and side["iteration"] == pair["iteration"]
            and side_ref.get("schema") == EVAL_ARTIFACT_SCHEMA
            and side_ref.get("relative_path")
            == ref["relative_path"] + f"#/sides/{name}"
            and side_ref.get("evidence_id") == paired_side["artifact_evidence_id"],
            f"skill {name} payload identity/source reference mismatch",
        )
        refs.append(
            {
                "schema": side_ref["schema"],
                "relative_path": side_ref["relative_path"],
                "evidence_id": side_ref["evidence_id"],
            }
        )
    result = {
        "id": pair["case"],
        "family": "skill",
        "contract": meta["contract"],
        "iteration": pair["iteration"],
        "execution_status": "complete",
        "classification": pair["comparison"]["decision"]["classification"]
        if pair["comparison"]["status"] == "compared"
        else "non-evidence"
        if pair["comparison"]["status"] == "non-evidence"
        else None,
        "error": None,
        "attempts": attempts,
        "evidence": family_result["ablation"]["candidate"]["evidence"],
        "checks": family_result["ablation"]["candidate"]["checks"],
        "semantic": None,
        "family_result": family_result,
        "source_artifacts": refs,
    }
    if source_input is not None:
        result["identity"] = {"skill": family_result["skill"], "case": pair["case"]}
        result["source_input"] = source_input
    return result


def load_verified_output(run_directory: str | os.PathLike[str]) -> dict[str, Any]:
    """Re-read and verify the terminal manifest and every referenced v1 record."""
    root = Path(run_directory).resolve(strict=True)
    try:
        owner = json.loads((root / ".eval-run-owner.json").read_text(encoding="utf-8"))
        _require(
            isinstance(owner, dict)
            and type(owner.get("run_id")) is str
            and bool(owner["run_id"]),
            "run directory ownership record is invalid",
        )
        store = RunArtifactStore(root, owner["run_id"])
        manifest = store.read_run_manifest()
        _require(manifest["summary"].get("status") != "running", "run is not terminal")
        input_meta = manifest.get("project_metadata", {}).get("runner_eval_input")
        _require(
            isinstance(input_meta, dict), "run manifest lacks built-in input identity"
        )
        combined = input_meta.get("schema") == "opencode-eval-runner/eval-input-set/v2"
        family = input_meta.get("family")
        _require(family in {"agent-runtime", "skill"}, "run input family is invalid")
        _require(
            input_meta.get("contract")
            == ("agent-runtime/v1" if family == "agent-runtime" else "skill-cases/v1"),
            "run input contract does not match family",
        )
        if combined:
            _require(
                family == "skill"
                and isinstance(input_meta.get("inputs"), list)
                and len(input_meta["inputs"]) >= 2,
                "combined input set is invalid",
            )
            for ordinal, source in enumerate(input_meta["inputs"], 1):
                _require(
                    type(source) is dict
                    and set(source)
                    == {"ordinal", "path", "skill", "contract", "sha256"},
                    "combined input provenance is invalid",
                )
                _require(
                    source["ordinal"] == ordinal
                    and type(source["path"]) is str
                    and bool(source["path"])
                    and type(source["skill"]) is str
                    and bool(source["skill"])
                    and source["contract"] == "skill-cases/v1"
                    and re.fullmatch(r"[0-9a-f]{64}", source["sha256"] or "")
                    is not None,
                    "combined input provenance fields are invalid",
                )
        else:
            _require(
                type(input_meta.get("sha256")) is str
                and re.fullmatch(r"[0-9a-f]{64}", input_meta["sha256"]) is not None,
                "run input digest is invalid",
            )
        jobs = []
        counts = {"pass": 0, "fail": 0, "non-evidence": 0, "error": 0, "not-run": 0}
        for item in manifest["jobs"]:
            status = item.get("status")
            _require(status in counts, "manifest contains an unresolved planned job")
            counts[status] += 1
        _require(
            counts["error"] == 0 and counts["not-run"] == 0,
            "run is ineligible for conforming output: a planned job has no family-owned result",
        )
        for item in manifest["jobs"]:
            status = item["status"]
            identity = ArtifactIdentity(
                manifest["run_id"], item["case"], item["iteration"]
            )
            if family == "skill":
                pair = store.read_paired_job_artifact(identity)
                _require(
                    pair["schema"] == EVAL_PAIRED_ARTIFACT_SCHEMA,
                    "skill job must use paired artifact",
                )
                meta = pair["project_metadata"].get("runner_eval", {})
                expected_family_schema = (
                    "opencode-eval-runner/eval-family-result/v2"
                    if combined
                    else "opencode-eval-runner/eval-family-result/v1"
                )
                _require(
                    meta.get("schema") == expected_family_schema
                    and meta.get("family") == family
                    and meta.get("case_id") == item["case"]
                    and meta.get("contract") == "skill-cases/v1",
                    "paired family identity mismatch",
                )
                if combined:
                    ordinal = meta.get("source_input")
                    _require(
                        type(ordinal) is int
                        and 1 <= ordinal <= len(input_meta["inputs"]),
                        "case source input ordinal is invalid",
                    )
                    source = input_meta["inputs"][ordinal - 1]
                    _require(
                        source["skill"] == meta["family_result"].get("skill")
                        and source["path"] == meta.get("source_path")
                        and source["sha256"] == meta.get("source_sha256"),
                        "case source input provenance mismatch",
                    )
                ref = _artifact_ref(
                    EVAL_PAIRED_ARTIFACT_SCHEMA,
                    item["artifact"],
                    pair["paired_artifact_evidence_id"],
                )
                job = _skill_result(pair, ref, source_input=ordinal if combined else None)
                if combined:
                    _require(job["identity"]["skill"] == source["skill"], "case skill provenance mismatch")
            else:
                artifact = store.read_job_artifact(identity)
                _require(
                    artifact["schema"] == EVAL_ARTIFACT_SCHEMA,
                    "agent job must use eval-artifact/v1",
                )
                meta = artifact["project_metadata"].get("runner_eval", {})
                _require(
                    meta.get("schema") == "opencode-eval-runner/eval-family-result/v1"
                    and meta.get("family") == family
                    and meta.get("case_id") == item["case"]
                    and meta.get("contract") == "agent-runtime/v1",
                    "artifact family identity mismatch",
                )
                ref = _artifact_ref(
                    EVAL_ARTIFACT_SCHEMA,
                    item["artifact"],
                    artifact["artifact_evidence_id"],
                )
                job = _agent_result(artifact, ref)
            _require(
                job["classification"] == status,
                "manifest/artifact classification mismatch",
            )
            jobs.append(job)
        summary = manifest["summary"]
        expected = {
            "pass": counts["pass"],
            "fail": counts["fail"],
            "non_evidence": counts["non-evidence"],
            "errors": counts["error"],
            "not_run": counts["not-run"],
            "total": len(manifest["jobs"]),
        }
        for key, value in expected.items():
            _require(
                summary.get("non-evidence" if key == "non_evidence" else key) == value,
                "manifest summary does not match terminal jobs",
            )
        expected_status = (
            "error"
            if expected["errors"] or expected["not_run"]
            else "verdict"
            if expected["fail"] or expected["non_evidence"]
            else "pass"
        )
        _require(
            summary.get("status") == expected_status,
            "manifest summary status does not match terminal jobs",
        )
        execution = {
            "mode": "skill-ablation" if family == "skill" else "agent-runtime",
            "selection": {
                "all": manifest["selection"].get("all", False),
                "selectors": manifest["selection"].get("selectors", []),
                "case_ids": manifest["selection"].get("cases", []),
            },
            "iterations": manifest["iterations"],
            "concurrency": manifest["concurrency"],
        }
        return {
            "schema": EVAL_OUTPUT_SCHEMA_V2 if combined else EVAL_OUTPUT_SCHEMA,
            "run": {
                "id": manifest["run_id"],
                "created_at": manifest["created_at"],
                "input": (
                    {
                        "family": family,
                        "contract": "skill-cases/v1",
                        "inputs": [
                            {
                                "ordinal": s["ordinal"],
                                "source_path": s["path"],
                                "contract": s["contract"],
                                "sha256": s["sha256"],
                                "skill": s["skill"],
                            }
                            for s in input_meta["inputs"]
                        ],
                    }
                    if combined
                    else {
                        "family": family,
                        "contract": "agent-runtime/v1"
                        if family == "agent-runtime"
                        else "skill-cases/v1",
                        "sha256": input_meta["sha256"],
                    }
                ),
                "execution": execution,
                "summary": {"status": summary["status"], **expected},
            },
            "cases": jobs,
        }
    except (EvalArtifactError, OSError, KeyError, TypeError, ValueError) as exc:
        raise EvalOutputError(f"cannot render verified run {root}: {exc}") from exc


def _json_tree(value: Any) -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        _require(math.isfinite(value), "output contains a non-finite number")
    elif type(value) is list:
        for item in value:
            _json_tree(item)
    elif type(value) is dict:
        _require(
            all(type(key) is str for key in value), "output object keys must be strings"
        )
        for item in value.values():
            _json_tree(item)
    else:
        raise EvalOutputError("output contains a non-JSON value")


def _exact_keys(value: Any, keys: set[str], where: str) -> None:
    _require(
        type(value) is dict and set(value) == keys,
        f"{where} does not match eval-output/v1 fields",
    )


def validate_output_model(model: dict[str, Any]) -> None:
    """Fail closed if the canonical projection drifts from the public v1 shape."""
    _json_tree(model)
    _exact_keys(model, {"schema", "run", "cases"}, "output")
    _require(
        model["schema"] in {EVAL_OUTPUT_SCHEMA, EVAL_OUTPUT_SCHEMA_V2}
        and type(model["cases"]) is list,
        "unsupported output schema or cases type",
    )
    combined = model["schema"] == EVAL_OUTPUT_SCHEMA_V2
    run = model["run"]
    _exact_keys(run, {"id", "created_at", "input", "execution", "summary"}, "run")
    _exact_keys(
        run["input"],
        {"family", "contract", "inputs"}
        if combined
        else {"family", "contract", "sha256"},
        "run.input",
    )
    _exact_keys(
        run["execution"],
        {"mode", "selection", "iterations", "concurrency"},
        "run.execution",
    )
    _exact_keys(
        run["execution"]["selection"],
        {"all", "selectors", "case_ids"},
        "run.execution.selection",
    )
    _exact_keys(
        run["execution"]["concurrency"],
        {"standard", "runtime"},
        "run.execution.concurrency",
    )
    _exact_keys(
        run["summary"],
        {"status", "pass", "fail", "non_evidence", "errors", "not_run", "total"},
        "run.summary",
    )
    _require(
        type(run["id"]) is str and bool(run["id"]) and type(run["created_at"]) is str,
        "run identity or timestamp is invalid",
    )
    _require(
        run["input"]["family"]
        in ({"skill"} if combined else {"agent-runtime", "skill"}),
        "run input family is invalid",
    )
    _require(
        run["input"]["contract"]
        == (
            "agent-runtime/v1"
            if run["input"]["family"] == "agent-runtime"
            else "skill-cases/v1"
        ),
        "run input contract is invalid",
    )
    if combined:
        sources = run["input"]["inputs"]
        _require(
            type(sources) is list and len(sources) >= 2, "run input sources are invalid"
        )
        for ordinal, source in enumerate(sources, 1):
            _exact_keys(
                source,
                {"ordinal", "source_path", "contract", "sha256", "skill"},
                f"run.input.inputs[{ordinal - 1}]",
            )
            _require(
                source["ordinal"] == ordinal
                and type(source["source_path"]) is str
                and bool(source["source_path"])
                and source["contract"] == "skill-cases/v1"
                and type(source["skill"]) is str
                and bool(source["skill"])
                and re.fullmatch(r"[0-9a-f]{64}", source["sha256"] or "") is not None,
                "run input source fields are invalid",
            )
    else:
        _require(
            type(run["input"]["sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", run["input"]["sha256"]) is not None,
            "run input digest is invalid",
        )
    execution = run["execution"]
    _require(
        execution["mode"]
        == (
            "agent-runtime"
            if run["input"]["family"] == "agent-runtime"
            else "skill-ablation"
        ),
        "run execution mode does not match family",
    )
    _require(
        type(execution["selection"]["all"]) is bool
        and type(execution["selection"]["selectors"]) is list
        and type(execution["selection"]["case_ids"]) is list,
        "run selection is invalid",
    )
    _require(
        type(execution["iterations"]) is int and execution["iterations"] >= 1,
        "run iterations is invalid",
    )
    _require(
        all(type(n) is int and n >= 0 for n in execution["concurrency"].values()),
        "run concurrency is invalid",
    )
    summary = run["summary"]
    _require(
        summary["status"] in {"pass", "verdict", "error"}
        and all(
            type(summary[k]) is int and summary[k] >= 0
            for k in summary
            if k != "status"
        ),
        "run summary is invalid",
    )
    _require(
        summary["total"]
        == sum(
            summary[k] for k in ("pass", "fail", "non_evidence", "errors", "not_run")
        ),
        "run summary counts are inconsistent",
    )
    case_keys = {
        "id",
        "family",
        "contract",
        "iteration",
        "execution_status",
        "classification",
        "error",
        "attempts",
        "evidence",
        "checks",
        "semantic",
        "family_result",
        "source_artifacts",
    }
    if combined:
        case_keys.update({"identity", "source_input"})
    observed_identities: set[tuple[str, str]] = set()
    for index, case in enumerate(model["cases"]):
        _exact_keys(case, case_keys, f"cases[{index}]")
        _require(
            case["family"] in {"agent-runtime", "skill"},
            f"cases[{index}].family is invalid",
        )
        _require(
            case["execution_status"] in {"complete", "error", "not-run"},
            f"cases[{index}].execution_status is invalid",
        )
        _require(
            case["classification"] in {"pass", "fail", "non-evidence", None},
            f"cases[{index}].classification is invalid",
        )
        _require(
            case["execution_status"] == "complete"
            and case["classification"] is not None
            and case["error"] is None
            and case["family_result"] is not None,
            f"cases[{index}] is not an eligible completed family result",
        )
        _require(
            case["family"] == run["input"]["family"]
            and case["contract"] == run["input"]["contract"],
            f"cases[{index}] family/contract does not match run",
        )
        _require(
            case["family_result"].get("kind")
            == (
                "agent-runtime/v1" if case["family"] == "agent-runtime" else "skill/v1"
            ),
            f"cases[{index}] family payload is missing or mismatched",
        )
        if case["family"] == "skill":
            family_result = case["family_result"]
            _exact_keys(
                family_result["case_identity"],
                {"case_id", "source_id", "authored_id", "source_index", "display_name"},
                f"cases[{index}].family_result.case_identity",
            )
            trap = family_result["trap"]
            _exact_keys(trap, {"declared", "text"}, f"cases[{index}].family_result.trap")
            for side_name in ("baseline", "candidate"):
                outcome_trap = family_result["ablation"][side_name]["skill_outcome"]["trap"]
                _exact_keys(
                    outcome_trap,
                    {"declared", "text", "observed", "evidence"},
                    f"cases[{index}].family_result.ablation.{side_name}.skill_outcome.trap",
                )
                if not trap["declared"]:
                    _require(
                        trap["text"] is None
                        and outcome_trap == {"declared": False, "text": None, "observed": None, "evidence": None},
                        f"cases[{index}] undeclared trap outcome is not null",
                    )
        if combined:
            _exact_keys(case["identity"], {"skill", "case"}, f"cases[{index}].identity")
            skill, case_id = case["identity"]["skill"], case["identity"]["case"]
            _require(
                type(skill) is str
                and bool(skill)
                and case_id == case["id"]
                and case_id
                == case["family_result"].get("case_identity", {}).get("case_id"),
                f"cases[{index}] composite identity is invalid",
            )
            ordinal = case["source_input"]
            _require(
                type(ordinal) is int and 1 <= ordinal <= len(run["input"]["inputs"]),
                f"cases[{index}] source_input is invalid",
            )
            source = run["input"]["inputs"][ordinal - 1]
            _require(
                source["skill"] == skill,
                f"cases[{index}] source skill does not match identity",
            )
            _require(
                case["family_result"].get("skill") == skill,
                f"cases[{index}] family skill does not match identity",
            )
            composite = (skill, case_id, case["iteration"])
            _require(
                composite not in observed_identities,
                f"cases[{index}] duplicate composite identity",
            )
            observed_identities.add(composite)
        for group in case["attempts"]:
            _exact_keys(group, {"phase", "attempts"}, f"cases[{index}].attempt group")
            for attempt in group["attempts"]:
                _exact_keys(
                    attempt,
                    {
                        "number",
                        "started_at",
                        "duration_seconds",
                        "invocation",
                        "host_exit_code",
                        "result",
                        "failure",
                        "retry_decision",
                    },
                    f"cases[{index}].attempt",
                )
                _exact_keys(
                    attempt["invocation"],
                    {
                        "transport",
                        "model",
                        "reasoning",
                        "agent",
                        "skill",
                        "workspace_mode",
                        "timeout_seconds",
                        "container_timeout",
                        "engine",
                        "network",
                        "image",
                        "expected_plugin",
                    },
                    f"cases[{index}].invocation",
                )
        _exact_keys(
            case["evidence"],
            {"status", "reasons", "required_boundaries", "runtime_evidence"},
            f"cases[{index}].evidence",
        )
        for check in case["checks"]:
            _exact_keys(
                check, {"name", "status", "reason", "metadata"}, f"cases[{index}].check"
            )
        if case["semantic"] is not None:
            _exact_keys(
                case["semantic"],
                {"status", "summary", "data"},
                f"cases[{index}].semantic",
            )
        for ref in case["source_artifacts"]:
            _exact_keys(
                ref,
                {"schema", "relative_path", "evidence_id"},
                f"cases[{index}].source artifact",
            )
            _require(
                ref["schema"] in {EVAL_ARTIFACT_SCHEMA, EVAL_PAIRED_ARTIFACT_SCHEMA}
                and type(ref["relative_path"]) is str
                and bool(ref["relative_path"])
                and type(ref["evidence_id"]) is str
                and re.fullmatch(r"[0-9a-f]{64}", ref["evidence_id"]) is not None,
                f"cases[{index}] source artifact reference is invalid",
            )


def _pretty(value: Any, depth: int = 0) -> str:
    """Readable Markdown tree that preserves every value and labels each field."""
    indent = "  " * depth
    if isinstance(value, dict):
        return (
            "\n".join(
                f"{indent}- **{k}:**\n{_pretty(v, depth + 1)}" for k, v in value.items()
            )
            or f"{indent}- *(none)*"
        )
    if isinstance(value, list):
        if not value:
            return f"{indent}- *(none)*"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.extend((f"{indent}-", _pretty(item, depth + 1)))
            else:
                lines.append(
                    f"{indent}- {json.dumps(item, ensure_ascii=False, allow_nan=False)}"
                )
        return "\n".join(lines)
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return f"{indent}{text}"


def _html_tree(value: Any) -> str:
    if isinstance(value, dict):
        if not value:
            return "<p>None.</p>"
        return (
            "<dl>"
            + "".join(
                f"<dt>{html.escape(str(k))}</dt><dd>{_html_tree(v)}</dd>"
                for k, v in value.items()
            )
            + "</dl>"
        )
    if isinstance(value, list):
        return (
            "<ul>"
            + (
                "".join(f"<li>{_html_tree(v)}</li>" for v in value)
                if value
                else "<li>None.</li>"
            )
            + "</ul>"
        )
    return (
        f"<p>{html.escape(json.dumps(value, ensure_ascii=False, allow_nan=False))}</p>"
    )


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False)
    if type(value) in {int, float}:
        return json.dumps(value, allow_nan=False)
    raise EvalOutputError("YAML scalar is not JSON-compatible")


def _yaml_tree(value: Any, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            return prefix + "{}"
        lines = []
        for key, item in value.items():
            label = json.dumps(key, ensure_ascii=False)
            if isinstance(item, (dict, list)) and item:
                lines.extend((prefix + label + ":", _yaml_tree(item, indent + 2)))
            else:
                lines.append(
                    prefix
                    + label
                    + ": "
                    + (
                        _yaml_tree(item, 0).strip()
                        if isinstance(item, (dict, list))
                        else _yaml_scalar(item)
                    )
                )
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return prefix + "[]"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)) and item:
                lines.extend((prefix + "-", _yaml_tree(item, indent + 2)))
            else:
                lines.append(
                    prefix
                    + "- "
                    + (
                        _yaml_tree(item, 0).strip()
                        if isinstance(item, (dict, list))
                        else _yaml_scalar(item)
                    )
                )
        return "\n".join(lines)
    return prefix + _yaml_scalar(value)


def _combined_skill_groups(
    cases: list[dict[str, Any]],
) -> list[tuple[str, list[tuple[str, list[dict[str, Any]]]]]]:
    skills: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for case in cases:
        skill = case["identity"]["skill"]
        case_id = case["identity"]["case"]
        skills.setdefault(skill, {}).setdefault(case_id, []).append(case)
    return [
        (
            skill,
            [
                (case_id, sorted(iterations, key=lambda item: item["iteration"]))
                for case_id, iterations in grouped.items()
            ],
        )
        for skill, grouped in skills.items()
    ]


def _skill_iteration_summary(case: dict[str, Any]) -> tuple[str, str]:
    result = case["family_result"]
    ablation = result["ablation"]
    comparison = ablation["comparison"]
    baseline = ablation["baseline"]["classification"]
    candidate = ablation["candidate"]["classification"]
    comparison_status = comparison["status"]
    decision = comparison.get("decision")
    data = (decision or {}).get("data", {})
    baseline_score = data.get("baseline_score")
    candidate_score = data.get("candidate_score")
    delta = data.get("delta_pp", comparison.get("delta_pp", comparison.get("delta")))
    comparison_classification = (
        decision["classification"] if decision else comparison_status
    )
    outcome = (
        f"Baseline: {baseline} ({_percent(baseline_score)}); "
        f"candidate: {candidate} ({_percent(candidate_score)}). "
        f"Candidate absolute pass: {'yes' if candidate == 'pass' else 'no' if candidate == 'fail' else 'unavailable'}. "
        f"Comparison: {comparison_classification} ({comparison_status}); "
        f"delta: {_percentage_points(delta)}; "
        f"skill value: {data.get('skill_value', 'unavailable')}. "
        f"Trap change: {_trap_change(case)}"
    )
    detail = _pretty(comparison)
    return outcome, detail


def _percent(value: Any) -> str:
    return f"{value * 100:.2f}%" if type(value) in (int, float) else "unavailable"


def _percentage_points(value: Any) -> str:
    return f"{value:+.2f} percentage points" if type(value) in (int, float) else "unavailable"


def _trap_change(case: dict[str, Any]) -> str:
    family = case["family_result"]
    trap = family["trap"]
    if not trap["declared"]:
        return "no trap declared; not applicable"
    baseline = family["ablation"]["baseline"]["skill_outcome"]["trap"]["observed"]
    candidate = family["ablation"]["candidate"]["skill_outcome"]["trap"]["observed"]
    if baseline is None or candidate is None:
        return "unavailable"
    if baseline and not candidate:
        return "fixed"
    if candidate and not baseline:
        return "regressed"
    return "observed on both sides" if candidate else "not observed on either side"


def _agent_narrative(case: dict[str, Any]) -> list[str]:
    family = case["family_result"]
    lines = [f"Suite: {family['suite']['name']}; agent: {family['case']['agent']}; execution: {family['case']['execution']}; classification: {case['classification']}."]
    assertions = family["assertions"]
    for assertion in assertions:
        lines.append(f"Assertion ({assertion['kind']}): {assertion['status']} — {assertion['reason'] or 'no reason recorded'}; authored: {json.dumps(assertion['authored'], ensure_ascii=False)}")
        observed = assertion.get("observed")
        if isinstance(observed, list):
            for observation in observed:
                lines.append(f"Observed evidence: tool {observation['tool'].get('value', 'unavailable')}; input {json.dumps(observation['input'].get('value'), ensure_ascii=False)}; outcome {observation['outcome']}; result {json.dumps(observation['result'].get('value'), ensure_ascii=False)}")
        elif observed is not None:
            lines.append(f"Observed evidence: {json.dumps(observed, ensure_ascii=False)}")
    if not assertions:
        lines.append("Assertions: none authored/applicable.")
    judge = family["semantic_judge"]
    if judge:
        lines.append(f"Semantic judge: {'PASS' if judge['passed'] else 'FAIL'} — {judge['summary']}")
        for expectation in judge["expectations"]:
            lines.append(f"Semantic expectation {'met' if expectation['met'] else 'not met'}: {expectation['expectation']} — {expectation['reason']}")
        for violation in judge["violations"]:
            lines.append(f"Forbidden rule {'violated' if violation['violated'] else 'not violated'}: {violation['rule']} — {violation['reason']}")
        lines.append(f"Declared trap: {family['case']['trap']}; observed: {judge['trap_observed']}; evidence: {judge['trap_evidence']}")
    else:
        lines.append("Semantic judge: not run/unavailable.")
    lines.extend(_attempt_narrative(case["attempts"], case["checks"], case["evidence"]))
    return lines


def _attempt_narrative(groups: list[dict[str, Any]], checks: list[dict[str, Any]], evidence: dict[str, Any]) -> list[str]:
    lines = []
    for group in groups:
        attempts = group["attempts"]
        def attempt_summary(attempt: dict[str, Any]) -> str:
            result = attempt["result"]
            if result is None:
                result_text = "result unavailable"
            else:
                exit_code = result.get("exit_code") if isinstance(result, dict) else None
                result_text = "result recorded" + (f" (reported exit code {exit_code})" if type(exit_code) is int else "")
            retry = attempt["retry_decision"]
            retry_text = retry.get("decision", "recorded") if isinstance(retry, dict) else retry
            reason = retry.get("reason") if isinstance(retry, dict) else None
            return f"attempt {attempt['number']} — {result_text}; retry {retry_text}" + (f" ({reason})" if reason else "")
        lines.append(f"{group['phase']} attempts: " + ("; ".join(attempt_summary(a) for a in attempts) if attempts else "none recorded."))
    lines.append("Checks: " + ("; ".join(f"{check['name']} — {check['status']}{(': ' + check['reason']) if check['reason'] else ''}" for check in checks) if checks else "none recorded."))
    lines.append(f"Evidence readiness: {evidence['status']}" + (f" — {', '.join(evidence['reasons'])}" if evidence["reasons"] else ""))
    return lines


def _literal_json(value: Any) -> str:
    # Indented JSON in a fence preserves Markdown-significant captured text literally.
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n```"


def _md_literal(value: Any) -> str:
    return html.escape(str(value), quote=False).replace("\n", " ")


def _skill_case_label(case_id: str, iterations: list[dict[str, Any]]) -> str:
    result = iterations[0]["family_result"]
    identity = result["case_identity"]
    readable = identity["display_name"] or identity["source_id"]
    return f"{result['skill']}: {readable}"


def _combined_markdown(model: dict[str, Any]) -> str:
    run = model["run"]
    summary = run["summary"]
    sections = [
        "# Evaluation run",
        "",
        f"## Run {run['id']}",
        "",
        f"- **Created:** {run['created_at']}",
        f"- **Status:** {summary['status']}",
        (
            f"- **Jobs:** {summary['total']} total; {summary['pass']} pass, {summary['fail']} fail, "
            f"{summary['non_evidence']} non-evidence, {summary['errors']} errors, {summary['not_run']} not run"
        ),
        "",
        "Raw captured stdout/stderr are process streams, not assistant answers or judge verdicts.",
    ]
    for skill_index, (skill, grouped_cases) in enumerate(
        _combined_skill_groups(model["cases"]), 1
    ):
        sections.extend(("", f"### Skill {_md_literal(skill)}"))
        for case_index, (case_id, iterations) in enumerate(grouped_cases, 1):
            sections.extend(
                (
                    "",
                    f"#### Case {_md_literal(_skill_case_label(case_id, iterations))}",
                    "",
                    f"Canonical case ID: {_md_literal(case_id)}",
                    "",
                    "**Iterations:**",
                )
            )
            for case in iterations:
                sections.append(
                    f"- Iteration {case['iteration']} — {case['classification']}"
                )
            for case in iterations:
                outcome, comparison = _skill_iteration_summary(case)
                sides = case["family_result"]["ablation"]
                side_lines = []
                for side_name in ("baseline", "candidate"):
                    side = sides[side_name]
                    side_lines.append(f"**{side_name.title()} result:** {side['classification']}; evidence readiness {side['evidence']['status']}; checks " + ("; ".join(f"{c['name']} — {c['status']}" for c in side["checks"]) or "none recorded."))
                    for item in side["skill_outcome"]["expectations"]:
                        side_lines.append(f"- Expectation {'met' if item['met'] else 'not met'}: {_md_literal(item['text'])}" + (f" — {_md_literal(item['reason'])}" if item["reason"] else ""))
                    for item in side["skill_outcome"]["negative_expectations"]:
                        side_lines.append(f"- Negative expectation {'violated' if item['violated'] else 'not violated'}: {_md_literal(item['text'])}" + (f" — {_md_literal(item['reason'])}" if item["reason"] else ""))
                side_lines.extend(_attempt_narrative(case["attempts"], case["checks"], case["evidence"]))
                sections.extend(
                    (
                        "",
                        f"##### Iteration {case['iteration']} — {case['classification']}",
                        "",
                        outcome,
                        "",
                        *side_lines,
                        "",
                        "**Per-iteration comparison:**",
                        comparison,
                        "",
                        "**Captured answers and evidence — supporting details:**",
                        "Full verified iteration record follows. Raw stdout/stderr fields remain raw process streams.",
                        "",
                        _literal_json(case),
                    )
                )
    sections.extend(
        ("", "## Run details", "", _pretty(run["input"]), "", _pretty(run["execution"]))
    )
    return "\n".join(sections) + "\n"


def _combined_html(model: dict[str, Any]) -> str:
    run = model["run"]
    summary = run["summary"]
    sections = [
        f"<section><h2>Run {html.escape(run['id'])}</h2>",
        f"<p>Created: {html.escape(run['created_at'])}</p>",
        f"<p>Status: {html.escape(summary['status'])}</p>",
        "<p>Jobs: {} total; {} pass, {} fail, {} non-evidence, {} errors, {} not run</p>".format(
            summary["total"],
            summary["pass"],
            summary["fail"],
            summary["non_evidence"],
            summary["errors"],
            summary["not_run"],
        ),
        "<p>Raw captured stdout/stderr are process streams, not assistant answers or judge verdicts.</p>",
    ]
    contents = ['<nav aria-label="Report contents"><h2>Contents</h2><ul>']
    sections_by_skill = []
    for skill_index, (skill, grouped_cases) in enumerate(
        _combined_skill_groups(model["cases"]), 1
    ):
        skill_anchor = f"skill-{skill_index}"
        skill_sections = [
            f'<section><h3 id="{skill_anchor}">Skill {html.escape(skill)}</h3>'
        ]
        contents.append(
            f'<li><a href="#{skill_anchor}">Skill {html.escape(skill)}</a><ul>'
        )
        for case_index, (case_id, iterations) in enumerate(grouped_cases, 1):
            case_anchor = f"case-{html.escape(case_id, quote=True)}"
            case_label = html.escape(_skill_case_label(case_id, iterations))
            skill_sections.append(
                f'<section><h4 id="{case_anchor}">Case {case_label}</h4>'
                f'<p class="case-id">Canonical case ID: <code>{html.escape(case_id)}</code></p>'
                "<h5>Iteration status index</h5><ul>"
            )
            contents.append(f'<li><a href="#{case_anchor}">Case {case_label}</a></li>')
            for case in iterations:
                anchor = f"{case_anchor}-iteration-{case['iteration']}"
                skill_sections.append(
                    f'<li><a href="#{anchor}">Iteration {case["iteration"]} — '
                    f"{html.escape(str(case['classification']))}</a></li>"
                )
            skill_sections.append("</ul>")
            for case in iterations:
                outcome, _comparison = _skill_iteration_summary(case)
                ablation = case["family_result"]["ablation"]
                side_summary = " ".join(f"{name.title()}: {ablation[name]['classification']}; readiness {ablation[name]['evidence']['status']}." for name in ("baseline", "candidate"))
                side_details = []
                for name in ("baseline", "candidate"):
                    side = ablation[name]
                    side_details.append(f"<h6>{name.title()} expectations</h6><ul>" + "".join(f"<li>Expectation {'met' if item['met'] else 'not met'}: {html.escape(item['text'])}{(': ' + html.escape(item['reason'])) if item['reason'] else ''}</li>" for item in side['skill_outcome']['expectations']) + "</ul><h6>Negative expectations</h6><ul>" + "".join(f"<li>Negative expectation {'violated' if item['violated'] else 'not violated'}: {html.escape(item['text'])}{(': ' + html.escape(item['reason'])) if item['reason'] else ''}</li>" for item in side['skill_outcome']['negative_expectations']) + "</ul>")
                attempts_summary = " ".join(_attempt_narrative(case["attempts"], case["checks"], case["evidence"]))
                anchor = f"{case_anchor}-iteration-{case['iteration']}"
                skill_sections.extend(
                    (
                        f'<section><h5 id="{anchor}">Iteration {case["iteration"]} — {html.escape(str(case["classification"]))}</h5>',
                        f"<p>{html.escape(outcome)}</p><p>{html.escape(side_summary)}</p>{''.join(side_details)}<p>{html.escape(attempts_summary)}</p><h6>Per-iteration comparison</h6>{_html_tree(case['family_result']['ablation']['comparison'])}",
                        f"<details><summary>Captured answers and evidence — iteration {case['iteration']}</summary>",
                        "<p>Full verified iteration record. Raw stdout/stderr fields are raw process streams, not answers or verdicts.</p>",
                        _html_tree(case),
                        "</details></section>",
                    )
                )
            skill_sections.append("</section>")
        contents.append("</ul></li>")
        skill_sections.append("</section>")
        sections_by_skill.extend(skill_sections)
    contents.append("</ul></nav>")
    sections.extend(contents)
    sections.extend(sections_by_skill)
    sections.append(
        f"<section><h2>Run details</h2>{_html_tree(run['input'])}{_html_tree(run['execution'])}</section></section>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>body{{overflow-wrap:anywhere;word-break:break-word}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%}}code{{overflow-wrap:anywhere}}.case-id{{font-size:.9em}}dl{{margin:.25rem 0}}dt{{font-weight:600;margin-block-start:.5rem}}dd{{margin-inline-start:0}}ul,ol{{padding-inline-start:0;list-style-position:inside}}li>ul,li>ol{{padding-inline-start:0}}</style>"
        "<title>Evaluation run</title></head><body><main><h1>Evaluation run</h1><p>Schema: {}</p>{}</main></body></html>\n"
    ).format(html.escape(model["schema"]), "".join(sections))


def serialize_output(model: dict[str, Any], format: str) -> bytes:
    _require(format in FORMATS, f"unsupported output format: {format}")
    validate_output_model(model)
    if format == "json":
        text = json.dumps(model, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    elif format == "yaml":
        text = _yaml_tree(model) + "\n"
    elif format == "markdown":
        if model["schema"] == EVAL_OUTPUT_SCHEMA_V2:
            text = _combined_markdown(model)
        else:
            sections = [
                "# Evaluation run",
                "",
                f"## Run {model['run']['id']}",
                "",
                f"- **Created:** {model['run']['created_at']}",
                f"- **Family / mode:** {model['run']['input']['family']} / {model['run']['execution']['mode']}",
                f"- **Status:** {model['run']['summary']['status']} — {model['run']['summary']['pass']} pass, {model['run']['summary']['fail']} fail, {model['run']['summary']['non_evidence']} non-evidence ({model['run']['summary']['total']} jobs)",
            ]
            cases = model["cases"]
            groups: dict[str, list[dict[str, Any]]] = {}
            for case in cases:
                family = case["family_result"]
                label = family.get("skill", "") if case["family"] == "skill" else (family["case"].get("skill") or "")
                groups.setdefault(label or "Evaluation", []).append(case)
            for skill, grouped in groups.items():
                sections.extend(("", f"## {_md_literal(skill)}", ""))
                for case in grouped:
                    identity = case["family_result"].get("case_identity", {})
                    display = identity.get("display_name") or identity.get("source_id") or case["id"]
                    sections.extend((f"### Case {_md_literal(display)}", f"Canonical case ID: {_md_literal(case['id'])}", "", f"#### Iteration {case['iteration']} — {case['classification']}", ""))
                    if case["family"] == "skill":
                        outcome, _ = _skill_iteration_summary(case)
                        sections.append(outcome)
                        for side_name in ("baseline", "candidate"):
                            side = case["family_result"]["ablation"][side_name]
                            sections.extend(("", f"**{side_name.title()} checks/readiness:** {side['evidence']['status']}; " + ("; ".join(f"{check['name']} — {check['status']}" for check in side["checks"]) or "no checks recorded.")))
                            for item in side["skill_outcome"]["expectations"]:
                                sections.append(f"- Expectation {'met' if item['met'] else 'not met'}: {item['text']}" + (f" — {item['reason']}" if item["reason"] else ""))
                            for item in side["skill_outcome"]["negative_expectations"]:
                                sections.append(f"- Negative expectation {'violated' if item['violated'] else 'not violated'}: {item['text']}" + (f" — {item['reason']}" if item["reason"] else ""))
                        sections.extend(_attempt_narrative(case["attempts"], case["checks"], case["evidence"]))
                    else:
                        sections.extend("")
                        for narrative_line in _agent_narrative(case):
                            sections.extend((narrative_line, ""))
                    sections.extend(("", "**Captured answers and evidence — supporting details:**", "", _literal_json(case)))
            sections.extend(("", "## Run details", "", _literal_json(model["run"])))
            text = "\n".join(sections) + "\n"
    else:
        if model["schema"] == EVAL_OUTPUT_SCHEMA_V2:
            text = _combined_html(model)
        else:
            run = model["run"]
            summary = run["summary"]
            sections = [f"<section><h2>Run {html.escape(run['id'])}</h2><p>Created: {html.escape(run['created_at'])}</p><p>Family / mode: {html.escape(run['input']['family'])} / {html.escape(run['execution']['mode'])}</p><p>Status: {html.escape(summary['status'])} — {summary['pass']} pass, {summary['fail']} fail, {summary['non_evidence']} non-evidence ({summary['total']} jobs)</p>"]
            for case in model["cases"]:
                heading = f"Case {case['id']} — {case['family']} iteration {case['iteration']}"
                identity = case["family_result"].get("case_identity", {})
                label = str(identity.get("display_name") or identity.get("source_id") or case["id"])
                narrative = "".join("<p>" + html.escape(line) + "</p>" for line in _agent_narrative(case)) if case["family"] == "agent-runtime" else f"<p>{html.escape(_skill_iteration_summary(case)[0])}</p>"
                details = _html_tree(case)
                sections.append(f"<section><h3>{html.escape(heading)} — {html.escape(label)}</h3>{narrative}<details><summary>Captured answers and evidence — iteration {case['iteration']}</summary>{details}</details></section>")
            sections.append("</section>")
            text = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{{overflow-wrap:anywhere;word-break:break-word}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%}}code{{overflow-wrap:anywhere}}dl{{margin:.25rem 0}}dd{{margin-inline-start:0}}ul,ol{{padding-inline-start:1rem}}</style><title>Evaluation run</title></head><body><main><h1>Evaluation run</h1><p>Schema: {}</p>{}</main></body></html>\n'.format(
                html.escape(model["schema"]), "".join(sections)
            )
    return text.encode("utf-8")


def write_output(
    model: dict[str, Any],
    format: str,
    destination: str | os.PathLike[str] | None,
    stdout: Any,
    *,
    run_directory: str | os.PathLike[str] | None = None,
) -> None:
    payload = serialize_output(model, format)
    if destination is None:
        try:
            stdout.write(payload.decode("utf-8"))
            stdout.flush()
        except (OSError, UnicodeError) as exc:
            raise EvalOutputError(f"cannot write output to stdout: {exc}") from exc
        return
    path = Path(destination)
    temp: Path | None = None
    try:
        run_root = Path(run_directory).resolve() if run_directory is not None else None
        resolved = path.resolve()
        if run_root is not None and (
            resolved == run_root or run_root in resolved.parents
        ):
            raise EvalOutputError(
                "output destination must not be inside the durable run directory"
            )
        if path.exists() and path.is_dir():
            raise EvalOutputError("output destination is a directory")
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                existing = None
            if isinstance(existing, dict) and existing.get("schema") in {
                "opencode-eval-runner/eval-run/v1",
                EVAL_ARTIFACT_SCHEMA,
                EVAL_PAIRED_ARTIFACT_SCHEMA,
            }:
                raise EvalOutputError("output destination is an existing v1 record")
        with tempfile.NamedTemporaryFile(
            dir=path.parent or Path("."),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, resolved)
        temp = None
    except EvalOutputError:
        raise
    except OSError as exc:
        raise EvalOutputError(f"cannot write output destination {path}: {exc}") from exc
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
