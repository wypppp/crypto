#!/usr/bin/env python3
"""DQ-43 D：自动化行为代理的事前标签（10-13，WM2 v5 §6）。先在合成数据上实现与测试。

四条判据（识别“高频、早买、高费”的行为，不是真实的机器人数量；分别报，也报并集；都不满足的记“未覆盖”，不等于人工）：
1. 单个 UTC 日买入 ≥50 个不同的币；
2. 有 ≥20 个币完成了往返（首买到首卖），各币持有时长的中位数 ≤60 秒；
3. 一半以上的首次买入在创建或建池后 2 个 slot 内；
4. 优先费加小费的中位，在全体买家的第 90 百分位以上（全体分位只在允许域、形成期内计算）。
事前标签：截至 as_of，只用 as_of 之前已经成熟的历史——买入与卖出都早于 as_of 的往返才算持有时长；
之后的行为不影响 as_of 的标签。事后画像＝把 as_of 设为观察窗终点，只用于描述生态（T8）。
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Act:
    entity: str
    coin: str
    ts: float
    side: str  # buy / sell
    slot_after_open: int  # 距创建（曲线）或建池（毕业后）的 slot 数
    fee: int  # 优先费＋小费，lamports


def _pctl(xs, q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("inf")
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def labels(acts, as_of: float) -> dict:
    """{实体: {'c1','c2','c3','c4' 各 bool, 'any': bool}}，只用 ts < as_of 的行为。"""
    hist = [a for a in acts if a.ts < as_of]
    by_ent = defaultdict(list)
    for a in hist:
        by_ent[a.entity].append(a)
    fee_med = {
        e: statistics.median([a.fee for a in v if a.side == "buy"])
        for e, v in by_ent.items()
        if any(a.side == "buy" for a in v)
    }
    p90 = _pctl(list(fee_med.values()), 0.9)
    out = {}
    for e, v in by_ent.items():
        eb = [a for a in v if a.side == "buy"]
        days = defaultdict(set)
        for a in eb:
            days[int(a.ts // 86400)].add(a.coin)
        c1 = any(len(s) >= 50 for s in days.values())
        holds = defaultdict(list)
        first_buy, first_sell = {}, {}
        for a in sorted(v, key=lambda a: a.ts):
            if a.side == "buy":
                first_buy.setdefault(a.coin, a)
            elif a.coin in first_buy:
                first_sell.setdefault(a.coin, a)
        for coin, b in first_buy.items():
            if coin in first_sell:  # 往返已在 as_of 之前完成
                holds[coin].append(first_sell[coin].ts - b.ts)
        c2 = (
            len(holds) >= 20
            and statistics.median([statistics.median(h) for h in holds.values()]) <= 60
        )
        c3 = bool(first_buy) and sum(
            1 for b in first_buy.values() if b.slot_after_open <= 2
        ) * 2 > len(first_buy)
        c4 = e in fee_med and fee_med[e] >= p90
        out[e] = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "any": c1 or c2 or c3 or c4}
    return out
