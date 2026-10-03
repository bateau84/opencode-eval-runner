"""QA of launch policy at the container-engine I/O boundary."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runner import protected_launch
from runner.protected import CaptureError, parser

REFERENCE = "ghcr.io/example/tool@sha256:" + "1" * 64


def inspected(volumes):
    return {"Id": "sha256:" + "2" * 64, "RepoDigests": [REFERENCE], "Config": {"Volumes": volumes}}


class ImagePolicyTests(unittest.TestCase):
    def test_image_declared_volumes_are_rejected_before_launch(self):
        replies = [subprocess.CompletedProcess([], 0, "", ""),
                   subprocess.CompletedProcess([], 0, json.dumps([inspected({"/state": {}})]), "")]
        with patch.object(protected_launch, "run", side_effect=replies):
            with self.assertRaisesRegex(CaptureError, "image_declares_volumes"):
                protected_launch.image_info(REFERENCE)

    def test_volume_free_image_remains_usable(self):
        for volumes in (None, {}):
            replies = [subprocess.CompletedProcess([], 0, "", ""),
                       subprocess.CompletedProcess([], 0, json.dumps([inspected(volumes)]), "")]
            with patch.object(protected_launch, "run", side_effect=replies):
                self.assertEqual(protected_launch.image_info(REFERENCE), inspected(volumes))

    def test_cleanup_only_attempts_resources_created_by_this_run(self):
        created = {"network": True, "target": False, "runtime": True}
        with patch.object(
            protected_launch.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0),
        ) as engine:
            failures = protected_launch.cleanup_resources(created, "runtime", "target", "network")
        self.assertEqual(failures, [])
        commands = [call.args[0] for call in engine.call_args_list]
        self.assertEqual(commands, [
            ["docker", "rm", "--volumes", "-f", "runtime"],
            ["docker", "network", "rm", "network"],
        ])

    def test_cleanup_failure_is_reported_even_for_negative_runs(self):
        created = {"network": True, "target": True, "runtime": True}
        replies = [
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 1),
        ]
        with patch.object(protected_launch.subprocess, "run", side_effect=replies):
            failures = protected_launch.cleanup_resources(created, "runtime", "target", "network")
        self.assertEqual(failures, ["runtime", "network"])

    def test_rejected_image_writes_specific_non_evidence_and_never_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "policy").write_text(json.dumps({"version": 1, "secrets": [], "allowed_values": []}))
            (root / "tools").write_text(json.dumps([{"name": "echo", "input": {}}]))
            (root / "program").write_text('return "unchanged";')
            args = parser().parse_args(["--image", REFERENCE, "--tool-image", REFERENCE,
                "--policy-file", str(root / "policy"), "--tools-file", str(root / "tools"),
                "--program-file", str(root / "program"), "--output", str(root / "result")])
            with patch.object(protected_launch, "image_info", side_effect=CaptureError("image_declares_volumes")), \
                 patch.object(protected_launch.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as engine:
                self.assertEqual(protected_launch.invoke(args), 2)
            result = json.loads((root / "result").read_text())
            self.assertFalse(result["observed_execution"]["evidence_eligible"])
            self.assertEqual(result["observed_execution"]["issues"], ["image_declares_volumes"])
            self.assertTrue(all(call.args[0][1] != "run" for call in engine.call_args_list))
            removals = [call.args[0] for call in engine.call_args_list
                        if len(call.args[0]) > 1 and call.args[0][1] in {"rm", "network"}]
            self.assertEqual(removals, [])


if __name__ == "__main__":
    unittest.main()
