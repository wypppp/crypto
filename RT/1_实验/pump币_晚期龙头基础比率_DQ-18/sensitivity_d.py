"""DQ-18 敏感性（非预登记主口径，只作稳健性说明）：
09-24 复核后：上界改调 analyze_d.oracle（同币同时只持一仓、只计已平仓现金）；另报剔除 3 条未解释入场的版本。
1) 完美选币上界：不循环重放（只用 21.5 个月窗口）；只用 b50 退出（不挑固定时点）；两者同时。
2) 入场延迟 5 分钟 / 60 分钟：用该笔打印价替代 10 秒入场的边际价，b50 退出不变（零规模倍数，含两边费率）。
"""
import json
import analyze_d as A

val = A.load()
out = {}

for replay in (True, False):
    for b50 in (False, True):
        out[f"oracle_replay{replay}_b50only{b50}"] = A.oracle(val, replay=replay, b50_only=b50,
                                                              days=365.25 * 3 if replay else A.WINDOW_DAYS)

# 09-24 复核后：打印价反推 SOL 与独立 SOL 偏差 >15% 且交易内池价几乎不动的入场（原因未查明），整币剔除
UNRESOLVED = [r["mint"] for r in val if r.get("entry_sol_dev") and abs(float(r["entry_sol_dev"])) > 0.15
              and r["mint"][:8] in ("F6ExBzKd", "3Jjt8Qhb", "3S8qX1Ms")]
out["unresolved_entry_mints"] = sorted(set(UNRESOLVED))
out["oracle_most_conservative_excl_unresolved"] = A.oracle(val, replay=False, b50_only=True, days=A.WINDOW_DAYS,
                                                           exclude=frozenset(UNRESOLVED))

delay = {}
for tier in (1_000_000, 5_000_000, 20_000_000, 100_000_000):
    rs = [r for r in val if r["est"] and r["ok"] and r["tier"] == tier and r["exit_marg_cap"]]
    for lab, key in (("L10s", "entry_cap_print"), ("L5m", "e5_cap_print"), ("L60m", "e60_cap_print")):
        xs = []
        for r in rs:
            e = A.f(r.get(key))
            if e:
                xs.append(((r["exit_marg_cap"]/e)*(1-r["entry_fee"])*(1-(r["exit_fee"] or 0)), r["weight"]))
        tw = sum(w for _, w in xs)
        delay[f"{tier}_{lab}"] = {"n": len(xs), "wmean": round(sum(x*w for x, w in xs)/tw, 4) if tw else None}
out["entry_delay_b50_marginal"] = delay
json.dump(out, open("results/sensitivity.json", "w"), indent=1)
print(json.dumps(out, indent=1))
