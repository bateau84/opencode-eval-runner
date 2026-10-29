from __future__ import annotations

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from container.runtime_evidence import (
    build_runtime_evidence,
    field_available,
    field_unavailable,
    unsupported_runtime_evidence,
)
from runner.cli import parser
from runner.eval_artifacts import (
    EvalArtifactError,
    RunArtifactStore,
    artifact_identity_for_job,
)
from runner.eval_cli import EVAL_EXIT_ERROR, EVAL_EXIT_PASS, EVAL_EXIT_VERDICT, run_eval
from runner.eval_execute import RESULT_SCHEMA
from runner.eval_input import combined_skill_case_id
from runner.eval_output import EvalOutputError, validate_output_model
from runner.eval_plan import build_run_plan
from runner.eval_types import ArtifactIdentity, NormalizedCase

TEST_OPENCODE_IMAGE = "a" * 64


def empty_complete_evidence():
    return build_runtime_evidence({
        "capture_started": True,
        "capture_ended": True,
        "records": [],
        "observer_failures": 0,
        "callback_failures": 0,
        "issues": [],
    })


def native_skill_evidence(skill: str, agent: str):
    def available(value):
        return {"state": "available", "value": value}

    start = {
        "kind": "native_start", "sequence": 1, "invocation_id": "native-1",
        "tool": available("skill"), "session_id": available("session-1"),
        "agent": available(agent), "message_id": available("message-1"),
        "call_id": available("call-1"), "parent_session_id": available(None),
        "input": available({"name": skill}), "boundary": "decoded-tool-execute",
    }
    terminal = {
        "kind": "native_terminal", "sequence": 2, "invocation_id": "native-1",
        "tool": available("skill"), "session_id": available("session-1"),
        "agent": available(agent), "message_id": available("message-1"),
        "call_id": available("call-1"), "outcome": "success",
        "boundary": "session.tool.success", "result": available({"content": "skill body"}),
    }
    return build_runtime_evidence({
        "capture_started": True,
        "capture_ended": True,
        "records": [start, terminal],
        "observer_failures": 0,
        "callback_failures": 0,
        "issues": [],
    })


def native_runtime_evidence():
    available = field_available
    return build_runtime_evidence({
        "capture_started": True, "capture_ended": True,
        "observer_failures": 0, "callback_failures": 0, "issues": [],
        "records": [
            {"kind": "native_start", "sequence": 1, "invocation_id": "runtime-1",
             "tool": available("read"), "session_id": available("session-1"),
             "agent": available("assistant"), "message_id": available("message-1"),
             "call_id": available("call-1"), "parent_session_id": available(None),
             "input": available({"filePath": "README.md"}), "boundary": "decoded-tool-execute"},
            {"kind": "native_terminal", "sequence": 2, "invocation_id": "runtime-1",
             "tool": available("read"), "session_id": available("session-1"),
             "agent": available("assistant"), "message_id": available("message-1"),
             "call_id": available("call-1"), "outcome": "success",
             "boundary": "session.tool.success", "result": available({"content": "ok"})},
        ],
    })


def runtime_action_missing_input_evidence():
    available = field_available
    records = [
        {"kind": "native_start", "sequence": 1, "invocation_id": "outer", "tool": available("execute"),
         "session_id": available("session-1"), "agent": available("assistant"), "message_id": available("m1"),
         "call_id": available("outer-call"), "parent_session_id": available(None), "input": available({"code": "return 1"}),
         "boundary": "tool-execute-before"},
        {"kind": "code_start", "sequence": 2, "invocation_id": "inner", "tool": available("runtimeevidence_innerEcho"),
         "session_id": available("session-1"), "agent": available("assistant"), "message_id": available("m1"),
         "call_id": available("outer-call"), "parent_invocation_id": "outer", "input": available({"value": 1}),
         "boundary": "decoded-code-tool-handler"},
        {"kind": "code_terminal", "sequence": 3, "invocation_id": "inner", "tool": available("runtimeevidence_innerEcho"),
         "session_id": available("session-1"), "agent": available("assistant"), "message_id": available("m1"),
         "call_id": available("outer-call"), "outcome": "success", "boundary": "tool-handler-return",
         "finality": field_unavailable("unsupported", "not captured")},
        {"kind": "native_terminal", "sequence": 4, "invocation_id": "outer", "tool": available("execute"),
         "session_id": available("session-1"), "agent": available("assistant"), "message_id": available("m1"),
         "call_id": available("outer-call"), "outcome": "success", "boundary": "session.tool.success",
         "result": available({"content": "done"})},
        {"kind": "native_start", "sequence": 5, "invocation_id": "read", "tool": available("read"),
         "session_id": available("session-1"), "agent": available("assistant"), "message_id": available("m2"),
         "call_id": available("read-call"), "parent_session_id": available(None), "input": field_unavailable("omitted", "capture policy"),
         "boundary": "decoded-tool-execute"},
        {"kind": "native_terminal", "sequence": 6, "invocation_id": "read", "tool": available("read"),
         "session_id": available("session-1"), "agent": available("assistant"), "message_id": available("m2"),
         "call_id": available("read-call"), "outcome": "success", "boundary": "session.tool.success",
         "result": available({"content": "ok"})},
    ]
    return build_runtime_evidence({
        "capture_started": True, "capture_ended": True, "records": records,
        "observer_failures": 0, "callback_failures": 0, "issues": [],
    })


