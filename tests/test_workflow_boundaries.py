"""Review checks for publication/signing workflow trust boundaries.

These inspect declared job boundaries; actual Actions runs must also exercise
image publication and digest-based verification. No YAML parser dependency.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def workflow_jobs(name):
    text = (ROOT / ".github/workflows" / name).read_text()
    prefix, body = text.split("\njobs:\n", 1)
    matches = list(re.finditer(r"^  ([a-z-]+):\n", body, re.MULTILINE))
    jobs = {m[1]: body[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(body)]
            for i, m in enumerate(matches)}
    return prefix, jobs


class PublicationBoundaryTests(unittest.TestCase):
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

    def test_external_actions_are_pinned_and_errors_not_ignored(self):
        for name in ("protected-channel.yml", "local-runtime.yml", "sign-normal-invoke-evidence.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            for action in re.findall(r"uses: (\S+)", text):
                self.assertRegex(action, r"^[A-Za-z0-9_/-]+@[0-9a-f]{40}$")
            self.assertNotIn("continue-on-error", text)
            self.assertNotIn("pull_request_target", text)

    def test_signer_is_default_branch_workflow_run_not_pr_code(self):
        text = (ROOT / ".github/workflows/sign-normal-invoke-evidence.yml").read_text()
        prefix, jobs = workflow_jobs("sign-normal-invoke-evidence.yml")
        self.assertIn("workflow_run:", prefix)
        self.assertNotIn("pull_request:", prefix)
        self.assertNotIn("workflow_dispatch:", prefix)
        self.assertEqual(set(jobs), {"sign"})
        signer = jobs["sign"]
        self.assertIn("id-token: write", prefix)
        self.assertIn("packages: write", prefix)
        self.assertIn("actions: read", prefix)
        self.assertNotIn("actions/checkout", signer)
        self.assertNotIn("docker run", signer)
        self.assertNotIn("docker build", signer)
        self.assertIn("EXPECTED_BUILD_WORKFLOW_BLOB", signer)
        self.assertIn("gh api", signer)
        self.assertIn("cosign sign --yes", signer)
        self.assertIn("cosign sign-blob --yes", signer)
        self.assertIn("--certificate-identity", signer)
        self.assertIn("protected_capture_accepted", signer)
        self.assertIn('"unsupported"', signer)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository", signer)

    def test_signer_pins_reviewed_build_workflow_blob(self):
        signer = (ROOT / ".github/workflows/sign-normal-invoke-evidence.yml").read_text()
        runtime = (ROOT / ".github/workflows/local-runtime.yml").read_bytes()
        import hashlib
        blob = hashlib.sha1(b"blob " + str(len(runtime)).encode() + b"\0" + runtime).hexdigest()
        match = re.search(r"EXPECTED_BUILD_WORKFLOW_BLOB:\s*([0-9a-f]{40})", signer)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), blob)


if __name__ == "__main__":
    unittest.main()
