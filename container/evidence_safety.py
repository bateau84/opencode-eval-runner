"""RSP v1: typed safety projection, not an observation authenticator.

Consume Loom's private_policy() shape without rediscovering credentials. The
same module is used before container emission and by the host verifier. No
policy values, source locations, or policy hashes are public evidence.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from pathlib import Path
from typing import Any

POLICY = 'loom-eval-credential-inventory/v1'
VERSION = 'source-path-roles/v1'
SAFETY = 'loom-eval-evidence-safety/v1'
REQUEST = 'opencode-eval-runner/evidence-safety-request/v1'
ACK = 'opencode-eval-runner/evidence-safety-ack/v1'
RESULT = 'opencode-eval-runner/safe-result/v1'
EVENTS = 'opencode-eval-runner/safe-tool-results/v1'
CONSUMER = 'runner-evidence-safety/v1'
RUNTIME_STATE = 'opencode-eval-runner/runtime-state/v1'
EXPECTED_MIGRATION_COUNT = 48
FIRST_MIGRATION = '20260127222353_familiar_lady_ursula'
LAST_MIGRATION = '20260923013825_project_time_active'
POLICY_LIMIT = 128_000
WIRE_LIMIT = 132_096
RESULT_LIMIT = 1_000_000
SUPPORTED_JSON_ESCAPE_LAYERS = 3
MAX_JSON_ESCAPE_RECOVERY_LAYERS = 32
SOURCE_NAMES = frozenset(('env', 'auth', 'config', 'models', 'credential_seed', 'config_root'))
STAGES = ['container.before_clip', 'container.before_output']
REASONS = ('credential_match', 'sensitive_key', 'inventory_incomplete', 'upstream_clipped',
           'unsupported_schema', 'unsupported_representation', 'opaque_payload_unverified',
           'size_limit', 'missing', 'invalid', 'write_failed')
MISSING = object()


class Invalid(ValueError):
    pass


def require(ok: bool, reason: str = 'invalid') -> None:
    if not ok:
        raise Invalid(reason)


def _pairs(pairs):
    obj = {}
    for k, v in pairs:
        require(k not in obj)
        obj[k] = v
    return obj


def _bad_number(_):
    raise Invalid('unsupported_representation')


def strict_loads(raw: bytes | str):
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='strict')
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_number)
    owned(value)
    return value


def owned(value: Any, depth=0, budget=None) -> Any:
    """Bounded JSON-only copy; never call user serialization hooks."""
    budget = [20_000] if budget is None else budget
    budget[0] -= 1
    require(depth <= 32 and budget[0] >= 0, 'unsupported_representation')
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        require(math.isfinite(value), 'unsupported_representation')
        return value
    if type(value) is str:
        value.encode('utf-8', errors='strict')
        return value
    if type(value) is list:
        return [owned(v, depth + 1, budget) for v in value]
    if type(value) is dict:
        require(all(type(k) is str for k in value), 'unsupported_representation')
        return {owned(k, depth + 1, budget): owned(v, depth + 1, budget) for k, v in value.items()}
    raise Invalid('unsupported_representation')


def encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def module_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def sensitive_key(key: str) -> bool:
    key = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', key)
    key = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', key)
    key = '_'.join(re.findall(r'[a-z0-9]+', key.lower()))
    return (key in {'key', 'apikey', 'access', 'refresh', 'token'} or
            key.endswith(('_key', '_token')) or any(
                key == x or key.endswith('_' + x) for x in
                ('secret', 'password', 'credential', 'authorization', 'cookie')))


_JSON_ESCAPE_SIMPLE = {
    '"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f',
    'n': '\n', 'r': '\r', 't': '\t',
}


def _json_unescape_layer(value: str) -> tuple[str, bool]:
    """Decode one JSON-string escaping layer without requiring a whole JSON document."""
    out: list[str] = []
    changed = False
    i = 0
    while i < len(value):
        if value[i] != '\\' or i + 1 >= len(value):
            out.append(value[i])
            i += 1
            continue
        kind = value[i + 1]
        simple = _JSON_ESCAPE_SIMPLE.get(kind)
        if simple is not None:
            out.append(simple)
            changed = True
            i += 2
            continue
        if kind == 'u' and i + 6 <= len(value):
            digits = value[i + 2:i + 6]
            if re.fullmatch(r'[0-9a-fA-F]{4}', digits):
                code = int(digits, 16)
                consumed = 6
                if 0xD800 <= code <= 0xDBFF and i + 12 <= len(value) and value[i + 6:i + 8] == '\\u':
                    low_digits = value[i + 8:i + 12]
                    if re.fullmatch(r'[0-9a-fA-F]{4}', low_digits):
                        low = int(low_digits, 16)
                        if 0xDC00 <= low <= 0xDFFF:
                            code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                            consumed = 12
                if not (0xD800 <= code <= 0xDFFF):
                    out.append(chr(code))
                    changed = True
                    i += consumed
                    continue
        out.append(value[i])
        i += 1
    return ''.join(out), changed


class Policy:
    def __init__(self, value=None):
        self.valid = False
        self.complete = False
        self.values: tuple[str, ...] = ()
        self.private = None
        self.matcher = None
        try:
            require(type(value) is dict and set(value) == {'schema', 'policy_version', 'complete', 'sources', 'values'})
            require(value['schema'] == POLICY and value['policy_version'] == VERSION)
            require(type(value['complete']) is bool and type(value['sources']) is dict)
            require(SOURCE_NAMES == value['sources'].keys())
            require(all(type(k) is str and type(v) is str and v in {'complete', 'incomplete', 'not_selected'}
                        for k, v in value['sources'].items()))
            require(type(value['values']) is list and len(value['values']) <= 4096)
            require(all(type(v) is str and v for v in value['values']))
            require(len(encode(value)) <= POLICY_LIMIT)
            complete = all(s in {'complete', 'not_selected'} for s in value['sources'].values())
            require(not value['complete'] or complete)
            self.private = owned(value)
            self.valid = True
            self.complete = value['complete'] and complete
            # An incomplete inventory is never upgraded using its partial matcher.
            if self.complete:
                self.values = tuple(sorted(set(value['values']), key=lambda v: (-len(v), v)))
                variants = set(self.values)
                frontier = variants.copy()
                for _ in range(SUPPORTED_JSON_ESCAPE_LAYERS):
                    new = {json.dumps(v, ensure_ascii=ascii_only)[1:-1]
                           for v in frontier for ascii_only in (False, True)} - variants
                    variants.update(new)
                    frontier = new
                # One substitution pass: generated markers are never re-scanned.
                if variants:
                    self.matcher = re.compile('|'.join(re.escape(v) for v in sorted(variants, key=lambda v: (-len(v), v))))
        except (Invalid, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            self.valid = self.complete = False
            self.values = ()
            self.private = None
            self.matcher = None

    def matches(self, value: str) -> bool:
        return self.matcher is not None and self.matcher.search(value) is not None

    def unsupported_recoverable(self, value: str) -> bool:
        """Detect recoverable JSON-escape representations beyond the supported profile."""
        if self.matcher is None:
            return False
        current = value
        for _ in range(MAX_JSON_ESCAPE_RECOVERY_LAYERS):
            current, changed = _json_unescape_layer(current)
            if not changed:
                return False
            if self.matches(current):
                return True
        # More than the bounded recovery profile is itself unsupported. Never
        # retain a partially understood deeply escaped representation.
        _, changed = _json_unescape_layer(current)
        return changed

    def payload(self, value):
        if type(value) is str:
            # An opaque string is not a declared nested JSON boundary. Never
            # mask its syntax into invalid JSON; a typed json_string role must
            # explicitly opt in to parsing/re-encoding instead.
            direct = self.matches(value)
            if value.lstrip().startswith(('{', '[')) and direct:
                raise Invalid('opaque_payload_unverified')
            if not direct and self.unsupported_recoverable(value):
                raise Invalid('unsupported_representation')
            safe = self.matcher.sub('***REDACTED***', value) if self.matcher else value
            return safe, safe != value
        if type(value) is list:
            parts = [self.payload(v) for v in value]
            return [v for v, _ in parts], any(changed for _, changed in parts)
        if type(value) is dict:
            # Mapping keys are payload data too, but rewriting them can change
            # protocol meaning or collide. Unsupported deeper JSON-escape
            # representations therefore omit the enclosing payload.
            if any(sensitive_key(k) or self.matches(k) for k in value):
                raise Invalid('sensitive_key')
            if any(self.unsupported_recoverable(k) for k in value):
                raise Invalid('unsupported_representation')
            parts = {k: self.payload(v) for k, v in value.items()}
            return {k: v for k, (v, _) in parts.items()}, any(changed for _, changed in parts.values())
        # Arbitrary scalar payloads are not protocol counters. Do not make an
        # invalid JSON token or change its type to hide a credential.
        if self.matches(encode(value).decode()):
            raise Invalid('credential_match')
        return value, False


class Projection:
    def __init__(self, policy: Policy, stage='runner'):
        self.policy = policy
        self.stage = stage
        self.fields = []
        self.loss = {reason: 0 for reason in REASONS}

    def omit(self, field, reason, event=None):
        require(reason in REASONS)
        self.fields.append({'event': event, 'field': field, 'state': 'omitted', 'reason': reason, 'stage': self.stage})
        self.loss[reason] += 1
        return MISSING

    def field(self, field, value=MISSING, *, role='payload', event=None, limit=6000, clipped=False):
        if value is MISSING:
            return self.omit(field, 'missing', event)
        if clipped:
            return self.omit(field, 'upstream_clipped', event)
        if not self.policy.complete:
            return self.omit(field, 'inventory_incomplete', event)
        try:
            value = owned(value)
            if role == 'identity':
                require(value is None or type(value) is str, 'invalid')
                if value is not None and self.policy.matches(value):
                    return self.omit(field, 'credential_match', event)
                if value is not None and self.policy.unsupported_recoverable(value):
                    return self.omit(field, 'unsupported_representation', event)
                safe, changed = value, False
            elif role == 'identities':
                require(type(value) is list and all(type(v) is str for v in value), 'invalid')
                if any(self.policy.matches(v) for v in value):
                    return self.omit(field, 'credential_match', event)
                if any(self.policy.unsupported_recoverable(v) for v in value):
                    return self.omit(field, 'unsupported_representation', event)
                safe, changed = value, False
            elif role == 'json_string':
                require(type(value) is str, 'unsupported_representation')
                safe_value, changed = self.policy.payload(strict_loads(value))
                safe = encode(safe_value).decode('utf-8') if changed else value
            else:
                safe, changed = self.policy.payload(value)
            # Sanitation always precedes the size decision. Never retain a prefix.
            if len(encode(safe)) > limit:
                return self.omit(field, 'size_limit', event)
            disposition = {'event': event, 'field': field, 'state': 'redacted' if changed else 'exact'}
            if changed:
                disposition.update(reason='credential_match', stage=self.stage)
                self.loss['credential_match'] += 1
            self.fields.append(disposition)
            return safe
        except (Invalid, ValueError, UnicodeError, TypeError, RecursionError, OverflowError) as exc:
            return self.omit(field, str(exc) if type(exc) is Invalid else 'unsupported_representation', event)

    def summary(self):
        return {'schema': SAFETY, 'policy_version': VERSION, 'inventory_complete': self.policy.complete,
                'coverage_complete': self.policy.complete and not any(self.loss.values()),
                'fields': self.fields, 'loss_counts': self.loss}


# Only these generated fields are protocol. Dynamic identifiers remain payload.
PUBLIC_COUNTERS = {'exit_code', 'stdout_total_chars', 'stderr_total_chars'}
PUBLIC_FLAGS = {'timed_out', 'infrastructure_error', 'stdout_truncated', 'stderr_truncated'}
DYNAMIC = {'model', 'reasoning', 'agent', 'skill', 'session_id', 'credential_source'}
OPAQUE = {'stdout', 'stderr', 'plugin_diagnostic', 'plugin_preflight'}
TOP_LEVEL_REQUIRED = DYNAMIC | OPAQUE | {
    'transport', 'reasoning_source', 'text', 'tools', 'actions', 'skills_loaded',
    'timing', 'tool_result_evidence'
}
TOP_LEVEL_PROTOCOL = {'transport', 'reasoning_source', 'timing', 'tool_result_evidence', 'runtime_state'}
ALLOWED = PUBLIC_COUNTERS | PUBLIC_FLAGS | TOP_LEVEL_REQUIRED | {'schema', 'runtime_state'}


def validated_runtime_state(value: Any) -> dict[str, Any]:
    require(type(value) is dict and set(value) == {
        'schema', 'profile', 'database_source', 'database_created', 'database_seed_present',
        'auth_source', 'session_rows_before_inference', 'credential_rows_before_inference',
        'migration_count', 'first_migration', 'last_migration',
    }, 'unsupported_schema')
    require(value['schema'] == RUNTIME_STATE and value['profile'] == 'disposable', 'invalid')
    require(value['database_source'] == 'runtime-bootstrap', 'invalid')
    require(value['database_created'] is True and value['database_seed_present'] is False, 'invalid')
    require(value['auth_source'] in {'none', 'explicit'}, 'invalid')
    for name in ('session_rows_before_inference', 'credential_rows_before_inference', 'migration_count'):
        require(type(value[name]) is int and 0 <= value[name] <= 2**53 - 1, 'invalid')
    require(value['session_rows_before_inference'] == 0 and value['credential_rows_before_inference'] == 0, 'invalid')
    require(value['migration_count'] == EXPECTED_MIGRATION_COUNT, 'invalid')
    require(value['first_migration'] == FIRST_MIGRATION, 'invalid')
    require(value['last_migration'] == LAST_MIGRATION, 'invalid')
    return owned(value)


def project_result(raw: Any, policy: Policy, stage='runner') -> dict:
    p = Projection(policy, stage)
    result = {'schema': RESULT}
    if type(raw) is not dict or set(raw) - ALLOWED or raw.get('schema') != 'opencode-eval-runner/v1':
        for name in TOP_LEVEL_REQUIRED:
            p.omit(name, 'unsupported_schema')
        result['evidence_safety'] = p.summary()
        return result
    for name in ('transport', 'reasoning_source'):
        options = {'transport': {'opencode', 'github-copilot-cli'},
                   'reasoning_source': {'explicit', 'model-variant', 'provider-default'}}[name]
        if raw.get(name) in options:
            result[name] = raw[name]
            p.fields.append({'event': None, 'field': name, 'state': 'exact'})
        else:
            p.omit(name, 'invalid')
    for name in PUBLIC_COUNTERS:
        if name in raw and type(raw[name]) is int and abs(raw[name]) <= 2**53 - 1:
            result[name] = raw[name]
    for name in PUBLIC_FLAGS:
        if name in raw and type(raw[name]) is bool:
            result[name] = raw[name]
    for name in DYNAMIC | {'text', 'tools', 'skills_loaded'}:
        role = 'identity' if name in DYNAMIC else 'identities' if name in {'tools', 'skills_loaded'} else 'payload'
        value = p.field(name, raw.get(name, MISSING), role=role, limit=200_000 if name == 'text' else 6000)
        if value is not MISSING:
            result[name] = value
    # Unknown/raw streams can contain arbitrary encodings, malformed/partial
    # JSON, and generated runtime secrets. They have no safe typed adapter yet.
    for name in OPAQUE:
        p.omit(name, 'upstream_clipped' if raw.get(name + '_truncated') else 'opaque_payload_unverified')
    if 'runtime_state' in raw:
        try:
            result['runtime_state'] = validated_runtime_state(raw['runtime_state'])
            p.fields.append({'event': None, 'field': 'runtime_state', 'state': 'exact'})
        except (Invalid, ValueError, UnicodeError, TypeError, RecursionError, OverflowError) as exc:
            p.omit('runtime_state', str(exc) if type(exc) is Invalid else 'unsupported_representation')

    timing = raw.get('timing')
    timing_keys = {'run_seconds', 'export_seconds', 'export_exit_code', 'total_seconds'}
    if type(timing) is dict and not (set(timing) - timing_keys) and all(
        v is None or (type(v) in (int, float) and math.isfinite(v)) for v in timing.values()):
        result['timing'] = dict(timing)
        p.fields.append({'event': None, 'field': 'timing', 'state': 'exact'})
    else:
        p.omit('timing', 'unsupported_schema')
    # Actions have fixed structure but dynamic selector values. If any action
    # loses identity/input fidelity, the whole action list is unavailable.
    actions = raw.get('actions')
    action_safe = []
    try:
        require(policy.complete, 'inventory_incomplete')
        require(type(actions) is list and len(actions) <= 64, 'size_limit')
        for action in actions:
            require(type(action) is dict and set(action) == {'tool', 'args'}, 'unsupported_schema')
            require(type(action['tool']) is str, 'invalid')
            require(not policy.matches(action['tool']), 'credential_match')
            require(not policy.unsupported_recoverable(action['tool']), 'unsupported_representation')
            require(type(action['args']) is dict, 'invalid')
            args, changed = policy.payload(owned(action['args']))
            require(not changed, 'credential_match')
            action_safe.append({'tool': action['tool'], 'args': args})
        require(len(encode(action_safe)) <= 48000, 'size_limit')
        result['actions'] = action_safe
        p.fields.append({'event': None, 'field': 'actions', 'state': 'exact'})
    except (Invalid, ValueError, UnicodeError, TypeError, RecursionError, OverflowError) as exc:
        p.omit('actions', str(exc) if type(exc) is Invalid else 'unsupported_representation')
    evidence = raw.get('tool_result_evidence')
    if type(evidence) is dict and evidence.get('schema') == 'runner-unclipped-events/internal-v1':
        events = evidence['events']
        rows = []
        count = 0
        for ev in events:
            if ev.get('type') != 'tool_use':
                continue
            count += 1
            part = ev.get('part')
            state = part.get('state') if type(part) is dict else None
            if (type(state) is not dict or part.get('type') != 'tool' or
                    set(ev) - {'type', 'timestamp', 'sessionID', 'part'} or
                    set(part) - {'id', 'partID', 'sessionID', 'messageID', 'type', 'callID', 'tool', 'state', 'time'} or
                    set(state) - {'status', 'input', 'output', 'error', 'title', 'metadata', 'time', 'attachments'}):
                p.omit('event', 'unsupported_schema', count - 1)
                continue
            if len(rows) >= 64:
                p.omit('event', 'size_limit', count - 1)
                continue
            row = {'sequence': count}
            if any(name in state for name in ('metadata', 'attachments', 'title')):
                p.omit('metadata', 'opaque_payload_unverified', count - 1)
            status = state.get('status')
            if status in {'pending', 'running', 'completed', 'error'}:
                row['status'] = status
                p.fields.append({'event': count - 1, 'field': 'status', 'state': 'exact'})
            else:
                p.omit('status', 'invalid', count - 1)
            fields = {'tool': part.get('tool', MISSING), 'call_id': part.get('callID', part.get('id', MISSING)),
                      'session_id': ev.get('sessionID', MISSING), 'input': state.get('input', MISSING)}
            for name in ('output', 'error'):
                if name in state:
                    fields[name] = state[name]
            if not any(name in state for name in ('output', 'error')):
                fields['output'] = MISSING
            metadata = state.get('metadata')
            # Pinned OpenCode declares Session truncation in metadata. Missing
            # or unfamiliar declarations cannot attest a complete native output.
            meta = metadata.get('metadata', metadata) if type(metadata) is dict else {}
            upstream_complete = type(meta) is dict and meta.get('truncated') is False
            upstream_clipped = type(meta) is dict and meta.get('truncated') is True
            for name, original in fields.items():
                if name == 'output' and not upstream_complete:
                    p.omit(name, 'upstream_clipped' if upstream_clipped else 'opaque_payload_unverified', count-1)
                    continue
                value = p.field(name, original, event=count-1,
                                role='identity' if name in {'tool', 'call_id', 'session_id'} else 'payload',
                                limit=2000 if name == 'input' else 256 if name.endswith('_id') or name == 'tool' else 6000)
                if value is not MISSING:
                    row[name] = value
            rows.append(row)
        result['tool_result_evidence'] = {'schema': EVENTS, 'source': 'opencode.event-stream.full',
            'observed_events': count, 'omitted_events': count - len(rows), 'events': rows}
        p.fields.append({'event': None, 'field': 'tool_result_evidence', 'state': 'exact'})
    else:
        p.omit('tool_result_evidence', 'upstream_clipped' if evidence else 'missing')
    result['evidence_safety'] = p.summary()
    return result


def receipt(policy: Policy, run_id: str, revision: str, binding_key: bytes = b'') -> dict:
    return {'schema': ACK, 'consumer': CONSUMER, 'run_id': run_id,
            'policy_schema': POLICY, 'policy_version': VERSION, 'projection_schema': SAFETY,
            'stages': STAGES, 'policy_valid': policy.valid, 'inventory_complete': policy.complete,
            'module_sha256': module_sha(), 'image_source_revision': revision,
            'policy_receipt': hmac.new(binding_key, encode(policy.private), hashlib.sha256).hexdigest()}


def fallback(reason='invalid', stage='transport', policy=None):
    p = Projection(policy or Policy(), stage)
    for name in sorted(TOP_LEVEL_REQUIRED):
        p.omit(name, reason)
    return {'schema': RESULT, 'exit_code': 2, 'infrastructure_error': True, 'evidence_safety': p.summary()}


def read_request(stream):
    """Private stdin is consumed before product startup and is never forwarded."""
    try:
        raw = stream.read(WIRE_LIMIT + 1)
        require(len(raw) <= WIRE_LIMIT)
        data = strict_loads(raw)
        require(type(data) is dict and set(data) == {'schema', 'run_id', 'policy', 'binding_key'})
        require(data['schema'] == REQUEST and type(data['run_id']) is str and
                re.fullmatch('[0-9a-f]{64}', data['run_id']) is not None)
        require(type(data['binding_key']) is str and re.fullmatch('[0-9a-f]{64}', data['binding_key']) is not None)
        return Policy(data['policy']), data['run_id'], bytes.fromhex(data['binding_key'])
    except (ValueError, Invalid, TypeError, UnicodeError, OSError, RecursionError):
        return Policy(), '0' * 64, b''


def assert_safe_preview(value, policy):
    """Validate sanitized payloads without rescanning generated display markers."""
    if type(value) is str:
        pieces = value.split('***REDACTED***')
        require(all(not policy.matches(v) and not policy.unsupported_recoverable(v) for v in pieces))
    elif type(value) is dict:
        require(all(not sensitive_key(k) and not policy.matches(k) and
                    not policy.unsupported_recoverable(k) for k in value))
        for v in value.values(): assert_safe_preview(v, policy)
    elif type(value) is list:
        for v in value: assert_safe_preview(v, policy)
    else:
        require(not policy.matches(encode(value).decode()))


def validate_reply(raw: bytes | str, policy: Policy, run_id: str, revision: str, binding_key: bytes = b'') -> dict:
    """Schema/availability acknowledgement, not authentication of hostile code."""
    require(len(raw) <= RESULT_LIMIT)
    reply = strict_loads(raw)
    require(type(reply) is dict and reply.get('schema') == RESULT)
    ack = reply.get('evidence_safety_ack')
    require(type(ack) is dict and type(ack.get('policy_valid')) is bool and type(ack.get('inventory_complete')) is bool)
    require(ack == receipt(policy, run_id, revision, binding_key))
    allowed = (PUBLIC_COUNTERS | PUBLIC_FLAGS | DYNAMIC | {
        'schema', 'transport', 'reasoning_source', 'text', 'tools', 'actions', 'skills_loaded',
        'timing', 'tool_result_evidence', 'runtime_state', 'evidence_safety', 'evidence_safety_ack'})
    require(not (set(reply) - allowed))
    summary = reply['evidence_safety']
    require(type(summary) is dict and set(summary) == {
        'schema', 'policy_version', 'inventory_complete', 'coverage_complete', 'fields', 'loss_counts'})
    require(summary['schema'] == SAFETY and summary['policy_version'] == VERSION)
    require(type(summary['inventory_complete']) is bool and summary['inventory_complete'] == policy.complete)
    require(type(summary['coverage_complete']) is bool)
    require(type(summary['loss_counts']) is dict and set(summary['loss_counts']) == set(REASONS))
    require(all(type(v) is int and 0 <= v <= 2**53 - 1 for v in summary['loss_counts'].values()))
    require(type(summary['fields']) is list and len(summary['fields']) <= 10_000)
    dispositions = {}
    counts = {r: 0 for r in REASONS}
    top_names = TOP_LEVEL_REQUIRED | {'runtime_state'}
    event_names = {'event', 'tool', 'call_id', 'session_id', 'input', 'output', 'error', 'status', 'metadata'}
    for item in summary['fields']:
        require(type(item) is dict)
        event, name, state = item.get('event'), item.get('field'), item.get('state')
        require(event is None or type(event) is int and 0 <= event <= 2**53 - 1)
        require(type(name) is str and name in (top_names if event is None else event_names))
        require(state in {'exact', 'redacted', 'omitted'})
        required = {'event', 'field', 'state'} | ({'reason', 'stage'} if state != 'exact' else set())
        require(set(item) == required and (event, name) not in dispositions)
        if state != 'exact':
            require(item['reason'] in REASONS and item['stage'] == 'runner')
            counts[item['reason']] += 1
            require(state != 'redacted' or item['reason'] == 'credential_match')
        require(
            policy.complete or
            state == 'omitted' or
            (event is None and name in TOP_LEVEL_PROTOCOL and state == 'exact') or
            (event is not None and name == 'status' and state == 'exact')
        )
        dispositions[(event, name)] = item
    require(counts == summary['loss_counts'])
    require(summary['coverage_complete'] == (policy.complete and not any(counts.values())))
    for name in TOP_LEVEL_REQUIRED:
        item = dispositions.get((None, name))
        require(item is not None)
        require((name in reply) == (item['state'] != 'omitted'))
        if name in TOP_LEVEL_PROTOCOL and name in reply:
            require(item['state'] == 'exact')
    runtime_item = dispositions.get((None, 'runtime_state'))
    if 'runtime_state' in reply:
        require(runtime_item is not None and runtime_item['state'] == 'exact')
    if runtime_item is not None and runtime_item['state'] == 'omitted':
        require('runtime_state' not in reply)
    for name in PUBLIC_COUNTERS:
        require(name not in reply or type(reply[name]) is int and abs(reply[name]) <= 2**53 - 1)
    for name in PUBLIC_FLAGS:
        require(name not in reply or type(reply[name]) is bool)
    require('transport' not in reply or reply['transport'] in {'opencode', 'github-copilot-cli'})
    require('reasoning_source' not in reply or reply['reasoning_source'] in {'explicit', 'model-variant', 'provider-default'})
    if 'runtime_state' in reply:
        require(validated_runtime_state(reply['runtime_state']) == reply['runtime_state'])
        require(dispositions.get((None, 'runtime_state'), {}).get('state') == 'exact')
    if 'tool_result_evidence' in reply:
        evidence = reply['tool_result_evidence']
        require(type(evidence) is dict and set(evidence) == {'schema', 'source', 'observed_events', 'omitted_events', 'events'})
        require(evidence['schema'] == EVENTS and evidence['source'] == 'opencode.event-stream.full')
        require(type(evidence['events']) is list and len(evidence['events']) <= 64)
        require(all(type(evidence[n]) is int and evidence[n] >= 0 for n in ('observed_events', 'omitted_events')))
        require(evidence['observed_events'] - evidence['omitted_events'] == len(evidence['events']))
        seen = set()
        for event in evidence['events']:
            require(type(event) is dict and not (set(event) - {'sequence','status','tool','call_id','session_id','input','output','error'}))
            seq = event.get('sequence')
            require(type(seq) is int and 1 <= seq <= evidence['observed_events'] and seq not in seen)
            seen.add(seq)
            event_id = seq - 1
            for required_name in ('tool', 'call_id', 'session_id', 'input', 'status'):
                require((event_id, required_name) in dispositions)
            require(any((event_id, name) in dispositions for name in ('output', 'error')))
            for name in event_names - {'event', 'metadata'}:
                item = dispositions.get((event_id, name))
                if name in event:
                    require(item is not None and item['state'] != 'omitted')
                    if name in {'tool', 'call_id', 'session_id'}:
                        require(item['state'] == 'exact' and type(event[name]) is str)
                    if name == 'status':
                        require(item['state'] == 'exact')
                if item and item['state'] == 'omitted':
                    require(name not in event)
            status = event.get('status')
            require(status is None or status in {'pending', 'running', 'completed', 'error'})
            status_item = dispositions[(event_id, 'status')]
            require((status is None) == (status_item['state'] == 'omitted'))
            if status == 'completed':
                require((event_id, 'output') in dispositions)
            if status == 'error':
                require((event_id, 'error') in dispositions)
        retained_ids = {event['sequence'] - 1 for event in evidence['events']}
        omitted_ids = {
            event for (event, name), item in dispositions.items()
            if event is not None and name == 'event' and item['state'] == 'omitted'
        }
        require(len(omitted_ids) == evidence['omitted_events'])
        require(all(0 <= event < evidence['observed_events'] for event in omitted_ids))
        require(not (retained_ids & omitted_ids))
        require(retained_ids | omitted_ids == set(range(evidence['observed_events'])))
        for (event, name), item in dispositions.items():
            if event is None:
                continue
            if name == 'event':
                require(item['state'] == 'omitted' and event in omitted_ids)
            else:
                require(event in retained_ids)
    timing = reply.get('timing')
    if timing is not None:
        require(type(timing) is dict and not (set(timing) - {'run_seconds','export_seconds','export_exit_code','total_seconds'}))
        require(all(v is None or type(v) in (int,float) and math.isfinite(v) for v in timing.values()))
    # A changed field may never pass as exact; no duplicate/missing metadata or
    # value attached to an omission may be admitted by a consumer.
    for (event, name), item in dispositions.items():
        if event is None:
            container = reply
        else:
            container = next((x for x in reply.get('tool_result_evidence', {}).get('events', [])
                              if x['sequence'] == event + 1), {})
        if item['state'] == 'omitted':
            require(name not in container)
        else:
            require(name in container)
            val = container[name]
            if name in DYNAMIC or name in {'tools','actions','skills_loaded','tool','call_id','session_id'}:
                require(item['state'] == 'exact')
            if name == 'text':
                require(type(val) is str)
            if item['state'] == 'redacted':
                assert_safe_preview(val, policy)
            if item['state'] == 'exact':
                check = Projection(policy)
                role = 'identity' if name in DYNAMIC or name in {'tool','call_id'} else 'identities' if name in {'tools','skills_loaded'} else 'payload'
                # Fixed action keys are protocol; nested tool/args were separately validated.
                if name == 'actions':
                    require(type(val) is list and len(val) <= 64)
                    for action in val:
                        require(type(action) is dict and set(action) == {'tool','args'})
                        require(type(action['tool']) is str and not policy.matches(action['tool'])
                                and not policy.unsupported_recoverable(action['tool']))
                        require(type(action['args']) is dict and policy.payload(action['args']) == (action['args'], False))
                elif name == 'runtime_state':
                    # Runtime-state counters/discriminators are reviewed protocol
                    # structure. Credentials such as "0", "1", "text", or "low"
                    # must not reclassify those fixed values as payload.
                    require(validated_runtime_state(val) == val)
                elif name == 'status':
                    require(val in {'pending', 'running', 'completed', 'error'})
                elif event is None and name in TOP_LEVEL_PROTOCOL:
                    pass
                else:
                    projected = check.field(name, val, role=role, limit=200_000 if name == 'text' else 6000)
                    require(projected is not MISSING and check.fields[0]['state'] == 'exact')
    return reply
