#!/usr/bin/env python3
"""第 4 项：分类与成本的受控测试（离线）。"""
import sys
import pilot_measure as P

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))

print("到达阶段 → 尝试次数（依据 Probe.sell 控制流）")
CASES = [
    ("buy 任意 stage", ("buy", 0, True), 1, 0),
    ("buy 失败仍算一次 swap", ("buy", 20, True), 1, 0),
    ("sell stage10 余额不足", ("sell", 10, True), 0, 0),
    ("sell stage11 授权不足", ("sell", 11, True), 0, 2),
    ("sell stage11 且未授权", ("sell", 11, False), 0, 0),
    ("sell stage0 成功", ("sell", 0, True), 1, 2),
    ("sell stage20 revert", ("sell", 20, True), 1, 2),
]
for name, (k, st, ap), want_swap, want_appr in CASES:
    r = P.reached_attempts(k, st, ap)
    check(name, r["swap"] == want_swap and r["approve"] == want_appr,
          f"swap={r['swap']} approve={r['approve']}")

r12 = P.reached_attempts("sell", 12, True)
check("sell stage12 授权次数不可从 stage 区分 ⇒ 记区间", r12["approve"] == (1, 2),
      str(r12["approve"]))
check("stage12 未到 swap", r12["swap"] == 0)
ru = P.reached_attempts("sell", 99, True)
check("未映射 stage ⇒ 全部未知", ru["swap"] is P.UNKNOWN and ru["approve"] is P.UNKNOWN)

print("\n成本：缺 baseFeePerGas 必须记未知，不记零")
g = P.gas_cost({"swap":1,"approve":0}, {"swap":1,"approve":2}, None, 10**9)
check("入场 base fee 缺失 ⇒ 全部情景未知",
      all(v is P.UNKNOWN for v in g.values()), str(list(g.values())[:2]))
g2 = P.gas_cost({"swap":1,"approve":0}, {"swap":1,"approve":2}, 10**9, None)
check("退出 base fee 缺失 ⇒ 全部情景未知", all(v is P.UNKNOWN for v in g2.values()))

print("\n成本：授权次数不确定 ⇒ 给区间而不是取一个数")
g3 = P.gas_cost({"swap":1,"approve":0}, P.reached_attempts("sell",12,True), 10**9, 10**9)
v = g3["swap150000_tip100000000"]
check("产出 min/max 区间", isinstance(v, dict) and set(v) == {"min","max"}, str(v))
check("区间差恰为一次 approve 的成本",
      v["max"] - v["min"] == P.APPROVE_GAS * (10**9 + 10**8),
      f"差 {v['max']-v['min']}")

print("\n成本：确定情形应为单值，9 个情景齐全")
g4 = P.gas_cost({"swap":1,"approve":0}, {"swap":1,"approve":2}, 10**9, 2*10**9)
check("9 个情景", len(g4) == 9, str(len(g4)))
check("均为单值整数", all(isinstance(x, int) for x in g4.values()))
exp = (1*150_000*(10**9+10**8) + 1*150_000*(2*10**9+10**8)
       + 0*P.APPROVE_GAS*(10**9+10**8) + 2*P.APPROVE_GAS*(2*10**9+10**8))
check("主情景数值可复算", g4["swap150000_tip100000000"] == exp,
      f"{g4['swap150000_tip100000000']} vs {exp}")

print("\n未到 swap 的阶段不得计 swap 成本")
g5 = P.gas_cost({"swap":1,"approve":0}, P.reached_attempts("sell",10,True), 10**9, 10**9)
g6 = P.gas_cost({"swap":1,"approve":0}, {"swap":0,"approve":0}, 10**9, 10**9)
check("stage10 的成本 == 只有买入的成本", g5 == g6, "两者应相同")

print(f"\n通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
