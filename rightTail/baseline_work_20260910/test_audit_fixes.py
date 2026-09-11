#!/usr/bin/env python3
"""针对审查方 13 个反例的回归测试 —— 断言【修复后】行为。

复用其 reproduce.py 的受控 flow()（见 audit_flow.py），
但断言的是修复后应有的结果，而不是 bug 存在。
"""
import json, sys, tempfile
from pathlib import Path
import audit_flow as A
import evidence as E
import pilot_measure as P

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

def tmp():
    return Path(tempfile.mkdtemp())

print("1 线程失败不得判成功")
d = tmp(); rc, doc, rows, _ = A.flow(d, "wc", parallel=2, worker_crash=True)
a = doc["acceptance"]
check("退出码非零", rc != 0, str(rc))
check("集合不完整被标出", a["set_complete"] is False and a["missing_candidates"], str(a["missing_candidates"]))
check("worker 异常被记录", len(a["worker_errors"]) > 0, str(a["worker_errors"])[:70])
check("validation_passed=False", a["validation_passed"] is False)

print("\n2 预算耗尽同样阻断")
d = tmp(); rc, doc, rows, _ = A.flow(d, "bc", parallel=2, max_calls=100)
check("退出码非零", rc != 0, str(rc))
# v1.17 改写：旧断言“缺失候选被列出”依赖的是一个副作用 —— 旧版恢复复读里
# BudgetExhausted 没被捕获，worker 直接崩掉，候选连结果都没有，才落进 missing。
# 审核要求“预算耗尽保持自己的原因”，所以候选现在有结果、状态 budget_exhausted。
# 本意（阻断）不变，改为更严的判定：两个候选都未完成、都不在完成集合里、原因各自保留。
_acc2 = doc["acceptance"]
_blocked2 = set(_acc2["missing_candidates"]) | set(_acc2.get("incomplete") or [])
check("两个候选均被列为未完成", _blocked2 == {1, 2}, str(sorted(_blocked2)))
check("未完成的原因是预算耗尽（不是崩溃、不是状态不符）",
      sorted(r["state"] for r in doc["results"]) == ["budget_exhausted"] * 2
      and not _acc2["worker_errors"],
      str([(r["index"], r["state"]) for r in doc["results"]]))

print("\n3 并行请求归属：区块请求必须属于本 worker")
d = tmp(); rc, doc, rows, inst = A.flow(d, "par", parallel=2)
unowned = [r for r in rows if r["kind"] == "rpc" and r.get("worker") is not None
           and r.get("candidate") is None]
check("无候选归属的 worker 请求为 0", len(unowned) == 0, f"{len(unowned)} 条")
actual = sum(len(x.records) for x in inst)
check("汇总 RPC 数与底层实际一致", doc["rpc_calls"] == actual,
      f"报告 {doc['rpc_calls']} vs 实际 {actual}")

print("\n4 pending_id 全局唯一")
keys = [(r.get("run_id"), r.get("pending_id"), r.get("worker"))
        for r in rows if r["kind"] == "rpc_begin"]
check("无重复标识", len(keys) == len(set(keys)), f"{len(keys)-len(set(keys))} 个重复")

print("\n5 续跑绑定覆盖运行期参数")
d = tmp(); ck = d/"shared.ck"
A.flow(d, "a", checkpoint=ck, slot_limit=2)
try:
    rc, doc, rows, _ = A.flow(d, "b", checkpoint=ck, slot_limit=0)
    check("slot_limit 改变后拒绝复用", False, f"未拒绝，exit={rc}")
except SystemExit as e:
    check("slot_limit 改变后拒绝复用", "绑定不符" in str(e), str(e)[:70])

print("\n6 正确的无 Mint 分支必须可完成")
d = tmp(); rc, doc, rows, _ = A.flow(d, "nm", no_mint=True)
st = [r["state"] for r in doc["results"]]
vp = [r["validation_passed"] for r in doc["results"]]
check("状态为 no_mint_by_cutoff", set(st) == {"no_mint_by_cutoff"}, str(st))
check("validation_passed 为 True", all(vp), str(vp))
check("退出码 0", rc == 0, str(rc))