def runner_result(*, text: str, evidence, agent: str | None = None, model: str = "provider/model", transport: str = "opencode", **extra):
    return {
        "schema": RESULT_SCHEMA,
        "transport": transport,
        "model": model,
        "reasoning": "provider-default",
        "reasoning_source": "provider-default",
        "exit_code": 0,
        "stderr": "",
        "text": text,
        "agent": agent,
        "tools": [],
        "actions": [],
        "skills_loaded": [],
        "session_id": "session-1",
        "runtime_evidence": evidence,
        **extra,
    }


def grade(expectations, forbidden, *, met=True, trap_observed=False):
    return json.dumps({
        "passed": bool(met and not trap_observed),
        "expectations": [{"expectation": item, "met": met, "reason": "observed" if met else "not observed"} for item in expectations],
        "violations": [{"rule": item, "violated": False, "reason": "not observed"} for item in forbidden],
        "trap_observed": trap_observed,
        "trap_evidence": "trap" if trap_observed else "not observed",
        "summary": "grade summary",
    })


class BuiltinInvoker:
    def __init__(self, *, agent_grade=None, skill_grades=None, runtime_evidence=None, skill_candidate_evidence=None):
        self.specs = []
        self.agent_grade = agent_grade
        self.skill_grades = skill_grades or [
            grade(["useful"], ["leaks"], met=False),
            grade(["useful"], ["leaks"], met=True),
        ]
        self.runtime_evidence = runtime_evidence or empty_complete_evidence()
        self.skill_candidate_evidence = skill_candidate_evidence
        self.skill_target_count = 0

    def __call__(self, spec):
        self.specs.append(spec)
        if spec.agent == "eval-judge":
            if self.agent_grade is not None:
                text = self.agent_grade
            else:
                text = self.skill_grades.pop(0)
            return 0, runner_result(text=text, evidence=empty_complete_evidence(), agent=spec.agent)
        if spec.agent in {"skill-baseline", "skill-eval"}:
            candidate = spec.agent == "skill-eval"
            evidence = (
                self.skill_candidate_evidence
                if candidate and self.skill_candidate_evidence is not None
                else native_skill_evidence(spec.skill or "helper", "skill-eval") if candidate and spec.transport == "opencode"
                else empty_complete_evidence()
            )
            return 0, runner_result(
                text="candidate response" if candidate else "baseline response",
                evidence=evidence,
                agent=spec.agent,
                skills_loaded=[spec.skill or "helper"] if candidate and spec.transport == "opencode" else [],
            )
        return 0, runner_result(text="target response", evidence=self.runtime_evidence, agent=spec.agent)


def write_agent_root(root: Path):
    (root / "agents").mkdir(parents=True)
    (root / "agents" / "assistant.md").write_text("---\nmode: primary\n---\nAssistant", encoding="utf-8")


def run_command(args, invoker):
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.dict(
        os.environ,
        {"OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE": TEST_OPENCODE_IMAGE},
        clear=False,
    ):
        result = run_eval(args, stdout=stdout, stderr=stderr, invoker=invoker, sleep=lambda _: None)
    return result, stdout.getvalue(), stderr.getvalue()


def test_builtin_agent_eval_uses_public_command_and_seals_family_metadata(tmp_path, monkeypatch):
    root = tmp_path / "project"
    write_agent_root(root)
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1,
        "name": "single",
        "cases": [{
            "id": "decision", "agent": "assistant", "execution": "role-decision",
            "requirements": ["BR-1"], "prompt": "Choose", "trap": "fabricate",
            "expectations": ["good", "safe"], "must_not": ["fake"],
        }],
    }))
    artifact_dir = tmp_path / "artifacts"
    judge = grade(["good", "safe"], ["fake"])
    invoker = BuiltinInvoker(agent_grade=judge)
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(artifact_dir),
    ])

    code, stdout, stderr = run_command(args, invoker)

    assert code == EVAL_EXIT_PASS
    assert '"schema": "opencode-eval-runner/eval-output/v1"' in stdout
    output = json.loads(stdout)
    validate_output_model(output)
    invalid_output = json.loads(stdout)
    invalid_output["cases"][0]["unexpected"] = True
    with pytest.raises(EvalOutputError, match=r"cases\[0\]"):
        validate_output_model(invalid_output)
    assert "Artifacts:" in stderr
    assert [spec.agent for spec in invoker.specs] == ["assistant", "eval-judge"]
    assert all(spec.model == "provider/model" for spec in invoker.specs)
    assert all(spec.require_local_image for spec in invoker.specs)
    assert all(
        spec.image == TEST_OPENCODE_IMAGE
        for spec in invoker.specs
    )
    assert all(spec.timeout_seconds == expected for spec, expected in zip(invoker.specs, [240, 120], strict=True))
    store = RunArtifactStore(artifact_dir, json.loads((artifact_dir / "run.json").read_text())["run_id"])
    manifest = store.read_run_manifest()
    identity = artifact_identity_for_job(manifest["run_id"], build_run_plan(
        manifest["run_id"],
        (NormalizedCase("decision", ("decision",), "standard", None, {}),),
        selectors=("decision",), select_all=False,
    ).jobs[0])
    artifact = store.read_job_artifact(identity)
    family = artifact["project_metadata"]["runner_eval"]
    assert family["family"] == "agent-runtime"
    assert family["contract"] == "agent-runtime/v1"
    assert family["case_id"] == "decision"
    assert family["family_result"]["case"]["execution"] == "role-decision"
    assert family["family_result"]["semantic_judge"]["passed"] is True
    assert len(artifact["project_metadata"]["runner_eval_invocations"]) == 2
    assert manifest["project_metadata"]["runner_eval_input"]["sha256"] == __import__("hashlib").sha256(source.read_bytes()).hexdigest()


