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

    @staticmethod
    def engine(*, removed, failures=(), foreign=False, missing=False, unavailable=False):
        """Independent daemon inventory, not the launcher's ownership flags."""
        identities = {"runtime": "a" * 64, "target": "b" * 64, "network": "c" * 64}
        def call(command, **kwargs):
            if command[2:3] == ["ls"]:
                if unavailable:
                    return subprocess.CompletedProcess(command, 1, "", "offline")
                name = next(arg[5:] for arg in command if arg.startswith("name="))
                name_field = "Name" if command[1] == "network" else "Names"
                output = "" if missing else json.dumps({name_field: name, "ID": identities[name]}) + "\n"
                return subprocess.CompletedProcess(command, 0, output, "")
            if command[2:3] == ["inspect"]:
                identity = command[-1]
                name = next(n for n, i in identities.items() if i == identity)
                labels = {protected_launch.OWNER_LABEL: "someone-else" if foreign else "owner"}
                payload = {"Id": identity, "Name": name}
                payload["Labels" if name == "network" else "Config"] = labels if name == "network" else {"Labels": labels}
                return subprocess.CompletedProcess(command, 0, json.dumps([payload]), "")
            removed.append(command)
            name = next(n for n, i in identities.items() if i == command[-1])
            return subprocess.CompletedProcess(command, int(name in failures), b"", b"")
        return call

    def test_cleanup_only_attempts_resources_with_verified_ownership(self):
        removed = []
        with patch.object(protected_launch.subprocess, "run", side_effect=self.engine(removed=removed)):
            failures = protected_launch.cleanup_resources(
                {"network": True, "target": False, "runtime": True}, "runtime", "target", "network", "owner")
        self.assertEqual(failures, [])
        self.assertEqual(removed, [["docker", "rm", "--volumes", "-f", "a" * 64],
                                   ["docker", "network", "rm", "c" * 64]])

    def test_cleanup_failure_is_reported_even_for_negative_runs(self):
        removed = []
        with patch.object(protected_launch.subprocess, "run", side_effect=self.engine(removed=removed, failures=("runtime", "network"))):
            failures = protected_launch.cleanup_resources(
                {"network": True, "target": True, "runtime": True}, "runtime", "target", "network", "owner")
        self.assertEqual(failures, ["runtime", "network"])
        self.assertEqual(len(removed), 3)

    def test_cleanup_does_not_delete_a_same_named_foreign_resource(self):
        removed = []
        with patch.object(protected_launch.subprocess, "run", side_effect=self.engine(removed=removed, foreign=True)):
            failures = protected_launch.cleanup_resources({"runtime": True}, "runtime", "target", "network", "owner")
        self.assertEqual(failures, ["runtime"])
        self.assertEqual(removed, [])

    def test_cleanup_distinguishes_absence_from_unavailable_engine(self):
        for missing, unavailable in ((True, False), (False, True)):
            removed = []
            with patch.object(protected_launch.subprocess, "run", side_effect=self.engine(
                    removed=removed, missing=missing, unavailable=unavailable)):
                failures = protected_launch.cleanup_resources({"runtime": True}, "runtime", "target", "network", "owner")
            self.assertEqual(failures, ["runtime"] if unavailable else [])
            self.assertEqual(removed, [])

    def test_create_response_loss_is_reconciled_for_network_and_both_containers(self):
        for stage in ("network", "target", "runtime"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "policy").write_text(json.dumps({"version": 1, "secrets": [], "allowed_values": []}))
                (root / "tools").write_text(json.dumps([{"name": "echo", "input": {}}]))
                (root / "program").write_text('return "unchanged";')
                args = parser().parse_args(["--image", REFERENCE, "--tool-image", REFERENCE,
                    "--policy-file", str(root / "policy"), "--tools-file", str(root / "tools"),
                    "--program-file", str(root / "program"), "--output", str(root / "result")])
                live = {}
                created = []
                removed = []
                def daemon(command, **kwargs):
                    if command[1:3] == ["network", "create"] or command[1] == "create":
                        is_network = command[1] == "network"
                        name = command[-1] if is_network else command[command.index("--name") + 1]
                        kind = "network" if is_network else "target" if name.endswith("-tools") else "runtime"
                        owner = command[command.index("--label") + 1].partition("=")[2]
                        identity = {"network": "a", "target": "b", "runtime": "c"}[kind] * 64
                        live[identity] = {"Id": identity, "Name": name,
                            "Labels" if is_network else "Config": {protected_launch.OWNER_LABEL: owner}
                            if is_network else {"Labels": {protected_launch.OWNER_LABEL: owner}}}
                        created.append(kind)
                        if kind == stage:
                            # Daemon has created it; CLI never receives its response.
                            raise subprocess.TimeoutExpired(command, 1)
                        return subprocess.CompletedProcess(command, 0, identity, "")
                    if command[2:3] == ["ls"]:
                        name = next(arg[5:] for arg in command if arg.startswith("name="))
                        name_field = "Name" if command[1] == "network" else "Names"
                        rows = [{name_field: r["Name"], "ID": i} for i, r in live.items() if r["Name"] == name]
                        return subprocess.CompletedProcess(command, 0, "\n".join(json.dumps(r) for r in rows), "")
                    if command[2:3] == ["inspect"]:
                        return subprocess.CompletedProcess(command, 0, json.dumps([live[command[-1]]]), "")
                    if command[1] == "rm" or command[1:3] == ["network", "rm"]:
                        removed.append(command[-1]); del live[command[-1]]
                    return subprocess.CompletedProcess(command, 0, "", "")
                with patch.object(protected_launch, "image_info", return_value=inspected(None)), \
                     patch.object(protected_launch.subprocess, "run", side_effect=daemon):
                    self.assertEqual(protected_launch.invoke(args), 2)
                self.assertEqual(created[-1], stage)
                self.assertEqual(len(removed), len(created))
                self.assertEqual(live, {})
                result = json.loads((root / "result").read_text())
                self.assertEqual(result["observed_execution"]["issues"], ["protected_transport_failed"])
                self.assertFalse(result["observed_execution"]["evidence_eligible"])

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
