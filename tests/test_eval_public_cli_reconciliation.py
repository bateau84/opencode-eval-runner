from __future__ import annotations

import importlib
import json
import sys
import tempfile
import threading
import time
import unittest
from collections import Counter
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

from container.runtime_evidence import (
    build_runtime_evidence,
    unsupported_runtime_evidence,
)
from runner.eval_execute import RESULT_SCHEMA


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE_MODULE = "generic_eval_profile"
_FIXTURE_REF = f"{_FIXTURE_MODULE}:profile"

_STANDARD_CASES = {"PF-PASS", "PF-FAIL", "PF-DETERMINISTIC"}
_RUNTIME_CASES = {"PF-NON-EVIDENCE", "PF-RETRY"}


def _public_eval_cli():
    """Load Worker A's public eval surface when present on integration.

    The acceptance worker branches from the frozen shared API before the
    parallel CLI worker. These tests therefore skip on the isolated worker and
    become active automatically during Task-6 reconciliation.
    """

    try:
        eval_cli = importlib.import_module("runner.eval_cli")
    except ModuleNotFoundError as exc:
        if exc.name == "runner.eval_cli":
            raise unittest.SkipTest(
                "public eval CLI is supplied by parallel Task-6 Worker A"
            ) from exc
        raise

    from runner.cli import parser

    return eval_cli, parser


@contextmanager
def fixture_profile_import_path():
    sys.path.insert(0, str(_FIXTURE_DIR))
    sys.modules.pop(_FIXTURE_MODULE, None)
    try:
        yield
    finally:
        sys.modules.pop(_FIXTURE_MODULE, None)
        try:
            sys.path.remove(str(_FIXTURE_DIR))
        except ValueError:
            pass


def _complete_empty_runtime_evidence():
    return build_runtime_evidence(
        {
            "capture_started": True,
            "capture_ended": True,
            "records": [],
            "observer_failures": 0,
            "callback_failures": 0,
            "issues": [],
        }
    )


def _result_for(
    spec,
    *,
    exit_code=0,
    stderr="",
    stdout="",
    runtime_evidence=None,
):
    return {
        "schema": RESULT_SCHEMA,
        "transport": spec.transport,
        "model": spec.model,
        "reasoning": spec.reasoning or "provider-default",
        "reasoning_source": "explicit" if spec.reasoning else "provider-default",
        "exit_code": exit_code,
        "stderr": stderr,
        "stdout": stdout,
        "runtime_evidence": (
            runtime_evidence
            if runtime_evidence is not None
            else unsupported_runtime_evidence("provider_free_public_cli")
        ),
    }