def test_builtin_eval_rejects_missing_or_mutable_image_before_invoker():
    for image in (None, "registry.example/opencode:latest"):
        args = parser().parse_args([
            "eval", "--input", "not-read.json", "--family", "agent-runtime",
            "--target-model", "provider/model", "--all",
        ])
        invoker = BuiltinInvoker()
        stdout, stderr = io.StringIO(), io.StringIO()
        environment = (
            {"OPENCODE_EVAL_RUNNER_IMAGE": "registry.example/default:latest"}
            if image is None
            else {"OPENCODE_EVAL_RUNNER_OPENCODE_IMAGE": image}
        )

        with patch.dict(os.environ, environment, clear=True):
            code = run_eval(args, stdout=stdout, stderr=stderr, invoker=invoker)

        assert code == EVAL_EXIT_ERROR
        assert "image identity" in stderr.getvalue()
        assert image is None or image not in stderr.getvalue()
        assert invoker.specs == []


def test_render_run_projects_one_verified_result_without_invocation(tmp_path, monkeypatch):
    root = tmp_path / "project"
    write_agent_root(root)
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1, "name": "single", "cases": [{
            "id": "decision", "agent": "assistant", "execution": "role-decision",
            "requirements": ["BR-1"], "prompt": "Choose <safely>", "trap": "fabricate",
            "expectations": ["good", "safe"], "must_not": ["fake"],
        }],
    }))
    artifact_dir = tmp_path / "artifacts"
    invoker = BuiltinInvoker(agent_grade=grade(["good", "safe"], ["fake"]))
    monkeypatch.chdir(root)
    execute = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(artifact_dir), "--output", str(tmp_path / "execute.json"),
    ])
    code, _, _ = run_command(execute, invoker)
    assert code == EVAL_EXIT_PASS
    invocations = len(invoker.specs)
    manifest_before = (artifact_dir / "run.json").read_bytes()
    json_target = tmp_path / "same-run.json"
    json_args = parser().parse_args([
        "eval", "--render-run", str(artifact_dir), "--format", "json", "--output", str(json_target),
    ])
    assert run_command(json_args, invoker)[0] == EVAL_EXIT_PASS
    canonical = json.loads(json_target.read_text(encoding="utf-8"))
    for format in ("json", "yaml", "markdown", "html"):
        target = tmp_path / f"result.{format}"
        render = parser().parse_args([
            "eval", "--render-run", str(artifact_dir), "--format", format, "--output", str(target),
        ])
        code, stdout, stderr = run_command(render, invoker)
        assert code == EVAL_EXIT_PASS
        assert stdout == ""
        assert stderr == ""
        rendered = target.read_text(encoding="utf-8")
        if format == "json":
            assert json.loads(rendered) == canonical
        elif format == "yaml":
            import yaml
            assert yaml.safe_load(rendered) == canonical
        elif format == "markdown":
            assert "## Run " in rendered and "### Case decision" in rendered
            assert '"pass"' in rendered and "semantic_judge" in rendered
        else:
            assert "<main>" in rendered and "<h1>" in rendered
            assert "<section><h2>Run " in rendered and "<section><h3>Case decision" in rendered
            assert rendered.index("<section><h2>Run ") < rendered.index("<section><h3>Case decision") < rendered.index("</section>")
            assert "<dt>classification</dt>" in rendered
            assert "Choose &lt;safely&gt;" in rendered
        assert len(invoker.specs) == invocations
        assert (artifact_dir / "run.json").read_bytes() == manifest_before

    stdout_render = parser().parse_args(["eval", "--render-run", str(artifact_dir), "--format", "json"])
    stdout_code, stdout_payload, stdout_errors = run_command(stdout_render, invoker)
    assert stdout_code == EVAL_EXIT_PASS
    assert json.loads(stdout_payload)["schema"] == "opencode-eval-runner/eval-output/v1"
    assert stdout_errors == ""
    source_bytes = (artifact_dir / "run.json").read_bytes()
    overwrite = parser().parse_args([
        "eval", "--render-run", str(artifact_dir), "--format", "json",
        "--output", str(artifact_dir / "run.json"),
    ])
    failed_code, _, failed_stderr = run_command(overwrite, invoker)
    assert failed_code == EVAL_EXIT_ERROR
    assert "must not be inside" in failed_stderr
    assert (artifact_dir / "run.json").read_bytes() == source_bytes

    artifact_bytes = next((artifact_dir / "jobs").glob("*/*.json")).read_bytes()
    external_v1 = tmp_path / "external-artifact.json"
    external_v1.write_bytes(artifact_bytes)
    external_render = parser().parse_args([
        "eval", "--render-run", str(artifact_dir), "--format", "json", "--output", str(external_v1),
    ])
    external_code, _, external_stderr = run_command(external_render, invoker)
    assert external_code == EVAL_EXIT_ERROR
    assert "existing v1 record" in external_stderr
    assert external_v1.read_bytes() == artifact_bytes

    impossible = parser().parse_args([
        "eval", "--render-run", str(artifact_dir), "--format", "json",
        "--output", str(tmp_path / "missing-parent" / "result.json"),
    ])
    impossible_code, impossible_stdout, _ = run_command(impossible, invoker)
    assert impossible_code == EVAL_EXIT_ERROR
    assert impossible_stdout == ""
    assert (artifact_dir / "run.json").read_bytes() == source_bytes
    assert next((artifact_dir / "jobs").glob("*/*.json")).read_bytes() == artifact_bytes


