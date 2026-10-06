#!/usr/bin/env python3
"""DQ-18 退出配对比较：逐笔加权回收与代理账户的差异诊断（10-06；总控第二十一轮第四节 C、GPT 批 1b C）。

python exit_pair_diag.py  → results/exit_pair_diag.json（结果写进 过程/退出配对比较_结果.md 第 8 节）
账户盈亏可以精确分解：期末合计 − 本金 ＝ Σ 投入_i ×(倍数_i − 1)。诊断四件事：
1. 层权重：逐笔均值按层权重与不加权；
2. 资金约束：935 个信号里哪些被跳过、为什么；成交的 407 笔与全部信号的倍数分布比较；
3. 集中度与未平仓：盈亏由哪些笔贡献，期末仍未平仓的部分占多少；
4. 交易顺序与仓位：把“每笔投入现金的 5%”换成“每笔固定 $70”（本金的 5%），看账户结果是否改变方向。
全部是代理结果，只用开发周创建的币。
"""

import heapq
import json
from collections import Counter

import exit_pair_d as E


def b50_c(r):
    return r["exit_marg_cap"] if r["exit_marg_cap"] is not None else r["exit_proxy_c"]


def account_trace(rows, frac=0.05, fixed=None):
    """与 exit_pair_d.account(rule='b50') 相同的规则，另记每笔与跳过原因；fixed 给定时每笔固定美元金额。"""
    cash, open_pos, held = E.USD, [], {}
    trades, skip = [], Counter()
    for r in sorted(rows, key=lambda r: r["st"]):
        t = r["st"]
        while open_pos and open_pos[0][0] <= t:
            cash += heapq.heappop(open_pos)[1]
        if held.get(r["mint"], t) > t:
            skip["同一个币仍在持有"] += 1
            continue
        if r["cap5_buy_usd"] is None:
            skip["入场容量未知"] += 1
            continue
        usd = min(fixed if fixed else cash * frac, r["cap5_buy_usd"], cash)
        if usd < 5:
            skip["可投金额 < $5"] += 1
            continue
        m = E.proxy_mult(r, b50_c(r), usd)
        if m is None:
            skip["退出市值缺失"] += 1
            continue
        cash -= usd
        heapq.heappush(open_pos, (r["et"], usd * max(m, 0.0)))
        held[r["mint"]] = r["et"]
        trades.append(
            dict(
                mint=r["mint"],
                st=r["st"],
                et=r["et"],
                usd=usd,
                m=max(m, 0.0),
                w=r["weight"],
            )
        )
    end = max(r["st"] for r in rows)
    for tr in trades:
        tr["open_at_end"] = tr["et"] > end
    return cash, sum(p for _, p in open_pos), trades, skip, end


def wmean(xs):
    tw = sum(w for _, w in xs)
    return sum(x * w for x, w in xs) / tw


def summarize_account(cash, open_v, trades):
    pnl = sum(t["usd"] * (t["m"] - 1) for t in trades)
    contrib = sorted(
        ((t["usd"] * (t["m"] - 1), t) for t in trades), key=lambda x: -x[0]
    )
    gains = [c for c, _ in contrib if c > 0]
    return dict(
        total=cash + open_v,
        pnl=pnl,
        check_identity=abs(cash + open_v - E.USD - pnl) < 1e-6,
        n_trades=len(trades),
        mean_m=sum(t["m"] for t in trades) / len(trades),
        dollar_weighted_m=sum(t["usd"] * t["m"] for t in trades)
        / sum(t["usd"] for t in trades),
        weighted_m_by_layer=wmean([(t["m"], t["w"]) for t in trades]),
        top5=[
            dict(
                mint=t["mint"],
                usd=round(t["usd"], 2),
                m=round(t["m"], 3),
                pnl=round(c, 2),
                open_at_end=t["open_at_end"],
            )
            for c, t in contrib[:5]
        ],
        pnl_without_top1=pnl - contrib[0][0],
        pnl_without_top3=pnl - sum(c for c, _ in contrib[:3]),
        gains_share_top3=sum(gains[:3]) / sum(gains) if gains else None,
        pnl_closed=sum(t["usd"] * (t["m"] - 1) for t in trades if not t["open_at_end"]),
        pnl_open=sum(t["usd"] * (t["m"] - 1) for t in trades if t["open_at_end"]),
        n_open=sum(t["open_at_end"] for t in trades),
    )


def main():
    rows, _ = E.load()
    pairs, _ = E.pair_table(rows, "D180")
    keep = set((m, st) for m, st, _, _, _ in pairs)
    rows = [r for r in rows if (r["mint"], r["st"]) in keep]
    out = {}
    # 1. 层权重
    mb = [(mb_, w) for _, _, mb_, _, w in pairs]
    strata = Counter(r["stratum"] for r in rows)
    out["per_signal"] = dict(
        n=len(pairs),
        weighted_mean=wmean(mb),
        unweighted_mean=sum(x for x, _ in mb) / len(mb),
        strata=dict(strata),
        mean_by_stratum={
            s: sum(E.proxy_mult(r, b50_c(r), E.USD) for r in rows if r["stratum"] == s)
            / n
            for s, n in strata.items()
        },
        weight_by_stratum={
            s: next(r["weight"] for r in rows if r["stratum"] == s) for s in strata
        },
    )
    # 2～3. 账户（与结果文件相同的规则）
    cash, open_v, trades, skip, end = account_trace(rows)
    out["account_f05"] = summarize_account(cash, open_v, trades)
    out["account_f05"]["skipped"] = dict(skip)
    traded = set((t["mint"], t["st"]) for t in trades)
    out["account_f05"]["mean_m_not_traded_at_1400"] = sum(
        E.proxy_mult(r, b50_c(r), E.USD)
        for r in rows
        if (r["mint"], r["st"]) not in traded
    ) / max(1, len(rows) - len(trades))
    out["account_f05"]["window_end"] = str(end)
    # 4. 固定金额
    cash2, open2, trades2, skip2, _ = account_trace(rows, fixed=0.05 * E.USD)
    out["account_fixed70"] = summarize_account(cash2, open2, trades2)
    out["account_fixed70"]["skipped"] = dict(skip2)
    (E.ROOT / "results" / "exit_pair_diag.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
