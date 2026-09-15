"""Offline transport/resource setup counterexamples. No real RLIMIT is installed."""
import sys,json,tempfile,time,urllib.error,resource
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
P,E=A.P,A.E
out=[]
def emit(name,**kw):
 out.append(dict(name=name,**kw));print(json.dumps(out[-1]),flush=True)
class Response:
 def __init__(self,rid):self.rid=rid
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def read(self,*a):return json.dumps(dict(jsonrpc='2.0',id=self.rid,result='0x1')).encode()
with tempfile.TemporaryDirectory(prefix='rta-v19-') as td:
 d=Path(td)
 # Actual package RPC performs its own retry; transport is mocked BELOW the HTTP gate.
 gov=E.ResourceGovernor(grace_calls=0,grace_seconds=0)
 gate=E.SharedGate(100000,10,5);gate.governor=gov
 log=E.EvidenceLog(d/'retry.jsonl');raw=A.REAL_RPC('https://offline.invalid',max_calls=10,max_seconds=5,rps=100000)
 tap=E.RpcTap(raw,log,gate=gate,worker=0);calls=[]
 def retry_transport(req,**kw):
  calls.append(dict(at=time.monotonic(),stopping=gov.stopping))
  if len(calls)==1:
   gov.request_stop('controlled_stop')
   raise urllib.error.HTTPError('https://offline.invalid',503,'mock',{},None)
  return Response(json.loads(req.data)['id'])
 E.install_http_gate(gate,transport=retry_transport)
 try:result=tap.request('eth_chainId',[])
 finally:E.uninstall_http_gate();log.close();gov.close()
 assert result=='0x1' and len(calls)==2 and calls[1]['stopping']
 emit('retry_starts_after_stop_outside_winddown',result=result,http_calls=len(calls),gap_s=calls[1]['at']-calls[0]['at'],grace_calls=0,governor=gov.report())
 # Grace time is checked before transport; it does not bound completion.
 gov=E.ResourceGovernor(grace_calls=1,grace_seconds=0.02);gate=E.SharedGate(100000,10,5);gate.governor=gov
 log=E.EvidenceLog(d/'slow.jsonl');raw=A.REAL_RPC('https://offline.invalid',max_calls=10,max_seconds=5,rps=100000)
 tap=E.RpcTap(raw,log,gate=gate,worker=0)
 slow_timeouts=[]
 def slow(req,**kw):slow_timeouts.append(kw.get('timeout'));time.sleep(0.15);return Response(json.loads(req.data)['id'])
 E.install_http_gate(gate,transport=slow);gov.request_stop('controlled_stop')
 try:
  with gov.winddown():result=tap.request('eth_chainId',[])
 finally:E.uninstall_http_gate();log.close();gov.close()
 assert result=='0x1' and gov.report()['stop_latency_s']>0.1
 emit('grace_seconds_not_completion_deadline',result=result,configured_grace_s=0.02,transport_timeout_s=slow_timeouts[0],latency_s=gov.report()['stop_latency_s'])
 # No real hard limit changes: inject OS rejection, verify full measure acceptance.
 orig=P.measure
 def set_requested_hard(args):args.hard_rss_mb=64;return orig(args)
 sub=d/'hardfail';sub.mkdir()
 with patch.object(P,'measure',side_effect=set_requested_hard),patch.object(resource,'setrlimit',side_effect=PermissionError('controlled setrlimit rejection')):
  rc,doc,rows,_=A.flow(sub,'run')
 applied=doc['resources']['limits']['hard_backstop']['applied']
 assert rc==0 and 'error' in applied['RLIMIT_AS']
 emit('hard_limit_install_failure_accepted',exit=rc,applied=applied,validation_passed=doc['acceptance']['validation_passed'])
 # Initialization fails after installing HTTP wrapper but before entering try/finally.
 sub=d/'initfail';sub.mkdir()
 try:
  with patch.object(A,'FakeRpc',side_effect=RuntimeError('controlled RPC construction failure')):
   try:A.flow(sub,'run')
   except RuntimeError:pass
  assert E.http_gate_installed()
  emit('constructor_failure_leaves_http_gate',installed=E.http_gate_installed())
 finally:E.uninstall_http_gate()
Path(__file__).with_name('observations.json').write_text(json.dumps(out,indent=2))