def test_render_run_rejects_corrupt_source_and_protects_source_records(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / ".eval-run-owner.json").write_text('{"run_id":"broken"}')
    (run / "run.json").write_text("{}")
    before = (run / "run.json").read_bytes()
    args = parser().parse_args(["eval", "--render-run", str(run)])

    code, stdout, stderr = run_command(args, BuiltinInvoker())

    assert code == EVAL_EXIT_ERROR
    assert stdout == ""
    assert "cannot render verified run" in stderr
    assert (run / "run.json").read_bytes() == before


def test_pre_result_failure_never_emits_output_and_render_rejects_run(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from runner import eval_builtin

    root = tmp_path / "project"
    write_agent_root(root)
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1, "name": "single", "cases": [{
            "id": "decision", "agent": "assistant", "execution": "role-decision",
            "requirements": ["BR"], "prompt": "Choose", "trap": "trap",
            "expectations": ["one", "two"], "must_not": ["none"],
        }],
    }))
    artifact_dir = tmp_path / "failed-run"
    output_path = tmp_path / "must-not-exist.json"

    @contextmanager
    def fail_before_result(self, case, iteration):
        del self, case, iteration
        raise RuntimeError("pre-result preparation failure")
        yield

    monkeypatch.setattr(eval_builtin.AgentRuntimeAdapter, "prepare", fail_before_result)
    monkeypatch.chdir(root)
    execute = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(artifact_dir), "--output", str(output_path),
    ])

    code, stdout, stderr = run_command(execute, BuiltinInvoker())

    assert code == EVAL_EXIT_ERROR
    assert stdout == ""
    assert "ineligible for conforming output" in stderr
    assert not output_path.exists()
    manifest = json.loads((artifact_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["jobs"][0]["status"] == "error"
    assert manifest["summary"]["status"] == "error"

    render = parser().parse_args(["eval", "--render-run", str(artifact_dir), "--format", "json"])
    render_code, render_stdout, render_stderr = run_command(render, BuiltinInvoker())
    assert render_code == EVAL_EXIT_ERROR
    assert render_stdout == ""
    assert "ineligible for conforming output" in render_stderr


def test_invalid_builtin_input_is_rejected_before_any_invocation(tmp_path, monkeypatch):
    root = tmp_path / "project"
    write_agent_root(root)
    source = tmp_path / "invalid.json"
    source.write_text('{"version":1,"name":"suite","cases":[],"extra":true}')
    invoker = BuiltinInvoker()
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model", "--all",
    ])

    code, _, stderr = run_command(args, invoker)

    assert code == EVAL_EXIT_ERROR
    assert "unknown field" in stderr
    assert invoker.specs == []


def test_builtin_selection_conflict_and_cross_family_controls_reject_before_invoke(tmp_path, monkeypatch):
    root = tmp_path / "project"
    write_agent_root(root)
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1, "name": "suite", "cases": [{
            "id": "a", "agent": "assistant", "execution": "role-decision",
            "requirements": ["BR"], "prompt": "p", "trap": "t",
            "expectations": ["one", "two"], "must_not": ["no"],
        }],
    }))
    invoker = BuiltinInvoker()
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model",
        "--all", "--cases", "a",
    ])

    code, _, stderr = run_command(args, invoker)

    assert code == EVAL_EXIT_ERROR
    assert "exactly one" in stderr
    assert invoker.specs == []


def test_unready_runtime_evidence_suppresses_agent_judge(tmp_path, monkeypatch):
    root = tmp_path / "project"
    write_agent_root(root)
    (root / "skills").mkdir()
    (root / "node_modules").mkdir()
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1, "name": "suite", "cases": [{
            "id": "runtime", "agent": "assistant", "execution": "runtime",
            "requirements": ["BR"], "prompt": "p", "trap": "t",
            "expectations": ["one", "two"], "must_not": ["no"],
        }],
    }))
    invoker = BuiltinInvoker(runtime_evidence=unsupported_runtime_evidence("not captured"))
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(artifact_dir),
    ])

    code, _, _ = run_command(args, invoker)

    assert code == EVAL_EXIT_VERDICT
    assert [spec.agent for spec in invoker.specs] == ["assistant"]
    manifest = json.loads((artifact_dir / "run.json").read_text())
    store = RunArtifactStore(artifact_dir, manifest["run_id"])
    identity = artifact_identity_for_job(manifest["run_id"], build_run_plan(
        manifest["run_id"],
        (NormalizedCase("runtime", ("runtime",), "runtime", None, {}),),
        selectors=("runtime",), select_all=False,
    ).jobs[0])
    artifact = store.read_job_artifact(identity)
    assert artifact["classification"] == "non-evidence"
    assert artifact["target"]["evidence_readiness"]["status"] == "unsupported"
    assert artifact["judge"]["attempts"] == []


