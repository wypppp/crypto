"""DQ-18 敏感性（非预登记主口径，只作稳健性说明）：
1) 完美选币上界：不循环重放（只用 21.5 个月窗口）；只用 b50 退出（不挑固定时点）；两者同时。
2) 入场延迟 5 分钟 / 60 分钟：用该笔打印价替代 10 秒入场的边际价，b50 退出不变（零规模倍数，含两边费率）。
"""
import json, math, heapq
from datetime import timedelta
import analyze_d as A

val = A.load()
out = {}

def oracle_variant(replay, b50_only, chain_sol=0.005):
    rows = sorted([r for r in val if r["est"] and r["ok"] and r["cap5_buy_usd"] is not None], key=lambda r: r["st"])
    best = None
    for k in (2, 3, 10, 100):
        cash, pos, trades = A.START_USD, [], 0
        end = A.W0 + timedelta(days=365.25 * 3 if replay else A.WINDOW_DAYS)
        shift = timedelta(days=A.WINDOW_DAYS); cyc = 0
        while A.W0 + shift * cyc < end:
            for r in rows:
                t = r["st"] + shift * cyc
                if t >= end: break
                while pos and pos[0][0] <= t: cash += heapq.heappop(pos)[1]
                usd = min(cash, r["cap5_buy_usd"])
                if usd < 5: continue
                cands = []
                m = A.mult_for(r, usd, chain_sol)
                if m is not None: cands.append((m, r["et"]))
                if not b50_only:
                    for h, d in (("D1",1),("D7",7),("D30",30),("D90",90),("D180",180)):
                        c = r["c_"+h]
                        if c and r["entry_marg_cap"] and r["entry_x"]:
                            xs = r["entry_x"]*math.sqrt(c/r["entry_marg_cap"]); ys = xs/(c/1e9/r["entry_sol_usd"])
                            tok = A.V.buy(r["entry_x"], r["entry_y"], usd/r["entry_sol_usd"], r["entry_fee"])
                            pr = A.V.sell(xs, ys, tok, r["entry_fee"])*r["entry_sol_usd"]
                            cands.append(((pr-2*chain_sol*r["entry_sol_usd"])/usd, r["st"]+timedelta(days=d)))
                if not cands: continue
                m, xt = max(cands)
                if m < k: continue
                cash -= usd; heapq.heappush(pos, (xt + shift*cyc, usd*m)); trades += 1
            cyc += 1
        final = cash + sum(p for _, p in pos)
        res = {"k": k, "net_gain_rmb": round((final - A.START_USD)*A.RMB_PER_USD), "trades": trades}
        if best is None or res["net_gain_rmb"] > best["net_gain_rmb"]: best = res
    return best

for replay in (True, False):
    for b50 in (False, True):
        out[f"oracle_replay{replay}_b50only{b50}"] = oracle_variant(replay, b50)

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
