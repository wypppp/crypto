#!/usr/bin/env python3
"""DQ-18 退出配对比较：b50 对固定期限（10-06；预登记 过程/退出配对比较_预登记.md，提交 7e23e1b9）。

python exit_pair_d.py  → results/exit_pair_dev.json、过程/退出配对比较_结果.md
- 只用 DQ-37 开发周创建的币（first_crossings.csv 的 created_at → weeks.week_class）；检验周、范围外的行在读入时丢弃。
- 两腿同一入场（$1,400）、同一代理估值：退出池深按价格平方根从入场池状态缩放、费率用入场费率（同 analyze_d.oracle）。
  b50 腿的退出市值取 exit_marg_cap（退出状态未知时 exit_proxy_c）；固定期限腿取 c_D1～c_D180。
- 全部是代理结果，不是净现金。
"""

import csv
import heapq
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import valuation as V

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT.parent / "发射台_前期右尾评测底座_DQ-37"))
import weeks  # noqa: E402

RMB_PER_USD = 7.14
USD = 10000 / RMB_PER_USD
CHAIN_SOL = 0.005
SEED = 20261006
REPS = 1000
HORIZONS = (("D1", 1), ("D7", 7), ("D30", 30), ("D90", 90), ("D180", 180))
NUM = (
    "weight entry_x entry_y entry_fee entry_sol_usd entry_marg_cap cap5_buy_usd "
    "exit_marg_cap exit_proxy_c c_D1 c_D7 c_D30 c_D90 c_D180"
).split()


