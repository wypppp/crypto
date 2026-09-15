"""Verify previous exact failures are blocked; mock below HTTP gate, no real RLIMIT."""
import sys,json,tempfile,urllib.error,resource
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
P,E=A.P,A.E
out=[]
def emit(name,**kw):out.append(dict(name=name,**kw));print(json.dumps(out[-1]),flush=True)
with tempfile.TemporaryDirectory(prefix='rta-v110-closed-') as td:
 d=Path(td);gov=E.ResourceGovernor(grace_calls=0,grace_seconds=0);gate=E.SharedGate(100000,10,5);gate.governor=gov
 log=E.EvidenceLog(d/'retry.jsonl');raw=A.REAL_RPC('https://offline.invalid',max_calls=10,max_seconds=5,rps=100000);tap=E.RpcTap(raw,log,gate=gate,worker=0);calls=[]
 def transport(*a,**kw):
  calls.append(1);gov.request_stop('controlled_stop')
  raise urllib.error.HTTPError('https://offline.invalid',503,'mock',{},None)
 E.install_http_gate(gate,transport=transport)
 try:
  try:tap.request('eth_chainId',[]);raise AssertionError('retry not blocked')
  except E.Shutdown as ex:
   assert len(calls)==1 and ex.detail['layer']=='http'
   emit('retry_blocked',http_sent=len(calls),layer=ex.detail['layer'])
 finally:E.uninstall_http_gate();log.close();gov.close()
 # A.flow expects a result file; precondition failure intentionally produces none.
 orig=P.measure;rets=[]
 def measure(args):args.hard_rss_mb=64;rc=orig(args);rets.append(rc);return rc
 sub=d/'hard';sub.mkdir()
 with patch.object(P,'measure',side_effect=measure),patch.object(resource,'setrlimit',side_effect=PermissionError('controlled setrlimit rejection')):
  try:A.flow(sub,'run')
  except FileNotFoundError:pass
 rows,_=E.read_evidence(sub/'run.jsonl',report=True)
 assert rets==[2] and not any(r.get('kind')=='candidate_start' for r in rows)
 emit('hard_install_failure_blocks',exit=rets[0],candidate_starts=0,result_exists=(sub/'run.json').exists())
 sub=d/'init';sub.mkdir()
 with patch.object(A,'FakeRpc',side_effect=RuntimeError('controlled constructor failure')):
  try:A.flow(sub,'run')
  except RuntimeError:pass
 assert not E.http_gate_installed()
 emit('constructor_cleanup',http_gate_installed=E.http_gate_installed())
Path(__file__).with_name('closed_observations.json').write_text(json.dumps(out,indent=2))