def test_complete_nonempty_runtime_capture_reaches_agent_judge(tmp_path, monkeypatch):
    root = tmp_path / "project"
    write_agent_root(root)
    (root / "skills").mkdir()
    (root / "node_modules").mkdir()
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1, "name": "suite", "cases": [{
            "id": "runtime", "agent": "assistant", "execution": "runtime",
            "requirements": ["BR"], "prompt": "p", "trap": "t",
            "expectations": ["one", "two"], "must_not": ["no"],
        }],
    }))
    invoker = BuiltinInvoker(agent_grade=grade(["one", "two"], ["no"]), runtime_evidence=native_runtime_evidence())
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(tmp_path / "artifacts"),
    ])

    code, _, _ = run_command(args, invoker)

    assert code == EVAL_EXIT_PASS
    assert [spec.agent for spec in invoker.specs] == ["assistant", "eval-judge"]


def test_tool_only_action_still_requires_input_readiness(tmp_path, monkeypatch):
    root = tmp_path / "project"
    write_agent_root(root)
    (root / "skills").mkdir()
    (root / "node_modules").mkdir()
    source = tmp_path / "suite.json"
    source.write_text(json.dumps({
        "version": 1, "name": "suite", "cases": [{
            "id": "runtime", "agent": "assistant", "execution": "runtime",
            "requirements": ["BR"], "prompt": "p", "trap": "t",
            "expectations": ["one", "two"], "must_not": ["no"],
            "actions": {"requires": [{"tool": "read"}]},
        }],
    }))
    invoker = BuiltinInvoker(runtime_evidence=runtime_action_missing_input_evidence())
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "agent-runtime", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(artifact_dir),
    ])

    code, _, _ = run_command(args, invoker)

    assert code == EVAL_EXIT_VERDICT
    assert [spec.agent for spec in invoker.specs] == ["assistant"]
    manifest = json.loads((artifact_dir / "run.json").read_text())
    store = RunArtifactStore(artifact_dir, manifest["run_id"])
    identity = artifact_identity_for_job(manifest["run_id"], build_run_plan(
        manifest["run_id"],
        (NormalizedCase("runtime", ("runtime",), "runtime", None, {}),),
        selectors=("runtime",), select_all=False,
    ).jobs[0])
    artifact = store.read_job_artifact(identity)
    assert artifact["target"]["evidence_readiness"]["status"] == "incomplete"
    assertion = artifact["project_metadata"]["runner_eval"]["family_result"]["assertions"][0]
    assert assertion["authored"] == {"tool": "read"}
    assert assertion["status"] == "non-evidence"
    assert artifact["judge"]["attempts"] == []


def test_skill_eval_runs_four_phases_and_preserves_comparison_and_pair_integrity(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "skills" / "helper").mkdir(parents=True)
    (root / "skills" / "helper" / "SKILL.md").write_text("Method", encoding="utf-8")
    source = tmp_path / "skill.json"
    source.write_text(json.dumps({"skill": "helper", "cases": [{
        "id": "smoke", "prompt": "Help", "expectations": ["useful"],
        "negative_expectations": ["leaks"], "trap": "unsafe",
    }]}))
    artifact_dir = tmp_path / "artifacts"
    invoker = BuiltinInvoker()
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "skill", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(artifact_dir),
    ])

    code, _, _ = run_command(args, invoker)

    assert code == EVAL_EXIT_PASS
    assert [spec.agent for spec in invoker.specs] == ["skill-baseline", "eval-judge", "skill-eval", "eval-judge"]
    assert [spec.skill for spec in invoker.specs] == [None, None, "helper", None]
    assert all(spec.require_local_image for spec in invoker.specs)
    assert all(spec.image == TEST_OPENCODE_IMAGE for spec in invoker.specs)
    assert len(invoker.specs) == 4
    manifest = json.loads((artifact_dir / "run.json").read_text())
    store = RunArtifactStore(artifact_dir, manifest["run_id"])
    job = build_run_plan(
        manifest["run_id"],
        (NormalizedCase("skill:helper:smoke", ("skill:helper:smoke",), "standard", None, {}),),
        selectors=("skill:helper:smoke",), select_all=False,
    ).jobs[0]
    identity = artifact_identity_for_job(manifest["run_id"], job)
    artifact = store.read_paired_job_artifact(identity)
    family = artifact["project_metadata"]["runner_eval"]
    skill_result = family["family_result"]
    assert family["case_id"] == "skill:helper:smoke"
    assert skill_result["case_identity"]["source_id"] == "smoke"
    assert skill_result["ablation"]["candidate"]["skill_outcome"]["trap"] == {
        "declared": True, "text": "unsafe", "observed": False, "evidence": "not observed"
    }
    assert skill_result["ablation"]["baseline"]["classification"] == "fail"
    assert skill_result["ablation"]["candidate"]["classification"] == "pass"
    comparison = skill_result["ablation"]["comparison"]
    assert comparison["status"] == "compared"
    assert comparison["decision"]["classification"] == "pass"
    assert comparison["decision"]["data"]["delta_pp"] == 33.33
    assert comparison["decision"]["data"]["skill_value"] == "material-improvement"
    assert artifact["paired_artifact_evidence_id"]
    paired_canonical = None
    for output_format in ("json", "yaml", "markdown", "html"):
        output = tmp_path / f"skill.{output_format}"
        render = parser().parse_args([
            "eval", "--render-run", str(artifact_dir), "--format", output_format,
            "--output", str(output),
        ])
        rendered_code, _, _ = run_command(render, invoker)
        assert rendered_code == EVAL_EXIT_PASS
        assert len(invoker.specs) == 4
        text = output.read_text(encoding="utf-8")
        if output_format == "json":
            result = json.loads(text)["cases"][0]
            paired_canonical = json.loads(text)
            assert result["family_result"]["ablation"]["baseline"]["classification"] == "fail"
            assert result["family_result"]["ablation"]["candidate"]["classification"] == "pass"
            assert result["family_result"]["ablation"]["comparison"]["decision"]["data"]["delta_pp"] == 33.33
        elif output_format == "yaml":
            import yaml
            result = yaml.safe_load(text)
            assert result == paired_canonical
            result = result["cases"][0]
            assert result["family_result"]["case_identity"]["source_id"] == "smoke"
        elif output_format == "markdown":
            assert "### Case skill:helper:smoke" in text
            assert "baseline-target" in text and "candidate-target" in text and "delta_pp" in text
        else:
            assert "<main>" in text and "<h3>Case skill:helper:smoke" in text
            assert "baseline-target" in text and "candidate-target" in text
            assert text.index("<section><h2>Run ") < text.index("<section><h3>Case skill:helper:smoke") < text.index("</section>")
    validate_output_model(paired_canonical)
    misplaced_v1 = json.loads(json.dumps(paired_canonical))
    misplaced_v1["cases"][0]["family_result"]["case_identity"]["source_path"] = str(source)
    with pytest.raises(EvalOutputError, match="case_identity"):
        validate_output_model(misplaced_v1)
    artifact_path = store.paired_job_path(identity)
    raw = json.loads(artifact_path.read_text())
    raw["project_metadata"]["runner_eval"]["family_result"]["prompt"] = "changed"
    artifact_path.write_text(json.dumps(raw))
    corrupt_render = parser().parse_args([
        "eval", "--render-run", str(artifact_dir), "--format", "json",
        "--output", str(tmp_path / "corrupt-output.json"),
    ])
    corrupt_code, corrupt_stdout, corrupt_stderr = run_command(corrupt_render, invoker)
    assert corrupt_code == EVAL_EXIT_ERROR
    assert corrupt_stdout == ""
    assert "evidence_id" in corrupt_stderr
    assert not (tmp_path / "corrupt-output.json").exists()
    try:
        store.read_paired_job_artifact(identity)
    except EvalArtifactError as exc:
        assert "evidence_id" in str(exc)
    else:
        raise AssertionError("family metadata tampering must invalidate the pair integrity ID")


