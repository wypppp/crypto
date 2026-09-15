"""量一下监督路径的稳态开销：本机 loopback，快响应，200 次请求。"""
import sys,json,time,threading,tempfile,statistics
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
import audit_flow as A
E=A.E
class H(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*a): pass
    def do_POST(self):
        req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        b=json.dumps(dict(jsonrpc='2.0',id=req['id'],result='0x1')).encode()
        self.send_response(200); self.send_header('Content-Length',str(len(b))); self.end_headers()
        self.wfile.write(b)
srv=HTTPServer(('127.0.0.1',0),H); th=threading.Thread(target=srv.serve_forever,daemon=True); th.start()
N=200
def run(with_gov):
    gov=E.ResourceGovernor() if with_gov else None
    gate=E.SharedGate(10**7,N+50,120)
    if gov: gate.governor=gov
    raw=A.REAL_RPC(f'http://127.0.0.1:{srv.server_port}',max_calls=N+50,max_seconds=120,timeout=5,rps=10**7)
    with tempfile.TemporaryDirectory() as td:
        log=E.EvidenceLog(Path(td)/'e.jsonl'); tap=E.RpcTap(raw,log,gate=gate,worker=0)
        E.install_http_gate(gate)
        lat=[]
        try:
            for _ in range(N):
                t0=time.perf_counter(); tap.request('eth_chainId',[]); lat.append(time.perf_counter()-t0)
        finally:
            E.uninstall_http_gate(); log.close()
            if gov: gov.close()
    return lat
base=run(False); sup=run(True)
threads=len([t for t in threading.enumerate()])
def ms(x): return round(statistics.mean(x)*1000,3)
def p95(x): return round(sorted(x)[int(len(x)*0.95)]*1000,3)
print(json.dumps(dict(
    次数=N,
    无治理器_均值ms=ms(base), 无治理器_p95ms=p95(base),
    有治理器_均值ms=ms(sup),  有治理器_p95ms=p95(sup),
    每请求增量ms=round(ms(sup)-ms(base),3),
    存活线程数=threads),ensure_ascii=False))
srv.shutdown(); srv.server_close(); th.join(timeout=5)
