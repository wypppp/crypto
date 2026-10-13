#!/usr/bin/env python3
"""DQ-43 T3 与 R2（10-13，总控第二轮：R2 三对合并，进入 §9.1）。合成数据实现，不读真实数据。

- 排名：每个窗口对，只用 W+1 周一 00:00 UTC 之前发生的成交、未平仓按那一刻的 HELD 估值，算实体在 W 创建队列上的 NET；
  取前十分位：⌈实体数 × 10%⌉ 个，并列按 sha256(实体) 定序。
- 结果：这些实体在 W+1 创建队列上的 IN＋COST 与 OUT＋HELD；W+1 没有任何成交的实体记“不活跃”，单列，不当作 MR＝0。
- R2（三对合并）：活跃的前十分位实体合计 MR＝Σ(OUT＋HELD)÷Σ(IN＋COST)，按实体聚类（同一实体跨对算一个簇）
  自助 2,000 次，取 2.5% 分位为 95% 下界；下界 >1 且 P 类（W 与 W+1 全成本净额都为正、不带 L、S、K）合计 ≥20 即成立。
  可计算：活跃的前十分位实体合计 ≥20；否则“不可计算”。
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from fractions import Fraction

MIN_ACTIVE = 20
MIN_P = 20


def top_decile(net_w: dict) -> list:
    """net_w：{实体: W 上的 NET（截至 W+1 周一）}。返回前十分位实体。"""
    order = sorted(
        net_w, key=lambda e: (-net_w[e], hashlib.sha256(e.encode()).hexdigest())
    )
    return order[: math.ceil(len(order) * 0.10)]


def r2_pooled(rows, n_boot: int = 2000, seed: int = 0) -> dict:
    """rows：前十分位实体在 W+1 的结果，每行 {pair, entity, in_cost, out_held, active, p_class}。"""
    act = [r for r in rows if r["active"]]
    n_p = sum(1 for r in rows if r["p_class"])
    if len(act) < MIN_ACTIVE:
        return {
            "computable": False,
            "mr": None,
            "lower": None,
            "n_active": len(act),
            "n_p": n_p,
            "holds": False,
        }
    num = sum(r["out_held"] for r in act)
    den = sum(r["in_cost"] for r in act)
    mr = Fraction(num, den) if den else None
    clusters = defaultdict(lambda: [0, 0])
    for r in act:
        clusters[r["entity"]][0] += r["out_held"]
        clusters[r["entity"]][1] += r["in_cost"]
    vals = list(clusters.values())
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        s = [vals[rng.randrange(len(vals))] for _ in vals]
        d = sum(v[1] for v in s)
        if d:
            boots.append(sum(v[0] for v in s) / d)
    boots.sort()
    lower = boots[int(0.025 * len(boots))] if boots else None
    holds = mr is not None and lower is not None and lower > 1 and n_p >= MIN_P
    return {
        "computable": mr is not None,
        "mr": mr,
        "lower": lower,
        "n_active": len(act),
        "n_p": n_p,
        "holds": holds,
    }


def keep_main_line(s3: dict, r2: dict) -> str:
    """§9.1 v2（总控第二轮）：两者都可计算，且 S3 显著为正或 R2 成立，才保持主线；其余一律降为观察线。"""
    both = s3.get("result") in ("positive", "not_positive") and r2.get("computable")
    if both and (s3["result"] == "positive" or r2["holds"]):
        return "keep"
    return "downgrade"
