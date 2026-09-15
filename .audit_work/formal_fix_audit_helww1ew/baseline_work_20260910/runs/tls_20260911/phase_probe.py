"""逐阶段实测停机上界：DNS / TCP 建连 / TLS 握手 / TLS 响应体。
仅本机 127.0.0.1；客户端**证书校验保持开启**（通过 SSL_CERT_FILE 信任测试证书）。
用法：SSL_CERT_FILE=<cert.pem> python3 phase_probe.py <cert.pem> <key.pem>
"""
import os, sys, json, time, socket, ssl, threading, tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
# RT_CODE_ROOT：被测代码所在目录（反向验证时指向旧快照）
sys.path.insert(0, os.environ.get('RT_CODE_ROOT', str(Path(__file__).resolve().parents[2])))
import audit_flow as A
E = A.E
CERT, KEY = sys.argv[1], sys.argv[2]
GRACE = 0.15


def run_rpc(url, gov, stop_before=False, timeout=3):
    gate = E.SharedGate(100000, 10, 10); gate.governor = gov
    raw = A.REAL_RPC(url, max_calls=10, max_seconds=10, timeout=timeout, rps=100000)
    td = tempfile.mkdtemp()
    log = E.EvidenceLog(Path(td) / 'e.jsonl')
    tap = E.RpcTap(raw, log, gate=gate, worker=0)
    E.install_http_gate(gate)
    t0 = time.monotonic()
    try:
        try:
            if stop_before:
                gov.request_stop('stop_before')
                with gov.winddown():
                    r = tap.request('eth_chainId', [])
            else:
                r = tap.request('eth_chainId', [])
        except E.Shutdown as e:
            r = 'Shutdown:' + e.reason + f"({e.detail.get('phase', e.detail.get('layer'))})"
        except Exception as e:
            r = f"{type(e).__name__}: {str(e)[:70]}"
    finally:
        E.uninstall_http_gate(); log.close()
    return r, time.monotonic() - t0


def gov_new():
    return E.ResourceGovernor(grace_calls=4, grace_seconds=GRACE, escalate_after=5,
                              force_exit_after=None)


out = []
def emit(**kw):
    out.append(kw); print(json.dumps(kw, ensure_ascii=False), flush=True)

# A. TLS 握手卡住：TCP 接受后不回应握手；在握手中停机
L = socket.socket(); L.bind(('127.0.0.1', 0)); L.listen(4)
gA = gov_new(); samples = []
def stall_tls():
    c, _ = L.accept()
    gA.request_stop('stop_during_tls')
    for _ in range(40):
        samples.append(gA.pending_inflight()); time.sleep(0.02)
    c.close()
threading.Thread(target=stall_tls, daemon=True).start()
r, el = run_rpc(f'https://127.0.0.1:{L.getsockname()[1]}', gA)
emit(阶段='TLS 握手（握手中停机）', 结果=r, 停机后耗时s=gA.report()['stop_latency_s'],
     期限s=GRACE, 握手期间登记数=max(samples) if samples else 0)
L.close(); gA.close()

# B. TCP 建连卡住：backlog 满，SYN 被丢
L2 = socket.socket(); L2.bind(('127.0.0.1', 0)); L2.listen(0)
fill = []
for _ in range(8):
    s = socket.socket(); s.setblocking(False)
    try: s.connect(L2.getsockname())
    except BlockingIOError: pass
    fill.append(s)
time.sleep(0.1)
gB = gov_new()
threading.Timer(0.1, lambda: gB.request_stop('stop_during_connect')).start()
r, el = run_rpc(f'http://127.0.0.1:{L2.getsockname()[1]}', gB, timeout=3)
emit(阶段='TCP 建连（建连中停机）', 结果=r, 停机后耗时s=gB.report()['stop_latency_s'],
     期限s=GRACE, socket_timeout_s=3)
for s in fill: s.close()
L2.close(); gB.close()

# C/D. 真实 TLS 服务（证书校验开启）的慢响应体
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(CERT, KEY)
class Slow(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        b = json.dumps(dict(jsonrpc='2.0', id=req['id'], result='0x1')).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(b))); self.end_headers()
        try:
            for i in range(0, len(b), 4):
                self.wfile.write(b[i:i + 4]); self.wfile.flush(); time.sleep(0.035)
        except Exception: pass
srv = HTTPServer(('127.0.0.1', 0), Slow)
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
url = f'https://127.0.0.1:{srv.server_port}'
gC = gov_new()
r, el = run_rpc(url, gC, stop_before=True)
emit(阶段='TLS 慢响应体（停机后发起）', 结果=r, 停机后耗时s=gC.report()['stop_latency_s'], 期限s=GRACE)
gC.close()
gD = gov_new()
r, el = run_rpc(url, gD)
emit(阶段='TLS 慢响应体（未停机对照，证书校验开启）', 结果=r, 耗时s=round(el, 3),
     在途登记残留=gD.pending_inflight())
gD.close()
srv.shutdown(); srv.server_close()
# 只写到**显式指定**的输出目录；未指定就不落盘（结果已逐行打印到 stdout）。
# 旧版固定写回自身旁边的 phase_probe.json —— 跑一次测试就覆盖一次交付件，
# 审核复跑时实际发生过（audit_v114_20260911）。
_out_dir = os.environ.get('RT_PROBE_OUT')
if _out_dir:
    Path(_out_dir).mkdir(parents=True, exist_ok=True)
    (Path(_out_dir) / 'phase_probe.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2))
