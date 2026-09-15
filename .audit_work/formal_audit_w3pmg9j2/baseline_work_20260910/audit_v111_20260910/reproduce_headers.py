"""Real urllib/RPC + loopback only: deadline during receipt of response headers."""
import sys,json,time,threading,tempfile
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
E=A.E
obs=[]
with tempfile.TemporaryDirectory(prefix='rta-v111-header-') as td:
 for mode in ['stop_before_headers','stop_during_headers']:
  escalations=[];gov=E.ResourceGovernor(grace_calls=2,grace_seconds=0.15,escalate_after=0.05,on_escalate=lambda x:escalations.append(x))
  samples=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_POST(self):
    req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
    if mode=='stop_during_headers':gov.request_stop('controlled_stop_during_headers')
    body=json.dumps(dict(jsonrpc='2.0',id=req['id'],result='0x1')).encode()
    # A valid header delivered slowly. urllib has not returned an HTTPResponse yet.
    wire=b'HTTP/1.0 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nX-Slow: abcdefghijklmnop\r\n\r\n'
    try:
     for i in range(0,len(wire),4):
      self.wfile.write(wire[i:i+4]);self.wfile.flush()
      samples.append(dict(at=time.monotonic(),registered=len(gov._inflight),escalations=gov.escalations))
      time.sleep(0.025)
     self.wfile.write(body);self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
  server=HTTPServer(('127.0.0.1',0),Handler);th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
  gate=E.SharedGate(100000,10,5);gate.governor=gov
  raw=A.REAL_RPC(f'http://127.0.0.1:{server.server_port}',max_calls=10,max_seconds=5,timeout=2,rps=100000)
  log=E.EvidenceLog(Path(td)/(mode+'.jsonl'));tap=E.RpcTap(raw,log,gate=gate,worker=0)
  E.install_http_gate(gate)
  try:
   try:
    if mode=='stop_before_headers':
     gov.request_stop('controlled_stop_before_headers')
     with gov.winddown():result=tap.request('eth_chainId',[])
    else:result=tap.request('eth_chainId',[])
   except E.Shutdown as e:result='Shutdown:'+e.reason
   lat=gov.report()['stop_latency_s']
   assert lat>0.35 and not escalations and all(s['registered']==0 for s in samples)
   r=dict(mode=mode,grace_s=.15,escalate_after_s=.05,stop_latency_s=lat,result=result,escalations=len(escalations),registered_during_headers=0,header_fragments=len(samples),max_gap_s=max(b['at']-a['at'] for a,b in zip(samples,samples[1:])),rpc_records=raw.records)
   obs.append(r);print(json.dumps(r),flush=True)
  finally:
   E.uninstall_http_gate();log.close();gov.close();server.shutdown();server.server_close();th.join()
   Path(__file__).with_name(mode+'.jsonl').write_bytes((Path(td)/(mode+'.jsonl')).read_bytes())
Path(__file__).with_name('header_observations.json').write_text(json.dumps(obs,indent=2))