print("\n7 检查点半行不得丢失已完成记录")
d = tmp(); ck = d/"p.ck"
A.flow(d, "x", checkpoint=ck)
before = sorted(E.Checkpoint(ck).completed())
with open(ck, "a", encoding="utf-8") as f:
    f.write('{"kind":"attempt","candidate":9')      # 半行
after = sorted(E.Checkpoint(ck).completed())
check("重开后已完成记录仍在", before == after and before, f"{before} → {after}")
check("半行被隔离", Path(str(ck) + ".orphan").exists())

print("\n8 begin 无配对 end ⇒ 证据不完整")
d = tmp(); A.flow(d, "y")
ev = d/"y.jsonl"
lines = ev.read_text(encoding="utf-8").splitlines()
inject = json.dumps({"seq": 99999, "run_id": json.loads(lines[0])["run_id"],
                     "kind": "rpc_begin", "pending_id": 987654, "worker": None})
ev.write_text("\n".join(lines[:-1] + [inject, lines[-1]]) + "\n", encoding="utf-8")
recs, diag = E.read_evidence(str(ev), report=True)
check("complete=False", diag["complete"] is False, str(diag["complete"]))
check("列出未配对的 begin", bool(diag["unmatched_rpc_begin"]), str(diag["unmatched_rpc_begin"])[:60])

print("\n9 结果 JSON 也必须脱敏")
d = tmp(); rc, doc, rows, _ = A.flow(d, "red", scan_error=True)
summary = (d/"red.json").read_text(encoding="utf-8")
check("假凭据不出现在结果 JSON", "FAKE_ONLY_SCAN_KEY" not in summary)
check("也不出现在证据 JSONL", "FAKE_ONLY_SCAN_KEY" not in (d/"red.jsonl").read_text(encoding="utf-8"))

print("\n10 未执行的一腿不得抹掉已知买入成本")
g = P.gas_cost({"swap": 1, "approve": 0}, {"swap": 0, "approve": 0}, 10**9, None)
check("买入成本仍为已知整数", all(isinstance(v, int) and v > 0 for v in g.values()),
      str(list(g.values())[:2]))

print("\n11 畸形 Mint 事件必须拒收")
BAD = [("两侧金额都为 0", {"data": "0x" + "00"*64}),
       ("data 非十六进制", {"data": "0x" + "zz"*64}),
       ("sender topic 高位非零", {"topics": [P.MINT_TOPIC, "0x" + "ff"*32]})]
base = {"address": A.PAIR, "blockNumber": hex(A.MINT), "logIndex": "0x0",
        "topics": [P.MINT_TOPIC, "0x" + "00"*31 + "01"], "data": "0x" + "11"*64,
        "transactionHash": "0x" + "22"*32}
for name, over in BAD:
    r = dict(base); r.update(over)
    why = P._validate_log(r, A.PAIR, A.MINT - 100, A.MINT + 100)
    check(f"{name} 被拒", why is not None, str(why))

print("\n12 底层重试不得超出共享预算（在真实 HTTP 边界上验证）")
# 旧断言测的是"预留两次额度"这套做法本身，属于实现细节；
# 审查要求的是：**每一次真实 HTTP**（含 V.RPC 内部对 503 的重试）都过闸门。
# 因此改成：原包真实 RPC + 真实 urlopen 边界，只把传输换成受控实现。
import time as _t12
import urllib.error as _ue12

REAL_RPC = A.REAL_RPC
_d12 = tmp()

_gate12 = E.SharedGate(rps=1, max_calls=1, max_seconds=60)   # 只允许 1 次真实 HTTP
_raw12 = REAL_RPC("https://offline.invalid", max_calls=10, max_seconds=10, rps=10**6)
_log12 = E.EvidenceLog(_d12 / "budget12.jsonl")
_tap12 = E.RpcTap(_raw12, _log12, gate=_gate12, worker=0)
_sent12 = []