def fnum(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def ts(s):
    return datetime.fromisoformat(s[:19].replace(" ", "T")) if s else None


def proxy_mult(r, c, usd, chain_sol=CHAIN_SOL):
    """按入场池状态买入 usd 美元，在“市值 c 美元”的代理池状态卖出，返回扣两笔链上成本后的净倍数。
    代理池：x' = x·sqrt(c / 入场边际市值)，y' = x' / (c / 1e9 / SOL 美元价)；费率两边都用入场费率。"""
    if c is None or not r["entry_marg_cap"] or not r["entry_x"]:
        return None
    sol = r["entry_sol_usd"]
    tok = V.buy(r["entry_x"], r["entry_y"], usd / sol, r["entry_fee"])
    xs = r["entry_x"] * math.sqrt(c / r["entry_marg_cap"])
    ys = xs / (c / 1e9 / sol)
    proceeds = V.sell(xs, ys, tok, r["entry_fee"]) * sol
    return (proceeds - 2 * chain_sol * sol) / usd


def load():
    created = {}
    with open(ROOT / "raw" / "census" / "first_crossings.csv", newline="") as f:
        for r in csv.DictReader(f):
            created.setdefault(r["mint"], r["created_at"])
    rows, drop = [], 0
    with open(ROOT / "raw" / "d" / "valued.csv", newline="") as f:
        for r in csv.DictReader(f):
            c = created.get(r["mint"])
            # 入口过滤：不是开发周创建的行，解析当行就丢掉
            if (
                not c
                or weeks.week_class(c[:10]) != weeks.DEV
                or r["stratum"] == "V_only"
            ):
                drop += 1
                continue
            for k in NUM:
                r[k] = fnum(r.get(k))
            r["st"] = ts(r["signal_time"])
            r["et"] = ts(r.get("exit_time")) or (r["st"] + timedelta(days=180))
            rows.append(r)
    return rows, drop


def wmean(xs):
    tw = sum(w for _, w in xs)
    return sum(x * w for x, w in xs) / tw if tw else None


def wmedian(xs):
    s = sorted(xs)
    tw, acc = sum(w for _, w in s), 0.0
    for x, w in s:
        acc += w
        if acc >= tw / 2:
            return x
    return None


def cluster_ci(pairs, reps=REPS, seed=SEED):
    """按币整群有放回重抽，返回加权均值的 2.5%、97.5% 分位。pairs: [(mint, diff, w)]。"""
    by = defaultdict(list)
    for m, d, w in pairs:
        by[m].append((d, w))
    mints = sorted(by)
    rng = random.Random(seed)
    out = []
    for _ in range(reps):
        xs = []
        for m in (rng.choice(mints) for _ in mints):
            xs += by[m]
        out.append(wmean(xs))
    out.sort()
    return out[int(0.025 * reps)], out[int(0.975 * reps) - 1]


def pair_table(rows, h):
    """返回 [(mint, st, m_b50, m_h, w)]，以及缺值个数。"""
    out, miss = [], 0
    for r in rows:
        cb = r["exit_marg_cap"] if r["exit_marg_cap"] is not None else r["exit_proxy_c"]
        mb = proxy_mult(r, cb, USD)
        mh = proxy_mult(r, r["c_" + h], USD)
        if mb is None or mh is None or not r["weight"]:
            miss += 1
            continue
        out.append((r["mint"], r["st"], mb, mh, r["weight"]))
    return out, miss


def summarize(pairs):
    d = [(mb - mh, w) for _, _, mb, mh, w in pairs]
    lo, hi = cluster_ci([(m, mb - mh, w) for m, _, mb, mh, w in pairs])
    res = {
        "n": len(pairs),
        "n_mints": len(set(p[0] for p in pairs)),
        "mean_b50": wmean([(mb, w) for _, _, mb, _, w in pairs]),
        "mean_fixed": wmean([(mh, w) for _, _, _, mh, w in pairs]),
        "median_b50": wmedian([(mb, w) for _, _, mb, _, w in pairs]),
        "median_fixed": wmedian([(mh, w) for _, _, _, mh, w in pairs]),
        "diff_mean": wmean(d),
        "diff_median": wmedian(d),
        "diff_ci95": [lo, hi],
        "share_b50_better": wmean([(1.0 if x > 0 else 0.0, w) for x, w in d]),
    }
    for f in (0.02, 0.05, 0.10):
        g = [
            (math.log(1 + f * (mb - 1)) - math.log(1 + f * (mh - 1)), w)
            for _, _, mb, mh, w in pairs
        ]
        res["dlog_f%02d" % int(f * 100)] = wmean(g)
    # 集中度：每个币对加权配对差的贡献
    contrib = defaultdict(float)
    tw = sum(w for _, w in d)
    for m, _, mb, mh, w in pairs:
        contrib[m] += (mb - mh) * w / tw
    sign = 1 if res["diff_mean"] >= 0 else -1
    top = sorted(contrib.items(), key=lambda kv: -sign * kv[1])
    res["top5"] = [
        {
            "mint": m,
            "contrib": c,
            "share": c / res["diff_mean"] if res["diff_mean"] else None,
        }
        for m, c in top[:5]
    ]
    keep = set(m for m, _ in top[2:])
    rest = [(mb - mh, w) for m, _, mb, mh, w in pairs if m in keep]
    res["diff_mean_drop_top2"] = wmean(rest) if rest else None
    res["undetermined_top2"] = res["diff_mean_drop_top2"] is not None and (
        res["diff_mean_drop_top2"] >= 0
    ) != (res["diff_mean"] >= 0)
    wk = defaultdict(float)
    for _, st, mb, mh, w in pairs:
        wk[(st - timedelta(days=st.weekday())).date().isoformat()] += (mb - mh) * w / tw
    bw = max(wk.items(), key=lambda kv: sign * kv[1])
    res["best_week"] = {"week": bw[0], "contrib": bw[1]}
    return res


def account(rows, rule, frac=0.05):
    """开发周信号按时间顺序；每笔投入现金的 frac（不超过入场容量）；同一个币同一时刻只持一仓。
    rule='b50'：在 exit_time 回笼；rule='D180'：在信号后 180 天回笼。返回 (期末现金, 未平仓日后所得, 笔数)。"""
    cash, open_pos, held, n = USD, [], {}, 0
    for r in sorted(rows, key=lambda r: r["st"]):
        t = r["st"]
        while open_pos and open_pos[0][0] <= t:
            cash += heapq.heappop(open_pos)[1]
        if held.get(r["mint"], t) > t or r["cap5_buy_usd"] is None:
            continue
        usd = min(cash * frac, r["cap5_buy_usd"])
        if usd < 5:
            continue
        if rule == "b50":
            c = (
                r["exit_marg_cap"]
                if r["exit_marg_cap"] is not None
                else r["exit_proxy_c"]
            )
            xt = r["et"]
        else:
            c, xt = r["c_D180"], t + timedelta(days=180)
        m = proxy_mult(r, c, usd)
        if m is None:
            continue
        cash -= usd
        heapq.heappush(open_pos, (xt, usd * max(m, 0.0)))
        held[r["mint"]] = xt
        n += 1
    return cash, sum(p for _, p in open_pos), n


def main():
    rows, drop = load()
    out = {
        "n_rows_dev": len(rows),
        "n_dropped_at_entry": drop,
        "usd": USD,
        "chain_sol": CHAIN_SOL,
    }
    both = None
    for h, _ in HORIZONS:
        pairs, miss = pair_table(rows, h)
        out[h] = summarize(pairs)
        out[h]["n_missing"] = miss
        if h == "D180":
            both = set((p[0], p[1]) for p in pairs)
    # 账户差只用两腿都可算的信号，保证同一入场集合
    acc_rows = [r for r in rows if (r["mint"], r["st"]) in both]
    a = account(acc_rows, "b50")
    b = account(acc_rows, "D180")
    out["account_f05"] = {
        "b50": {"cash": a[0], "open": a[1], "trades": a[2]},
        "D180": {"cash": b[0], "open": b[1], "trades": b[2]},
        "diff_total_rmb": (a[0] + a[1] - b[0] - b[1]) * RMB_PER_USD,
    }
    # 对照：b50 按真实退出池状态的倍数（analyze_d.mult_for 的口径）
    real = []
    for r in rows:
        if r["entry_x"] is None or r["weight"] is None:
            continue
        if r.get("exit_x") not in ("", None):
            sol = r["entry_sol_usd"]
            tok = V.buy(r["entry_x"], r["entry_y"], USD / sol, r["entry_fee"])
            pr = V.sell(
                float(r["exit_x"]), float(r["exit_y"]), tok, float(r["exit_fee"])
            )
            m = (pr * float(r["exit_sol_usd"]) - 2 * CHAIN_SOL * sol) / USD
            real.append((m, r["weight"]))
    out["b50_real_exit_state"] = {
        "n": len(real),
        "mean": wmean(real),
        "median": wmedian(real),
    }
    (ROOT / "results" / "exit_pair_dev.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