def test_combined_skill_run_preserves_source_occurrence_in_v2_and_rejects_duplicates(tmp_path, monkeypatch):
    root = tmp_path / "project"
    for skill in ("helper", "second"):
        (root / "skills" / skill).mkdir(parents=True)
        (root / "skills" / skill / "SKILL.md").write_text("Method", encoding="utf-8")
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text(json.dumps({"skill": "helper", "cases": [{"id": "one", "prompt": "Do", "expectations": ["useful"]}]}))
    second.write_text(json.dumps({"skill_name": "second", "evals": [{"id": "two", "prompt": "Do", "expectations": ["useful"]}]}))
    monkeypatch.chdir(root)
    artifact_dir = tmp_path / "combined"
    grades = [grade(["useful"], [], met=value) for value in (False, True) * 4]
    invoker = BuiltinInvoker(skill_grades=grades)
    args = parser().parse_args([
        "eval", "--input", str(first), "--skill", "helper", "--input", str(second), "--skill", "second",
        "--family", "skill", "--target-model", "provider/model", "--all", "--iterations", "2",
        "--artifact-dir", str(artifact_dir),
    ])

    code, stdout, stderr = run_command(args, invoker)

    assert code == EVAL_EXIT_PASS, stderr
    output = json.loads(stdout)
    validate_output_model(output)
    assert output["schema"] == "opencode-eval-runner/eval-output/v2"
    assert [entry["source_path"] for entry in output["run"]["input"]["inputs"]] == [str(first), str(second)]
    assert [(case["identity"]["skill"], case["source_input"], case["iteration"]) for case in output["cases"]] == [
        ("helper", 1, 1), ("helper", 1, 2), ("second", 2, 1), ("second", 2, 2),
    ]
    assert len(invoker.specs) == 16
    manifest = json.loads((artifact_dir / "run.json").read_text())
    store = RunArtifactStore(artifact_dir, manifest["run_id"])
    pair = store.read_paired_job_artifact(ArtifactIdentity(manifest["run_id"], output["cases"][0]["id"], 1))
    metadata = pair["project_metadata"]["runner_eval"]
    assert metadata["schema"] == "opencode-eval-runner/eval-family-result/v2"
    assert metadata["source_input"] == 1
    assert metadata["source_path"] == str(first)
    assert metadata["source_sha256"] == __import__("hashlib").sha256(first.read_bytes()).hexdigest()
    family = metadata["family_result"]
    assert set(family["case_identity"]) == {
        "case_id", "source_id", "authored_id", "source_index", "display_name"
    }
    assert family["ablation"]["candidate"]["skill_outcome"]["trap"] == {
        "declared": False, "text": None, "observed": None, "evidence": None
    }

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(first.read_text())
    bad = parser().parse_args([
        "eval", "--input", str(first), "--skill", "helper", "--input", str(duplicate), "--skill", "helper",
        "--family", "skill", "--target-model", "provider/model", "--cases", combined_skill_case_id("helper", "one"),
    ])
    before = len(invoker.specs)
    bad_code, bad_stdout, bad_stderr = run_command(bad, invoker)
    assert bad_code == EVAL_EXIT_ERROR
    assert bad_stdout == ""
    assert "duplicate composite" in bad_stderr
    assert len(invoker.specs) == before


