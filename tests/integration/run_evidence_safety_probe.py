#!/usr/bin/env python3
"""Real public invoke -> updated image -> pre-output projection -> host sink.

Fixtures use synthetic values only. Raw product output stays in private memory;
verification artifacts contain safe projections and fixed boolean results only.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from container import evidence_safety as S

LONG='LONG-CREDENTIAL-'+'z'*9000
ESCAPED='quoted-"line\nback\\slash-UNIQUE'
ONLY_POLICY='PRIVATE-POLICY-ONLY-NOT-FOR-TARGET'
VALUES=['0','1','text','low',LONG,ESCAPED,ONLY_POLICY,'fixture']
OUTPUT='low text 0 1 | '+LONG+' | '+ESCAPED
PLUGIN='''
export default { id: "capturersp", async setup(ctx) {
  await ctx.tool.transform(editor => {
    editor.namespace({name:"capturersp", description:"Synthetic RSP fixture"});
    editor.add({name:"emit", description:"Return an independently known value", 
      input:{type:"object",properties:{scenario:{type:"string"}},required:["scenario"],additionalProperties:false},
      options:{namespace:"capturersp",codemode:false},
      execute: async input => {
        if (Object.values(process.env).some(v => String(v).includes("PRIVATE-POLICY-ONLY-NOT-FOR-TARGET")))
          throw Error("policy_leaked_to_child_environment");
        if (input.scenario === "timeout") await new Promise(resolve=>setTimeout(resolve,12000));
        if (input.scenario === "failure") throw Error(FAILURE);
        return {content: input.scenario === "oversize" ? "public ".repeat(1000) : SENTINEL};
      }
    });
  });
}};
'''.replace('SENTINEL',json.dumps(OUTPUT)).replace('FAILURE',json.dumps('FAILURE-'+ESCAPED))


def inventory(kind):
    if kind=='missing': return None
    p={'schema':S.POLICY,'policy_version':S.VERSION,'complete':True,
       'sources':{n:'complete' if n in {'env', 'config'} else 'not_selected' for n in S.SOURCE_NAMES},'values':VALUES}
    if kind=='incomplete': p['complete']=False;p['sources']['env']='incomplete';p['values']=[]
    if kind=='future': p['policy_version']='unsupported-future'
    return p


def once(image, root, name, policy_kind, scenario='success', legacy=False, disposable=False, database_override=False, ambient_traps=False):
    workspace=root/name; workspace.mkdir()
    (workspace/'.opencode/plugins').mkdir(parents=True)
    (workspace/'.opencode/plugins/rsp.ts').write_text(PLUGIN)
    seen=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            length=int(self.headers.get('Content-Length','0'))
            if length>2_000_000: self.send_error(400);return
            body=json.loads(self.rfile.read(length));seen.append(body)
            if len(seen)==1:
                names=[x['function']['name'] for x in body.get('tools',[])]
                actual=next((n for n in names if n.endswith('capturersp_emit')),None)
                if not actual: self.send_error(400);return
                delta={'role':'assistant','tool_calls':[{'index':0,'id':'rsp-tool-call','type':'function',
                    'function':{'name':actual,'arguments':json.dumps({'scenario':scenario})}}]}
                finish='tool_calls'
            else:
                delta={'role':'assistant','content':'PUBLIC-DONE'};finish='stop'
            common={'id':'mock','created':1,'model':body['model'],'object':'chat.completion.chunk'}
            chunks=[{**common,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                    {**common,'choices':[{'index':0,'delta':{},'finish_reason':finish}],
                     'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}]
            raw=(''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n').encode()
            self.send_response(200);self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    config={'$schema':'https://opencode.ai/config.json','model':'fixture/mock','enabled_providers':['fixture'],
            'provider':{'fixture':{'npm':'@ai-sdk/openai-compatible','name':'Synthetic',
                'options':{'baseURL':f'http://127.0.0.1:{server.server_port}/v1','apiKey':'fixture'},
                'models':{'mock':{'name':'Mock','limit':{'context':1_000_000,'output':32768}}}}}}
    (workspace/'opencode.json').write_text(json.dumps(config))
    prompt=workspace/'prompt.txt';prompt.write_text('Run the prescribed fixture.');output=root/(name+'-result.json')
    env=dict(os.environ)
    for key in list(env):
        if key.startswith('OPENCODE_EVAL_RUNNER_') or key in {
            'OPENAI_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','OPENCODE_API_KEY',
            'GITHUB_TOKEN','GH_TOKEN','COPILOT_GITHUB_TOKEN','OPENCODE_CONFIG_DIR'}:
            env.pop(key,None)
    state=workspace/'isolated';state.mkdir()
    for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME'):
        path=state/key;path.mkdir();env[key]=str(path)
    ambient_db=None
    if ambient_traps:
        ambient_data=Path(env['XDG_DATA_HOME'])/'opencode';ambient_data.mkdir(parents=True)
        (ambient_data/'auth.json').write_text(json.dumps({'token':'AMBIENT-AUTH-MUST-NOT-BE-READ'}))
        ambient_db=ambient_data/'opencode.db'
        with sqlite3.connect(ambient_db) as db:
            db.execute('CREATE TABLE session (id TEXT PRIMARY KEY)')
            db.execute("INSERT INTO session VALUES ('AMBIENT-SESSION-MUST-NOT-BE-READ')")
            db.commit()
    command=[sys.executable,str(ROOT/'bin/opencode-eval-runner'),'invoke','--engine','docker',
             '--network','host','--image',image,'--workspace',str(workspace),'--workspace-mode','rw',
             '--model','fixture/mock','--config',str(workspace/'opencode.json'),'--prompt-file',str(prompt),'--output',str(output),
             '--timeout-seconds','4' if scenario=='timeout' else '30','--container-timeout','60','--print-result']
    if disposable:
        command += ['--opencode-state-profile','disposable']
    if database_override:
        explicit_db=root/(name+'-explicit.db')
        with sqlite3.connect(explicit_db) as db:
            db.execute('CREATE TABLE session (id TEXT PRIMARY KEY)')
        command += ['--database',str(explicit_db)]
    if not legacy:
        command.append('--require-evidence-safety')
        policy=inventory(policy_kind)
        if policy is not None:
            private=root/(name+'-private-policy.json');private.write_text(json.dumps(policy));private.chmod(0o600)
            command+=['--evidence-policy-file',str(private)]
    else:
        env['EVAL_EVIDENCE_SAFETY']='0'; command+=['--env','EVAL_EVIDENCE_SAFETY']
    try:
        proc=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,timeout=80,check=False)
        result=json.loads(output.read_bytes()) if output.is_file() else {}
        emitted=json.loads(proc.stdout) if proc.stdout.strip() else {}
        oracle=[m.get('content') for request in seen[1:] for m in request.get('messages',[]) if m.get('role')=='tool']
        return result,emitted,proc.returncode,oracle,len(seen)
    finally:
        server.shutdown();server.server_close();t.join(3)


def check_safety(name,r,emitted,code,policy_kind):
    checks={}
    checks[name+':file_equals_print']=r==emitted and r.get('schema')==S.RESULT
    checks[name+':raw_streams_absent']='stdout' not in r and 'stderr' not in r
    checks[name+':explicit_safety']=r.get('evidence_safety',{}).get('schema')==S.SAFETY
    checks[name+':private_inventory_absent']=all(x not in S.encode(r).decode() for x in (LONG,ESCAPED,ONLY_POLICY))
    checks[name+':host_validates_ack']=r.get('evidence_safety_validation',{}).get('acknowledged') is True
    fields=r.get('evidence_safety',{}).get('fields',[])
    if policy_kind=='valid':
        checks[name+':transport_success']=code==0
        checks[name+':no_changed_field_exact']=all(
            f['state']!='exact' for f in fields if f['field']=='output' and f['event'] is not None)
    else:
        checks[name+':incomplete_non_evidence']=code!=0 and not r.get('evidence_safety',{}).get('inventory_complete',True)
        checks[name+':payloads_absent']=all(key not in r for key in ('text','tools','actions','session_id'))
    return checks


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--image',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True);checks={}
    with tempfile.TemporaryDirectory(prefix='rsp-real-image-') as tmp:
        root=Path(tmp)
        _,_,legacy_code,legacy_oracle,_=once(args.image,root,'legacy','missing',legacy=True)
        r,e,code,oracle,_=once(args.image,root,'valid','valid')
        checks.update(check_safety('valid',r,e,code,'valid'))
        fields=r.get('evidence_safety',{}).get('fields',[])
        outputs=[x for x in r.get('tool_result_evidence',{}).get('events',[]) if 'output' in x]
        checks['valid:actual_product_unchanged']=legacy_code==0 and bool(legacy_oracle) and legacy_oracle==oracle
        checks['valid:actual_output_retained']=len(outputs)==1 and '***REDACTED***' in outputs[0]['output']
        checks['valid:short_payloads_marked']=any(f['field']=='output' and f['state']=='redacted' for f in fields)
        checks['valid:protocol_zero_preserved']=r.get('exit_code')==0
        checks['valid:protocol_text_key_preserved']=r.get('text')=='PUBLIC-DONE'
        (out/'valid.json').write_bytes(S.encode(r)+b'\n')
        for policy_kind in ('missing','incomplete','future'):
            for scenario in ('success','failure','timeout'):
                name=policy_kind+'-'+scenario
                r,e,code,_,_=once(args.image,root,name,policy_kind,scenario)
                checks.update(check_safety(name,r,e,code,policy_kind))
                if scenario=='timeout':checks[name+':product_timeout_preserved']=r.get('timed_out') is True and r.get('exit_code')==124
                (out/(name+'.json')).write_bytes(S.encode(r)+b'\n')
        for scenario in ('failure','oversize'):
            r,e,code,_,_=once(args.image,root,scenario,'valid',scenario)
            checks.update(check_safety(scenario,r,e,code,'valid'))
            fields=r.get('evidence_safety',{}).get('fields',[])
            if scenario=='failure':checks['actual_error_protected']=any(f['field']=='error' and f['state']=='redacted' for f in fields)
            else:checks['safe_then_size_omission']=any(f['field']=='output' and f['state']=='omitted' and f['reason']=='size_limit' for f in fields)
            (out/(scenario+'.json')).write_bytes(S.encode(r)+b'\n')

        # First discriminate the disposable lifecycle itself without the RSP
        # envelope. All values in this fixture are synthetic, so preserving the
        # fixed transport error in the artifact is safe and helps distinguish
        # OpenCode bootstrap failures from safety-admission failures.
        raw,e_raw,raw_code,_,raw_requests=once(
            args.image,root,'disposable-lifecycle','missing',legacy=True,
            disposable=True,ambient_traps=True
        )
        checks['disposable-lifecycle:bootstrap_succeeds']=raw_code==0
        checks['disposable-lifecycle:runtime_state_attested']=(
            raw.get('runtime_state',{}).get('profile')=='disposable' and
            raw.get('runtime_state',{}).get('database_source')=='runtime-bootstrap' and
            raw.get('runtime_state',{}).get('migration_count')==48)
        checks['disposable-lifecycle:provider_after_bootstrap']=raw_requests>0
        (out/'disposable-lifecycle.json').write_text(json.dumps(raw,indent=2)+'\n')

        # DB handoff: real invoke, fresh runtime-owned DB, ambient host auth/DB traps present.
        r,e,code,oracle,requests=once(
            args.image,root,'disposable-valid','valid',disposable=True,ambient_traps=True
        )
        checks.update(check_safety('disposable-valid',r,e,code,'valid'))
        state=r.get('runtime_state',{})
        state_disp=next((x for x in r.get('evidence_safety',{}).get('fields',[])
                         if x.get('event') is None and x.get('field')=='runtime_state'),{})
        checks['disposable-valid:runtime_bootstrap_attested']=(
            state.get('schema')=='opencode-eval-runner/runtime-state/v1' and
            state.get('profile')=='disposable' and state.get('database_source')=='runtime-bootstrap' and
            state.get('database_created') is True and state.get('database_seed_present') is False and
            state.get('auth_source')=='none' and state.get('session_rows_before_inference')==0 and
            state.get('credential_rows_before_inference')==0 and state.get('migration_count')==48 and
            state.get('first_migration')=='20260127222353_familiar_lady_ursula' and
            state.get('last_migration')=='20260923013825_project_time_active' and
            state_disp.get('state')=='exact')
        checks['disposable-valid:ambient_state_not_read']=(
            'AMBIENT-AUTH-MUST-NOT-BE-READ' not in json.dumps(r) and
            'AMBIENT-SESSION-MUST-NOT-BE-READ' not in json.dumps(r) and requests > 0)
        (out/'disposable-valid.json').write_bytes(S.encode(r)+b'\n')

        # Missing safety policy and incompatible explicit DB selection fail before provider inference.
        r,e,code,_,requests=once(args.image,root,'disposable-missing','missing',disposable=True,ambient_traps=True)
        checks['disposable-missing:pre_inference_fail']=code!=0 and requests==0 and not r.get('evidence_safety',{}).get('inventory_complete',True)
        checks['disposable-missing:no_payload']=all(k not in r for k in ('text','tools','actions','session_id'))
        (out/'disposable-missing.json').write_bytes(S.encode(r)+b'\n')

        r,e,code,_,requests=once(args.image,root,'disposable-explicit-db','valid',disposable=True,database_override=True)
        checks['disposable-explicit-db:pre_inference_fail']=code!=0 and requests==0
        checks['disposable-explicit-db:no_payload']=all(k not in r for k in ('text','tools','actions','session_id'))
        (out/'disposable-explicit-db.json').write_bytes(S.encode(r)+b'\n')

    summary={'schema':'rsp-image-proof/v1','image':args.image,'checks':checks,'passed':all(checks.values()),
             'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'real_provider_inference':False,'full_capture_accepted':False,'loom_composition':'not_run'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
