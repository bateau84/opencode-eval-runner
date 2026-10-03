"""Trusted host launch and private collection; not an unsigned-file verifier."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile

from .protected import (CaptureError, IMAGE, PROFILE, _require, _shape, empty_projection,
                        import_capture, read_private, strict_json)


def run(command, *, timeout=120):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def bounded_file(path, limit):
    # Open each input once, then execute this snapshot, not a reopened original.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        _require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), "input_not_regular")
        raw = source.read(limit + 1)
    _require(len(raw) <= limit, "input_limit")
    return raw


def image_info(reference):
    run(["docker", "pull", reference])
    info = strict_json(run(["docker", "image", "inspect", reference]).stdout)[0]
    _require(reference in info.get("RepoDigests", []), "image_digest_not_resolved")
    _require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", info.get("Id", ""))), "invalid_image_id")
    # Docker otherwise creates anonymous persistent storage before the later
    # mount audit can reject it. This profile permits no image-declared volumes.
    _require(not (info.get("Config") or {}).get("Volumes"), "image_declares_volumes")
    return info


def cleanup_resources(created, runtime, target, network):
    """Remove only resources this invocation successfully created."""
    failures = []
    resources = (
        ("runtime", ["docker", "rm", "--volumes", "-f", runtime]),
        ("target", ["docker", "rm", "--volumes", "-f", target]),
        ("network", ["docker", "network", "rm", network]),
    )
    for resource, command in resources:
        if not created.get(resource, False):
            continue
        try:
            cleanup = subprocess.run(command, capture_output=True, timeout=20, check=False)
            if cleanup.returncode:
                failures.append(resource)
        except (OSError, subprocess.SubprocessError):
            failures.append(resource)
    return failures


def invoke(args: argparse.Namespace, *, _test_receive=None, _test_prepare=None, _test_target_probe=None) -> int:
    for reference in (args.image, args.tool_image):
        _require(bool(IMAGE.fullmatch(reference)), "immutable_image_required")
    _require(type(args.timeout) is int and 1 <= args.timeout <= 300, "invalid_timeout")
    policy_raw = bounded_file(args.policy_file, 1024 * 1024)
    policy = strict_json(policy_raw)
    _shape(policy, ("version", "secrets", "allowed_values"))
    _require(type(policy["version"]) is int and policy["version"] == 1, "invalid_policy")
    _require(isinstance(policy["allowed_values"], list) and isinstance(policy["secrets"], list)
             and all(isinstance(s, str) and s for s in policy["secrets"]), "invalid_policy")
    tools_raw = bounded_file(args.tools_file, 1024 * 1024)
    tools = strict_json(tools_raw)
    _require(isinstance(tools, list) and 0 < len(tools) <= 64, "invalid_tools")
    for tool in tools:
        _require(isinstance(tool, dict) and {"name", "input"} <= tool.keys()
                 and not tool.keys() - {"name", "input", "description"}, "invalid_tools")
        _require(isinstance(tool["name"], str) and bool(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", tool["name"])), "invalid_tools")
        _require(isinstance(tool["input"], dict) and isinstance(tool.get("description", ""), str), "invalid_tools")
    _require(len({tool["name"] for tool in tools}) == len(tools), "duplicate_tool")
    program_raw = bounded_file(args.program_file, 128 * 1024)
    program = program_raw.decode("utf-8")
    run_id = secrets.token_hex(32)
    prefix = "capture-" + run_id[:16]
    network, target, runtime = prefix + "-net", prefix + "-tools", prefix + "-runtime"
    output = Path(os.path.abspath(args.output))
    _require(all(output.resolve() != Path(p).resolve() for p in (args.program_file, args.tools_file, args.policy_file)), "output_overwrites_input")
    output.parent.mkdir(parents=True, exist_ok=True)
    policy_id = hashlib.sha256(policy_raw).hexdigest()
    repo = Path(__file__).resolve().parents[1]
    collector_sources = {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in
                         ("runner/protected.py", "runner/protected_launch.py", "bin/opencode-eval-runner")}
    launch = {"collector_sources_sha256": collector_sources, "run_id": run_id, "profile": PROFILE, "runtime_image": args.image, "tool_image": args.tool_image,
              "policy_sha256": policy_id, "program_sha256": hashlib.sha256(program_raw).hexdigest(),
              "tools_sha256": hashlib.sha256(tools_raw).hexdigest()}
    result = {"schema": "opencode-eval-runner/v1", "profile": PROFILE, "run_id": run_id,
              "runtime_image": args.image, "tool_image": args.tool_image, "policy_id": policy_id,
              "observed_execution": empty_projection(run_id),
              "image_signatures_verified": False, "artifact_signed": False}
    code = 4
    with tempfile.TemporaryDirectory(prefix="protected-capture-") as tmp:
        root = Path(tmp)
        inputs, capture = root / "input", root / "capture"
        inputs.mkdir(mode=0o755)
        capture.mkdir(mode=0o777)
        capture.chmod(0o777)  # Only its parent is host-private; the target gets no mount.
        hardening = ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                     "--pids-limit", "128", "--memory", "1g", "--cpus", "2", "--user", "1000:1000",
                     "--log-driver", "none"]
        created = {"network": False, "target": False, "runtime": False}
        try:
            runtime_info, target_info = image_info(args.image), image_info(args.tool_image)
            launch.update(runtime_config_digest=runtime_info["Id"], tool_config_digest=target_info["Id"])
            launch_raw = json.dumps(launch, sort_keys=True, separators=(",", ":")).encode()
            launch_id = hashlib.sha256(launch_raw).hexdigest()
            request = {"run_id": run_id, "program": program, "tools": tools, "tool_url": "http://" + target + ":8080",
                       "policy_id": policy_id, "launch_id": launch_id, "observe": not args.no_observe}
            (inputs / "request.json").write_text(json.dumps(request))
            (inputs / "policy.json").write_bytes(policy_raw)
            (inputs / "tools.json").write_bytes(tools_raw)
            (inputs / "launch.json").write_bytes(launch_raw)
            for file in inputs.iterdir():
                file.chmod(0o644)
            result.update(launch=launch, launch_id=launch_id)
            if _test_prepare is not None:
                _test_prepare(capture)
            run(["docker", "network", "create", "--internal", network])
            created["network"] = True
            run(["docker", "run", "-d", "--name", target, "--network", network, *hardening,
                 "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m", args.tool_image])
            created["target"] = True
            # No arbitrary mounts, plugin roots, host credentials or command override.
            command = ["docker", "run", "--name", runtime, "--network", network, *hardening,
                       "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=1g",
                       "--tmpfs", "/workspace:rw,nosuid,nodev,size=32m,mode=1777",
                       "--volume", str(inputs) + ":/input:ro", "--volume", str(capture) + ":/capture:rw",
                       "--entrypoint", "python3", args.image, "/opt/protected/invoke.py"]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout, check=False)
            # A named runtime container exists only if inspect succeeds. Track it
            # before any later validation so failed/ineligible runs still clean it.
            runtime_state = strict_json(run(["docker", "inspect", runtime]).stdout)[0]
            created["runtime"] = True
            # Verify the engine's actual container identities, not claims in JSON.
            target_state = strict_json(run(["docker", "inspect", target]).stdout)[0]
            _require(runtime_state["Image"] == launch["runtime_config_digest"]
                     and target_state["Image"] == launch["tool_config_digest"], "launched_image_mismatch")
            _require(runtime_state["State"]["Running"] is False, "writer_still_running")
            _require(not target_state.get("Mounts") and not target_state["HostConfig"].get("PidMode"), "unexpected_target_access")
            result["launched_images_verified"] = True
            envelope = strict_json(completed.stdout)
            _shape(envelope, ("profile", "run_id", "launch_id", "runtime_exit", "script_output", "writer_exited", "receipt"))
            _require(envelope["profile"] == PROFILE and envelope["run_id"] == run_id
                     and envelope["launch_id"] == launch_id, "invalid_supervisor")
            result["collection_receipt"] = envelope["receipt"]
            result.update(runtime_exit=envelope["runtime_exit"], script_output=envelope["script_output"])
            transport_ok = completed.returncode == 0 and type(envelope["runtime_exit"]) is int and envelope["runtime_exit"] == 0 and envelope["writer_exited"] is True
            if args.no_observe:
                result["observed_execution"]["issues"] = ["capture_not_requested"]
                code = 0 if transport_ok else 2
            else:
                try:
                    raw = read_private(capture / "events.jsonl")
                except FileNotFoundError:
                    raw = b""
                if _test_receive is not None:
                    raw = _test_receive(raw, run_id, policy_id)
                result["observed_execution"] = import_capture(raw, run_id=run_id, policy_id=policy_id, launch_id=launch_id,
                    receipt=envelope["receipt"], tools={"isolated_" + t["name"] for t in tools}, transport_ok=transport_ok)
                code = 0 if result["observed_execution"]["evidence_eligible"] else 4
            # Test-only oracle access. Never a CLI option or an evidence producer.
            if _test_target_probe is not None:
                _test_target_probe(target, runtime_state, target_state)
        except CaptureError as exc:
            result["observed_execution"] = empty_projection(run_id)
            result["observed_execution"]["issues"] = [str(exc)]
            code = 2
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, RecursionError):
            result["observed_execution"] = empty_projection(run_id)
            result["observed_execution"]["issues"] = ["protected_transport_failed"]
            code = 2
        finally:
            cleanup_failures = cleanup_resources(created, runtime, target, network)
            if cleanup_failures:
                result["observed_execution"]["evidence_eligible"] = False
                result["observed_execution"]["status"] = "incomplete"
                if "cleanup_failed" not in result["observed_execution"]["issues"]:
                    result["observed_execution"]["issues"].append("cleanup_failed")
                result["cleanup_failures"] = cleanup_failures
                for record in result["observed_execution"]["records"]:
                    record["evidence_eligible"] = False
                code = 2
        # Atomically replace a host artifact without following an existing symlink.
        fd, staged = tempfile.mkstemp(prefix=".capture-", dir=output.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(result, stream, indent=2)
                stream.write("\n")
            os.replace(staged, output)
        finally:
            Path(staged).unlink(missing_ok=True)
    return code
