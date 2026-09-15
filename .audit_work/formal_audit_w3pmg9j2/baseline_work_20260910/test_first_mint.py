#!/usr/bin/env python3
"""首次 Mint 核验的受控测试（离线，无网络）。

覆盖验收要求的四类：
  A 空响应但链上供给非零   → 必须 log_incomplete，不得记 no_mint
  B 恰好满页               → 必须识别截断并递归收窄
  C 越界／错误身份事件      → 必须拒收
  D 正常无 Mint 的正对照    → 必须正确判 no_mint_by_cutoff
"""
import sys
import pilot_measure as P

PAIR = "0x" + "ab" * 20
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

def mk(rows, status="1"):
    return {"status": status, "message": "OK" if status == "1" else "No records found",
            "result": rows}

def ev(block, pair=PAIR, topic=None, idx="0x0"):
    """规范 Mint 事件：Mint(address indexed sender,uint256,uint256)
    ⇒ topics 恰好 2 个、data 为 2 个 uint256。旧版只造 1 个 topic 且无 data，
    在收紧校验后会被正确拒收（审查 C 指出）。"""
    return {"address": pair, "blockNumber": hex(block), "logIndex": idx,
            "topics": [topic or P.MINT_TOPIC, "0x" + "00" * 31 + "01"],
            "data": "0x" + "11" * 64,
            "transactionHash": "0x" + "11" * 32}

def run(responder, frm=1000, to=2000, supply=0, first_at=None):
    """本文件专测【日志层】。first_at 给定时构造「该块前为 0、该块起 >0」的供给，
    使首次性成立；不给则不做首次性校验（由 test_step3.py 覆盖）。"""
    P.etherscan = lambda key, **kw: responder(kw)
    sa = (lambda n: 0 if n < first_at else max(supply, 1)) if first_at else None
    return P.first_mint("K", PAIR, frm, to, supply_at_cutoff=supply, supply_at=sa)

print("A 空响应但链上供给非零")
b, st, d = run(lambda kw: mk([], "0"), supply=1000)
check("不得记 no_mint_by_cutoff", st != "no_mint_by_cutoff", f"实得 {st}")
check("记 log_incomplete", st == "log_incomplete", st)
check("留下供给证据", d["supply_at_cutoff"] == 1000)

print("\nD 正常无 Mint 的正对照（供给为零 + 空响应）")
b, st, d = run(lambda kw: mk([], "0"), supply=0)
check("正确判 no_mint_by_cutoff", st == "no_mint_by_cutoff" and b is None, st)

print("\nD2 供给为零但 status=1 返回空数组")
b, st, d = run(lambda kw: mk([]), supply=0)
check("同样判 no_mint_by_cutoff", st == "no_mint_by_cutoff", st)

print("\nC 越界／错误身份事件必须拒收")
b, st, d = run(lambda kw: mk([ev(999)]), frm=1000, to=2000, supply=0)      # 块号越界
check("块号越界被拒", b is None and st == "no_mint_by_cutoff", f"{b} / {st}")
check("拒收原因落盘", any("block_out_of_range" in str(x) for x in d["rejected"]),
      str(d["rejected"])[:60])
b, st, d = run(lambda kw: mk([ev(1500, pair="0x" + "cd" * 20)]), supply=0)  # 地址不符
check("address 不符被拒", b is None, str(b))
check("拒收原因落盘", any("address_mismatch" in str(x) for x in d["rejected"]))
b, st, d = run(lambda kw: mk([ev(1500, topic="0x" + "00" * 32)]), supply=0)  # topic 不符
check("topic0 不符被拒", b is None, str(b))
check("拒收原因落盘", any("topic0_mismatch" in str(x) for x in d["rejected"]))
b, st, d = run(lambda kw: mk([{"blockNumber": hex(1500), "logIndex": "0x0"}]), supply=0)
check("缺 address/topics 被拒", b is None, str(b))

print("\nB 恰好满页必须识别截断并递归收窄")
TRUE_FIRST = 1100
def paged(kw):
    a, b_ = int(kw["fromBlock"]), int(kw["toBlock"])
    # 1100..2999 共 1900 个事件；整段查询会满页（>=1000），必须收窄才找得到最早的
    hits = [x for x in range(TRUE_FIRST, 3000) if a <= x <= b_]
    return mk([ev(x) for x in hits][:P.LOG_PAGE])
b, st, d = run(paged, frm=1000, to=3000, supply=1000, first_at=TRUE_FIRST)
check("识别到截断", d["truncated"] is True)
check("递归收窄后仍找到真正的首个 Mint", b == TRUE_FIRST, f"实得 {b}，期望 {TRUE_FIRST}")
check("多页查询被记录", d["pages"] > 1, f"{d['pages']} 页")

print("\nB2 满页且无法再收窄（单块内 >= 1000 条）")
b, st, d = run(lambda kw: mk([ev(1500) for _ in range(P.LOG_PAGE)]), frm=1500, to=1500,
               supply=1000)
check("判 log_incomplete 而非取首条", st == "log_incomplete", st)

print("\nE 首页非升序也必须取到最早的")
b, st, d = run(lambda kw: mk([ev(1800), ev(1200), ev(1600)]), supply=1000, first_at=1200)
check("取最小块号", b == 1200, str(b))

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
