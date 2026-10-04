"""Review checks for publication/signing workflow trust boundaries.

These inspect declared job boundaries; actual Actions runs must also exercise
image publication and digest-based verification. No YAML parser dependency.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


JOB_ID = r"[A-Za-z_][A-Za-z0-9_-]*"


def parse_workflow_jobs(text):
    prefix, body = text.split("\njobs:\n", 1)
    matches = list(re.finditer(rf"^  ({JOB_ID}):\n", body, re.MULTILINE))
    jobs = {m[1]: body[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(body)]
            for i, m in enumerate(matches)}
    return prefix, jobs


def workflow_jobs(name):
    return parse_workflow_jobs((ROOT / ".github/workflows" / name).read_text())


class PublicationBoundaryTests(unittest.TestCase):
    def test_job_parser_covers_digits_and_underscores(self):
        prefix, jobs = parse_workflow_jobs(
            "name: fixture\non:\n  pull_request:\njobs:\n"
            "  build:\n    runs-on: ubuntu-latest\n"
            "  publish_2:\n    runs-on: ubuntu-latest\n"
            "  _verify9:\n    runs-on: ubuntu-latest\n"
        )
        self.assertIn("pull_request", prefix)
        self.assertEqual(set(jobs), {"build", "publish_2", "_verify9"})

    def test_normal_invoke_workflow_tracks_public_runner_implementation(self):
        text = (ROOT / ".github/workflows/local-runtime.yml").read_text()
        for path in (
            "runtime-patches/**",
            "runner/cli.py",
            "runner/observer.py",
            "container/**",
            "bin/opencode-eval-runner",
            "tests/integration/run_capture_probe.py",
            "tests/integration/capture_probe.ts",
        ):
            self.assertIn("- " + path, text)

    def test_only_fresh_publisher_has_package_write_authority(self):
        for name in ("protected-channel.yml", "local-runtime.yml"):
            with self.subTest(workflow=name):
                prefix, jobs = workflow_jobs(name)
                self.assertNotIn("packages: write", prefix)
                self.assertEqual(set(jobs), {"build", "publish", "verify"})
                for job in ("build", "verify"):
                    self.assertNotIn("packages: write", jobs[job])
                    self.assertNotIn("secrets.", jobs[job])
                    self.assertNotIn("github.token", jobs[job])
                    self.assertNotIn("id-token: write", jobs[job])
                publisher = jobs["publish"]
                self.assertIn("needs: build", publisher)
                self.assertIn("packages: write", publisher)
                self.assertIn("docker load", publisher)
                self.assertNotIn("actions/checkout", publisher)
                for prohibited in ("docker run", "docker build", "bun ", "python", "./bin/", "./scripts/", "source ", "eval "):
                    self.assertNotIn(prohibited, publisher)
                self.assertIn("needs: [build, publish]", jobs["verify"])
                self.assertIn("needs.publish.outputs", jobs["verify"])
                self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", jobs["build"])

    def test_evidence_safety_image_copies_and_hashes_only_reviewed_container_sources(self):
        containerfile = (ROOT / "evidence-safety/Containerfile").read_text()
        workflow = (ROOT / ".github/workflows/evidence-safety.yml").read_text()
        self.assertNotIn("COPY container /opt/opencode-eval-runner/container", containerfile)
        for path in ("__init__.py", "evidence_safety.py", "invoke.py"):
            self.assertIn(
                f"COPY container/{path} /opt/opencode-eval-runner/container/{path}",
                containerfile,
            )
            self.assertIn("container/" + path, workflow)
        self.assertIn("ARG PACKAGE_INIT_SHA256", containerfile)
        self.assertIn("io.opencode-eval.evidence-safety-init=$PACKAGE_INIT_SHA256", containerfile)
        self.assertIn("$PACKAGE_INIT_SHA256  /opt/opencode-eval-runner/container/__init__.py", containerfile)
        self.assertIn("--build-arg PACKAGE_INIT_SHA256=", workflow)

    def test_external_actions_are_pinned_and_errors_not_ignored(self):
        for name in ("protected-channel.yml", "local-runtime.yml", "sign-normal-invoke-evidence.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            for action in re.findall(r"uses: (\S+)", text):
                self.assertRegex(action, r"^[A-Za-z0-9_/-]+@[0-9a-f]{40}$")
            self.assertNotIn("continue-on-error", text)
            self.assertNotIn("pull_request_target", text)

    def test_signer_is_manual_default_branch_rebuild_with_approval_gate(self):
        text = (ROOT / ".github/workflows/sign-normal-invoke-evidence.yml").read_text()
        prefix, jobs = workflow_jobs("sign-normal-invoke-evidence.yml")
        self.assertIn("workflow_dispatch:", prefix)
        self.assertNotIn("workflow_run:", prefix)
        self.assertNotRegex(prefix, r"(?m)^  pull_request:\s*$")
        self.assertNotIn("pull_request_target", text)
        self.assertEqual(set(jobs), {"build", "publish", "verify", "sign"})

        build = jobs["build"]
        self.assertIn("github.ref == 'refs/heads/main'", build)
        self.assertIn("gh api", build)
        self.assertIn(".head.sha", build)
        self.assertIn("runtime-patches/apply.py", build)
        self.assertIn("docker build", build)
        self.assertNotIn("packages: write", build)
        self.assertNotIn("id-token: write", build)

        publisher = jobs["publish"]
        self.assertIn("packages: write", publisher)
        self.assertNotIn("id-token: write", publisher)
        self.assertNotIn("actions/checkout", publisher)
        self.assertNotIn("docker run", publisher)
        self.assertIn("docker load", publisher)

        verifier = jobs["verify"]
        self.assertNotIn("packages: write", verifier)
        self.assertNotIn("id-token: write", verifier)
        self.assertIn("run_image_probe.py", verifier)
        self.assertIn("run_eval_live_compat_probe.py", verifier)
        self.assertIn("run_delegated_session_probe.py", verifier)

        signer = jobs["sign"]
        self.assertIn("environment: release-signing", signer)
        self.assertIn("packages: write", signer)
        self.assertIn("id-token: write", signer)
        self.assertNotIn("actions/checkout", signer)
        self.assertNotIn("docker run", signer)
        self.assertNotIn("docker build", signer)
        self.assertIn("cosign sign --yes", signer)
        self.assertIn("cosign sign-blob --yes", signer)
        self.assertIn("--certificate-identity", signer)
        self.assertIn("protected_capture_accepted", signer)
        self.assertIn('"unsupported"', signer)
        self.assertIn("docker login ghcr.io", signer)
        self.assertIn('eval-live-invoke-compatibility', signer)
        self.assertIn('delegated-session-normal-invoke', signer)
        self.assertIn('normal-invoke-runtime-seam-probe', signer)
        self.assertIn('.image == $image', signer)
        self.assertIn('.runner_revision == $source', signer)

    def test_signer_expressions_are_not_escaped_literals(self):
        text = (ROOT / ".github/workflows/sign-normal-invoke-evidence.yml").read_text()
        self.assertNotRegex(text, r"\\\\\$\{\{")
        self.assertNotRegex(text, r"\\\\\$\{[A-Z_]")

    def test_signer_never_auto_signs_pr_artifacts(self):
        text = (ROOT / ".github/workflows/sign-normal-invoke-evidence.yml").read_text()
        self.assertNotIn("github.event.workflow_run", text)
        self.assertNotIn("runtime-publication-", text)
        self.assertNotIn("local-runtime-", text)
        self.assertIn("approved-build-", text)
        self.assertIn("approved-evidence-", text)
        self.assertIn("Reviewed 40-hex source commit", text)


if __name__ == "__main__":
    unittest.main()
