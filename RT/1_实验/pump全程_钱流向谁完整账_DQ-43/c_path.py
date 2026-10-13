#!/usr/bin/env python3
"""DQ-43 C：路径解剖的价格构造、触发与截至时刻特征（10-13，WM2 v5 §5）。先在合成数据上实现与测试。

价格构造（冻结前写死，GPT C07）：
- 只用名义额 ≥0.01 SOL 的成交（F110 尘埃成交会造成伪穿越）；
- 同一 slot 内按交易序、外层指令序、内层指令序排序（排序键必须唯一）；
- 每 5 秒按 SOL 成交额加权的均价（Σsol ÷ Σtok）；空桶沿用前值并标记 filled；
- 毕业后的成交价由调用方按有效报价储备给出（本模块只做聚合）；
- 之字形在对数价格上：从运行最高价下跌 δ 记一次“顶”确认；从运行最低价回升到 1/(1−δ) 倍记一次“底”确认。
触发只在完整的 5 秒桶结束之后判定；“前一波”只用触发时已确认的顶。
结果窗不完整（触发后 7 天超出观察窗或止日）记“未成熟”，不删、不当作没涨。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DUST_LAMPORTS = 10_000_000  # 0.01 SOL
BUCKET_S = 5


@dataclass(frozen=True)
class Trade:
    ts: float  # epoch 秒
    slot: int
    tx: int
    outer: int
    inner: int
    sol: int  # lamports
    tok: int


def ordered(trades):
    keys = [(t.slot, t.tx, t.outer, t.inner) for t in trades]
    if len(set(keys)) != len(keys):
        raise ValueError("排序键不唯一")
    return sorted(trades, key=lambda t: (t.slot, t.tx, t.outer, t.inner))


def buckets(
    trades, t0: float, t_end: float, size: int = BUCKET_S, min_sol: int = DUST_LAMPORTS
):
    """[(桶序号, 桶结束时刻, 价格或 None, filled)]。只覆盖 [t0, t_end) 内的完整桶。"""
    n = int((t_end - t0) // size)
    agg = [[0, 0] for _ in range(n)]
    for t in ordered(trades):
        if t.sol < min_sol or t.tok <= 0:
            continue
        i = int((t.ts - t0) // size)
        if 0 <= i < n:
            agg[i][0] += t.sol
            agg[i][1] += t.tok
    out, last = [], None
    for i, (s, q) in enumerate(agg):
        if q:
            last = s / q
            out.append((i, t0 + (i + 1) * size, last, False))
        else:
            out.append((i, t0 + (i + 1) * size, last, last is not None))
    return out


def zigzag(prices, delta: float):
    """对数价格上的之字形。返回确认列表 [(确认时的序号, 'peak'|'trough', 极值所在序号, 极值价格)]。"""
    up = -math.log(1 - delta)  # 回升到 1/(1−δ) 倍
    down = math.log(1 - delta)  # 跌到 (1−δ) 倍
    out = []
    mode = None  # None：还没有方向；'up'：在找顶；'down'：在找底
    hi_i = lo_i = None
    for i, p in enumerate(prices):
        if p is None:
            continue
        lp = math.log(p)
        if hi_i is None:
            hi_i = lo_i = i
            hi = lo = lp
            continue
        if lp > hi:
            hi, hi_i = lp, i
        if lp < lo:
            lo, lo_i = lp, i
        if mode in (None, "up") and lp - hi <= down:
            out.append((i, "peak", hi_i, math.exp(hi)))
            mode, lo, lo_i = "down", lp, i
        elif mode in (None, "down") and lp - lo >= up:
            out.append((i, "trough", lo_i, math.exp(lo)))
            mode, hi, hi_i = "up", lp, i
    return out


def pullback_trigger(series, delta: float, mult: float = 2.0):
    """候选进场点 3：此前已涨到起点的 mult 倍以上，且第一次从运行最高价回撤 δ。
    series 是 buckets() 的输出；判定只在桶结束时做，返回触发桶的序号与时刻（在该时刻之后才能下单）。"""
    p0 = next((p for _, _, p, _ in series if p is not None), None)
    if p0 is None:
        return None
    run_max = 0.0
    for i, t_end, p, _ in series:
        if p is None:
            continue
        run_max = max(run_max, p)
        if run_max >= mult * p0 and p <= (1 - delta) * run_max:
            return i, t_end
    return None


def prior_wave_high(pivots, at_index: int):
    """截至序号 at_index 已确认的最近一个顶的价格；确认发生在 at_index 之后的不算。"""
    peaks = [pv for pv in pivots if pv[1] == "peak" and pv[0] <= at_index]
    return peaks[-1][3] if peaks else None


def exceed_label(
    series, trigger_index: int, level: float, horizon_buckets: int, status: str
):
    """标签：触发之后 horizon 内是否超过 level。status 来自 contract_filter.label_status；未成熟返回 'immature'。"""
    if status != "mature":
        return "immature"
    after = [
        p
        for i, _, p, filled in series[
            trigger_index + 1 : trigger_index + 1 + horizon_buckets
        ]
        if p is not None and not filled
    ]
    return int(any(p > level for p in after))
