"""DQ-18 最终分析（预登记：过程/D段_口径与账户模拟_预登记.md §4；README §3.4、§3.5、§5）。

输入：raw/d/valued.csv（value_signals.py）、raw/census/first_crossings.csv、raw/census/sample_D.csv。
输出：results/summary.json 与终端表格。

- 描述量按层权重（S100、S20 权重 1；S5、S1 为层大小/抽中数）；验证专用币（V_only）不参与估计。
- 第二层倍数：mult_1400（$1,400 按入场池状态买、按退出池状态卖，含两边费率；链上固定成本另计）。
  入场或退出状态未知：入场未知 → 不可参与；退出未知 → 用代理（exit_is_proxy），单列。
- 全买账户：分层插补蒙特卡洛 1,000 次；f = 2%/5%/10%；链上成本 0.002/0.005/0.01 SOL/笔。
- 完美选币上界：只用样本；k = 2/3/10/100 取最好；退出规则在 b50 与固定时点中事后取最好（固定时点按路径价 + 费率 + 按池深缩放的冲击，代理）。
- 三年：窗口按原顺序循环重放至 36 个月。
"""
import csv
import json
import math
import heapq
import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import valuation as V

ROOT = Path(__file__).resolve().parent
RMB_PER_USD = 7.14
START_USD = 10000 / RMB_PER_USD
TARGET_USD = 1_000_000 / RMB_PER_USD
W0, W1 = datetime(2024, 6, 1), datetime(2026, 3, 15)
import os
REPS = int(os.environ.get("DQ18_REPS", "1000"))
WINDOW_DAYS = (W1 - W0).days


def f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def ts(s):
    return datetime.fromisoformat(s[:19].replace(" ", "T")) if s else None


def half(d):
    return f"{d.year}H{1 if d.month <= 6 else 2}"


def load():
    val = list(csv.DictReader(open(ROOT / "raw" / "d" / "valued.csv")))
    for r in val:
        r["tier"] = int(r["tier"])
        r["weight"] = f(r["weight"]) or 0.0
        r["st"] = ts(r["signal_time"])
        for k in ("mult_1400", "mult_marginal", "cap5_buy_usd", "cap5_sell_usd", "entry_x", "entry_y", "exit_x",
                  "exit_y", "entry_fee", "exit_fee", "entry_sol_usd", "exit_sol_usd", "entry_marg_cap",
                  "exit_marg_cap", "max_cap", "c_D1", "c_D7", "c_D30", "c_D90", "c_D180", "cross_hour_vwap"):
            r[k] = f(r.get(k))
        r["et"] = ts(r.get("exit_time")) or (r["st"] + timedelta(days=180))
        r["est"] = r["stratum"] != "V_only"
        r["ok"] = r["entry_x"] is not None and (r["mult_1400"] is not None or r["mult_marginal"] is not None)
    return val


def mult_for(r, usd, chain_sol):
    """投入 usd 美元的净倍数（含费、冲击；链上固定成本两笔）。"""
    if r["entry_x"] is None:
        return None
    sol_e = r["entry_sol_usd"]
    q = usd / sol_e
    tok = V.buy(r["entry_x"], r["entry_y"], q, r["entry_fee"])
    if r["exit_x"] is not None:
        proceeds = V.sell(r["exit_x"], r["exit_y"], tok, r["exit_fee"]) * r["exit_sol_usd"]
    elif r["mult_marginal"] is not None:
        proceeds = usd * r["mult_marginal"]
    else:
        return None
    cost = 2 * chain_sol * sol_e
    return (proceeds - cost) / usd


def wstats(rows, key):
    xs = [(r[key], r["weight"]) for r in rows if r[key] is not None]
    if not xs:
        return {}
    tw = sum(w for _, w in xs)
    mean = sum(x * w for x, w in xs) / tw
    s = sorted(xs)
    acc, med = 0.0, None
    for x, w in s:
        acc += w
        if acc >= tw / 2:
            med = x
            break
    share = lambda t: sum(w for x, w in xs if x >= t) / tw
    return {"n": len(xs), "weighted_n": round(tw, 1), "mean": round(mean, 4), "median": round(med, 4),
            "share_ge3": round(share(3), 5), "share_ge10": round(share(10), 5), "share_ge100": round(share(100), 6)}


