"""审查方 reproduce_retry.py 的对照版本 —— 唯一区别：闸门真的装在 HTTP 边界上。

原件用 patch.object(V.urllib.request, 'urlopen') 把 urlopen 整个换掉，
而修复正是在这一层包住 urlopen；换掉它等于把闸门一起换掉，
所以原件在修复后仍会"复现"，且它自己的输出就写明了实际发出计数为 0
（闸门一次都没被调用）。

这里把受控传输通过 install_http_gate(..., transport=...) 装在**闸门之下**，
其余完全一致：同一个真实 RPC 类、同一个 RpcTap/SharedGate、同样的 503 重试。
"""
import os, sys, json, tempfile, time, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import audit_flow as A
E = A.E

with tempfile.TemporaryDirectory() as td:
    raw = A.REAL_RPC('https://offline.invalid', max_calls=10, max_seconds=10, rps=1000000)
    log = E.EvidenceLog(Path(td) / 'e.jsonl')
    gate = E.SharedGate(0.1, 2, 30)          # 与原件一致：间隔 10 秒，预算 2
    tap = E.RpcTap(raw, log, gate=gate, worker=0)
    starts = []

    class Response:
        def __init__(self, rid): self.rid = rid
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, *a):
            return json.dumps(dict(jsonrpc='2.0', id=self.rid, result='0x1')).encode()

    def transport(req, *a, **kw):
        starts.append(time.monotonic() - gate.started)
        if len(starts) == 1:
            raise urllib.error.HTTPError('https://offline.invalid', 503, 'mock', {}, None)
        return Response(json.loads(req.data.decode())['id'])

    E.install_http_gate(gate, transport=transport)
    try:
        result = tap.request('eth_chainId', [])
    finally:
        E.uninstall_http_gate()
        log.close()

    gap = starts[1] - starts[0]
    report = dict(required_http_interval_seconds=gate.interval,
                  http_start_seconds=starts,
                  observed_gap_seconds=round(gap, 3),
                  retry_respected_global_interval=gap >= gate.interval - 0.05,
                  result=result, gate=gate.stats())
    print(json.dumps(report, ensure_ascii=False))
    # 每次复跑写**新文件**，不覆盖既有测量。
    # 旧版固定写回 retry_gated.json，复跑会把交付时的原始测量冲掉（审查 v1.5 附注）。
    # 只写到显式指定的输出目录；未指定就不落盘。不往交付目录里写任何东西。
    _out_dir = os.environ.get('RT_PROBE_OUT')
    if _out_dir:
        stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        Path(_out_dir).mkdir(parents=True, exist_ok=True)
        out = Path(_out_dir) / f'retry_gated.{stamp}.json'
        out.write_text(json.dumps(report, indent=2))
        print(f'-> {out}')
    assert len(starts) == 2, '两次真实 HTTP 都应发生'
    assert gap >= gate.interval - 0.05, f'重试未按全局间隔排队：{gap:.2f}s < {gate.interval}s'
    assert gate.sent == 2, f'两次 HTTP 都应计入实际发出次数，实际 {gate.sent}'
    print('OK: 重试经过全局限流，且计入实际 HTTP 次数')
