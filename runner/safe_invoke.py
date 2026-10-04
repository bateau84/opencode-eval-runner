"""Opt-in normal invoke safety at host sinks, with explicit image handshake.

This is not an alternate tool/session runner. It uses cli's normal command and
input resolution; only the evidence channel and admission are changed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

from container import evidence_safety as s


def load_policy(path):
    try:
        with Path(path).open('rb') as f:
            raw = f.read(s.POLICY_LIMIT + 1)
        s.require(len(raw) <= s.POLICY_LIMIT)
        return s.Policy(s.strict_loads(raw))
    except (ValueError, TypeError, OSError, RecursionError):
        return s.Policy()


def audit_selected_inputs(policy, command, host_env, explicit_sources=None, state_profile='default'):
    """Downgrade omissions/defaults not represented by Loom's selected profile.

    This does not discover new real state, classify arbitrary configs, or infer
    credentials from public values. Loom owns source/path classification.
    """
    if not policy.complete:
        return policy
    selected = set()
    categories = {'/seed/auth.json': 'auth', '/seed/opencode.json': 'config',
                  '/seed/models.json': 'models', '/seed/opencode.db': 'credential_seed',
                  '/seed/opencode-config': 'config_root'}
    contradictory = False
    for index, arg in enumerate(command[:-1]):
        value = command[index + 1]
        if arg == '--volume':
            target = value.rsplit(':', 2)[1]
            if target in categories:
                selected.add(categories[target])
                # The legacy/default profile has no path-role contract for an
                # ambient plugin config root. The disposable profile does:
                # explicit --config-root is allowed when Loom marks config_root
                # complete and the explicit-source set agrees.
                contradictory |= (
                    target == '/seed/opencode-config' and state_profile != 'disposable'
                )
        elif arg == '--env':
            name, _, inline = value.partition('=')
            actual = inline if '=' in value else host_env.get(name, '')
            if s.sensitive_key(name) and actual:
                contradictory |= actual not in policy.values
    states = policy.private['sources']
    contradictory |= any(states[category] != 'complete' for category in selected)
    if state_profile == 'disposable':
        # The disposable profile makes default database/auth/config selection an
        # explicit runner guarantee. Policy source states must describe the
        # actually selected explicit inputs, not an ambient fallback.
        expected = {
            'auth': 'complete' if 'auth' in selected else 'not_selected',
            'config': 'complete' if 'config' in selected else 'not_selected',
            'models': 'complete' if 'models' in selected else 'not_selected',
            'credential_seed': 'not_selected',
            'config_root': 'complete' if 'config_root' in selected else 'not_selected',
        }
        contradictory |= any(states[name] != value for name, value in expected.items())
    if explicit_sources is not None:
        # The v1 policy has no path bindings for runner-resolved defaults.
        # Never infer that a category label describes an ambient fallback.
        contradictory |= bool(selected - explicit_sources)
    if contradictory:
        private = dict(policy.private)
        private['complete'] = False
        private['values'] = []
        return s.Policy(private)
    return policy


def resolved_image(command):
    reference = command[-1]
    s.require(type(reference) is str and re.fullmatch(r'[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}', reference) is not None)
    engine = command[0]
    # No selected credentials, inputs or policy are provided to this preflight.
    inspect = subprocess.run([engine, 'image', 'inspect', reference], capture_output=True, timeout=120, check=False)
    if inspect.returncode:
        pulled = subprocess.run([engine, 'pull', reference], capture_output=True, timeout=120, check=False)
        s.require(pulled.returncode == 0)
        inspect = subprocess.run([engine, 'image', 'inspect', reference], capture_output=True, timeout=120, check=False)
    s.require(inspect.returncode == 0)
    info = s.strict_loads(inspect.stdout)[0]
    labels = info.get('Config', {}).get('Labels') or {}
    s.require(reference in info.get('RepoDigests', []))
    s.require(labels.get('io.opencode-eval.evidence-safety') == s.CONSUMER)
    s.require(labels.get('io.opencode-eval.evidence-safety-module') == s.module_sha())
    s.require(labels.get('io.opencode-eval.evidence-safety-invoke') == hashlib.sha256(
        (Path(__file__).resolve().parents[1] / 'container/invoke.py').read_bytes()).hexdigest())
    revision = labels.get('org.opencontainers.image.revision')
    s.require(type(revision) is str and re.fullmatch('[0-9a-f]{40}', revision) is not None)
    config_id = info.get('Id')
    s.require(type(config_id) is str and re.fullmatch('sha256:[0-9a-f]{64}', config_id) is not None)
    # Execute that exact local content-addressed config, not a mutable tag.
    command[-1] = config_id
    return {'image': reference, 'image_config': config_id, 'image_source_revision': revision}


def execute_container(command, request, timeout, run_id, host_env=None):
    """Create before attach so client timeouts still have an owned cleanup name."""
    engine = command[0]
    name = 'rsp-' + run_id[:32]
    create = [engine, 'create', *command[2:]]
    create.remove('--rm')
    create[-1:-1] = ['--name', name]
    try:
        proc = subprocess.run(create, env=host_env, capture_output=True, timeout=120, check=False)
        s.require(proc.returncode == 0)
        return subprocess.run([engine, 'start', '--attach', '--interactive', name],
                              input=request, capture_output=True, timeout=timeout, check=False)
    finally:
        # This randomly named invocation is owned before attach can time out.
        # No returned exception/engine output is reflected into evidence.
        removed = subprocess.run([engine, 'rm', '--force', '--volumes', name],
                                 capture_output=True, timeout=30, check=False)
        s.require(removed.returncode == 0)


def write_projection(path, result, print_result):
    """Atomic, private first write, never raw stdout or a raw result tempfile."""
    raw = s.encode(result)
    s.require(len(raw) <= s.RESULT_LIMIT)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.safe-evidence-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if print_result:
        sys.stdout.write(raw.decode('utf-8') + '\n')


def invoke(args):
    from runner import cli
    result = s.fallback('invalid')
    code = 4
    try:
        # Do not accidentally treat the legacy HMAC path as this acknowledgement.
        s.require(not getattr(args, 'observer_key_file', None), 'unsupported_schema')
        policy = load_policy(getattr(args, 'evidence_policy_file', None))
        run_id = secrets.token_hex(32)
        binding_key = secrets.token_bytes(32)
        s.require(type(args.container_timeout) is int and args.container_timeout > 0)
        # Preserve ordinary invoke mounts; reject safety negotiation if a mount
        # could replace the reviewed emitter/interpreter, rather than silently
        # changing that mount or running an unprotected image.
        for spec in args.mount:
            parts = spec.rsplit(':', 2)
            target = parts[-2] if parts[-1] in {'ro', 'rw'} else parts[-1]
            target = PurePosixPath(target)
            s.require(target.is_absolute() and '..' not in target.parts and str(target).startswith('/workspace/'), 'unsupported_schema')
        with tempfile.TemporaryDirectory(prefix='runner-safe-invoke-') as tmp:
            root = Path(tmp)
            inputs, output = root / 'input', root / 'output'
            inputs.mkdir()
            output.mkdir()
            # Authorized execution inputs are distinct from evidence copies.
            shutil.copyfile(args.prompt_file, inputs / 'prompt.txt')
            if args.system_file:
                shutil.copyfile(args.system_file, inputs / 'system.txt')
            else:
                (inputs / 'system.txt').write_text('')
            host_env = cli.host_environment_for_transport(args.transport)
            state_profile = cli.opencode_state_profile(args, host_env)
            database = cli.resolve_database_seed(args, root / 'credentials.db', host_env)
            command, _ = cli.build_container_command(args, inputs, output, host_env, database)
            explicit = {name for name, value in {
                'auth': args.auth, 'config': args.config, 'models': args.models_catalog,
                'credential_seed': args.database, 'config_root': args.config_root}.items() if value}
            policy = audit_selected_inputs(policy, command, host_env, explicit, state_profile)
            if state_profile == 'disposable' and not policy.complete:
                result = s.fallback('inventory_incomplete', 'transport', policy)
                write_projection(args.output, result, args.print_result)
                return 4
            loaded = resolved_image(command)
            # Send only to the supervisor's consumed stdin; do not expose policy
            # values in a bind-mounted file, argv, or inherited runtime env.
            command[-1:-1] = ['-i', '--log-driver', 'none', '--env', 'EVAL_EVIDENCE_SAFETY=1']
            request = s.encode({'schema': s.REQUEST, 'run_id': run_id, 'policy': policy.private, 'binding_key': binding_key.hex()})
            s.require(len(request) <= s.WIRE_LIMIT)
            # Environment-selected normal --env values must reach docker create;
            # the private policy still travels only on the attached stdin.
            proc = execute_container(command, request, args.container_timeout, run_id, host_env)
            try:
                result = s.validate_reply(proc.stdout, policy, run_id, loaded['image_source_revision'], binding_key)
            except (ValueError, TypeError, KeyError, RecursionError):
                result = s.fallback('unsupported_schema')
            else:
                runtime_state = result.get('runtime_state')
                if state_profile == 'disposable':
                    s.require(type(runtime_state) is dict and
                              runtime_state.get('profile') == 'disposable' and
                              runtime_state.get('database_source') == 'runtime-bootstrap' and
                              runtime_state.get('database_seed_present') is False and
                              runtime_state.get('database_created') is True)
                else:
                    s.require(runtime_state is None)
                loaded['host_executable_sha256'] = hashlib.sha256(
                    (Path(__file__).resolve().parents[1] / 'bin/opencode-eval-runner').read_bytes()).hexdigest()
                loaded['host_adapter_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                loaded['policy_module_sha256'] = s.module_sha()
                # Code provenance is generated by the host, never accepted from
                # a container reply or target output. No source policy is copied.
                checkout = Path(__file__).resolve().parents[1]
                try:
                    rev = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'],
                                         capture_output=True, timeout=5, check=False).stdout.decode().strip()
                    dirty = subprocess.run(['git', '-C', str(checkout), 'status', '--porcelain', '--untracked-files=no'],
                                           capture_output=True, timeout=5, check=False)
                    loaded['host_source_revision'] = rev if re.fullmatch('[0-9a-f]{40}', rev) else None
                    loaded['host_tracked_tree_clean'] = dirty.returncode == 0 and not dirty.stdout
                except (OSError, subprocess.SubprocessError, UnicodeError):
                    loaded['host_source_revision'] = None
                    loaded['host_tracked_tree_clean'] = False
                result['evidence_load'] = loaded
                result['evidence_safety_validation'] = {'schema': 'opencode-eval-runner/evidence-safety-validation/v1',
                    'acknowledged': True, 'stages': ['host.before_write', 'host.before_print']} 
                code = proc.returncode or (0 if policy.complete else 4)
        write_projection(args.output, result, args.print_result)
        return code
    except (Exception,):
        # Includes timeouts with partial stdout/stderr and default-resolution
        # errors. Never format exception text or a command containing secrets.
        result = s.fallback('invalid')
        try:
            write_projection(args.output, result, args.print_result)
        except Exception:
            print('runner evidence write failed', file=sys.stderr)
        return 2
