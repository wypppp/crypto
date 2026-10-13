#!/usr/bin/env python3
"""DQ-43 A：剩余预测关联检验的标签与置换（10-13 v2，按 GPT 门 1 第 12～15 条修改）。合成数据实现，不读真实数据。

1. 风险集：窗口内每一笔买入都进风险集，不论买方是谁、之后有没有事件（零事件的币留在分母）。
2. 先后用完整链上顺序键 (slot, 交易序, 外层指令序, 内层指令序) 判断：事件的键大于买入的键，且事件时刻 ≤ 买入时刻＋H。
3. 成熟：买入时刻＋H 严格早于该币的观察终点（创建后 30 天与止日取早者）才算成熟；未成熟单列，不进检验。
4. 自身触发按“逐事件”排除：由同一实体、同一笔交易、或同一 slot 内关联体触发的事件不算命中，
   但窗内若还有外部事件，仍算命中。窗内有自身事件的买入标 self=1，置换时单独成层（不与普通行互换）。
5. 检验单位：同一实体在同一个币上只保留一笔事先规定的买入——按顺序键的首笔成熟买入；
   状态、结果窗、命中与 self 都取这一笔（GPT 增量 05）。旧写法“状态取首笔、命中取任一笔”会让
   多次买入者靠更多结果窗覆盖得到更多命中，而比较只控制首笔状态，层内不可交换（反例见测试）。
6. 置换：在 (币, UTC 日, 状态分箱, self) 层内打乱命中标签。一个实体所在的层全都没有标签变化时，置换分布退化，记“不可检验”。
7. 分辨率：置换的最小 p＝1/(1＋次数)；它大于族内最严的 Holm 门槛 α/m 时，整族记“分辨率不足”。
   “不显著”“不可检验”“分辨率不足”分开记，后两类不能当作“显著实体为 0”（GPT 15）。
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
    key: tuple  # (slot, 交易序, 外层指令序, 内层指令序)
    tx: str
    state: tuple  # 买入当时可见的状态分箱
    obs_end: float  # 该币观察终点（epoch 秒，不含）


@dataclass(frozen=True)
class Event:
    coin: str
    kind: str  # grad / boost
    ts: float
    key: tuple
    tx: str
    trigger_entity: str


def label(
    buys, events, kind: str, horizon: float = 1800.0, affiliates=None
) -> list[dict]:
    """每笔买入一行：hit（窗内有外部事件）、self（窗内有自身触发的事件）、mature。"""
    affiliates = affiliates or {}
    by_coin = defaultdict(list)
    for e in events:
        if e.kind == kind:
            by_coin[e.coin].append(e)
    rows = []
    for b in buys:
        hit = own = 0
        for e in by_coin.get(b.coin, ()):
            if not (e.key > b.key and e.ts <= b.ts + horizon):
                continue
            is_own = (
                e.trigger_entity == b.entity
                or e.tx == b.tx
                or (
                    e.key[0] == b.key[0]
                    and e.trigger_entity in affiliates.get(b.entity, ())
                )
            )
            if is_own:
                own = 1
            else:
                hit = 1
        rows.append(
            {
                "bid": b.bid,
                "entity": b.entity,
                "coin": b.coin,
                "key": b.key,
                "day": int(b.ts // 86400),
                "state": b.state,
                "hit": hit,
                "self": own,
                "mature": b.ts + horizon < b.obs_end,
            }
        )
    return rows


def collapse(rows) -> list[dict]:
    """同一实体在同一币上只留首笔成熟买入（按顺序键）；它的状态、日、命中、self 原样保留。未成熟行不进。
    成熟只取决于“买入时刻＋H 早于该币观察终点”，所以首笔买入未成熟时，后面的也都未成熟。"""
    groups: dict = {}
    for r in sorted((r for r in rows if r["mature"]), key=lambda r: r["key"]):
        k = (r["entity"], r["coin"])
        if k not in groups:
            groups[k] = dict(r)
    out = []
    for g in groups.values():
        g["stratum"] = (g["coin"], g["day"], g["state"], g["self"])
        out.append(g)
    return out


def entity_hits(rows) -> dict:
    out: dict = defaultdict(int)
    for r in rows:
        out[r["entity"]] += r["hit"]
    return dict(out)


def expected_hits(rows) -> dict:
    tot, n = defaultdict(int), defaultdict(int)
    for r in rows:
        tot[r["stratum"]] += r["hit"]
        n[r["stratum"]] += 1
    out: dict = defaultdict(float)
    for r in rows:
        out[r["entity"]] += tot[r["stratum"]] / n[r["stratum"]]
    return dict(out)


def permutation_p(rows, n_perm: int = 999, seed: int = 0) -> dict:
    """rows 须已 collapse()。返回 {实体: {obs, exp, p, status}}；status：testable／untestable。"""
    rng = random.Random(seed)
    strata = defaultdict(list)
    for i, r in enumerate(rows):
        strata[r["stratum"]].append(i)
    varying = {s for s, idx in strata.items() if len({rows[i]["hit"] for i in idx}) > 1}
    obs, exp = entity_hits(rows), expected_hits(rows)
    testable = {r["entity"] for r in rows if r["stratum"] in varying}
    ge = defaultdict(int)
    hits = [r["hit"] for r in rows]
    ents = [r["entity"] for r in rows]
    for _ in range(n_perm):
        perm = hits[:]
        for s in varying:
            idx = strata[s]
            vals = [hits[i] for i in idx]
            rng.shuffle(vals)
            for i, v in zip(idx, vals):
                perm[i] = v
        cnt: dict = defaultdict(int)
        for e, h in zip(ents, perm):
            cnt[e] += h
        for e in testable:
            if cnt[e] >= obs[e]:
                ge[e] += 1
    out = {}
    for e in obs:
        if e in testable:
            out[e] = {
                "obs": obs[e],
                "exp": exp[e],
                "p": (1 + ge[e]) / (1 + n_perm),
                "status": "testable",
            }
        else:
            out[e] = {"obs": obs[e], "exp": exp[e], "p": None, "status": "untestable"}
    return out


def holm_classify(res: dict, alpha: float, n_perm: int) -> dict:
    """{实体: significant／not_significant／untestable／resolution_insufficient}。族＝可检验的实体。"""
    tested = sorted((v["p"], e) for e, v in res.items() if v["status"] == "testable")
    m = len(tested)
    out = {e: "untestable" for e, v in res.items() if v["status"] != "testable"}
    if m and 1 / (1 + n_perm) > alpha / m:
        out.update({e: "resolution_insufficient" for _, e in tested})
        return out
    stop = False
    for i, (p, e) in enumerate(tested):
        if not stop and p <= alpha / (m - i):
            out[e] = "significant"
        else:
            stop = True
            out[e] = "not_significant"
    return out


def n_perm_for(m: int, alpha: float, factor: int = 20) -> int:
    """与族规模匹配的置换次数：最小 p 至少比最严门槛 α/m 小 factor 倍。"""
    return max(999, int(factor * m / alpha))


def v4_circular_rate(
    buys, events, kind: str, entity: str, horizon: float = 1800.0
) -> float | None:
    """反例：v4 先挑“事件前 horizon 内的买入”，再算这些买入之后发生事件的比例——恒为 1。"""

    def follows(b):
        return any(
            e.kind == kind and e.coin == b.coin and b.ts < e.ts <= b.ts + horizon
            for e in events
        )

    sel = [b for b in buys if b.entity == entity and follows(b)]
    if not sel:
        return None
    return sum(1 for b in sel if follows(b)) / len(sel)


# ---------- S3：事前选集、事后整体检验（10-13，总控第二轮采纳） ----------
#
# 选集规则（在 W 上，只用 W+1 周一 00:00 UTC 之前可得的信息；调用方把 W 的买入按
# obs_end＝min(该币观察终点, W+1 周一) 标成熟，事件只取 W+1 周一之前发生的）：
#   1. 合格：在 W 上至少有 MIN_ROWS 行（合并后的“实体 × 币”成熟行）；
#   2. 得分：命中 − 同层期望（score＝obs − exp）；
#   3. 候选：得分 > 0；
#   4. 入选：候选按得分从高到低（并列按 sha256(实体) 定序），取 ⌈合格数 × TOP_FRAC⌉ 个。
# 检验（在 W+1 上，只用 W+1 创建的币）：统计量 T＝Σ 入选实体 (命中 − 同层期望)；
#   零分布：每个窗口对在自己的 W+1 分层内各自置换命中标签，再把各对的 T 相加（三对合并成一次检验）；
#   单侧 p＝(1＋#{置换 T ≥ 观测 T})/(1＋置换次数)；p ≤ ALPHA（2.5%，GPT 增量 08）为“显著为正”。
#   可计算：入选且在 W+1 有成熟行的实体，按实体编号跨对去重后至少 MIN_ACTIVE 个；否则“不可计算”。
#   同时报“实体 × 窗口对”数（GPT 增量 04：7 个实体出现在三对里，不能算 21 个实体）。

MIN_ROWS = 5
TOP_FRAC = 0.10
MIN_ACTIVE = 20
ALPHA = 0.025


def _ekey(e: str) -> str:
    import hashlib

    return hashlib.sha256(e.encode()).hexdigest()


def select_set(rows_w) -> list:
    """rows_w：W 上 collapse() 之后的行。返回入选实体列表（按得分排序）。"""
    n_rows: dict = defaultdict(int)
    for r in rows_w:
        n_rows[r["entity"]] += 1
    eligible = [e for e, n in n_rows.items() if n >= MIN_ROWS]
    if not eligible:
        return []
    obs, exp = entity_hits(rows_w), expected_hits(rows_w)
    cand = [e for e in eligible if obs[e] - exp[e] > 0]
    cand.sort(key=lambda e: (-(obs[e] - exp[e]), _ekey(e)))
    k = -(-len(eligible) * TOP_FRAC // 1)  # 向上取整
    return cand[: int(k)]


def set_statistic(rows, members: set) -> float:
    exp = expected_hits(rows)
    obs = entity_hits(rows)
    return sum(obs.get(e, 0) - exp.get(e, 0.0) for e in members)


def set_test(pairs, n_perm: int = 9999, alpha: float = ALPHA, seed: int = 0) -> dict:
    """pairs：[(W+1 上 collapse() 之后的行, W 上选出的实体集), …]。返回 T、p、活跃入选实体数、结论。
    层内置换下，落在入选实体行上的命中数服从超几何分布：从该层 n 行（其中 h 行命中）里随机取入选实体的 m 行。
    所以每次置换只需在每个含入选行的层里抽一次，等价于逐行打乱，但快得多。"""
    import numpy as np

    active_pairs = [
        (i, e)
        for i, (rows, m) in enumerate(pairs)
        for e in {r["entity"] for r in rows} & set(m)
    ]
    active = len({e for _, e in active_pairs})
    out = {"active": active, "active_pairs": len(active_pairs)}
    if active < MIN_ACTIVE:
        return dict(out, T=None, p=None, result="not_computable")
    t_obs = sum(set_statistic(rows, set(m)) for rows, m in pairs)
    groups = []  # (n, h, m)：层的行数、命中数、入选实体行数
    e_total = 0.0
    for rows, members in pairs:
        members = set(members)
        e_total += sum(v for e, v in expected_hits(rows).items() if e in members)
        agg: dict = defaultdict(lambda: [0, 0, 0])
        for r in rows:
            g = agg[r["stratum"]]
            g[0] += 1
            g[1] += r["hit"]
            g[2] += r["entity"] in members
        groups += [tuple(g) for g in agg.values() if g[2] > 0]
    rng = np.random.Generator(np.random.PCG64(seed))
    hits = np.zeros(n_perm)
    for n, h, m in groups:
        if h == 0:
            continue
        if h == n:
            hits += m
            continue
        hits += rng.hypergeometric(h, n - h, m, size=n_perm)
    ge = int(np.sum(hits - e_total >= t_obs - 1e-9))
    p = (1 + ge) / (1 + n_perm)
    return dict(out, T=t_obs, p=p, result="positive" if p <= alpha else "not_positive")