def describe(val):
    est = [r for r in val if r["est"]]
    out = {}
    years = WINDOW_DAYS / 365.25
    for tier in (1_000_000, 5_000_000, 20_000_000, 100_000_000):
        rs = [r for r in est if r["tier"] == tier]
        tw = sum(r["weight"] for r in rs)
        known = [r for r in rs if r["ok"]]
        for r in known:
            r["m1400"] = r["mult_1400"] if r["mult_1400"] is not None else r["mult_marginal"]
            r["entry_over_thr"] = (r["entry_marg_cap"] or 0) / tier
            for h in ("D1", "D7", "D30", "D90", "D180"):
                c = r["c_" + h]
                r["L1_" + h] = c / r["entry_marg_cap"] if c and r["entry_marg_cap"] else None
            r["L1_max"] = r["max_cap"] / r["entry_marg_cap"] if r["max_cap"] and r["entry_marg_cap"] else None
        both = [r for r in known if r["cap5_buy_usd"] is not None]
        big = lambda m: sum(r["weight"] for r in both if (r["m1400"] or 0) >= m and r["cap5_buy_usd"] >= 1400)
        # 单次命中：投入 min(1400, 入场容量)，净收益 ≥10 万 / ≥100 万元
        hit = {100_000: 0.0, 1_000_000: 0.0}
        for r in both:
            usd = min(1400.0, r["cap5_buy_usd"])
            m = mult_for(r, usd, 0.005)
            if m is None:
                continue
            gain_rmb = usd * (m - 1) * RMB_PER_USD
            for t in hit:
                if gain_rmb >= t:
                    hit[t] += r["weight"]
        conc = sorted(((r["m1400"] or 0) * r["weight"], r) for r in known)[::-1]
        tot = sum(x for x, _ in conc) or 1
        out[str(tier)] = {
            "signals_weighted": round(tw, 1), "per_year": round(tw / years, 1),
            "valued_share": round(sum(r["weight"] for r in known) / tw, 4) if tw else None,
            "exit_proxy_share": round(sum(r["weight"] for r in known if r["mult_1400"] is None) / max(1e-9, sum(r["weight"] for r in known)), 4),
            "L2_b50_1400": wstats(known, "m1400"),
            **{"L1_" + h: wstats(known, "L1_" + h) for h in ("D1", "D7", "D30", "D90", "D180", "max")},
            "zero_D30_share": round(sum(r["weight"] for r in known if (r["L1_D30"] or 0) <= 0.1) / max(1e-9, sum(r["weight"] for r in known)), 4),
            "zero_D180_share": round(sum(r["weight"] for r in known if (r["L1_D180"] or 0) <= 0.1) / max(1e-9, sum(r["weight"] for r in known)), 4),
            "per_year_ge10_cap1400": round(big(10) / years, 2), "per_year_ge3_cap1400": round(big(3) / years, 2),
            "per_year_ge100_cap1400": round(big(100) / years, 2),
            "per_year_single_hit_ge100k_rmb": round(hit[100_000] / years, 2),
            "per_year_single_hit_ge1m_rmb": round(hit[1_000_000] / years, 2),
            "top_contrib_share": {str(n): round(sum(x for x, _ in conc[:n]) / tot, 4) for n in (1, 3, 5)},
            "entry_over_threshold_median": round(sorted(r["entry_over_thr"] for r in known)[len(known) // 2], 3) if known else None,
            "by_half": {h: wstats([r for r in known if half(r["st"]) == h], "m1400")
                        for h in sorted({half(r["st"]) for r in known})},
        }
    return out


def donors(val):
    d = defaultdict(list)
    for r in val:
        if r["est"] and r["stratum"] in ("S5", "S1") and r["ok"]:
            d[(r["stratum"], r["tier"], half(r["st"]))].append(r)
    return d


def frame_opps(val):
    """普查帧里窗口内全部信号：抽中的用自身，S5/S1 未抽中的记为待插补。"""
    sample = {r["mint"]: r for r in csv.DictReader(open(ROOT / "raw" / "census" / "sample_D.csv"))}
    by_key = {(r["mint"], r["tier"], r["signal_time"][:19]): r for r in val}
    top = defaultdict(int)
    fr = [r for r in csv.DictReader(open(ROOT / "raw" / "census" / "first_crossings.csv"))
          if "2024-06-01" <= r["hour_start"][:10] <= "2026-03-15"]
    for r in fr:
        top[r["mint"]] = max(top[r["mint"]], int(r["threshold_usd"]))
    strat = {100_000_000: "S100", 20_000_000: "S20", 5_000_000: "S5", 1_000_000: "S1"}
    opps = []
    for r in fr:
        k = (r["mint"], int(r["threshold_usd"]), r["signal_time"][:19])
        own = by_key.get(k)
        s = sample.get(r["mint"])
        use_own = own is not None and s is not None and s["stratum"] != "V_only"
        opps.append({"st": ts(r["signal_time"]), "tier": k[1], "stratum": strat[top[r["mint"]]],
                     "own": own if use_own else None})
    return sorted(opps, key=lambda o: o["st"])


def simulate(opps, dn, frac, chain_sol, rng, cycles_days=365.25 * 3):
    """全买账户：按时间顺序；每笔投入 min(现金×frac, 入场容量)；退出时回笼。循环重放到 36 个月。"""
    cash = START_USD
    open_pos = []  # (exit_time, proceeds)
    end = W0 + timedelta(days=cycles_days)
    shift = timedelta(days=WINDOW_DAYS)
    k = 0
    n_trades = 0
    while True:
        for o in opps:
            t = o["st"] + shift * k
            if t >= end:
                break
            while open_pos and open_pos[0][0] <= t:
                cash += heapq.heappop(open_pos)[1]
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
            n_trades += 1
        else:
            k += 1
            if W0 + shift * k >= end:
                break
            continue
        break
    for _, p in open_pos:
        cash += p
    return cash, n_trades


def oracle(val, chain_sol=0.005):
    """完美选币上界（只用样本）：事后只买 k 倍以上的机会，退出在 b50 与固定时点中取最好。"""
    rows = [r for r in val if r["est"] and r["ok"] and r["cap5_buy_usd"] is not None]

    def best_mult(r, usd):
        cands = []
        m = mult_for(r, usd, chain_sol)
        if m is not None:
            cands.append((m, r["et"]))
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
    for k in (2, 3, 10, 100):
        cash, open_pos, trades = START_USD, [], 0
        end = W0 + timedelta(days=365.25 * 3)
        shift = timedelta(days=WINDOW_DAYS)
        cyc = 0
        opps = sorted(rows, key=lambda r: r["st"])
        while W0 + shift * cyc < end:
            for r in opps:
                t = r["st"] + shift * cyc
                if t >= end:
                    break
                while open_pos and open_pos[0][0] <= t:
                    cash += heapq.heappop(open_pos)[1]
                usd = min(cash, r["cap5_buy_usd"])
                if usd < 5:
                    continue
                m, xt = best_mult(r, usd)
                if m is None or m < k:
                    continue
                cash -= usd
                heapq.heappush(open_pos, (xt + shift * cyc, usd * m))
                trades += 1
            cyc += 1
        final = cash + sum(p for _, p in open_pos)
        res = {"k": k, "final_usd": round(final), "net_gain_rmb": round((final - START_USD) * RMB_PER_USD), "trades": trades}
        if best is None or final > best["final_usd"]:
            best = res
    return best


def main():
    val = load()
    summary = {"describe": describe(val)}
    dn = donors(val)
    opps = frame_opps(val)
    rng = random.Random(20260924)
    acc = {}
    for frac in (0.02, 0.05, 0.10):
        for chain in (0.002, 0.005, 0.01):
            finals = sorted(simulate(opps, dn, frac, chain, rng)[0] for _ in range(REPS))
            q = lambda p: round((finals[int(p * (len(finals) - 1))] - START_USD) * RMB_PER_USD)
            acc[f"f{frac}_c{chain}"] = {"p10_gain_rmb": q(0.1), "p50_gain_rmb": q(0.5), "p90_gain_rmb": q(0.9),
                                        "share_gain_pos": round(sum(x > START_USD for x in finals) / len(finals), 3)}
    summary["all_buy_account_3y"] = acc
    summary["oracle_3y_sample_lower_bound_of_bound"] = oracle(val)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(summary, indent=1, ensure_ascii=False, default=str)[:6000])


if __name__ == "__main__":
    main()
