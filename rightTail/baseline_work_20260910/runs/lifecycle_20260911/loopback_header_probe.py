"""真实 loopback 慢**响应头**场景：验证期限从发出请求之前就生效。
仅连 127.0.0.1 临时端口，不访问任何外部地址，不替换 urlopen。
"""
import sys, json, time, threading, tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import audit_flow as A
E = A.E

with tempfile.TemporaryDirectory(prefix='hdr-') as td:
    for mode in ['stop_before_headers', 'stop_during_headers', 'no_stop_control']:
        gov = E.ResourceGovernor(grace_calls=2, grace_seconds=0.15,
                                 escalate_after=0.05, force_exit_after=None,
                                 on_escalate=lambda x: None)
        samples = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if mode == 'stop_during_headers':
                    gov.request_stop('stop_during_headers')
                body = json.dumps(dict(jsonrpc='2.0', id=req['id'], result='0x1')).encode()
                # 合法但**分段慢送**的响应头：urlopen 尚未返回 response 对象
                wire = (b'HTTP/1.0 200 OK\r\nContent-Length: '
                        + str(len(body)).encode()
                        + b'\r\nX-Slow: abcdefghijklmnop\r\n\r\n')
                try:
                    for i in range(0, len(wire), 4):
                        self.wfile.write(wire[i:i + 4]); self.wfile.flush()
                        samples.append(len(gov._inflight)); time.sleep(0.025)
                    self.wfile.write(body); self.wfile.flush()
                except Exception:
                    pass

        srv = HTTPServer(('127.0.0.1', 0), H)
        th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        gate = E.SharedGate(100000, 10, 5); gate.governor = gov
        raw = A.REAL_RPC(f'http://127.0.0.1:{srv.server_port}', max_calls=10,
                         max_seconds=5, timeout=2, rps=100000)
        log = E.EvidenceLog(Path(td) / (mode + '.jsonl'))
        tap = E.RpcTap(raw, log, gate=gate, worker=0)
        E.install_http_gate(gate); t0 = time.monotonic()
        try:
            try:
                if mode == 'stop_before_headers':
                    gov.request_stop('stop_before_headers')
                    with gov.winddown():
                        res = tap.request('eth_chainId', [])
                else:
                    res = tap.request('eth_chainId', [])
            except E.Shutdown as e:
                res = 'Shutdown:' + e.reason
            except Exception as e:
                res = type(e).__name__
            el = time.monotonic() - t0; rep = gov.report()
            print(json.dumps(dict(
                mode=mode, result=res, 总耗时s=round(el, 3),
                停机后耗时s=rep['stop_latency_s'], 头分段=len(samples),
                收头期间登记数=max(samples) if samples else 0,
                升级次数=rep['escalations'],
                到点强制关闭=rep['absolute_deadline_closures']),
                ensure_ascii=False), flush=True)
        finally:
            E.uninstall_http_gate(); log.close(); gov.close()
            srv.shutdown(); srv.server_close(); th.join(timeout=5)
