"""两项：①不信任测试证书时，校验必须照样失败（没有削弱正常 HTTPS 校验）；
②DNS 阶段没有可打断句柄 —— 核实它实际由什么兜底、上界是多少。
仅本机 127.0.0.1；DNS 阻塞用替换 getaddrinfo 模拟（真实解析器无法可控地卡住）。
"""
import os, sys, json, time, socket, ssl, threading, tempfile, subprocess, os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
ROOT = Path(os.environ.get('RT_CODE_ROOT', str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))
import audit_flow as A
E = A.E
CERT, KEY = sys.argv[1], sys.argv[2]

# ① 证书校验：服务端用测试证书，客户端**不**信任它
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(CERT, KEY)
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        b = json.dumps(dict(jsonrpc='2.0', id=req['id'], result='0x1')).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)
srv = HTTPServer(('127.0.0.1', 0), H)
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
gov = E.ResourceGovernor(force_exit_after=None)
gate = E.SharedGate(100000, 10, 10); gate.governor = gov
raw = A.REAL_RPC(f'https://127.0.0.1:{srv.server_port}', max_calls=10, max_seconds=10,
                 timeout=3, rps=100000)
log = E.EvidenceLog(Path(tempfile.mkdtemp()) / 'e.jsonl')
tap = E.RpcTap(raw, log, gate=gate, worker=0)
E.install_http_gate(gate)
try:
    try:
        r = tap.request('eth_chainId', []); verdict = 'ACCEPTED_UNTRUSTED_CERT'
    except Exception as e:
        r = f"{type(e).__name__}: {str(e)[:90]}"
        verdict = 'REJECTED' if 'CERTIFICATE_VERIFY_FAILED' in str(e) or 'certificate' in str(e).lower() else 'OTHER'
finally:
    E.uninstall_http_gate(); log.close(); gov.close()
srv.shutdown(); srv.server_close()
print(json.dumps(dict(项='不信任测试证书时的校验', 判定=verdict, 细节=r,
                      残留登记=gov.pending_inflight()), ensure_ascii=False), flush=True)

# ② DNS：子进程里模拟 getaddrinfo 卡住，看是否在途登记、是否被升级兜底带走
code = r'''
import sys, time, socket, os, json, tempfile
from pathlib import Path
sys.path.insert(0, %r)
import audit_flow as A
E = A.E
def slow_dns(*a, **kw):
    time.sleep(30)            # 不可中断的解析
    raise OSError('never')
socket.getaddrinfo = slow_dns
gov = E.ResourceGovernor(grace_seconds=0.1, escalate_after=0.1, force_exit_after=0.1)
gate = E.SharedGate(100000, 10, 60); gate.governor = gov
raw = A.REAL_RPC('http://dns-stall.invalid:80', max_calls=10, max_seconds=60, timeout=30, rps=100000)
log = E.EvidenceLog(Path(tempfile.mkdtemp()) / 'e.jsonl')
tap = E.RpcTap(raw, log, gate=gate, worker=0)
E.install_http_gate(gate)
import threading
def sampler():
    time.sleep(0.05)
    os.write(1, ('INFLIGHT_DURING_DNS=%%d\n' %% gov.pending_inflight()).encode())
    gov.request_stop('stop_during_dns')
threading.Thread(target=sampler, daemon=True).start()
T0 = time.monotonic()
try:
    tap.request('eth_chainId', [])
except Exception as e:
    os.write(1, ('RETURNED %%s\n' %% type(e).__name__).encode())
os.write(1, b'NO_FORCED_EXIT\n'); sys.exit(9)
''' % str(ROOT)
t0 = time.monotonic()
p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
wall = time.monotonic() - t0
inflight = next((l.split('=')[1] for l in p.stdout.splitlines() if l.startswith('INFLIGHT_DURING_DNS=')), '?')
print(json.dumps(dict(项='DNS 阶段（getaddrinfo 卡 30s）', 退出码=p.returncode,
                      DNS期间在途登记=inflight,
                      子进程总耗时s=round(wall, 3),
                      理论上界s='停机于0.05s + grace 0.1 + escalate 0.1 + force_exit 0.1 ≈ 0.35（另含解释器启动）',
                      未被强制退出='NO_FORCED_EXIT' in p.stdout), ensure_ascii=False), flush=True)
