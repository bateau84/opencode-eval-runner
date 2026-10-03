"""CI exit-policy tests; synthetic summaries are not runtime capture evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "capture_probe_exit_policy",
    Path(__file__).parent / "integration" / "run_capture_probe.py",
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

# The expected old-image diagnostic shape is independent of the policy's set.
BASELINE = {
    "kind": "capture-boundary-probe",
    "version": 1,
    "image": "ghcr.io/bateau84/opencode-eval-runner@sha256:68ef7322c75aede0e8cc76d0e3531e8b82dd417bbb5e5100264a89eab7fe8627",
    "diagnostics_passed": True,
    "handoff_acceptance": "BLOCKED",
    "independent_code_approval": False,
    "checks": {
        "pinned_image": True,
        "runtime_2_0_18": True,
        "scenarios_completed": True,
        "identical_calls_overlap_and_finish_reversed": True,
        "tool_behavior_unchanged": True,
        "missing_producer_not_evidence": True,
        "forged_sidecar_rejected": True,
        "diagnostic_hooks_toggle": True,
        "shared_id_counterexample": True,
        "caught_throw_has_no_after_hook": True,
        "early_after_is_not_final_return": True,
        "no_capture_eligible": True,
    },
}


class CaptureProbeExitTests(unittest.TestCase):
    def check_modes(self, summary, expected):
        for negative in (False, True):
            with self.subTest(negative_control=negative):
                self.assertEqual(
                    probe.probe_exit_code(summary, expect_unsupported_baseline=negative), expected,
                )

    def test_default_still_rejects_blocked_capture(self):
        self.assertEqual(probe.probe_exit_code(BASELINE), 4)

    def test_explicit_negative_control_passes_without_acceptance(self):
        before = copy.deepcopy(BASELINE)
        self.assertEqual(probe.probe_exit_code(BASELINE, expect_unsupported_baseline=True), 0)
        self.assertEqual(BASELINE, before)
        self.assertEqual(BASELINE["handoff_acceptance"], "BLOCKED")
        self.assertIs(BASELINE["independent_code_approval"], False)

    def test_every_diagnostic_failure_still_fails_both_modes(self):
        for name in BASELINE["checks"]:
            with self.subTest(check=name):
                summary = copy.deepcopy(BASELINE)
                summary["checks"][name] = False
                self.check_modes(summary, 1)

    def test_missing_check_is_not_a_smaller_passing_suite(self):
        for name in BASELINE["checks"]:
            with self.subTest(check=name):
                summary = copy.deepcopy(BASELINE)
                del summary["checks"][name]
                self.check_modes(summary, 1)

    def test_empty_extra_and_malformed_checks_fail(self):
        for checks in ({}, None, [], True, {**BASELINE["checks"], "unexpected": True}):
            with self.subTest(checks=checks):
                self.check_modes({**BASELINE, "checks": checks}, 1)

    def test_truthy_nonboolean_diagnostics_are_not_success(self):
        for value in (1, "true", [True], None):
            with self.subTest(value=value):
                summary = copy.deepcopy(BASELINE)
                summary["checks"]["no_capture_eligible"] = value
                self.check_modes(summary, 1)
                self.check_modes({**BASELINE, "diagnostics_passed": value}, 1)

    def test_new_or_mutable_image_cannot_use_old_image_control(self):
        for image in ("ghcr.io/bateau84/opencode-eval-runner:opencode-edge",
                      "ghcr.io/bateau84/opencode-eval-runner@sha256:" + "a" * 64, None):
            with self.subTest(image=image):
                self.check_modes({**BASELINE, "image": image}, 1)

    def test_unexpected_acceptance_or_approval_fails(self):
        for key, value in (("handoff_acceptance", "PASS"), ("handoff_acceptance", None),
                           ("independent_code_approval", True), ("independent_code_approval", 0),
                           ("diagnostics_passed", False)):
            with self.subTest(key=key, value=value):
                self.check_modes({**BASELINE, key: value}, 1)

    def test_wrong_summary_kind_or_version_fails(self):
        for key, value in (("kind", "different-probe"), ("version", 2), ("version", True),
                           ("version", "1")):
            with self.subTest(key=key, value=value):
                self.check_modes({**BASELINE, key: value}, 1)

    def test_missing_required_summary_fields_fail(self):
        for key in BASELINE:
            with self.subTest(key=key):
                summary = copy.deepcopy(BASELINE)
                del summary[key]
                self.check_modes(summary, 1)


if __name__ == "__main__":
    unittest.main()
