from __future__ import annotations

import argparse
import io
import json
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from container.runtime_evidence import unsupported_runtime_evidence
from runner.cli import parser
from runner.eval_cli import (
    EVAL_EXIT_ERROR,
    EVAL_EXIT_PASS,
    EVAL_EXIT_VERDICT,
    run_eval,
)
from runner.eval_evidence import EvidenceRequirement
from runner.eval_execute import RESULT_SCHEMA
from runner.eval_types import (
    CheckOutcome,
    InvocationSpec,
    NormalizedCase,
    SemanticDecision,
)


def make_spec(
    workspace: Path,
    *,
    model: str,
    transport: str = "opencode",
) -> InvocationSpec:
    return InvocationSpec(
        transport=transport,  # type: ignore[arg-type]
        model=model,
        reasoning=None,
        agent=None,
        skill=None,
        workspace=workspace,
        workspace_mode="ro",
        prompt=f"prompt for {model}",
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
        timeout_seconds=10,
        container_timeout=20,
    )


class FakeInvoker:
    def __init__(self):
        self.specs: list[InvocationSpec] = []
        self._lock = threading.Lock()

    def __call__(self, spec: InvocationSpec):
        with self._lock:
            self.specs.append(spec)
        reasoning = spec.reasoning or "provider-default"
        return 0, {
            "schema": RESULT_SCHEMA,
            "transport": spec.transport,
            "model": spec.model,
            "reasoning": reasoning,
            "reasoning_source": (
                "explicit" if spec.reasoning is not None else "provider-default"
            ),
            "exit_code": 0,
            "stderr": "",
            "runtime_evidence": unsupported_runtime_evidence(
                "provider_free_eval_cli_fixture"
            ),
        }


class FakeProfile:
    def __init__(
        self,
        workspace: Path,
        *,
        checks: tuple[CheckOutcome, ...] = (
            CheckOutcome("deterministic", "pass", "ok", {}),
        ),
        judge: bool = True,
    ):
        self.workspace = workspace
        self.checks = checks
        self.judge = judge
        self.prepare_calls = 0
        self.target_calls = 0
        self.judge_calls = 0

    def discover_cases(self):
        return (
            NormalizedCase(
                id="CASE-1",
                selectors=("CASE-1", "smoke"),
                lane="standard",
                project_data=None,
                metadata={},
            ),
            NormalizedCase(
                id="RUNTIME-1",
                selectors=("RUNTIME-1", "runtime"),
                lane="runtime",
                project_data=None,
                metadata={},
            ),
        )

    @contextmanager
    def prepare(self, case, iteration):
        self.prepare_calls += 1
        yield {"case": case.id, "iteration": iteration}

    def target_spec(self, case, prepared):
        self.target_calls += 1
        return make_spec(self.workspace, model="profile/target")

    def target_evidence_requirement(self, case, prepared):
        return EvidenceRequirement()

    def deterministic_checks(self, case, prepared, target, readiness):
        return self.checks

    def judge_spec(self, case, prepared, target, checks):
        self.judge_calls += 1
        if not self.judge:
            return None
        return make_spec(self.workspace, model="profile/judge")

    def parse_judge(self, case, prepared, judge):
        return SemanticDecision("pass", "provider-free pass", {})

    def artifact_metadata(self, case, prepared):
        return {
            "fixture": "provider-free",
            "prepared_case": prepared["case"],
        }


