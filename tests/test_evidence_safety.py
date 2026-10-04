"""Provider-free RSP tests: actual container emitter + host first-write path."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from container import evidence_safety as S
from runner import cli, safe_invoke

ROOT = Path(__file__).resolve().parents[1]
REV = 'a' * 40
IMAGE = 'ghcr.io/test/runner@sha256:' + 'b' * 64


def inventory(values=(), complete=True):
    # Exact private_policy() fields inspected in Loom 1a85b1a/run-evals.py.
    return {'schema': S.POLICY, 'policy_version': S.VERSION, 'complete': complete,
            'sources': {name: 'complete' if name == 'env' else 'not_selected' for name in S.SOURCE_NAMES},
            'values': list(values) if complete else []}


def tool(output=None, args=None, *, status='completed', toolname='demo'):
    state = {'status': status, 'input': {} if args is None else args, 'metadata': {'truncated': False}}
    state['error' if status == 'error' else 'output'] = output
    return {'type': 'tool_use', 'timestamp': 1, 'sessionID': 'session',
            'part': {'type': 'tool', 'tool': toolname, 'callID': 'call', 'state': state}}


def raw_result(events=None, text='follow workflow context text low', code=0):
    events = [tool('safe')] if events is None else events
    return {'schema': 'opencode-eval-runner/v1', 'transport': 'opencode', 'reasoning_source': 'explicit',
            'reasoning': 'low', 'model': 'fixture/mock', 'agent': 'worker', 'skill': None,
            'exit_code': code, 'session_id': 'session', 'text': text, 'tools': ['demo'],
            'actions': [{'tool': 'demo', 'args': {'choice': 'text'}}], 'skills_loaded': [],
            'stdout': '\n'.join(json.dumps(e) for e in events), 'stderr': 'opaque',
            'tool_result_evidence': {'schema': 'runner-unclipped-events/internal-v1', 'events': events}}


def disposition(result, field, event=None):
    return next(f for f in result['evidence_safety']['fields'] if f['field'] == field and f['event'] == event)


def invoke_module():
    spec = importlib.util.spec_from_file_location('rsp_test_container', ROOT / 'container/invoke.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PolicyTests(unittest.TestCase):
    def test_exact_loom_wire_shape_and_short_credentials(self):
        p = S.Policy(inventory(['0', '1', 'text', 'low']))
        self.assertTrue(p.valid and p.complete)
        self.assertEqual(set(p.values), {'0', '1', 'text', 'low'})

    def test_disposable_runtime_state_has_strict_exact_shape(self):
        state={
            'schema':S.RUNTIME_STATE,'profile':'disposable','database_source':'runtime-bootstrap',
            'database_created':True,'database_seed_present':False,'auth_source':'none',
            'session_rows_before_inference':0,'credential_rows_before_inference':0,'migration_count':48,
            'first_migration':'20260127222353_familiar_lady_ursula',
            'last_migration':'20260923013825_project_time_active',
        }
        policy=S.Policy(inventory(['0','1','text','low']))
        r=S.project_result({**raw_result(),'runtime_state':state},policy)
        self.assertEqual(r['runtime_state'],state)
        self.assertEqual(disposition(r,'runtime_state')['state'],'exact')
        run_id='a'*64; revision='b'*40; binding=b'c'*32
        r['evidence_safety_ack']=S.receipt(policy,run_id,revision,binding)
        self.assertEqual(
            S.validate_reply(S.encode(r),policy,run_id,revision,binding)['runtime_state'],
            state,
        )
        for bad in (
            {**state,'database_seed_present':True},
            {**state,'migration_count':47},
            {**state,'first_migration':'wrong'},
            {**state,'last_migration':'wrong'},
        ):
            r=S.project_result({**raw_result(),'runtime_state':bad},S.Policy(inventory()))
            self.assertNotIn('runtime_state',r)
            self.assertEqual(disposition(r,'runtime_state')['state'],'omitted')

    def test_missing_incompatible_and_incomplete_policy_never_complete(self):
        for data in (None, {}, {'values': ['secret']}, {**inventory(), 'complete': 1},
                     {**inventory(), 'policy_version': 'future'}, {**inventory(), 'schema': 'future'},
                     {**inventory(), 'sources': {}}, {**inventory(), 'extra': 'secret'},
                     {**inventory(), 'sources': {'env': 'incomplete'}}, inventory(complete=False)):
            self.assertFalse(S.Policy(data).complete)

    def test_policy_limit_and_utf8_strictness(self):
        self.assertFalse(S.Policy(inventory(['x' * S.POLICY_LIMIT])).valid)
        self.assertFalse(S.Policy(inventory(['\ud800'])).valid)

    def test_no_marker_rescan(self):
        p = S.Policy(inventory(['secret', 'REDACTED']))
        value, changed = p.payload('secret REDACTED')
        self.assertTrue(changed)
        self.assertEqual(value, '***REDACTED*** ***REDACTED***')

    def test_existing_clip_is_omission_even_without_credentials(self):
        p = S.Projection(S.Policy(inventory()))
        self.assertIs(p.field('text', 'otherwise safe', clipped=True), S.MISSING)
        self.assertEqual(p.fields[0]['reason'], 'upstream_clipped')


class ProjectionTests(unittest.TestCase):
    def test_protocol_constants_survive_short_secrets_without_payload_waiver(self):
        r = S.project_result(raw_result([tool({'choice': 'text', 'priority': 'low', 'yes': True}, {'choice': 'text'})], code=1),
                             S.Policy(inventory(['0', '1', 'text', 'low'])))
        self.assertEqual(r['exit_code'], 1)
        self.assertEqual(r['schema'], S.RESULT)
        self.assertIn('text', r)
        self.assertEqual(disposition(r, 'text')['state'], 'redacted')
        e = r['tool_result_evidence']['events'][0]
        self.assertEqual(e['sequence'], 1)
        self.assertEqual(e['status'], 'completed')
        self.assertEqual(e['output']['choice'], '***REDACTED***')
        self.assertEqual(e['output']['priority'], '***REDACTED***')
        self.assertIs(e['output']['yes'], True)
        self.assertEqual(disposition(r, 'output', 0)['state'], 'redacted')
        self.assertNotIn('reasoning', r)  # identity low is omitted, never renamed.
        self.assertNotIn('actions', r)  # lost selector fidelity is not absence.
        self.assertEqual(disposition(r, 'actions')['state'], 'omitted')
        self.assertEqual(S.strict_loads(S.encode(r)), r)

    def test_public_only_inventory_retains_exact_bytes_and_type(self):
        raw = raw_result([tool(None)], text='workflow follow context text low')
        r = S.project_result(raw, S.Policy(inventory(['unrelated-real-token'])))
        self.assertEqual(r['text'], raw['text'])
        self.assertEqual(disposition(r, 'text')['state'], 'exact')
        self.assertIsNone(r['tool_result_evidence']['events'][0]['output'])
        self.assertEqual(disposition(r, 'output', 0)['state'], 'exact')

    def test_payload_numbers_omitted_not_coerced_to_markers(self):
        for value in (0, 1):
            r = S.project_result(raw_result([tool(value)]), S.Policy(inventory(['0', '1'])))
            self.assertNotIn('output', r['tool_result_evidence']['events'][0])
            self.assertEqual(disposition(r, 'output', 0)['reason'], 'credential_match')

    def test_payload_key_collision_omits_enclosing_field(self):
        for value in ({'text': 'public', 'low': 'public'}, {'apiKey': 'secret'}, {'token': 'secret'}):
            r = S.project_result(raw_result([tool(value)]), S.Policy(inventory(['text', 'low'])))
            self.assertNotIn('output', r['tool_result_evidence']['events'][0])
            self.assertEqual(disposition(r, 'output', 0)['reason'], 'sensitive_key')

    def test_status_lookalike_is_protocol_but_identity_is_not(self):
        r = S.project_result(raw_result([tool('completed', toolname='completed')]), S.Policy(inventory(['completed'])))
        e = r['tool_result_evidence']['events'][0]
        self.assertEqual(e['status'], 'completed')
        self.assertNotIn('tool', e)
        self.assertEqual(disposition(r, 'tool', 0)['state'], 'omitted')

    def test_redaction_before_size_decision(self):
        secret = 'z' * 20_000
        r = S.project_result(raw_result([tool(secret)]), S.Policy(inventory([secret])))
        self.assertEqual(r['tool_result_evidence']['events'][0]['output'], '***REDACTED***')
        self.assertEqual(disposition(r, 'output', 0)['state'], 'redacted')
        self.assertNotIn(secret, S.encode(r).decode())

    def test_oversize_is_omitted_without_prefix_hash_or_suffix(self):
        r = S.project_result(raw_result([tool('safe-' * 2000)]), S.Policy(inventory()))
        self.assertNotIn('output', r['tool_result_evidence']['events'][0])
        d = disposition(r, 'output', 0)
        self.assertEqual(d, {'event': 0, 'field': 'output', 'state': 'omitted', 'reason': 'size_limit', 'stage': 'runner'})

    def test_escaped_values_raw_through_three_layers(self):
        secret = 'tok-"line\n\\ending'
        val = secret
        for _ in range(4):
            r = S.project_result(raw_result([tool(val)]), S.Policy(inventory([secret])))
            self.assertEqual(disposition(r, 'output', 0)['state'], 'redacted')
            val = json.dumps(val)[1:-1]

    def test_bad_representations_and_unknown_schema_omit(self):
        cycle = {}; cycle['self'] = cycle
        for value in (cycle, float('nan'), {'a': float('inf')}, b'no'):
            p = S.Projection(S.Policy(inventory()))
            self.assertIs(p.field('text', value), S.MISSING)
            self.assertEqual(p.fields[0]['reason'], 'unsupported_representation')
        r = S.project_result({**raw_result(), 'unknown': 'private'}, S.Policy(inventory()))
        self.assertNotIn('private', S.encode(r).decode())
        self.assertEqual(disposition(r, 'transport')['reason'], 'unsupported_schema')

    def test_incomplete_inventory_no_payload_slots(self):
        r = S.project_result(raw_result(), S.Policy(inventory(complete=False)))
        for name in ('text', 'actions', 'tools', 'model', 'reasoning', 'session_id'):
            self.assertNotIn(name, r)
            self.assertEqual(disposition(r, name)['state'], 'omitted')
        self.assertFalse(r['evidence_safety']['inventory_complete'])

    def test_sources_and_values_never_exported_and_input_unchanged(self):
        policy = inventory(['secret'])
        raw = raw_result([tool('secret')]); original = copy.deepcopy(raw)
        r = S.project_result(raw, S.Policy(policy))
        self.assertEqual(raw, original)
        self.assertNotIn('sources', r)
        self.assertNotIn('values', r)
        self.assertFalse(r['evidence_safety']['coverage_complete'])


class ContainerBoundaryTests(unittest.TestCase):
    def run_container(self, policy, events, *, timeout=False, failure=False):
        m = invoke_module(); m.RSP_ACTIVE = True; m.RSP_POLICY = m.rsp_module().Policy(policy); m.RSP_RUN_ID = 'c' * 64
        stdout = '\n'.join(json.dumps(e) for e in events)
        def execute(command, cwd, env, seconds):
            if timeout:
                raise subprocess.TimeoutExpired(command, seconds, stdout.encode(), b'PRIVATE-ERROR')
            return subprocess.CompletedProcess(command, 1 if failure else 0, stdout, 'PRIVATE-ERROR')
        with patch.object(m, 'prepare_opencode_env', return_value={}), patch.object(m, 'plugin_diagnostic', return_value={}), \
             patch.object(m, 'verify_expected_plugin', return_value={}), patch.object(m, 'run', side_effect=execute):
            original = m.invoke_opencode('fixture/mock', 'worker', 'prompt', 5)
        emitted = io.StringIO()
        with patch.object(m.sys, 'stdout', emitted):
            m.emit_result(original)
        return original, json.loads(emitted.getvalue())

    def test_success_and_failure_cross_real_preclip_emitter(self):
        secret = 'long-' * 2000
        for failure in (False, True):
            before, after = self.run_container(inventory([secret]), [tool(secret)], failure=failure)
            self.assertEqual(before['tool_result_evidence']['events'][0]['part']['state']['output'], secret)
            self.assertFalse(before['stdout_truncated'])
            self.assertEqual(after['tool_result_evidence']['events'][0]['output'], '***REDACTED***')
            self.assertNotIn('stdout', after)
            self.assertNotIn('stderr', after)
            self.assertEqual(after['exit_code'], int(failure))

    def test_timeout_same_sink_keeps_real_error_outcome(self):
        before, after = self.run_container(inventory(['low']), [tool('low', status='error')], timeout=True)
        self.assertTrue(after['timed_out'])
        self.assertEqual(after['exit_code'], 124)
        self.assertEqual(after['tool_result_evidence']['events'][0]['error'], '***REDACTED***')
        self.assertNotIn('PRIVATE-ERROR', json.dumps(after))

    def test_absent_policy_omits_in_all_outcomes(self):
        for kw in ({}, {'failure': True}, {'timeout': True}):
            _, after = self.run_container(None, [tool('private')], **kw)
            self.assertNotIn('private', json.dumps(after))
            self.assertFalse(after['evidence_safety_ack']['inventory_complete'])

    def test_raw_large_stream_is_not_clipped_before_projection(self):
        m = invoke_module(); m.RSP_ACTIVE = True
        text = 'x' * (m.STDOUT_CAPTURE_LIMIT + 1)
        self.assertEqual(m.evidence_slice(text, 5), '')
        m.RSP_ACTIVE = False
        self.assertEqual(m.evidence_slice(text, 5), 'xxxxx')


class HostBoundaryTests(unittest.TestCase):
    def reply(self, policy=None, nonce='c' * 64):
        policy = S.Policy(inventory(['secret'])) if policy is None else policy
        result = S.project_result(raw_result([tool('secret')]), policy)
        result['evidence_safety_ack'] = S.receipt(policy, nonce, REV)
        return policy, result

    def test_real_reply_accepted_missing_or_forged_ack_rejected(self):
        p, r = self.reply()
        self.assertEqual(S.validate_reply(S.encode(r), p, 'c' * 64, REV), r)
        for name, value in (('run_id', 'd' * 64), ('module_sha256', 'f' * 64), ('stages', []),
                            ('policy_version', 'future'), ('inventory_complete', False)):
            bad = copy.deepcopy(r); bad['evidence_safety_ack'][name] = value
            with self.assertRaises(ValueError):
                S.validate_reply(S.encode(bad), p, 'c' * 64, REV)
        bad = dict(r); del bad['evidence_safety_ack']
        with self.assertRaises(ValueError):
            S.validate_reply(S.encode(bad), p, 'c' * 64, REV)

    def test_incomplete_policy_keeps_only_fixed_event_status_exact(self):
        policy = S.Policy(inventory(complete=False))
        run_id = 'c' * 64
        revision = REV
        binding = b'd' * 32
        result = S.project_result(raw_result([tool('private-output')]), policy)
        result['evidence_safety_ack'] = S.receipt(policy, run_id, revision, binding)
        event_fields = [
            item for item in result['evidence_safety']['fields']
            if item.get('event') == 0
        ]
        status = next(item for item in event_fields if item['field'] == 'status')
        self.assertEqual(status['state'], 'exact')
        self.assertTrue(all(
            item['state'] == 'omitted'
            for item in event_fields if item['field'] != 'status'
        ))
        admitted = S.validate_reply(S.encode(result), policy, run_id, revision, binding)
        self.assertEqual(admitted['tool_result_evidence']['events'][0]['status'], 'completed')
        self.assertNotIn('private-output', json.dumps(admitted))

    def test_fallback_has_total_top_level_dispositions_and_preserves_outcome_metadata(self):
        policy = S.Policy(inventory(complete=False))
        run_id = 'f' * 64
        revision = REV
        binding = b'e' * 32
        result = S.fallback('size_limit', 'runner', policy)
        result['exit_code'] = 124
        result['timed_out'] = True
        result['evidence_safety_ack'] = S.receipt(policy, run_id, revision, binding)
        top = {
            item['field']: item
            for item in result['evidence_safety']['fields']
            if item.get('event') is None
        }
        self.assertEqual(set(top), S.TOP_LEVEL_REQUIRED)
        self.assertTrue(all(item['state'] == 'omitted' for item in top.values()))
        admitted = S.validate_reply(S.encode(result), policy, run_id, revision, binding)
        self.assertEqual(admitted['exit_code'], 124)
        self.assertTrue(admitted['timed_out'])

    def test_every_required_top_level_field_has_disposition(self):
        policy = S.Policy(inventory(['unrelated-secret']))
        run_id = 'c' * 64
        revision = REV
        binding = b'd' * 32
        result = S.project_result(raw_result(), policy)
        result['evidence_safety_ack'] = S.receipt(policy, run_id, revision, binding)
        top = {
            item['field'] for item in result['evidence_safety']['fields']
            if item.get('event') is None
        }
        self.assertTrue(S.TOP_LEVEL_REQUIRED <= top)
        self.assertEqual(S.validate_reply(S.encode(result), policy, run_id, revision, binding), result)

        malformed = {
            'schema': S.RESULT,
            'evidence_safety_ack': S.receipt(policy, run_id, revision, binding),
            'evidence_safety': {
                'schema': S.SAFETY,
                'policy_version': S.VERSION,
                'inventory_complete': True,
                'coverage_complete': True,
                'fields': [],
                'loss_counts': {reason: 0 for reason in S.REASONS},
            },
        }
        with self.assertRaises(ValueError):
            S.validate_reply(S.encode(malformed), policy, run_id, revision, binding)

    def test_omitted_event_count_is_bound_to_event_dispositions(self):
        policy = S.Policy(inventory(['unrelated-secret']))
        run_id = 'c' * 64
        revision = REV
        binding = b'd' * 32
        malformed_event = {
            'type': 'tool_use',
            'timestamp': 1,
            'sessionID': 'session',
            'part': {'type': 'tool', 'tool': 'broken', 'state': []},
        }
        result = S.project_result(raw_result([tool('safe-output'), malformed_event]), policy)
        result['evidence_safety_ack'] = S.receipt(policy, run_id, revision, binding)
        evidence = result['tool_result_evidence']
        self.assertEqual(evidence['observed_events'], 2)
        self.assertEqual(evidence['omitted_events'], 1)
        self.assertEqual(
            [item for item in result['evidence_safety']['fields']
             if item.get('field') == 'event'],
            [{'event': 1, 'field': 'event', 'state': 'omitted',
              'reason': 'unsupported_schema', 'stage': 'runner'}],
        )
        self.assertEqual(S.validate_reply(S.encode(result), policy, run_id, revision, binding), result)

        no_reason = copy.deepcopy(result)
        no_reason['evidence_safety']['fields'] = [
            item for item in no_reason['evidence_safety']['fields']
            if item.get('field') != 'event'
        ]
        no_reason['evidence_safety']['loss_counts']['unsupported_schema'] -= 1
        no_reason['evidence_safety']['coverage_complete'] = True
        with self.assertRaises(ValueError):
            S.validate_reply(S.encode(no_reason), policy, run_id, revision, binding)

        retained_omitted = copy.deepcopy(result)
        event_item = next(
            item for item in retained_omitted['evidence_safety']['fields']
            if item.get('field') == 'event'
        )
        event_item['event'] = 0
        with self.assertRaises(ValueError):
            S.validate_reply(S.encode(retained_omitted), policy, run_id, revision, binding)

        out_of_range = copy.deepcopy(result)
        event_item = next(
            item for item in out_of_range['evidence_safety']['fields']
            if item.get('field') == 'event'
        )
        event_item['event'] = 9
        with self.assertRaises(ValueError):
            S.validate_reply(S.encode(out_of_range), policy, run_id, revision, binding)

    def test_retained_event_requires_complete_field_dispositions(self):
        policy = S.Policy(inventory(['unrelated-secret']))
        run_id = 'c' * 64
        revision = REV
        binding = b'd' * 32
        result = S.project_result(raw_result([tool('safe-output')]), policy)
        result['evidence_safety_ack'] = S.receipt(policy, run_id, revision, binding)
        event_fields = {
            item['field'] for item in result['evidence_safety']['fields']
            if item.get('event') == 0
        }
        self.assertTrue({'tool','call_id','session_id','input','status','output'} <= event_fields)
        self.assertEqual(S.validate_reply(S.encode(result), policy, run_id, revision, binding), result)

        for field in ('tool','call_id','session_id','input','status'):
            bad = copy.deepcopy(result)
            bad['evidence_safety']['fields'] = [
                item for item in bad['evidence_safety']['fields']
                if not (item.get('event') == 0 and item.get('field') == field)
            ]
            with self.assertRaises(ValueError):
                S.validate_reply(S.encode(bad), policy, run_id, revision, binding)

        bad = copy.deepcopy(result)
        bad['evidence_safety']['fields'] = [
            item for item in bad['evidence_safety']['fields']
            if not (item.get('event') == 0 and item.get('field') in {'output','error'})
        ]
        with self.assertRaises(ValueError):
            S.validate_reply(S.encode(bad), policy, run_id, revision, binding)

    def test_omitted_value_smuggling_and_duplicate_disposition_rejected(self):
        p, r = self.reply()
        bad = copy.deepcopy(r); bad['stdout'] = 'secret'
        with self.assertRaises(ValueError): S.validate_reply(S.encode(bad), p, 'c' * 64, REV)
        bad = copy.deepcopy(r); bad['evidence_safety']['fields'].append(bad['evidence_safety']['fields'][0])
        with self.assertRaises(ValueError): S.validate_reply(S.encode(bad), p, 'c' * 64, REV)

    def test_atomic_file_and_print_have_only_projected_data(self):
        _, result = self.reply()
        with tempfile.TemporaryDirectory() as tmp, patch('sys.stdout', new_callable=io.StringIO) as output:
            path = Path(tmp) / 'out.json'
            safe_invoke.write_projection(path, result, True)
            self.assertEqual(json.loads(path.read_text()), result)
            self.assertEqual(json.loads(output.getvalue()), result)
            self.assertNotIn('secret', path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(tmp).glob('.safe*')), [])

    def test_resolved_image_binds_all_executable_container_sources(self):
        root = Path(safe_invoke.__file__).resolve().parents[1]
        init_sha = __import__('hashlib').sha256((root/'container/__init__.py').read_bytes()).hexdigest()
        invoke_sha = __import__('hashlib').sha256((root/'container/invoke.py').read_bytes()).hexdigest()
        config_id = 'sha256:' + 'c' * 64
        info = [{
            'RepoDigests': [IMAGE],
            'Id': config_id,
            'Config': {'Labels': {
                'io.opencode-eval.evidence-safety': S.CONSUMER,
                'io.opencode-eval.evidence-safety-init': init_sha,
                'io.opencode-eval.evidence-safety-module': S.module_sha(),
                'io.opencode-eval.evidence-safety-invoke': invoke_sha,
                'org.opencontainers.image.revision': REV,
            }},
        }]
        command = ['docker', 'run', IMAGE]
        with patch.object(
            safe_invoke.subprocess, 'run',
            return_value=subprocess.CompletedProcess([], 0, json.dumps(info).encode(), b''),
        ):
            loaded = safe_invoke.resolved_image(command)
        self.assertEqual(command[-1], config_id)
        self.assertEqual(loaded['image_package_init_sha256'], init_sha)
        self.assertEqual(loaded['image_policy_module_sha256'], S.module_sha())
        self.assertEqual(loaded['image_invoke_sha256'], invoke_sha)

        info[0]['Config']['Labels']['io.opencode-eval.evidence-safety-init'] = '0' * 64
        with patch.object(
            safe_invoke.subprocess, 'run',
            return_value=subprocess.CompletedProcess([], 0, json.dumps(info).encode(), b''),
        ), self.assertRaises(ValueError):
            safe_invoke.resolved_image(['docker', 'run', IMAGE])

    def test_unacknowledged_or_timeout_transport_never_writes_raw_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prompt = root/'prompt'; prompt.write_text('execute')
            policy_path = root/'private.json'; policy_path.write_text(json.dumps(inventory(['secret'])))
            args = cli.parser().parse_args(['invoke', '--model', 'fixture/mock', '--prompt-file', str(prompt),
                '--output', str(root/'result.json'), '--evidence-policy-file', str(policy_path), '--workspace', tmp,
                '--image', IMAGE, '--engine', 'docker', '--print-result'])
            for failure in (subprocess.CompletedProcess([], 0, b'{"text":"secret"}', b'secret'),
                            subprocess.TimeoutExpired('raw-secret-command', 1, b'secret', b'secret')):
                with patch.object(cli, 'existing_seed', return_value=None), \
                     patch.object(cli, 'resolve_engine', return_value='docker'), \
                     patch.object(safe_invoke, 'resolved_image', return_value={'image_source_revision': REV}), \
                     patch.object(safe_invoke.subprocess, 'run', side_effect=failure if isinstance(failure, Exception) else None,
                                  return_value=failure), patch('sys.stdout', new_callable=io.StringIO) as output:
                    code = cli.invoke(args)
                    self.assertNotEqual(code, 0)
                    self.assertNotIn('secret', (root/'result.json').read_text())
                    self.assertNotIn('secret', output.getvalue())

    def test_disposable_profile_policy_must_match_explicit_seed_selection(self):
        p=S.Policy(inventory())
        command=['docker','--volume','/synthetic/config:/seed/opencode.json:ro',IMAGE]
        q=safe_invoke.audit_selected_inputs(p,command,{}, {'config'}, 'disposable')
        self.assertFalse(q.complete)  # policy claimed config not_selected
        data=inventory(); data['sources']['config']='complete'
        q=safe_invoke.audit_selected_inputs(S.Policy(data),command,{}, {'config'}, 'disposable')
        self.assertTrue(q.complete)
        self.assertEqual(q.private['sources']['credential_seed'],'not_selected')

    def test_disposable_profile_accepts_explicit_config_root_when_inventory_matches(self):
        data = inventory()
        data['sources']['config_root'] = 'complete'
        command = [
            'docker', '--volume', '/synthetic/root:/seed/opencode-config:ro', IMAGE
        ]
        q = safe_invoke.audit_selected_inputs(
            S.Policy(data), command, {}, {'config_root'}, 'disposable'
        )
        self.assertTrue(q.complete)

        legacy = safe_invoke.audit_selected_inputs(
            S.Policy(data), command, {}, {'config_root'}, 'default'
        )
        self.assertFalse(legacy.complete)

    def test_forwarded_sensitive_env_must_be_declared_selected_and_present(self):
        command = ['docker', '--env', 'OPENAI_API_KEY', IMAGE]
        host_env = {'OPENAI_API_KEY': 'synthetic-forwarded-secret'}

        not_selected = inventory(['synthetic-forwarded-secret'])
        not_selected['sources']['env'] = 'not_selected'
        q = safe_invoke.audit_selected_inputs(
            S.Policy(not_selected), command, host_env, set(), 'disposable'
        )
        self.assertFalse(q.complete)

        complete = inventory(['synthetic-forwarded-secret'])
        complete['sources']['env'] = 'complete'
        q = safe_invoke.audit_selected_inputs(
            S.Policy(complete), command, host_env, set(), 'disposable'
        )
        self.assertTrue(q.complete)

        missing_value = inventory(['different-secret'])
        missing_value['sources']['env'] = 'complete'
        q = safe_invoke.audit_selected_inputs(
            S.Policy(missing_value), command, host_env, set(), 'disposable'
        )
        self.assertFalse(q.complete)

    def test_selected_default_source_not_selected_downgrades_policy(self):
        p = S.Policy(inventory())
        q = safe_invoke.audit_selected_inputs(p, ['docker', '--volume', '/private/auth:/seed/auth.json:ro', IMAGE], {})
        self.assertFalse(q.complete)
        self.assertTrue(p.complete)


if __name__ == '__main__':
    unittest.main()
