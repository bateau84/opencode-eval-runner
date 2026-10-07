from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from container.runtime_evidence import (
    BOUNDARY_NATIVE,
    build_runtime_evidence,
    unsupported_runtime_evidence,
)
from runner.eval_evidence import EvidenceRequirement
from runner.eval_execute import (
    RESULT_SCHEMA,
    TransientProviderRetryPolicy,
    invoke_once,
    run_target_attempts,
)
from runner.eval_types import InvocationSpec, RetryDecision


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


def incomplete_runtime_evidence():
    return build_runtime_evidence(
        {
            "capture_started": True,
            "capture_ended": False,
            "records": [],
            "observer_failures": None,
            "callback_failures": None,
            "issues": ["missing_capture_end"],
        }
    )



def make_spec(workspace: Path, *, reasoning: str | None = "medium") -> InvocationSpec:
    return InvocationSpec(
        transport="opencode",
        model="openai/test-model",
        reasoning=reasoning,
        agent="general",
        skill=None,
        workspace=workspace,
        workspace_mode="ro",
        prompt="test prompt",
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


def valid_result(
    spec: InvocationSpec,
    *,
    exit_code: int = 0,
    host_infrastructure: bool = False,
    timed_out: bool = False,
    stderr: str = "",
    runtime_evidence: dict | None = None,
) -> dict:
    result = {
        "schema": RESULT_SCHEMA,
        "transport": spec.transport,
        "model": spec.model,
        "reasoning": spec.reasoning or "provider-default",
        "reasoning_source": "explicit" if spec.reasoning else "provider-default",
        "exit_code": exit_code,
        "stderr": stderr,
        "runtime_evidence": runtime_evidence or unsupported_runtime_evidence("test_transport"),
    }
    if host_infrastructure:
        result["infrastructure_error"] = True
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


class AlwaysRetryPolicy:
    def __init__(self):
        self.calls = 0

    def decide(self, attempts, latest):
        self.calls += 1
        return RetryDecision(True, "test requests retry", 0.0)


class EvalExecuteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.spec = make_spec(self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def test_success_is_one_invoke_and_preserves_provenance_and_timing(self):
        invoker = SequenceInvoker([(0, valid_result(self.spec))])

        outcome = run_target_attempts(self.spec, invoker=invoker)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.readiness.status, "ready")
        self.assertEqual(invoker.calls, 1)
        self.assertEqual(len(outcome.attempts), 1)
        attempt = outcome.final_attempt
        self.assertEqual(attempt.attempt, 1)
        self.assertEqual(attempt.host_exit_code, 0)
        self.assertIsNone(attempt.failure)
        self.assertGreaterEqual(attempt.duration_seconds, 0.0)
        self.assertTrue(attempt.started_at.endswith("Z"))
        self.assertEqual(outcome.spec.transport, "opencode")
        self.assertEqual(outcome.spec.model, "openai/test-model")
        self.assertEqual(outcome.spec.reasoning, "medium")
        self.assertEqual(attempt.result["reasoning"], "medium")

    def test_default_adapter_calls_existing_invoke_exactly_once(self):
        expected = valid_result(self.spec)

        def fake_invoke(args):
            Path(args.output).write_text(json.dumps(expected), encoding="utf-8")
            return 0

        with patch("runner.eval_execute.invoke", side_effect=fake_invoke) as mocked:
            host_exit, result = invoke_once(self.spec)

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(host_exit, 0)
        self.assertEqual(result, expected)

    def test_product_failure_is_not_infrastructure_or_retryable(self):
        policy = AlwaysRetryPolicy()
        invoker = SequenceInvoker(
            [(0, valid_result(
                self.spec,
                exit_code=7,
                runtime_evidence=complete_empty_runtime_evidence(),
            ))]
        )

        outcome = run_target_attempts(
            self.spec,
            invoker=invoker,
            retry_policy=policy,
            max_attempts=3,
        )

        failure = outcome.final_attempt.failure
        self.assertEqual(failure.plane, "product")
        self.assertEqual(failure.code, "product_error")
        self.assertFalse(failure.retry_safe)
        self.assertEqual(outcome.readiness.status, "ready")
        self.assertEqual(invoker.calls, 1)
        self.assertEqual(policy.calls, 0)
        self.assertFalse(outcome.retry_decisions[-1].retry)

    def test_inner_timeout_is_product_failure(self):
        invoker = SequenceInvoker(
            [(0, valid_result(self.spec, exit_code=124, timed_out=True))]
        )

        outcome = run_target_attempts(self.spec, invoker=invoker)

        failure = outcome.final_attempt.failure
        self.assertEqual(failure.plane, "product")
        self.assertEqual(failure.code, "product_timeout")
        self.assertIsNotNone(outcome.final_attempt.result)

    def test_outer_timeout_is_infrastructure_and_has_no_result(self):
        invoker = SequenceInvoker(
            [subprocess.TimeoutExpired(["podman", "run"], timeout=20)]
        )

        outcome = run_target_attempts(self.spec, invoker=invoker)

        failure = outcome.final_attempt.failure
        self.assertEqual(failure.plane, "infrastructure")
        self.assertEqual(failure.code, "invoke_outer_timeout")
        self.assertFalse(failure.retry_safe)
        self.assertIsNone(outcome.final_attempt.result)
        self.assertIsNone(outcome.final_attempt.host_exit_code)

    def test_invalid_result_fails_closed(self):
        invalid = valid_result(self.spec)
        invalid["schema"] = "wrong/v1"
        invoker = SequenceInvoker([(0, invalid)])

        outcome = run_target_attempts(self.spec, invoker=invoker)

        failure = outcome.final_attempt.failure
        self.assertEqual(failure.plane, "infrastructure")
        self.assertEqual(failure.code, "invoke_invalid_result")
        self.assertIsNone(outcome.final_attempt.result)

    def test_explicit_transient_retry_then_success_preserves_prior_error(self):
        transient = valid_result(
            self.spec,
            exit_code=2,
            stderr="ProviderError: provider.no-route: Model unavailable",
            runtime_evidence=complete_empty_runtime_evidence(),
        )
        invoker = SequenceInvoker([(2, transient), (0, valid_result(self.spec))])

        outcome = run_target_attempts(
            self.spec,
            invoker=invoker,
            retry_policy=TransientProviderRetryPolicy(),
            max_attempts=2,
        )

        self.assertTrue(outcome.succeeded)
        self.assertEqual(invoker.calls, 2)
        self.assertEqual([a.attempt for a in outcome.attempts], [1, 2])
        self.assertEqual(
            outcome.attempts[0].failure.code, "provider_transient_unavailable"
        )
        self.assertTrue(outcome.attempts[0].failure.retry_safe)
        self.assertIsNone(outcome.attempts[1].failure)
        self.assertEqual(len(outcome.retry_decisions), 1)
        self.assertTrue(outcome.retry_decisions[0].retry)

    def test_transient_text_without_authoritative_empty_capture_is_not_replay_safe(self):
        transient = valid_result(
            self.spec,
            exit_code=2,
            stderr="provider.no-route: Model unavailable",
        )
        invoker = SequenceInvoker([(2, transient), (0, valid_result(self.spec))])

        outcome = run_target_attempts(
            self.spec,
            invoker=invoker,
            retry_policy=TransientProviderRetryPolicy(),
            max_attempts=2,
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(outcome.final_attempt.failure.code, "provider_transient_unavailable")
        self.assertFalse(outcome.final_attempt.failure.retry_safe)
        self.assertIn("not replay-safe", outcome.retry_decisions[0].reason)

    def test_retry_exhaustion_is_bounded_and_history_is_visible(self):
        transient = valid_result(
            self.spec,
            exit_code=2,
            stderr="provider.no-route: Model unavailable",
            runtime_evidence=complete_empty_runtime_evidence(),
        )
        invoker = SequenceInvoker([(2, transient), (2, transient)])

        outcome = run_target_attempts(
            self.spec,
            invoker=invoker,
            retry_policy=TransientProviderRetryPolicy(),
            max_attempts=2,
        )

        self.assertEqual(invoker.calls, 2)
        self.assertEqual(len(outcome.attempts), 2)
        self.assertEqual(
            [a.failure.code for a in outcome.attempts],
            ["provider_transient_unavailable", "provider_transient_unavailable"],
        )
        self.assertEqual(len(outcome.retry_decisions), 2)
        self.assertTrue(outcome.retry_decisions[0].retry)
        self.assertFalse(outcome.retry_decisions[1].retry)
        self.assertEqual(outcome.retry_decisions[1].reason, "maximum attempts reached")

    def test_non_retryable_failure_blocks_even_aggressive_policy(self):
        policy = AlwaysRetryPolicy()
        invoker = SequenceInvoker([(0, valid_result(self.spec, exit_code=9))])

        outcome = run_target_attempts(
            self.spec,
            invoker=invoker,
            retry_policy=policy,
            max_attempts=5,
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(policy.calls, 0)
        self.assertIn("not replay-safe", outcome.retry_decisions[0].reason)

    def test_canonical_readiness_is_applied_and_not_retried(self):
        policy = AlwaysRetryPolicy()
        invoker = SequenceInvoker(
            [(0, valid_result(self.spec, runtime_evidence=incomplete_runtime_evidence()))]
        )

        outcome = run_target_attempts(
            self.spec,
            invoker=invoker,
            evidence_requirement=EvidenceRequirement((BOUNDARY_NATIVE,)),
            max_attempts=2,
            retry_policy=policy,
        )

        self.assertEqual(outcome.readiness.status, "incomplete")
        self.assertEqual(outcome.final_attempt.failure.plane, "evidence")
        self.assertEqual(outcome.final_attempt.failure.code, "evidence_incomplete")
        self.assertFalse(outcome.final_attempt.failure.retry_safe)
        self.assertEqual(invoker.calls, 1)
        self.assertEqual(policy.calls, 0)

    def test_product_failure_keeps_nonready_evidence_separate(self):
        invoker = SequenceInvoker(
            [
                (
                    0,
                    valid_result(
                        self.spec,
                        exit_code=7,
                        runtime_evidence=incomplete_runtime_evidence(),
                    ),
                )
            ]
        )

        outcome = run_target_attempts(
            self.spec,
            invoker=invoker,
            evidence_requirement=EvidenceRequirement((BOUNDARY_NATIVE,)),
        )

        self.assertEqual(outcome.final_attempt.failure.plane, "product")
        self.assertEqual(outcome.final_attempt.failure.code, "product_error")
        self.assertEqual(outcome.readiness.status, "incomplete")
        self.assertEqual(invoker.calls, 1)

    def test_max_attempts_validation_rejects_unbounded_or_invalid_values(self):
        invoker = SequenceInvoker([(0, valid_result(self.spec))])
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    run_target_attempts(
                        self.spec,
                        invoker=invoker,
                        max_attempts=value,  # type: ignore[arg-type]
                    )


if __name__ == "__main__":
    unittest.main()
