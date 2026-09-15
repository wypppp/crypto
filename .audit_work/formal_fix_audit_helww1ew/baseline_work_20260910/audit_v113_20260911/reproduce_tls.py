"""Real HTTPS client, loopback TCP peer that stalls TLS. No external data source."""
import sys,socket,threading,time,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
E=A.E
with tempfile.TemporaryDirectory(prefix='rta-v113-tls-') as td:
 escalations=[];gov=E.ResourceGovernor(grace_seconds=.15,escalate_after=.05,force_exit_after=None,on_escalate=lambda x:escalations.append(x))
 listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();samples=[]
 def server():
  c,_=listener.accept()
  try:
   # TCP is already established. Stop while client is performing TLS handshake.
   gov.request_stop('controlled_stop_after_tcp_before_tls_complete')
   for _ in range(20):
    samples.append(gov.pending_inflight());time.sleep(.025)
  finally:c.close()
 th=threading.Thread(target=server,daemon=True);th.start()
 gate=E.SharedGate(100000,10,3);gate.governor=gov
 raw=A.REAL_RPC(f'https://127.0.0.1:{listener.getsockname()[1]}',max_calls=10,max_seconds=3,timeout=2,rps=100000)
 log=E.EvidenceLog(Path(td)/'tls.jsonl');tap=E.RpcTap(raw,log,gate=gate)
 E.install_http_gate(gate)
 try:
  try:result=tap.request('eth_chainId',[])
  except Exception as e:result=type(e).__name__+':'+str(e)
  latency=gov.report()['stop_latency_s']
  assert latency>.4 and samples and max(samples)==0 and not escalations
  obs=dict(tcp_established=True,phase='TLS handshake',grace_s=.15,escalate_after_s=.05,stop_latency_s=latency,registered_during_tls=max(samples),escalations=len(escalations),result=result,rpc_records=raw.records)
  print(json.dumps(obs),flush=True)
  Path(__file__).with_name('tls_observation.json').write_text(json.dumps(obs,indent=2))
 finally:
  E.uninstall_http_gate();log.close();gov.close();th.join(2);listener.close()
  Path(__file__).with_name('tls.jsonl').write_bytes((Path(td)/'tls.jsonl').read_bytes())
