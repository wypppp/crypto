"""Offline integration test: omit required bindings in otherwise unchanged evidence."""
import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
fields=['script_sha256','evidence_module_sha256','spec_sha256','sample_sha256','universe_sha256_now','finalized_snapshot']
observations=[]
with tempfile.TemporaryDirectory(prefix='rta-v16-') as td:
 d=Path(td);ck=d/'shared.ck'
 rc,doc,rows,_=A.flow(d,'first',checkpoint=ck)
 assert rc==0
 original=(d/'first.jsonl').read_text()
 for key in fields:
  rr=[json.loads(x) for x in original.splitlines()]
  for r in rr:
   if r.get('kind')=='run_header':r.pop(key,None)
  (d/'first.jsonl').write_text('\n'.join(json.dumps(r) for r in rr)+'\n')
  rc,doc,rows,_=A.flow(d,'resume_'+key,checkpoint=ck)
  assert rc==0 and not doc['acceptance']['evidence_chain_problems']
  observations.append(dict(removed=key,exit=rc,n=len(doc['results']),validation_passed=doc['acceptance']['validation_passed'],evidence_chain_problems=doc['acceptance']['evidence_chain_problems']))
 print(json.dumps(observations,indent=2))
 Path(__file__).with_name('missing_binding.json').write_text(json.dumps(observations,indent=2))