def test_combined_markdown_and_html_render_five_iterations_under_repeated_skill_inputs(
    tmp_path, monkeypatch
):
    root = tmp_path / "project"
    (root / "skills" / "helper").mkdir(parents=True)
    (root / "skills" / "helper" / "SKILL.md").write_text("Method", encoding="utf-8")
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text(
        json.dumps(
            {
                "skill": "helper",
                "cases": [{"id": "one-" + "x" * 40, "name": "<first case>", "prompt": "<one>", "expectations": ["useful"]}],
            }
        )
    )
    second.write_text(
        json.dumps(
            {
                "skill_name": "helper",
                "evals": [{"id": "two", "name": "<second case>", "prompt": "<two>", "expectations": ["useful"]}],
            }
        )
    )
    monkeypatch.chdir(root)
    artifact_dir = tmp_path / "combined-five"
    invoker = BuiltinInvoker(
        skill_grades=[grade(["useful"], [], met=True) for _ in range(40)]
    )
    execute = parser().parse_args(
        [
            "eval",
            "--input",
            str(first),
            "--skill",
            "helper",
            "--input",
            str(second),
            "--skill",
            "helper",
            "--family",
            "skill",
            "--target-model",
            "provider/model",
            "--all",
            "--iterations",
            "5",
            "--artifact-dir",
            str(artifact_dir),
        ]
    )

    code, _, stderr = run_command(execute, invoker)

    assert code == EVAL_EXIT_PASS, stderr
    canonical_path = tmp_path / "combined.json"
    canonical_args = parser().parse_args(
        [
            "eval",
            "--render-run",
            str(artifact_dir),
            "--format",
            "json",
            "--output",
            str(canonical_path),
        ]
    )
    assert run_command(canonical_args, invoker)[0] == EVAL_EXIT_PASS
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    validate_output_model(canonical)
    invalid = json.loads(canonical_path.read_text(encoding="utf-8"))
    invalid["cases"][0]["family_result"]["case_identity"]["source_input"] = 1
    with pytest.raises(EvalOutputError, match="case_identity"):
        validate_output_model(invalid)
    invalid = json.loads(canonical_path.read_text(encoding="utf-8"))
    invalid["cases"][0]["unexpected"] = True
    with pytest.raises(EvalOutputError, match=r"cases\[0\]"):
        validate_output_model(invalid)
    invalid = json.loads(canonical_path.read_text(encoding="utf-8"))
    invalid["cases"][0]["family_result"]["ablation"]["candidate"]["skill_outcome"]["trap"]["observed"] = False
    with pytest.raises(EvalOutputError, match="undeclared trap"):
        validate_output_model(invalid)
    assert canonical["schema"] == "opencode-eval-runner/eval-output/v2"
    assert len(canonical["cases"]) == 10
    assert len(canonical["cases"][0]["id"]) > 60
    created_at = canonical["run"]["created_at"]
    assert {
        (case["identity"]["skill"], case["source_input"]) for case in canonical["cases"]
    } == {("helper", 1), ("helper", 2)}
    yaml_path = tmp_path / "combined.yaml"
    yaml_args = parser().parse_args(
        [
            "eval",
            "--render-run",
            str(artifact_dir),
            "--format",
            "yaml",
            "--output",
            str(yaml_path),
        ]
    )
    assert run_command(yaml_args, invoker)[0] == EVAL_EXIT_PASS
    import yaml

    assert yaml.safe_load(yaml_path.read_text(encoding="utf-8")) == canonical

    for output_format in ("markdown", "html"):
        destination = tmp_path / f"combined.{output_format}"
        render = parser().parse_args(
            [
                "eval",
                "--render-run",
                str(artifact_dir),
                "--format",
                output_format,
                "--output",
                str(destination),
            ]
        )
        assert run_command(render, invoker)[0] == EVAL_EXIT_PASS
        text = destination.read_text(encoding="utf-8")
        assert created_at in text
        assert text.count("Iteration 1 — pass") == 4
        assert text.count("Iteration 2 — pass") == 4
        assert text.count("Iteration 3 — pass") == 4
        assert text.count("Iteration 4 — pass") == 4
        assert text.count("Iteration 5 — pass") == 4
        assert "baseline_score" in text and "candidate_score" in text and "Captured answers and evidence" in text
        assert "source_id" in text
        assert "one-" + "x" * 40 in text
        assert "two" in text
        assert "<one>" not in text and "&lt;one&gt;" in text if output_format == "html" else "<one>" in text
        if output_format == "html":
            assert text.count("<h3 id=\"skill-") == 1
            assert text.count("<h4 id=\"case-") == 2
            assert text.count("<h5 id=\"case-") == 10
            assert "&lt;first case&gt;" in text and "&lt;second case&gt;" in text
            assert f'<a href="#case-{canonical["cases"][0]["id"]}">Case helper: &lt;first case&gt;</a>' in text
            assert "Case helper: &lt;first case&gt;" in text
            assert "Case helper: &lt;second case&gt;" in text
            assert "overflow-wrap:anywhere" in text
            assert "word-break:break-word" in text
            assert "dd{margin-inline-start:0}" in text
            assert "ul,ol{padding-inline-start:0;list-style-position:inside}" in text
            assert "<dl>" in text and "<dt>" in text and "<dd>" in text
            assert "<dt>observations</dt><dd><ul>" in text
            assert "<dt>tool</dt>" in text and "native-1" in text and "skill body" in text
            assert "Raw captured stdout/stderr" in text
        else:
            assert text.count("### Skill helper") == 1
            assert text.count("#### Case ") == 2
            assert text.count("##### Iteration ") == 10
            assert "Raw captured stdout/stderr" in text
        assert "skill summary" not in text.lower()