class ConcurrentProviderFreeInvoker:
    """Provider-free adapter that also observes public lane concurrency bounds."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counts = Counter()
        self.calls = []
        self.active = {"standard": 0, "runtime": 0}
        self.max_active = {"standard": 0, "runtime": 0}

    def _lane(self, case_id):
        if case_id in _STANDARD_CASES:
            return "standard"
        if case_id in _RUNTIME_CASES:
            return "runtime"
        raise AssertionError(f"unknown provider-free case: {case_id}")

    def __call__(self, spec):
        try:
            _, phase, case_id = spec.model.split("/", 2)
        except ValueError as exc:
            raise AssertionError(f"unexpected fixture model: {spec.model}") from exc

        lane = self._lane(case_id)
        with self._lock:
            self.calls.append(spec.model)
            self._counts[spec.model] += 1
            call_number = self._counts[spec.model]
            self.active[lane] += 1
            self.max_active[lane] = max(
                self.max_active[lane],
                self.active[lane],
            )

        # Make overlap observable without touching providers, containers, or
        # network. ThreadPoolExecutor should reach the configured bound.
        try:
            time.sleep(0.03)

            if phase == "target" and case_id == "PF-RETRY" and call_number == 1:
                return (
                    2,
                    _result_for(
                        spec,
                        exit_code=2,
                        stderr="ProviderError: provider.no-route: Model unavailable",
                        runtime_evidence=_complete_empty_runtime_evidence(),
                    ),
                )

            stdout = ""
            if phase == "judge":
                status = "fail" if case_id == "PF-FAIL" else "pass"
                stdout = json.dumps({"case": case_id, "status": status})

            return 0, _result_for(spec, stdout=stdout)
        finally:
            with self._lock:
                self.active[lane] -= 1


class PublicEvalReconciliationAcceptanceTests(unittest.TestCase):
    def test_public_list_is_provider_free(self):
        eval_cli, make_parser = _public_eval_cli()

        class RejectingInvoker:
            def __call__(self, spec):
                raise AssertionError(f"listing unexpectedly invoked {spec.model}")

        stdout = StringIO()
        stderr = StringIO()
        with fixture_profile_import_path():
            args = make_parser().parse_args(
                ["eval", "--profile", _FIXTURE_REF, "--list"]
            )
            exit_code = eval_cli.run_eval(
                args,
                stdout=stdout,
                stderr=stderr,
                invoker=RejectingInvoker(),
            )

        self.assertEqual(exit_code, eval_cli.EVAL_EXIT_PASS)
        self.assertEqual(stderr.getvalue(), "")
        listed = stdout.getvalue()
        self.assertIn("PF-PASS", listed)
        self.assertIn("PF-NON-EVIDENCE", listed)
        self.assertIn("PF-RETRY", listed)

    def test_public_run_enforces_lane_concurrency_and_verdict_exit_summary(self):
        eval_cli, make_parser = _public_eval_cli()
        invoker = ConcurrentProviderFreeInvoker()

        with tempfile.TemporaryDirectory() as temp, fixture_profile_import_path():
            artifact_dir = Path(temp) / "all"
            args = make_parser().parse_args(
                [
                    "eval",
                    "--profile",
                    _FIXTURE_REF,
                    "--all",
                    "--parallel",
                    "2",
                    "--runtime-parallel",
                    "2",
                    "--transport-retries",
                    "1",
                    "--artifact-dir",
                    str(artifact_dir),
                ]
            )
            exit_code = eval_cli.run_eval(
                args,
                stdout=StringIO(),
                stderr=StringIO(),
                invoker=invoker,
                sleep=lambda _: None,
            )

            manifest = json.loads(
                (artifact_dir / "run.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, eval_cli.EVAL_EXIT_VERDICT)
        self.assertEqual(
            manifest["summary"],
            {
                "status": "verdict",
                "pass": 3,
                "fail": 1,
                "non-evidence": 1,
                "errors": 0,
                "not_run": 0,
                "total": 5,
            },
        )
        self.assertEqual(manifest["concurrency"], {"standard": 2, "runtime": 2})
        self.assertEqual(invoker.max_active["standard"], 2)
        self.assertEqual(invoker.max_active["runtime"], 2)

    def test_public_retry_is_explicit_durable_and_can_exit_pass(self):
        eval_cli, make_parser = _public_eval_cli()
        invoker = ConcurrentProviderFreeInvoker()

        with tempfile.TemporaryDirectory() as temp, fixture_profile_import_path():
            artifact_dir = Path(temp) / "retry"
            args = make_parser().parse_args(
                [
                    "eval",
                    "--profile",
                    _FIXTURE_REF,
                    "--cases",
                    "PF-RETRY",
                    "--transport-retries",
                    "1",
                    "--artifact-dir",
                    str(artifact_dir),
                ]
            )
            exit_code = eval_cli.run_eval(
                args,
                stdout=StringIO(),
                stderr=StringIO(),
                invoker=invoker,
                sleep=lambda _: None,
            )
            manifest = json.loads(
                (artifact_dir / "run.json").read_text(encoding="utf-8")
            )
            artifact_path = artifact_dir / manifest["jobs"][0]["artifact"]
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, eval_cli.EVAL_EXIT_PASS)
        self.assertEqual(manifest["summary"]["status"], "pass")
        self.assertEqual(manifest["summary"]["pass"], 1)
        self.assertEqual(manifest["summary"]["total"], 1)
        attempts = artifact["target"]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertTrue(attempts[0]["retry_decision"]["retry"])
        self.assertIsNone(attempts[1]["failure"])


if __name__ == "__main__":
    unittest.main()
