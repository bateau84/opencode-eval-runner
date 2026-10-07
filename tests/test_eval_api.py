from __future__ import annotations

import sys
import types
import unittest
from contextlib import nullcontext
from pathlib import Path

from runner.eval_api import (
    EVAL_COMMAND,
    EVAL_PROFILE_API,
    EVAL_PROFILE_OPTION,
    EVAL_PROFILE_REFERENCE_SYNTAX,
    EvalProfile,
    EvalProfileError,
    EvidenceRequirement,
    InvocationSpec,
    NormalizedCase,
    SemanticDecision,
    load_eval_profile,
    validate_eval_profile,
)
from runner.eval_types import (
    InvocationSpec as InternalInvocationSpec,
    NormalizedCase as InternalNormalizedCase,
)


class CompleteProfile:
    def discover_cases(self):
        return (
            NormalizedCase(
                id="PUBLIC-API-1",
                selectors=("PUBLIC-API-1",),
                lane="standard",
                project_data=None,
                metadata={},
            ),
        )

    def prepare(self, case, iteration):
        return nullcontext({"case": case.id, "iteration": iteration})

    def target_spec(self, case, prepared):
        return InvocationSpec(
            transport="opencode",
            model="test/model",
            reasoning=None,
            agent=None,
            skill=None,
            workspace=Path("."),
            workspace_mode="ro",
            prompt="target",
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
            timeout_seconds=1,
            container_timeout=2,
        )

    def target_evidence_requirement(self, case, prepared):
        return EvidenceRequirement()

    def deterministic_checks(self, case, prepared, target, readiness):
        return ()

    def judge_spec(self, case, prepared, target, checks):
        return None

    def parse_judge(self, case, prepared, judge):
        return SemanticDecision("pass", "ok", None)

    def artifact_metadata(self, case, prepared):
        return {"profile": "test"}


class IncompleteProfile:
    def discover_cases(self):
        return ()


class EvalPublicApiTests(unittest.TestCase):
    def test_public_import_surface_reuses_canonical_engine_types(self):
        self.assertEqual(EVAL_COMMAND, "eval")
        self.assertEqual(EVAL_PROFILE_API, "opencode-eval-runner/eval-profile/v1")
        self.assertEqual(EVAL_PROFILE_OPTION, "--profile")
        self.assertEqual(EVAL_PROFILE_REFERENCE_SYNTAX, "module:attribute")
        self.assertIs(NormalizedCase, InternalNormalizedCase)
        self.assertIs(InvocationSpec, InternalInvocationSpec)

    def test_complete_profile_validates_without_running_hooks(self):
        profile = CompleteProfile()

        validated = validate_eval_profile(profile)

        self.assertIs(validated, profile)
        self.assertIsInstance(profile, EvalProfile)

    def test_validation_reports_missing_required_hooks(self):
        with self.assertRaisesRegex(
            EvalProfileError,
            "prepare.*target_spec.*target_evidence_requirement.*"
            "deterministic_checks.*judge_spec.*parse_judge.*artifact_metadata",
        ):
            validate_eval_profile(IncompleteProfile())

    def test_uninstantiated_profile_class_is_rejected(self):
        with self.assertRaisesRegex(EvalProfileError, "initialized object"):
            validate_eval_profile(CompleteProfile)

    def test_loader_resolves_exact_module_attribute_object(self):
        module_name = "_opencode_eval_runner_test_profile"
        module = types.ModuleType(module_name)
        profile = CompleteProfile()
        module.profile = profile
        prior = sys.modules.get(module_name)
        sys.modules[module_name] = module
        try:
            loaded = load_eval_profile(f"{module_name}:profile")
        finally:
            if prior is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = prior

        self.assertIs(loaded, profile)

    def test_loader_rejects_malformed_reference(self):
        for reference in (
            "",
            "module",
            ":profile",
            "module:",
            "module:profile:extra",
            " module:profile",
            "module:not-an-identifier",
        ):
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(
                    EvalProfileError,
                    "module:attribute",
                ):
                    load_eval_profile(reference)

    def test_loader_rejects_missing_export(self):
        module_name = "_opencode_eval_runner_test_profile_missing"
        module = types.ModuleType(module_name)
        prior = sys.modules.get(module_name)
        sys.modules[module_name] = module
        try:
            with self.assertRaisesRegex(EvalProfileError, "has no export"):
                load_eval_profile(f"{module_name}:profile")
        finally:
            if prior is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = prior


if __name__ == "__main__":
    unittest.main()