def _t12transport(*a, **kw):
    _sent12.append(_t12.monotonic())
    raise _ue12.HTTPError("https://offline.invalid", 503, "mock", {}, None)


E.install_http_gate(_gate12, transport=_t12transport)
try:
    _tap12.request("eth_chainId", [])
    _outcome12 = "no-raise"
except E.BudgetExhausted as e:
    _outcome12 = f"budget:{e}"
except Exception as e:                                        # noqa: BLE001
    _outcome12 = f"{type(e).__name__}: {e}"
finally:
    E.uninstall_http_gate()
    _log12.close()
check("重试那一次 HTTP 被预算拦下（只发出 1 次）", len(_sent12) == 1,
      f"实际发出 {len(_sent12)} 次")
check("拦截发生在预算层", _outcome12.startswith("budget:"), _outcome12)
check("实际发出次数等于传输实际执行次数", _gate12.sent == len(_sent12),
      f"sent={_gate12.sent} 传输={len(_sent12)}")
check("预留不超过上限", _gate12.reserved <= _gate12.max_calls,
      f"{_gate12.reserved} / {_gate12.max_calls}")
# 闸门拒绝的请求并未发出，证据里不得留下无配对的 begin
_r12, _diag12 = E.read_evidence(_d12 / "budget12.jsonl", report=True)
check("被拒的请求仍写了配对的 rpc_end", not _diag12["unmatched_rpc_begin"],
      str(_diag12["unmatched_rpc_begin"]))

print("\n12b 底层重试必须同样受全局限流约束")
# 反例原状：闸门要求 10s 间隔，两次真实 HTTP 却相隔 1.0s（V.RPC 自己 sleep(1) 后重试）
_gate12b = E.SharedGate(rps=0.5, max_calls=10, max_seconds=60)   # 间隔 2s > V.RPC 的 1s
_raw12b = REAL_RPC("https://offline.invalid", max_calls=10, max_seconds=30, rps=10**6)
_log12b = E.EvidenceLog(_d12 / "budget12b.jsonl")
_tap12b = E.RpcTap(_raw12b, _log12b, gate=_gate12b, worker=0)
_at12b = []


class _Ok12b:
    def __init__(self, rid): self.rid = rid
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=None):
        return json.dumps({"jsonrpc": "2.0", "id": self.rid,
                           "result": "0x1"}).encode()


def _t12btransport(req, *a, **kw):
    _at12b.append(_t12.monotonic())
    if len(_at12b) == 1:
        raise _ue12.HTTPError("https://offline.invalid", 503, "mock", {}, None)
    # 回显请求里的 id，否则包内 validate_envelope 会判信封不匹配
    return _Ok12b(json.loads(req.data.decode())["id"])


E.install_http_gate(_gate12b, transport=_t12btransport)
try:
    _res12b = _tap12b.request("eth_chainId", [])
finally:
    E.uninstall_http_gate()
    _log12b.close()
_gap12b = (_at12b[1] - _at12b[0]) if len(_at12b) == 2 else None
check("两次真实 HTTP 都发生", len(_at12b) == 2, str(len(_at12b)))
check("重试也按全局间隔排队（≥ interval）",
      _gap12b is not None and _gap12b >= _gate12b.interval - 0.05,
      f"间隔 {_gap12b:.2f}s，要求 {_gate12b.interval}s" if _gap12b else "只发出一次")
check("两次 HTTP 都计入实际发出次数", _gate12b.sent == 2, str(_gate12b.sent))
check("实际发出与传输执行次数一致", _gate12b.sent == len(_at12b),
      f"sent={_gate12b.sent} 传输={len(_at12b)}")
check("逻辑请求仍只算一次", _gate12b.logical == 1, str(_gate12b.logical))

print("\n13 时间预算耗尽后不得放行")
import time as _t
gate2 = E.SharedGate(rps=20, max_calls=10**6, max_seconds=0.01)
_t.sleep(0.05)
try:
    gate2.acquire(0)
    check("超时后拒绝", False, "未拒绝")
except RuntimeError as e:
    check("超时后拒绝", "time budget" in str(e), str(e))

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
