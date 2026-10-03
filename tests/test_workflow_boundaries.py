"""Review checks for the two new fixed publication workflows.

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
        for name in ("protected-channel.yml", "local-runtime.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            for action in re.findall(r"uses: (\S+)", text):
                self.assertRegex(action, r"^[A-Za-z0-9_/-]+@[0-9a-f]{40}$")
            self.assertNotIn("continue-on-error", text)
            self.assertNotIn("pull_request_target", text)


if __name__ == "__main__":
    unittest.main()
