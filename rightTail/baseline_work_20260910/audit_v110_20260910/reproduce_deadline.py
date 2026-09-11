"""Real urllib + package RPC against a controlled LOOPBACK server only.
No external network, API quota, credentials, or RLIMIT changes.
"""
import sys,json,time,threading,tempfile
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
E=A.E
observations=[]
with tempfile.TemporaryDirectory(prefix='rta-v110-') as td:
 for mode in ['stop_before_request','stop_during_request']:
  gov=E.ResourceGovernor(grace_calls=2,grace_seconds=0.15)
  sent=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_POST(self):
    req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
    if mode=='stop_during_request':gov.request_stop('controlled_inflight_stop')
    body=json.dumps(dict(jsonrpc='2.0',id=req['id'],result='0x1')).encode()
    self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
    # Every idle interval is below socket timeout, but entire response exceeds grace.
    try:
     for i in range(0,len(body),4):
      self.wfile.write(body[i:i+4]);self.wfile.flush();sent.append(time.monotonic());time.sleep(0.035)
    except (BrokenPipeError,ConnectionResetError):pass
  server=HTTPServer(('127.0.0.1',0),Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  gate=E.SharedGate(100000,10,5);gate.governor=gov
  raw=A.REAL_RPC(f'http://127.0.0.1:{server.server_port}',max_calls=10,max_seconds=5,timeout=2,rps=100000)
  log=E.EvidenceLog(Path(td)/(mode+'.jsonl'));tap=E.RpcTap(raw,log,gate=gate,worker=0)
  E.install_http_gate(gate)
  try:
   if mode=='stop_before_request':
    gov.request_stop('controlled_stop')
    with gov.winddown():result=tap.request('eth_chainId',[])
   else:result=tap.request('eth_chainId',[])
   lat=gov.report()['stop_latency_s']
   assert result=='0x1' and lat>0.3
   obs=dict(mode=mode,result=result,grace_s=0.15,observed_stop_latency_s=lat,body_fragments=len(sent),max_gap_s=max(b-a for a,b in zip(sent,sent[1:])),http_sent=gate.sent,rpc_records=raw.records)
   observations.append(obs);print(json.dumps(obs),flush=True)
  finally:
   E.uninstall_http_gate();log.close();gov.close();server.shutdown();server.server_close();thread.join()
   Path(__file__).with_name(mode+'.jsonl').write_bytes((Path(td)/(mode+'.jsonl')).read_bytes())
Path(__file__).with_name('deadline_observations.json').write_text(json.dumps(observations,indent=2))
