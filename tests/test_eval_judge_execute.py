from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from container.runtime_evidence import build_runtime_evidence, unsupported_runtime_evidence
from runner.eval_execute import (
    RESULT_SCHEMA,
    TransientProviderRetryPolicy,
    run_judge_attempts,
)
from runner.eval_types import InvocationSpec


def complete_empty_runtime_evidence():
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


def make_judge_spec(workspace: Path) -> InvocationSpec:
    return InvocationSpec(
        transport="opencode",
        model="openai/judge-test-model",
        reasoning="high",
        agent="judge",
        skill=None,
        workspace=workspace,
        workspace_mode="ro",
        prompt="profile-produced judge prompt",
        system="profile-produced judge system",
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


def valid_result(
    spec: InvocationSpec,
    *,
    exit_code: int = 0,
    timed_out: bool = False,
    stderr: str = "",
    runtime_evidence: dict | None = None,
) -> dict:
    result = {
        "schema": RESULT_SCHEMA,
        "transport": spec.transport,
        "model": spec.model,
        "reasoning": spec.reasoning,
        "reasoning_source": "explicit",
        "exit_code": exit_code,
        "stderr": stderr,
        "runtime_evidence": runtime_evidence
        or unsupported_runtime_evidence("judge_test_transport"),
    }
    if timed_out:
        result["timed_out"] = True
    return result


class SequenceInvoker:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, spec):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class JudgeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.spec = make_judge_spec(self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def test_success_uses_one_invoke_and_preserves_timing_and_provenance(self):
        invoker = SequenceInvoker([(0, valid_result(self.spec))])

        outcome = run_judge_attempts(self.spec, invoker=invoker)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(invoker.calls, 1)
        self.assertEqual(len(outcome.attempts), 1)
        attempt = outcome.final_attempt
        self.assertEqual(attempt.attempt, 1)
        self.assertEqual(attempt.host_exit_code, 0)
        self.assertIsNone(attempt.failure)
        self.assertGreaterEqual(attempt.duration_seconds, 0.0)
        self.assertTrue(attempt.started_at.endswith("Z"))
        self.assertEqual(outcome.spec.model, "openai/judge-test-model")
        self.assertEqual(outcome.spec.reasoning, "high")
        self.assertEqual(attempt.result["model"], "openai/judge-test-model")
        self.assertEqual(attempt.result["reasoning"], "high")

    def test_invalid_result_contract_fails_closed_as_infrastructure(self):
        invalid = valid_result(self.spec)
        invalid["schema"] = "wrong/v1"
        invoker = SequenceInvoker([(0, invalid)])

        outcome = run_judge_attempts(self.spec, invoker=invoker)

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(outcome.final_attempt.failure.plane, "infrastructure")
        self.assertEqual(outcome.final_attempt.failure.code, "invoke_invalid_result")
        self.assertIsNone(outcome.final_attempt.result)

    def test_inner_timeout_is_a_normalized_failed_judge_attempt(self):
        invoker = SequenceInvoker(
            [(0, valid_result(self.spec, exit_code=124, timed_out=True))]
        )

        outcome = run_judge_attempts(self.spec, invoker=invoker)

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(outcome.final_attempt.failure.plane, "product")
        self.assertEqual(outcome.final_attempt.failure.code, "product_timeout")
        self.assertFalse(outcome.final_attempt.failure.retry_safe)
        self.assertIsNotNone(outcome.final_attempt.result)

    def test_outer_timeout_is_infrastructure_and_has_no_result(self):
        invoker = SequenceInvoker(
            [subprocess.TimeoutExpired(["podman", "run"], timeout=20)]
        )

        outcome = run_judge_attempts(self.spec, invoker=invoker)

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(outcome.final_attempt.failure.plane, "infrastructure")
        self.assertEqual(outcome.final_attempt.failure.code, "invoke_outer_timeout")
        self.assertIsNone(outcome.final_attempt.result)

    def test_explicit_retry_then_success_preserves_full_attempt_history(self):
        transient = valid_result(
            self.spec,
            exit_code=2,
            stderr="ProviderError: provider.no-route: Model unavailable",
            runtime_evidence=complete_empty_runtime_evidence(),
        )
        invoker = SequenceInvoker([(2, transient), (0, valid_result(self.spec))])

        outcome = run_judge_attempts(
            self.spec,
            invoker=invoker,
            retry_policy=TransientProviderRetryPolicy(),
            max_attempts=2,
        )

        self.assertTrue(outcome.succeeded)
        self.assertEqual(invoker.calls, 2)
        self.assertEqual(invoker.calls, len(outcome.attempts))
        self.assertEqual([attempt.attempt for attempt in outcome.attempts], [1, 2])
        self.assertEqual(outcome.attempts[0].failure.code, "invoke_host_error")
        self.assertTrue(outcome.attempts[0].failure.retry_safe)
        self.assertIsNone(outcome.attempts[1].failure)
        self.assertEqual(len(outcome.retry_decisions), 1)
        self.assertTrue(outcome.retry_decisions[0].retry)

    def test_retryable_failure_without_explicit_policy_does_not_retry(self):
        transient = valid_result(
            self.spec,
            exit_code=2,
            stderr="ProviderError: provider.no-route: Model unavailable",
            runtime_evidence=complete_empty_runtime_evidence(),
        )
        invoker = SequenceInvoker([(2, transient), (0, valid_result(self.spec))])

        outcome = run_judge_attempts(self.spec, invoker=invoker, max_attempts=2)

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(len(outcome.attempts), 1)
        self.assertFalse(outcome.retry_decisions[0].retry)
        self.assertEqual(outcome.retry_decisions[0].reason, "no retry policy configured")

    def test_retry_exhaustion_is_bounded_and_visible(self):
        transient = valid_result(
            self.spec,
            exit_code=2,
            stderr="ProviderError: provider.no-route: Model unavailable",
            runtime_evidence=complete_empty_runtime_evidence(),
        )
        invoker = SequenceInvoker([(2, transient), (2, transient)])

        outcome = run_judge_attempts(
            self.spec,
            invoker=invoker,
            retry_policy=TransientProviderRetryPolicy(),
            max_attempts=2,
        )

        self.assertEqual(invoker.calls, 2)
        self.assertEqual(len(outcome.attempts), 2)
        self.assertEqual(len(outcome.retry_decisions), 2)
        self.assertTrue(outcome.retry_decisions[0].retry)
        self.assertFalse(outcome.retry_decisions[1].retry)
        self.assertEqual(outcome.retry_decisions[1].reason, "maximum attempts reached")


if __name__ == "__main__":
    unittest.main()
