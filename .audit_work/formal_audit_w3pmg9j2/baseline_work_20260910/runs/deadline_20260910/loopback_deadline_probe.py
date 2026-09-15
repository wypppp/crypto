"""同一真实 loopback 场景，测修复后的实际上界。仅本机 127.0.0.1。"""
import sys,json,time,threading,tempfile
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,'/home/ancillary/rightTail/baseline_work_20260910')
import audit_flow as A
E=A.E
out=[]
with tempfile.TemporaryDirectory(prefix='dl-') as td:
    for mode in ['stop_before_request','stop_during_request','no_stop_control']:
        gov=E.ResourceGovernor(grace_calls=2,grace_seconds=0.15)
        sent=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_POST(self):
                req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if mode=='stop_during_request': gov.request_stop('controlled_inflight_stop')
                body=json.dumps(dict(jsonrpc='2.0',id=req['id'],result='0x1')).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:
                    for i in range(0,len(body),4):
                        self.wfile.write(body[i:i+4]);self.wfile.flush();sent.append(time.monotonic());time.sleep(0.035)
                except Exception: pass
        server=HTTPServer(('127.0.0.1',0),Handler)
        th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
        gate=E.SharedGate(100000,10,5);gate.governor=gov
        raw=A.REAL_RPC(f'http://127.0.0.1:{server.server_port}',max_calls=10,max_seconds=5,timeout=2,rps=100000)
        log=E.EvidenceLog(Path(td)/(mode+'.jsonl'));tap=E.RpcTap(raw,log,gate=gate,worker=0)
        E.install_http_gate(gate)
        t0=time.monotonic()
        try:
            if mode=='stop_before_request':
                gov.request_stop('controlled_stop')
                with gov.winddown():
                    try: res=tap.request('eth_chainId',[])
                    except E.Shutdown as e: res=f"Shutdown:{e.reason}"
            elif mode=='stop_during_request':
                try: res=tap.request('eth_chainId',[])
                except E.Shutdown as e: res=f"Shutdown:{e.reason}"
            else:
                try: res=tap.request('eth_chainId',[])
                except Exception as e: res=f"{type(e).__name__}"
            rep=gov.report()
            out.append(dict(mode=mode,result=res,grace_s=0.15,
                            总耗时s=round(time.monotonic()-t0,3),
                            停机后耗时s=rep['stop_latency_s'],
                            分段数=len(sent),最大段间隔s=round(max([b-a for a,b in zip(sent,sent[1:])],default=0),4),
                            到点强制关闭=rep['absolute_deadline_closures'],升级=rep['escalations']))
            print(json.dumps(out[-1],ensure_ascii=False),flush=True)
        finally:
            E.uninstall_http_gate();log.close();gov.close();server.shutdown();server.server_close();th.join()