def test_skill_pair_non_evidence_side_preserves_both_outcomes_without_scores(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "skills" / "helper").mkdir(parents=True)
    (root / "skills" / "helper" / "SKILL.md").write_text("Method", encoding="utf-8")
    source = tmp_path / "skill.json"
    source.write_text(json.dumps({"skill": "helper", "cases": [{
        "prompt": "Help", "expectations": ["useful"],
    }]}))
    artifact_dir = tmp_path / "artifacts"
    invoker = BuiltinInvoker(
        skill_candidate_evidence=unsupported_runtime_evidence("capture unsupported"),
        skill_grades=[grade(["useful"], [], met=False), grade(["useful"], [], met=True)],
    )
    monkeypatch.chdir(root)
    args = parser().parse_args([
        "eval", "--input", str(source), "--family", "skill", "--target-model", "provider/model",
        "--all", "--artifact-dir", str(artifact_dir),
    ])

    code, _, _ = run_command(args, invoker)

    assert code == EVAL_EXIT_VERDICT
    assert [spec.agent for spec in invoker.specs] == ["skill-baseline", "eval-judge", "skill-eval"]
    manifest = json.loads((artifact_dir / "run.json").read_text())
    store = RunArtifactStore(artifact_dir, manifest["run_id"])
    job = build_run_plan(
        manifest["run_id"],
        (NormalizedCase("skill:helper:1", ("skill:helper:1",), "standard", None, {}),),
        selectors=("skill:helper:1",), select_all=False,
    ).jobs[0]
    pair = store.read_paired_job_artifact(artifact_identity_for_job(manifest["run_id"], job))
    result = pair["project_metadata"]["runner_eval"]["family_result"]["ablation"]
    assert result["baseline"]["classification"] == "fail"
    assert result["candidate"]["classification"] == "non-evidence"
    assert result["comparison"]["status"] == "non-evidence"
    assert result["comparison"]["decision"] is None
    assert result["comparison"]["failure"] is not None


def test_builtin_retry_default_is_zero_and_profile_mode_still_parses_unchanged():
    profile_args = parser().parse_args(["eval", "--profile", "project.eval:PROFILE", "--all"])
    builtin_args = parser().parse_args([
        "eval", "--input", "suite.json", "--family", "agent-runtime", "--target-model", "provider/model", "--all",
    ])

    assert profile_args.profile == "project.eval:PROFILE"
    assert profile_args.input is None
    assert builtin_args.profile is None
    assert builtin_args.transport_retries == 0


def test_new_builtin_controls_cannot_change_the_existing_profile_path():
    args = parser().parse_args([
        "eval", "--profile", "project.eval:PROFILE", "--family", "skill", "--all",
    ])
    invoker = BuiltinInvoker()

    code, _, stderr = run_command(args, invoker)

    assert code == EVAL_EXIT_ERROR
    assert "cannot be combined with --profile" in stderr
    assert invoker.specs == []


@pytest.mark.parametrize(
    "transport_flag",
    ["--target-transport", "--judge-transport"],
    ids=["target-copilot-rejected", "judge-copilot-rejected"],
)
def test_builtin_non_opencode_transport_is_rejected_before_invocation(tmp_path, transport_flag):
    invoker = BuiltinInvoker()
    args = parser().parse_args([
        "eval", "--input", str(tmp_path / "not-read.json"), "--family", "agent-runtime",
        "--target-model", "provider/model", "--all", transport_flag, "github-copilot-cli",
    ])

    code, _, stderr = run_command(args, invoker)

    assert code == EVAL_EXIT_ERROR
    assert "only the opencode transport" in stderr
    assert invoker.specs == []


def test_skill_comparison_uses_ten_point_threshold_and_trap_regression_precedence(tmp_path):
    from runner.eval_builtin import SkillAblationAdapter

    case = NormalizedCase(
        "skill:helper:case", ("skill:helper:case",), "standard",
        {"skill": "helper", "trap": "unsafe"}, {},
    )
    adapter = object.__new__(SkillAblationAdapter)
    baseline = SimpleNamespace(
        case=case, classification="fail",
        semantic=SimpleNamespace(data={"behavior_score": 0.5, "trap_observed": False}),
    )
    candidate = SimpleNamespace(
        case=case, classification="pass",
        semantic=SimpleNamespace(data={"behavior_score": 0.6, "trap_observed": False}),
    )

    material = adapter.compare_pair(baseline, candidate)

    assert material.data["delta_pp"] == 10.0
    assert material.data["skill_value"] == "material-improvement"
    assert material.data["candidate_absolute_pass"] is True

    candidate.semantic.data["trap_observed"] = True
    candidate.classification = "fail"
    regression = adapter.compare_pair(baseline, candidate)

    assert regression.data["trap_regression"] is True
    assert regression.data["skill_value"] == "regression"
    assert regression.classification == "fail"
