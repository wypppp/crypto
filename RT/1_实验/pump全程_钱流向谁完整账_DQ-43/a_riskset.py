#!/usr/bin/env python3
"""DQ-43 A：剩余预测关联检验（10-13，WM2 v5 §4）。先在合成数据上实现与测试，不读真实数据。

1. 风险集：窗口内每一笔买入都进风险集，不论买方是谁、之后有没有事件（零事件的币留在分母）。
2. 标签：买入之后 horizon 秒内（默认 30 分钟），同一个币是否发生该类事件（毕业、InitBoost 分开做）。
3. 排除自身触发：事件由这笔买入所在实体的交易、同一笔交易、或同一 slot 内关联体的交易直接触发的，
   标签记 0，并标 self=1（自己买到毕业，不等于预知毕业）。
4. 比较：每个实体的命中数，对比“同状态的随机买入”。在 (币, UTC 日, 买入当时可见状态) 分层内
   置换命中标签，得到命中数的置换分布；p＝(1＋#{置换 ≥ 观测})/(1＋置换次数)。
v4 的“超额命中率”先按事件挑出“事件前买入”再算事件率，结果由定义决定（循环筛选），保留为反例函数。
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Buy:
    bid: int
    entity: str
    coin: str
    ts: float  # epoch 秒
    slot: int
    tx: str
    state: tuple  # 买入当时可见的状态分箱：阶段、进度十分位、前 60 秒净买入档、本笔大小档、UTC 小时


@dataclass(frozen=True)
class Event:
    coin: str
    kind: str  # grad / boost
    ts: float
    slot: int
    tx: str
    trigger_entity: str  # 触发交易的实体


def label(
    buys, events, kind: str, horizon: float = 1800.0, affiliates=None
) -> list[dict]:
    """风险集：每笔买入一行，hit∈{0,1}，self∈{0,1}。affiliates：实体 → 关联体集合（截至时刻版本）。"""
    affiliates = affiliates or {}
    by_coin = defaultdict(list)
    for e in events:
        if e.kind == kind:
            by_coin[e.coin].append(e)
    rows = []
    for b in buys:
        hit = self_ = 0
        for e in by_coin.get(b.coin, ()):
            if not (b.ts < e.ts <= b.ts + horizon):
                continue
            own = (
                e.trigger_entity == b.entity
                or e.tx == b.tx
                or (
                    e.slot == b.slot
                    and e.trigger_entity in affiliates.get(b.entity, ())
                )
            )
            if own:
                self_ = 1
            else:
                hit = 1
        if self_:
            hit = 0
        day = int(b.ts // 86400)
        rows.append(
            {
                "bid": b.bid,
                "entity": b.entity,
                "stratum": (b.coin, day, b.state),
                "hit": hit,
                "self": self_,
            }
        )
    return rows


def entity_hits(rows) -> dict:
    out: dict = defaultdict(int)
    for r in rows:
        out[r["entity"]] += r["hit"]
    return dict(out)


def expected_hits(rows) -> dict:
    """同层随机买入给出的期望命中数：Σ 该实体每笔买入所在层的命中率。"""
    tot, n = defaultdict(int), defaultdict(int)
    for r in rows:
        tot[r["stratum"]] += r["hit"]
        n[r["stratum"]] += 1
    out: dict = defaultdict(float)
    for r in rows:
        out[r["entity"]] += tot[r["stratum"]] / n[r["stratum"]]
    return dict(out)


def permutation_p(rows, n_perm: int = 999, seed: int = 0) -> dict:
    """分层置换：每层内打乱命中标签。返回 {实体: (观测命中, 期望命中, p)}。"""
    rng = random.Random(seed)
    strata = defaultdict(list)
    for i, r in enumerate(rows):
        strata[r["stratum"]].append(i)
    obs = entity_hits(rows)
    exp = expected_hits(rows)
    ge = defaultdict(int)
    hits = [r["hit"] for r in rows]
    ents = [r["entity"] for r in rows]
    for _ in range(n_perm):
        perm = hits[:]
        for idx in strata.values():
            vals = [hits[i] for i in idx]
            rng.shuffle(vals)
            for i, v in zip(idx, vals):
                perm[i] = v
        cnt: dict = defaultdict(int)
        for e, h in zip(ents, perm):
            cnt[e] += h
        for e in obs:
            if cnt[e] >= obs[e]:
                ge[e] += 1
    return {e: (obs[e], exp[e], (1 + ge[e]) / (1 + n_perm)) for e in obs}


def v4_circular_rate(
    buys, events, kind: str, entity: str, horizon: float = 1800.0
) -> float | None:
    """反例：v4 先挑“事件前 horizon 内的买入”，再算这些买入之后发生事件的比例——恒为 1。"""
    sel = [
        b
        for b in buys
        if b.entity == entity
        and any(
            e.kind == kind and e.coin == b.coin and b.ts < e.ts <= b.ts + horizon
            for e in events
        )
    ]
    if not sel:
        return None
    return sum(
        1
        for b in sel
        if any(
            e.kind == kind and e.coin == b.coin and b.ts < e.ts <= b.ts + horizon
            for e in events
        )
    ) / len(sel)
