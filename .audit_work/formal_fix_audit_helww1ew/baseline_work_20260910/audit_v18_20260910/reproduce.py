"""Independent offline shutdown audit. No real network; bounded memory allocation."""
import sys,json,tempfile,signal,threading,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
P,E=A.P,A.E
out=[]
def emit(name,**kw):
 out.append(dict(name=name,**kw));print(json.dumps(out[-1]),flush=True)
with tempfile.TemporaryDirectory(prefix='rta-v18-') as td:
 d=Path(td)
 # A stop during slot scan is after the last implemented safety point.
 orig_slot=P.find_slot;stop={}
 def scan(rpc,*args,**kw):
  if not stop:
   stop['before_rpc']=len(rpc.records)
   signal.raise_signal(signal.SIGTERM)
  return orig_slot(rpc,*args,**kw)
 with patch.object(P,'find_slot',side_effect=scan):
  rc,doc,rows,rs=A.flow(d,'slotstop')
 attempts=[json.loads(x) for x in (d/'slotstop.ck').read_text().splitlines() if json.loads(x).get('kind')=='attempt']
 rr=doc['results'][0]
 assert rc==3 and rr['state']=='measured_exit' and attempts[0]['completed']
 emit('active_candidate_finishes_after_sigterm',exit=rc,state=rr['state'],checkpoint_completed=attempts[0]['completed'],rpc_after_signal=len(rs[0].records)-stop['before_rpc'],not_started=doc['acceptance']['not_started'])
 # Cooperative monitor does not prevent allocations even after it has detected excess.
 gov=E.ResourceGovernor(max_rss_kb=1);gov.check()
 assert gov.stopping
 block=bytearray(8*1024*1024)
 emit('no_hard_memory_enforcement',limit_kb=1,stopping=gov.stopping,allocated_after_stop_bytes=len(block),peak_kb=E.rss_peak_kb())
 del block;gov.close()
 # Failure before candidate work must still restore handlers and close watchdog/gate.
 orig_measure=P.measure;orig_fake=A.FakeRpc;orig_gov=E.ResourceGovernor
 previous={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)};gs=[];rets=[]
 def factory(*a,**kw):g=orig_gov(*a,**kw);gs.append(g);return g
 def fake(cfg):return orig_fake(dict(cfg,chain_id=2))
 def measure(args):rc=orig_measure(args);rets.append(rc);return rc
 sub=d/'startup';sub.mkdir()
 try:
  with patch.object(A,'FakeRpc',side_effect=fake),patch.object(P,'measure',side_effect=measure),patch.object(E,'ResourceGovernor',side_effect=factory):
   try:A.flow(sub,'wrongchain',max_wall_s=1000)
   except FileNotFoundError:pass # no result JSON on this precondition return
  changed=[int(s) for s,h in previous.items() if signal.getsignal(s)!=h]
  alive=[g._thread.is_alive() if g._thread else False for g in gs]
  assert rets==[2] and changed and any(alive) and E.http_gate_installed()
  emit('precondition_return_leaks_governor',exit=rets[0],changed_signal_handlers=changed,watchdogs_alive=alive,http_gate_still_installed=E.http_gate_installed())
 finally:
  for g in gs:g.close()
  for s,h in previous.items():signal.signal(s,h)
  E.uninstall_http_gate()
Path(__file__).with_name('observations.json').write_text(json.dumps(out,indent=2))
