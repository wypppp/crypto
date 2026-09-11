#!/usr/bin/env python3
"""第 3 项审查（A–F）的受控反例测试，全部离线。"""
import sys
import pilot_measure as P

PAIR = "0x" + "ab" * 20
TOKEN = "0x" + "cd" * 20
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

def ev(block, *, pair=PAIR, topic=None, idx="0x0", removed=False,
       topics_n=2, data_words=2, tx=True):
    tp = [topic or P.MINT_TOPIC, "0x" + "00"*31 + "01"][:topics_n]
    r = {"address": pair, "blockNumber": hex(block), "logIndex": idx, "topics": tp,
         "data": "0x" + "11" * (32 * data_words)}
    if tx: r["transactionHash"] = "0x" + "22" * 32
    if removed: r["removed"] = True
    return r

def run(responder, frm=1000, to=3000, supply=1000, supply_at=None):
    P.etherscan = lambda key, **kw: responder(kw)
    return P.first_mint("K", PAIR, frm, to, supply_at_cutoff=supply, supply_at=supply_at)

print("A 截止供给非零不证明找到的是首次 Mint")
# 真正首次在 1200（该块前供给为 0）；只返回后续的 1800
b, st, d = run(lambda kw: {"status":"1","result":[ev(1800)]},
               supply_at=lambda n: 0 if n < 1200 else 5000)
check("漏掉真正首次 ⇒ 判 not_first_mint", st == "not_first_mint" and b is None, f"{b}/{st}")
check("留下前后供给证据", d["supply_before"] == 5000 and d["supply_at_block"] == 5000,
      f"before={d['supply_before']} at={d['supply_at_block']}")
b, st, d = run(lambda kw: {"status":"1","result":[ev(1200)]},
               supply_at=lambda n: 0 if n < 1200 else 5000)
check("正确的首次 Mint 通过（前 0、当块 >0）", st == "ok" and b == 1200, f"{b}/{st}")

print("\nB 满页递归必须查右半区间")
P.LOG_PAGE = 2
asked = []
def paged(kw):
    a, b_ = int(kw["fromBlock"]), int(kw["toBlock"])
    asked.append((a, b_))
    hits = [x for x in (2800, 2801, 2802) if a <= x <= b_]
    return {"status":"1","result":[ev(x) for x in hits][:P.LOG_PAGE]}
b, st, d = run(paged, supply_at=lambda n: 0 if n < 2800 else 7000)
check("找到右半区间的 2800", b == 2800 and st == "ok", f"{b}/{st}")
check("确实查询了右半区间", any(a > 2000 for a, _ in asked), str(asked))
P.LOG_PAGE = 1000

print("\nC 事件规范性")
for name, kw_ in (("removed=True", dict(removed=True)),
                  ("只有 1 个 topic", dict(topics_n=1)),
                  ("data 长度不符", dict(data_words=1)),
                  ("缺 transactionHash", dict(tx=False)),
                  ("缺 logIndex", dict(idx=None))):
    b, st, d = run(lambda kw, k=kw_: {"status":"1","result":[ev(1500, **k)]}, supply=0)
    check(f"{name} 被拒收", b is None and st == "no_mint_by_cutoff", f"{b}/{st}")
    check(f"{name} 拒收原因落盘", bool(d["rejected"]), str(d["rejected"])[:50])

print("\nC2 有日志但截止供给为零 = 矛盾")
b, st, d = run(lambda kw: {"status":"1","result":[ev(1500)]}, supply=0)
check("判 state_contradiction", st == "state_contradiction", st)

print("\nE 块结构与时间包围必须能阻断")
class FakeRpc: pass
def mkblk(mapping):
    return lambda n, fresh=False: mapping[n]
good = {100: {"number": hex(100), "hash": "0x"+"aa"*32, "parentHash": "0x"+"bb"*32,
              "timestamp": hex(2000)},
        99:  {"number": hex(99), "hash": "0x"+"bb"*32, "parentHash": "0x"+"cc"*32,
              "timestamp": hex(1900)}}
s1 = P.snapshot_block(FakeRpc(), mkblk(good), 100)
check("正常块无失败项", not s1["failures"], str(s1["failures"]))
bad = {100: dict(good[100], parentHash="0x"+"ff"*32), 99: good[99]}
s2 = P.snapshot_block(FakeRpc(), mkblk(bad), 100)
check("父链接断裂被记为失败", any("parent link" in f for f in s2["failures"]), str(s2["failures"]))
s3 = P.snapshot_block(FakeRpc(), mkblk(good), 100, bracket_target=1950)
check("时间包围成立时通过", not s3["failures"], str(s3["failures"]))
s4 = P.snapshot_block(FakeRpc(), mkblk(good), 100, bracket_target=1899)
check("目标早于前块 ⇒ 未包围，失败", any("bracketed" in f for f in s4["failures"]))
s5 = P.snapshot_block(FakeRpc(), mkblk(good), 100, bracket_target=2500)
check("目标晚于当块 ⇒ 未包围，失败", any("bracketed" in f for f in s5["failures"]))
s6 = P.snapshot_block(FakeRpc(), mkblk({100: dict(good[100], hash="0xzz"), 99: good[99]}), 100)
check("hash 格式不合法被记为失败", any("bad hash" in f for f in s6["failures"]), str(s6["failures"]))

print("\nD 防重组：fresh 复读必须发新请求")
calls = []
def blk_counting(n, fresh=False):
    calls.append((n, fresh))
    h = "0x" + ("aa" if not fresh else "99") * 32       # 第二次返回不同 hash
    return {"number": hex(n), "hash": h, "parentHash": "0x"+"bb"*32, "timestamp": hex(2000)}
first = blk_counting(100)["hash"]
second = blk_counting(100, fresh=True)["hash"]
check("fresh 调用被单独记录", calls == [(100, False), (100, True)], str(calls))
check("第二次返回不同 hash ⇒ 可检出重组", first != second)

print("\nG 建池与首次 Mint 同块：block-1 上合约不存在，供给按定义为 0")
SAME = 24188628
calls = []
def supply_same_block(n):
    calls.append(n)
    return 0 if n < SAME else 10**20        # 建池前无代码 ⇒ 定义为 0
b, st, d = run(lambda kw: {"status":"1","result":[ev(SAME)]},
               frm=SAME, to=SAME+100, supply=10**20, supply_at=supply_same_block)
check("同块建池+首铸 判 ok", st == "ok" and b == SAME, f"{b}/{st}")
check("确实查了 block-1", SAME - 1 in calls, str(calls))
check("before=0 被记录", d["supply_before"] == 0, str(d["supply_before"]))

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
