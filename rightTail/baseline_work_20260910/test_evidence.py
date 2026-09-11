#!/usr/bin/env python3
"""证据层受控测试：中断可读、hash 拒绝、增量落盘、资源计量。"""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
import evidence as E

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    (globals().__setitem__('ok', ok+1) if cond else globals().__setitem__('fail', fail+1))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

d = Path(tempfile.mkdtemp())

# T1 增量落盘：每条写完立即可被另一进程读到
log = E.EvidenceLog(d/"e1.jsonl")
log.write("run_header", note="x")
for i in range(3):
    log.write("candidate_start", candidate=i)
    mid, _ = E.read_evidence(d/"e1.jsonl")
    if i == 1:
        check("写入即可被独立读取（无需 close）", len(mid) == 3, f"读到 {len(mid)} 条")
log.close()
recs, trunc = E.read_evidence(d/"e1.jsonl")
check("记录条数与写入一致", len(recs) == 4 and trunc == 0, f"{len(recs)} 条 / 截断 {trunc}")
check("每条带 seq/run_id/kind/at", all({"seq","run_id","kind","at"} <= set(r) for r in recs))
check("seq 严格递增", [r["seq"] for r in recs] == list(range(1, 5)))

# T2 硬中断（SIGKILL）后证据仍可读
script = d/"writer.py"
script.write_text(f"""
import sys, time
sys.path.insert(0, {str(Path.cwd())!r})
import evidence as E
log = E.EvidenceLog({str(d/'e2.jsonl')!r})
log.write("run_header", note="before work")
i = 0
while True:
    log.write("rpc", candidate=i, stage="loop", record={{"id": i}})
    i += 1
    time.sleep(0.05)
""", encoding="utf-8")
p = subprocess.Popen([sys.executable, str(script)])
time.sleep(1.2)
os.kill(p.pid, signal.SIGKILL)
p.wait()
recs2, trunc2 = E.read_evidence(d/"e2.jsonl")
check("SIGKILL 后证据文件仍可读", len(recs2) >= 3, f"读到 {len(recs2)} 条，截断 {trunc2} 行")
check("运行头在工作记录之前", recs2[0]["kind"] == "run_header")
check("被杀前的请求记录全部在盘上",
      all(r["kind"] == "rpc" for r in recs2[1:]) and recs2[-1]["record"]["id"] == len(recs2)-2,
      f"最后一条 id={recs2[-1].get('record',{}).get('id')}")

# T3 台账 hash 不符必须拒绝
uni = d/"u.csv"; uni.write_text("index,pair\n1,0xa\n", encoding="utf-8")
log3 = E.EvidenceLog(d/"e3.jsonl")
try:
    E.run_header(log3, script=__file__, spec=__file__, sample=__file__, universe=uni,
                 declared_universe_sha="0"*64, chain_id=1, snapshot={}, params={})
    check("台账 hash 不符时拒绝", False, "未拒绝")
except SystemExit as e:
    check("台账 hash 不符时拒绝", "拒绝复用" in str(e))
r3, _ = E.read_evidence(d/"e3.jsonl")
check("拒绝前仍留下运行头证据", r3 and r3[0]["kind"] == "run_header"
      and r3[0]["universe_match"] is False)
log3.close()

# T4 台账 hash 相符则放行
log4 = E.EvidenceLog(d/"e4.jsonl")
E.run_header(log4, script=__file__, spec=__file__, sample=__file__, universe=uni,
             declared_universe_sha=E.sha256_file(uni), chain_id=1,
             snapshot={"number": 1}, params={"k": "v"})
r4, _ = E.read_evidence(d/"e4.jsonl")
check("hash 相符放行且记录 chain_id/快照/参数",
      r4[0]["universe_match"] and r4[0]["chain_id"] == 1 and r4[0]["params"] == {"k": "v"})
log4.close()

# T5 资源计量
log5 = E.EvidenceLog(d/"e5.jsonl"); log5.resource(candidate=7, stage="s"); log5.close()
r5, _ = E.read_evidence(d/"e5.jsonl")
check("资源记录含 RSS 与 CPU", r5[0]["rss_kb"] and r5[0]["cpu_s"] is not None,
      f"rss={r5[0]['rss_kb']}kB cpu={r5[0]['cpu_s']}s")

# T6 半行截断（模拟写到一半断电）必须被跳过而不是整文件不可读
log6 = E.EvidenceLog(d/"e6.jsonl")
log6.write("run_header", note="a"); log6.write("rpc", candidate=1); log6.close()
with open(d/"e6.jsonl", "a", encoding="utf-8") as f:
    f.write('{"seq": 3, "kind": "rpc", "record": {"id"')      # 故意半行
r6, t6 = E.read_evidence(d/"e6.jsonl")
check("半行截断被跳过，前面记录仍可读", len(r6) == 2 and t6 == 1, f"{len(r6)} 条 / 截断 {t6} 行")
log6.close()

