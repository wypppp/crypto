"""交替 A/B 测每请求开销：同一轮内逐次切换治理器开关，消掉机器漂移。
另外直接数**创建过的线程数**——那是结构事实，不受噪声影响。
"""
import sys, json, time, threading, tempfile, statistics
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import audit_flow as A
E = A.E


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *a): pass
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        b = json.dumps(dict(jsonrpc='2.0', id=req['id'], result='0x1')).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)


srv = HTTPServer(('127.0.0.1', 0), H)
th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
N = 300
created = {'n': 0}
_orig_start = threading.Thread.start
def counting_start(self, *a, **kw):
    created['n'] += 1
    return _orig_start(self, *a, **kw)

def make(with_gov):
    gov = E.ResourceGovernor() if with_gov else None
    gate = E.SharedGate(10**7, N + 50, 300)
    if gov: gate.governor = gov
    raw = A.REAL_RPC(f'http://127.0.0.1:{srv.server_port}', max_calls=N + 50,
                     max_seconds=300, timeout=5, rps=10**7)
    td = tempfile.mkdtemp()
    log = E.EvidenceLog(Path(td) / 'e.jsonl')
    return gov, gate, E.RpcTap(raw, log, gate=gate, worker=0), log

gov_on, gate_on, tap_on, log_on = make(True)
gov_off, gate_off, tap_off, log_off = make(False)
on, off = [], []
threading.Thread.start = counting_start
try:
    for i in range(N):
        # 交替：相邻两次的机器状态最接近，漂移基本抵消
        E.install_http_gate(gate_on)
        t0 = time.perf_counter(); tap_on.request('eth_chainId', []); on.append(time.perf_counter() - t0)
        E.uninstall_http_gate()
        before = created['n']
        E.install_http_gate(gate_off)
        t0 = time.perf_counter(); tap_off.request('eth_chainId', []); off.append(time.perf_counter() - t0)
        E.uninstall_http_gate()
finally:
    threading.Thread.start = _orig_start
    log_on.close(); log_off.close(); gov_on.close()
pairs = [a - b for a, b in zip(on, off)]           # 逐对之差
def ms(x): return round(statistics.mean(x) * 1000, 3)
print(json.dumps(dict(
    次数=N,
    有治理器_均值ms=ms(on), 无治理器_均值ms=ms(off),
    逐对差_均值ms=ms(pairs),
    逐对差_中位数ms=round(statistics.median(pairs) * 1000, 3),
    逐对差_标准差ms=round(statistics.stdev(pairs) * 1000, 3),
    测量期间创建的线程总数=created['n'],
    说明="创建线程数应为 0：监督不再为每个请求开线程"), ensure_ascii=False))
srv.shutdown(); srv.server_close(); th.join(timeout=5)
