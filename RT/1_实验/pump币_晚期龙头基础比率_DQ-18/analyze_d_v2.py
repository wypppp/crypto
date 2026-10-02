"""DQ-18 analyze_d.py 的 simulate、oracle 修正版（代码审计 10-03 第 5 处）。原 analyze_d.py 不改。

第 5 处：两个函数只在“下一次机会到来时”释放到期回款，循环结束后没有处理截止前已经到期的仓位，
于是期末现金偏低、“未平仓”偏高；完美选币上界只计已平仓现金，因而被压低（审计的反例里上界甚至选择不交易）。
v2 在返回前把退出时刻 ≤ 截止的仓位计入现金，只有退出时刻在截止之后的才算未平仓。其余逐字照抄原版。
DQ-18 重开之前用本模块替换原函数重算 F111 ⑥⑦（总控第十轮第 6 条）；现在只修代码、不重跑。
"""

import heapq
import math
from collections import defaultdict
from datetime import timedelta

import valuation as V
from analyze_d import RMB_PER_USD, START_USD, W0, WINDOW_DAYS, half, mult_for


def simulate(opps, dn, frac, chain_sol, rng, start=W0, days=365.25 * 3, replay=True):
    """全买账户：按时间顺序；每笔投入 min(现金×frac, 入场容量)；退出时回笼；同币同时只持一仓。
    replay=True 时循环重放到 start+days。返回（期末现金, 期末未平仓的日后卖出所得, 笔数）。"""
    cash = START_USD
    open_pos = []  # (exit_time, proceeds)
    held = {}  # mint -> 退出时间
    end = start + timedelta(days=days)
    shift = timedelta(days=WINDOW_DAYS)
    k = 0
    n_trades = 0
    while True:
        for o in opps:
            t = o["st"] + shift * k
            if t < start:
                continue
            if t >= end:
                break
            while open_pos and open_pos[0][0] <= t:
                cash += heapq.heappop(open_pos)[1]
            if held.get(o["mint"], t) > t:
                continue
            r = o["own"]
            if r is None:
                pool = dn.get((o["stratum"], o["tier"], half(o["st"])))
                if not pool:
                    continue
                r = rng.choice(pool)
            if r is None or not r["ok"] or r["cap5_buy_usd"] is None:
                continue
            usd = min(cash * frac, r["cap5_buy_usd"])
            if usd < 5:
                continue
            m = mult_for(r, usd, chain_sol)
            if m is None:
                continue
            cash -= usd
            hold = (r["et"] - r["st"]) if r["et"] and r["st"] else timedelta(days=180)
            heapq.heappush(open_pos, (t + hold, usd * max(m, 0.0)))
            held[o["mint"]] = t + hold
            n_trades += 1
        k += 1
        if not replay or W0 + shift * k >= end:
            break
    while open_pos and open_pos[0][0] <= end:  # v2（审计第 5 处）：截止前已到期的回款计入现金
        cash += heapq.heappop(open_pos)[1]
    return cash, sum(p for _, p in open_pos), n_trades


def oracle(val, chain_sol=0.005, replay=True, b50_only=False, start=W0, days=365.25 * 3, exclude=frozenset()):
    """完美选币上界（只用样本）：事后只买 k 倍以上的机会，退出在 b50 与固定时点中取最好；同币同时只持一仓。
    报告只计已平仓现金的净收益（未平仓单列），并给出路径上贡献最大的 3 个币。"""
    rows = sorted([r for r in val if r["est"] and r["ok"] and r["cap5_buy_usd"] is not None
                   and r["mint"] not in exclude], key=lambda r: r["st"])

    def best_mult(r, usd):
        cands = []
        m = mult_for(r, usd, chain_sol)
        if m is not None:
            cands.append((m, r["et"]))
        if b50_only:
            return max(cands) if cands else (None, None)
        for h, d in (("D1", 1), ("D7", 7), ("D30", 30), ("D90", 90), ("D180", 180)):
            c = r["c_" + h]
            if c and r["entry_marg_cap"] and r["entry_x"]:
                # 固定时点代理：池深按价格平方根缩放
                xs = r["entry_x"] * math.sqrt(c / r["entry_marg_cap"])
                ys = xs / (c / 1e9 / r["entry_sol_usd"])
                q = usd / r["entry_sol_usd"]
                tok = V.buy(r["entry_x"], r["entry_y"], q, r["entry_fee"])
                proceeds = V.sell(xs, ys, tok, r["entry_fee"]) * r["entry_sol_usd"]
                cands.append(((proceeds - 2 * chain_sol * r["entry_sol_usd"]) / usd, r["st"] + timedelta(days=d)))
        return max(cands) if cands else (None, None)

    best = None
    end = start + timedelta(days=days)
    shift = timedelta(days=WINDOW_DAYS)
    for k in (2, 3, 10, 100):
        cash, open_pos, held, gains, trades, cyc = START_USD, [], {}, defaultdict(float), 0, 0
        while True:
            for r in rows:
                t = r["st"] + shift * cyc
                if t < start:
                    continue
                if t >= end:
                    break
                while open_pos and open_pos[0][0] <= t:
                    cash += heapq.heappop(open_pos)[1]
                if held.get(r["mint"], t) > t:
                    continue
                usd = min(cash, r["cap5_buy_usd"])
                if usd < 5:
                    continue
                m, xt = best_mult(r, usd)
                if m is None or m < k:
                    continue
                cash -= usd
                heapq.heappush(open_pos, (xt + shift * cyc, usd * m))
                held[r["mint"]] = xt + shift * cyc
                gains[r["mint"]] += usd * (m - 1)
                trades += 1
            cyc += 1
            if not replay or W0 + shift * cyc >= end:
                break
        while open_pos and open_pos[0][0] <= end:  # v2（审计第 5 处）：截止前已到期的回款计入现金
            cash += heapq.heappop(open_pos)[1]
        open_usd = sum(p for _, p in open_pos)
        tot = sum(g for g in gains.values() if g > 0) or 1
        top = sorted(gains.items(), key=lambda kv: -kv[1])[:3]
        res = {"k": k, "net_gain_rmb": round((cash - START_USD) * RMB_PER_USD),
               "open_at_end_rmb": round(open_usd * RMB_PER_USD), "trades": trades,
               "top3": [{"mint": mt, "share_of_gains": round(g / tot, 4)} for mt, g in top]}
        if best is None or res["net_gain_rmb"] > best["net_gain_rmb"]:
            best = res
    return best