# ── 第二轮审查的修复 ──────────────────────────────────────────────
# T7 截断尾部被隔离，新运行头不再被吞
f7 = d/"e7.jsonl"
l = E.EvidenceLog(f7); l.write("run_header", run=1); l.close()
open(f7, "a", encoding="utf-8").write('{"seq":2,"kind":"rpc","rec')     # 半行
l = E.EvidenceLog(f7); l.write("run_header", run=2); l.write("rpc", x=1); l.close()
r7, diag7 = E.read_evidence(f7, report=True)
hdrs = [x for x in r7 if x["kind"] == "run_header"]
check("截断后新运行头不再丢失", len(hdrs) == 2, f"{len(hdrs)} 个运行头")
check("半行被隔离到 .orphan", (Path(str(f7)+".orphan")).exists()
      and (Path(str(f7)+".orphan")).read_bytes() == b'{"seq":2,"kind":"rpc","rec')
check("隔离动作本身留证据", any(x["kind"] == "orphan_recovered" for x in r7))
check("无残留坏行", not diag7["bad_lines"], str(diag7["bad_lines"]))

# T8 中间损坏与尾部截断必须区分
f8 = d/"e8.jsonl"
l = E.EvidenceLog(f8); l.write("run_header"); l.write("rpc", i=1); l.write("run_footer"); l.close()
t8 = f8.read_text().splitlines(); f8.write_text(t8[0]+"\nBROKEN\n"+t8[1]+"\n"+t8[2]+"\n")
_, d8 = E.read_evidence(f8, report=True)
check("中间损坏被识别为 mid_file_corruption", d8["mid_file_corruption"] is True)
check("且不被当作尾部截断", d8["tail_truncation_only"] is False)
check("整体判定为不完整", d8["complete"] is False)

f8b = d/"e8b.jsonl"
l = E.EvidenceLog(f8b); l.write("run_header"); l.write("run_footer"); l.close()
open(f8b, "a", encoding="utf-8").write('{"seq":3,"partial')
_, d8b = E.read_evidence(f8b, report=True)
check("纯尾部截断标记为 tail_truncation_only", d8b["tail_truncation_only"] is True
      and d8b["mid_file_corruption"] is False)

# T9 缺结束记录 / seq 不连续必须暴露
f9 = d/"e9.jsonl"
l = E.EvidenceLog(f9); l.write("run_header"); l.write("rpc"); l.close()      # 无 footer
_, d9 = E.read_evidence(f9, report=True)
check("缺 run_footer 被列出", d9["runs_without_footer"] and not d9["runs_with_footer"])
check("缺 footer ⇒ 不完整", d9["complete"] is False)

# T10 规格缺失必须阻断
u10 = d/"u10.csv"; u10.write_text("a\n", encoding="utf-8")
l10 = E.EvidenceLog(d/"e10.jsonl")
try:
    E.run_header(l10, script=Path("evidence.py").resolve(), spec="NO_SUCH_SPEC.md",
                 sample=Path("evidence.py").resolve(), universe=u10,
                 declared_universe_sha=E.sha256_file(u10), chain_id=1, snapshot={}, params={})
    check("规格缺失时阻断", False, "未阻断")
except SystemExit as e:
    check("规格缺失时阻断", "规格文件缺失" in str(e))
r10, _ = E.read_evidence(d/"e10.jsonl")
check("阻断前留下 abort 证据", r10 and r10[0]["kind"] == "abort"
      and r10[0]["reason"] == "spec_missing")
l10.close()

# T11 统一脱敏：任意字段与异常串
SEC = "SECRETKEY_ABCDEF0123456789"
l11 = E.EvidenceLog(d/"e11.jsonl", secrets={SEC})
l11.write("etherscan", error=f"URLError: <urlopen error {SEC}>", params={"k": "v"})
l11.write("rpc", record={"nested": {"deep": f"...{SEC}..."}})
l11.close()
blob = (d/"e11.jsonl").read_text(encoding="utf-8")
check("异常串中的凭据被脱敏", SEC not in blob and "<redacted>" in blob)
check("嵌套字段中的凭据也被脱敏", blob.count("<redacted>") >= 2)

# T12 被杀在请求中：只有 begin 没有 end ⇒ 结果未知
f12 = d/"e12.jsonl"
class _Boom:
    records = []
    def request(self, m, p): raise KeyboardInterrupt("killed mid-retry")
l12 = E.EvidenceLog(f12)
tap = E.RpcTap(_Boom(), l12)
tap.mark(candidate=9, stage="entry_buy")
try:
    tap.request("eth_call", [])
except KeyboardInterrupt:
    pass
l12.close()
r12, _ = E.read_evidence(f12)
begins = [x for x in r12 if x["kind"] == "rpc_begin"]
ends = [x for x in r12 if x["kind"] == "rpc_end"]
check("请求前已写 begin", len(begins) == 1 and begins[0]["candidate"] == 9)
check("begin 有配对 end（finally 保证）", len(ends) == 1)
f12b = d/"e12b.jsonl"
l12b = E.EvidenceLog(f12b); tap2 = E.RpcTap(_Boom(), l12b)
tap2._begin("request", {"method": "eth_call"})      # 模拟写完 begin 即被 SIGKILL
l12b.close()
r12b, _ = E.read_evidence(f12b)
unmatched = ([x["pending_id"] for x in r12b if x["kind"] == "rpc_begin"]
             != [x["pending_id"] for x in r12b if x["kind"] == "rpc_end"])
check("只有 begin 无 end ⇒ 可判定为结果未知", unmatched)

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