class EvalCliTests(unittest.TestCase):
    def test_parser_exposes_public_eval_controls(self):
        args = parser().parse_args(
            [
                "eval",
                "--profile",
                "project.eval:PROFILE",
                "--cases",
                "CASE-1,smoke",
                "--iterations",
                "3",
                "--parallel",
                "4",
                "--runtime-parallel",
                "2",
                "--target-transport",
                "github-copilot-cli",
                "--judge-transport",
                "opencode",
                "--target-model",
                "target/model",
                "--judge-model",
                "judge/model",
                "--reasoning",
                "medium",
                "--target-reasoning",
                "high",
                "--judge-reasoning",
                "low",
                "--engine",
                "docker",
                "--network",
                "host",
                "--artifact-dir",
                "/tmp/eval-artifacts",
                "--timeout-seconds",
                "111",
                "--container-timeout",
                "222",
                "--transport-retries",
                "2",
            ]
        )

        self.assertEqual(args.command, "eval")
        self.assertEqual(args.profile, "project.eval:PROFILE")
        self.assertEqual(args.cases, ["CASE-1,smoke"])
        self.assertEqual(args.iterations, 3)
        self.assertEqual(args.parallel, 4)
        self.assertEqual(args.runtime_parallel, 2)
        self.assertEqual(args.target_transport, "github-copilot-cli")
        self.assertEqual(args.judge_transport, "opencode")
        self.assertEqual(args.target_model, "target/model")
        self.assertEqual(args.judge_model, "judge/model")
        self.assertEqual(args.reasoning, "medium")
        self.assertEqual(args.target_reasoning, "high")
        self.assertEqual(args.judge_reasoning, "low")
        self.assertEqual(args.engine, "docker")
        self.assertEqual(args.network, "host")
        self.assertEqual(args.timeout_seconds, 111)
        self.assertEqual(args.container_timeout, 222)
        self.assertEqual(args.transport_retries, 2)

    def test_parser_parallel_without_limit_requests_full_standard_parallelism(self):
        args = parser().parse_args(
            ["eval", "--profile", "project.eval:PROFILE", "--all", "--parallel"]
        )
        self.assertEqual(args.parallel, 0)

    def test_list_is_provider_free_and_does_not_require_live_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = FakeProfile(Path(tmp))
            args = parser().parse_args(
                ["eval", "--profile", "project.eval:PROFILE", "--list"]
            )
            stdout = io.StringIO()
            invoker = FakeInvoker()

            with patch("runner.eval_cli.load_eval_profile", return_value=profile):
                code = run_eval(args, stdout=stdout, invoker=invoker)

            self.assertEqual(code, EVAL_EXIT_PASS)
            self.assertIn("CASE-1\tstandard\tsmoke", stdout.getvalue())
            self.assertIn("RUNTIME-1\truntime\truntime", stdout.getvalue())
            self.assertEqual(profile.prepare_calls, 0)
            self.assertEqual(profile.target_calls, 0)
            self.assertEqual(profile.judge_calls, 0)
            self.assertEqual(invoker.specs, [])

    def test_live_run_refuses_implicit_selection_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = FakeProfile(Path(tmp))
            args = parser().parse_args(
                ["eval", "--profile", "project.eval:PROFILE"]
            )
            stderr = io.StringIO()
            invoker = FakeInvoker()

            with patch("runner.eval_cli.load_eval_profile", return_value=profile):
                code = run_eval(args, stderr=stderr, invoker=invoker)

            self.assertEqual(code, EVAL_EXIT_ERROR)
            self.assertIn("spend model inference", stderr.getvalue())
            self.assertEqual(profile.prepare_calls, 0)
            self.assertEqual(invoker.specs, [])

    def test_selected_provider_free_run_applies_phase_and_common_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            artifact_dir = root / "artifacts"
            profile = FakeProfile(workspace)
            invoker = FakeInvoker()
            args = parser().parse_args(
                [
                    "eval",
                    "--profile",
                    "project.eval:PROFILE",
                    "--cases",
                    "smoke",
                    "--target-transport",
                    "github-copilot-cli",
                    "--judge-transport",
                    "opencode",
                    "--target-model",
                    "cli/target",
                    "--judge-model",
                    "cli/judge",
                    "--reasoning",
                    "low",
                    "--target-reasoning",
                    "high",
                    "--engine",
                    "docker",
                    "--network",
                    "host",
                    "--timeout-seconds",
                    "33",
                    "--container-timeout",
                    "44",
                    "--artifact-dir",
                    str(artifact_dir),
                ]
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch("runner.eval_cli.load_eval_profile", return_value=profile):
                code = run_eval(
                    args,
                    stdout=stdout,
                    stderr=stderr,
                    invoker=invoker,
                    sleep=lambda _: None,
                )

            self.assertEqual(code, EVAL_EXIT_PASS, stderr.getvalue())
            self.assertEqual(len(invoker.specs), 2)
            target, judge = invoker.specs
            self.assertEqual(target.transport, "github-copilot-cli")
            self.assertEqual(target.model, "cli/target")
            self.assertEqual(target.reasoning, "high")
            self.assertEqual(judge.transport, "opencode")
            self.assertEqual(judge.model, "cli/judge")
            self.assertEqual(judge.reasoning, "low")
            for spec in invoker.specs:
                self.assertEqual(spec.engine, "docker")
                self.assertEqual(spec.network, "host")
                self.assertEqual(spec.timeout_seconds, 33)
                self.assertEqual(spec.container_timeout, 44)

            manifest = json.loads(
                (artifact_dir / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["summary"]["status"], "pass")
            self.assertEqual(manifest["summary"]["pass"], 1)
            self.assertEqual(manifest["summary"]["total"], 1)
            self.assertEqual(manifest["selection"]["selectors"], ["smoke"])

            artifact = json.loads(
                (artifact_dir / "jobs" / "case-CASE-1" / "iteration-1.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(artifact["classification"], "pass")
            self.assertEqual(
                artifact["project_metadata"]["fixture"],
                "provider-free",
            )
            self.assertIn("CASE-1 ... PASS", stdout.getvalue())

    def test_all_iterations_and_lane_concurrency_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            artifact_dir = root / "artifacts"
            profile = FakeProfile(workspace)
            invoker = FakeInvoker()
            args = parser().parse_args(
                [
                    "eval",
                    "--profile",
                    "project.eval:PROFILE",
                    "--all",
                    "--iterations",
                    "2",
                    "--parallel",
                    "2",
                    "--runtime-parallel",
                    "1",
                    "--artifact-dir",
                    str(artifact_dir),
                ]
            )

            with patch("runner.eval_cli.load_eval_profile", return_value=profile):
                code = run_eval(
                    args,
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                    invoker=invoker,
                    sleep=lambda _: None,
                )

            self.assertEqual(code, EVAL_EXIT_PASS)
            self.assertEqual(len(invoker.specs), 8)
            manifest = json.loads(
                (artifact_dir / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["iterations"], 2)
            self.assertEqual(
                manifest["concurrency"],
                {"standard": 2, "runtime": 1},
            )
            self.assertEqual(manifest["summary"]["pass"], 4)
            self.assertEqual(manifest["summary"]["total"], 4)

    def test_non_evidence_result_has_stable_verdict_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            profile = FakeProfile(
                workspace,
                checks=(
                    CheckOutcome(
                        "deterministic",
                        "non-evidence",
                        "missing project evidence",
                        {},
                    ),
                ),
                judge=False,
            )
            args = parser().parse_args(
                [
                    "eval",
                    "--profile",
                    "project.eval:PROFILE",
                    "--cases",
                    "CASE-1",
                    "--artifact-dir",
                    str(root / "artifacts"),
                ]
            )

            with patch("runner.eval_cli.load_eval_profile", return_value=profile):
                code = run_eval(
                    args,
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                    invoker=FakeInvoker(),
                    sleep=lambda _: None,
                )

            self.assertEqual(code, EVAL_EXIT_VERDICT)

    def test_retry_bound_is_validated_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = FakeProfile(Path(tmp))
            args = parser().parse_args(
                [
                    "eval",
                    "--profile",
                    "project.eval:PROFILE",
                    "--all",
                    "--transport-retries",
                    "6",
                ]
            )
            invoker = FakeInvoker()
            stderr = io.StringIO()

            with patch("runner.eval_cli.load_eval_profile", return_value=profile):
                code = run_eval(args, stderr=stderr, invoker=invoker)

            self.assertEqual(code, EVAL_EXIT_ERROR)
            self.assertIn("--transport-retries", stderr.getvalue())
            self.assertEqual(invoker.specs, [])


if __name__ == "__main__":
    unittest.main()
