"""Offline audit. Network is mocked; outputs confined to temporary directories."""
import sys,json,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
P,E=A.P,A.E
out=[]
def emit(name,**kw):
 out.append(dict(name=name,**kw));print(json.dumps(out[-1]),flush=True)
with tempfile.TemporaryDirectory(prefix='rta-v15-') as td:
 d=Path(td); ck=d/'shared.ck'
 rc,doc,rows,_=A.flow(d,'first',checkpoint=ck)
 assert rc==0
 # Replace referenced evidence by structurally complete evidence for a different run.
 ev=d/'other.jsonl';log=E.EvidenceLog(ev);log.write('run_header',note='unrelated run');log.write('run_footer');log.close()
 (d/'first.jsonl').write_bytes(ev.read_bytes())
 rc,doc,rows,_=A.flow(d,'resumed',checkpoint=ck)
 assert rc!=0 and doc['acceptance']['evidence_chain_problems']
 emit('unrelated_evidence_blocked',exit=rc,n=len(doc['results']),acceptance=doc['acceptance'])
 # Test actual HTTP accounting at the transport boundary on a rejected wait.
 gate=E.SharedGate(10,10,0.02);calls=[]
 def transport(*a,**kw):calls.append(1);return 'ok'
 E.install_http_gate(gate,transport=transport)
 try:
  E.urllib.request.urlopen('https://offline.invalid')
  try:E.urllib.request.urlopen('https://offline.invalid')
  except E.BudgetExhausted:pass
 finally:E.uninstall_http_gate()
 assert len(calls)==1 and gate.stats()['http_sent']==1 and gate.stats()['http_reserved']==2 and gate.stats()['http_rejected_after_wait']==1
 emit('sent_counter_correct',transport_calls=len(calls),stats=gate.stats())
 # Existing flow pins diagnostics off; wrapper changes only diagnostics at entry.
 original_measure=P.measure;original_probe=P.V.probe_call
 def diag_measure(args):args.diagnostics=True;return original_measure(args)
 def probe(*args,**kw):
  if kw.get('selling') and args[5]==1:raise P.V.RpcFailure('transport','injected diagnostic failure')
  result=original_probe(*args,**kw)
  if kw.get('selling'):result.update(stage=20, classification='simulated_revert', token_after=result['token_before'], cash_in=0)
  return result
 sub=d/'cost';sub.mkdir()
 with patch.object(P,'measure',side_effect=diag_measure),patch.object(P.V,'probe_call',side_effect=probe):
  rc,doc,rows,_=A.flow(sub,'run')
 rr=doc['results'][0]
 assert rr['exit']['stage']==20 and rr['cost']['exit_attempts']['swap']==1 and rr['cost']['exit_attempts']['approve']==2
 emit('sell_attempts_preserved',exit=rc,state=rr['state'],sell=rr['exit'],cost=rr['cost'])
Path(__file__).with_name('observations.json').write_text(json.dumps(out,indent=2))
