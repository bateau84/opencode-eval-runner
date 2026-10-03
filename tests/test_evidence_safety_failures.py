"""Negative controls for policy acknowledgement and real first output boundaries."""
import copy
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
from test_evidence_safety import inventory, raw_result, tool, disposition, invoke_module, REV

class SafetyFailureTests(unittest.TestCase):
    def test_bound_receipt_rejects_swapped_complete_policy(self):
        a, b = S.Policy(inventory(['AAA'])), S.Policy(inventory(['BBB']))
        key = b'private-test-binding-key'
        r = S.project_result(raw_result(), a)
        r['evidence_safety_ack'] = S.receipt(a, 'a'*64, REV, key)
        with self.assertRaises(ValueError):
            S.validate_reply(S.encode(r), b, 'a'*64, REV, key)
        self.assertNotIn(key.decode(), S.encode(r).decode())
        self.assertNotIn('AAA', S.encode(r).decode())

    def test_full_schema_dispositions_required_and_exact_secret_rejected(self):
        p=S.Policy(inventory(['UNIQUE-SECRET']))
        r=S.project_result(raw_result([tool('plain')]),p)
        r['evidence_safety_ack']=S.receipt(p,'c'*64,REV)
        for alter in ('exact-secret','delete','omit-value','event-metadata'):
            bad=copy.deepcopy(r)
            if alter=='exact-secret': bad['text']='UNIQUE-SECRET'
            elif alter=='delete': bad['evidence_safety']['fields']=[x for x in bad['evidence_safety']['fields'] if x['field']!='text']
            elif alter=='omit-value': bad['stdout']='UNIQUE-SECRET'
            else: bad['tool_result_evidence']['events'][0]['metadata']='UNIQUE-SECRET'
            with self.subTest(alter=alter), self.assertRaises(ValueError):
                S.validate_reply(S.encode(bad),p,'c'*64,REV)

    def test_real_clipping_declaration_drops_output_before_any_replacement(self):
        ev=tool('VISIBLE-CREDENTIAL-PREFIX')
        ev['part']['state']['metadata']={'metadata':{'truncated':True}}
        r=S.project_result(raw_result([ev]),S.Policy(inventory()))
        self.assertNotIn('output', r['tool_result_evidence']['events'][0])
        self.assertEqual(disposition(r,'output',0)['reason'],'upstream_clipped')
        self.assertNotIn('VISIBLE-CREDENTIAL-PREFIX',S.encode(r).decode())

    def test_native_call_id_uses_id_not_part_id(self):
        ev=tool('plain')
        ev['part']['id']=ev['part'].pop('callID')
        ev['part']['partID']='part-not-invocation'
        r=S.project_result(raw_result([ev]),S.Policy(inventory()))
        self.assertEqual(r['tool_result_evidence']['events'][0]['call_id'],'call')

    def test_opaque_json_string_omitted_but_declared_json_string_keeps_structure(self):
        p=S.Projection(S.Policy(inventory(['0','1','text'])))
        raw=' {"label": "text", "ok": true} '
        self.assertIs(p.field('output',raw),S.MISSING)
        safe=p.field('nested_json',raw,role='json_string')
        self.assertEqual(json.loads(safe),{'label':'***REDACTED***','ok':True})
        self.assertEqual(p.fields[-1]['state'],'redacted')
        p=S.Projection(S.Policy(inventory()))
        self.assertEqual(p.field('nested_json',raw,role='json_string'),raw)
        self.assertEqual(p.fields[-1]['state'],'exact')
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{bad', '[[['):
            self.assertIs(p.field('nested_json',raw,role='json_string'),S.MISSING)

    def test_deeper_escape_not_a_false_exact(self):
        secret='quoted-"\n\\secret'
        value=secret
        for _ in range(4): value=json.dumps(value)[1:-1]
        p=S.Projection(S.Policy(inventory([secret])))
        self.assertIs(p.field('output',value),S.MISSING)

    def test_request_rejects_bad_versions_encoding_and_duplicates(self):
        request={'schema':S.REQUEST,'run_id':'a'*64,'policy':inventory(['0','1']),'binding_key':'b'*64}
        p,nonce,key=S.read_request(io.BytesIO(S.encode(request)))
        self.assertTrue(p.complete);self.assertEqual(nonce,'a'*64);self.assertEqual(key,bytes.fromhex('b'*64))
        for raw in (b'', S.encode(request).replace(S.REQUEST.encode(),b'future'),
                    json.dumps(request).encode('utf-16'),b'{"a":1,"a":2}',b'x'*(S.WIRE_LIMIT+2)):
            self.assertFalse(S.read_request(io.BytesIO(raw))[0].complete)

    def test_actual_attach_timeout_still_removes_owned_container(self):
        calls=[]
        def engine(command, **kwargs):
            calls.append(command)
            if command[1] == 'start':
                raise subprocess.TimeoutExpired(command, 1, b'private partial output', b'private error')
            return subprocess.CompletedProcess(command, 0, b'', b'')
        with patch.object(safe_invoke.subprocess,'run',side_effect=engine):
            with self.assertRaises(subprocess.TimeoutExpired):
                safe_invoke.execute_container(['docker','run','--rm','-i','immutable-image'], b'private-policy', 1, 'a'*64)
        self.assertEqual([c[1] for c in calls], ['create','start','rm'])
        self.assertIn('--volumes', calls[-1])
        self.assertNotIn('private-policy', repr(calls))

    def test_invalid_cli_diagnostics_do_not_echo_arguments(self):
        command=[sys.executable, str(Path(__file__).resolve().parents[1]/'bin/opencode-eval-runner'),
                 'invoke','--require-evidence-safety','--model','NOT-A-CREDENTIAL', '--unknown=PRIVATE']
        proc=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(proc.returncode,0)
        self.assertNotIn('PRIVATE',proc.stdout+proc.stderr)
        self.assertNotIn('NOT-A-CREDENTIAL',proc.stdout+proc.stderr)

    def test_missing_policy_emit_success_failure_timeout_without_echo(self):
        # Real emitter and main path, not a substitute result serializer.
        for kw in ({'exit_code':0},{'exit_code':1},{'exit_code':124,'timed_out':True}):
            m=invoke_module()
            with tempfile.TemporaryDirectory() as tmp:
                prompt=Path(tmp)/'prompt';prompt.write_text('script')
                env={'EVAL_EVIDENCE_SAFETY':'1','EVAL_MODEL':'fixture/mock', 'EVAL_PROMPT_FILE':str(prompt)}
                class In:
                    buffer=io.BytesIO(b'')
                out=io.StringIO()
                with patch.dict(os.environ,env,clear=True),patch.object(m.sys,'stdin',In()),patch.object(m.sys,'stdout',out),\
                     patch.object(m,'invoke_opencode',return_value={**raw_result([tool('PRIVATE')]),**kw}):
                    result=m.main()
                parsed=json.loads(out.getvalue())
                self.assertEqual(result,0)  # Transport envelope emitted; product exit is in the result.
                self.assertNotIn('PRIVATE',out.getvalue())
                self.assertEqual(parsed['exit_code'],kw['exit_code'])
                self.assertFalse(parsed['evidence_safety_ack']['policy_valid'])

if __name__=='__main__': unittest.main()
