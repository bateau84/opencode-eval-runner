import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_POST(self):
  n=int(self.headers.get('content-length','0')); body=json.loads(self.rfile.read(n)); msgs=body.get('messages',[])
  print(json.dumps({'path':self.path,'model':body.get('model'),'stream':body.get('stream'),'tools':[t.get('function',{}).get('name') for t in body.get('tools',[]) if isinstance(t,dict)]}),flush=True)
  text='\n'.join(str(m.get('content','')) for m in msgs)
  # Distinguish judge prompts from target prompts and emit a valid strict grade using authored contract text.
  skill_match=__import__('re').search(r'Load the native skill `([^`]+)`',text)
  skill_tool=next((t.get('function',{}).get('name') for t in body.get('tools',[]) if isinstance(t,dict) and isinstance(t.get('function'),dict) and t.get('function',{}).get('name','').lower().endswith('skill')),None)
  if skill_match and skill_tool and not any(m.get('role') == 'tool' for m in msgs) and 'Evaluate this skill-ablation response.' not in text:
   call={'id':'fixture-skill-call','type':'function','function':{'name':skill_tool,'arguments':json.dumps({'id':skill_match.group(1)})}}
   obj={'id':'chatcmpl-fixture','object':'chat.completion','created':1,'model':body.get('model','fixture/mock'),'choices':[{'index':0,'message':{'role':'assistant','content':None,'tool_calls':[call]},'finish_reason':'tool_calls'}]}
   result_obj=obj
  else: result_obj=None
  if result_obj is not None:
   pass
  elif 'Evaluate this skill-ablation response.' in text or 'Evaluate this behavioral case.' in text:
   marker='Evaluate this skill-ablation response.' if 'Evaluate this skill-ablation response.' in text else 'Evaluate this behavioral case.'
   prompt=next((str(m.get('content','')) for m in msgs if marker in str(m.get('content',''))),'')
   pos=prompt.split('POSITIVE EXPECTATIONS:\n',1)[-1].split('\nFORBIDDEN BEHAVIOR:',1)[0]
   neg=prompt.split('\nFORBIDDEN BEHAVIOR:\n',1)[-1].split('\n',1)[0] if 'FORBIDDEN BEHAVIOR:' in prompt else ''
   if marker == 'Evaluate this skill-ablation response.': neg=prompt.split('\nFORBIDDEN BEHAVIOR:\n',1)[-1].split('\nOBSERVED ASSISTANT TEXT:',1)[0]
   positives=[line.split('. ',1)[1] for line in pos.splitlines() if '. ' in line]
   negatives=[line.split('. ',1)[1] for line in neg.splitlines() if '. ' in line]
   result=json.dumps({'passed':True,'expectations':[{'expectation':x,'met':True,'reason':'deterministic fixture grade'} for x in positives],'violations':[{'rule':x,'violated':False,'reason':'deterministic fixture grade'} for x in negatives],'trap_observed':False,'trap_evidence':'not observed','summary':'Fixture accepted all authored positive expectations.'})
  elif 'strict JSON only:' in text:
   # Agent/runtime contract judge is separately handled below with a strict generic minimal response.
   result='{}'
  else: result='Deterministic fixture response: provide a clear, complete answer satisfying all requested expectations; use AsyncMock for awaited calls, isolated tmp_path databases, parametrize independent cases, preserve domain errors with causes, narrow catches and log exceptions.'
  if result_obj is None:
   obj={'id':'chatcmpl-fixture','object':'chat.completion','created':1,'model':body.get('model','fixture/mock'),'choices':[{'index':0,'message':{'role':'assistant','content':result},'finish_reason':'stop'}]}
  else: obj=result_obj
  if body.get('stream'):
   message=obj['choices'][0]['message']
   finish=obj['choices'][0]['finish_reason']
   if message.get('tool_calls'):
    calls=[{'index':i,'id':c['id'],'type':'function','function':c['function']} for i,c in enumerate(message['tool_calls'])]
    delta={'role':'assistant','tool_calls':calls}
   else: delta={'role':'assistant','content':message.get('content','')}
   chunks=[{**{k:obj[k] for k in ('id','created','model')},'object':'chat.completion.chunk','choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**{k:obj[k] for k in ('id','created','model')},'object':'chat.completion.chunk','choices':[{'index':0,'delta':{},'finish_reason':finish}]}]
   raw=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode(); mime='text/event-stream'
  else:
   raw=json.dumps(obj).encode(); mime='application/json'
  self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
ThreadingHTTPServer(('0.0.0.0',18761),H).serve_forever()
