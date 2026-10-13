"""DQ-43 T3 与 R2（10-13，总控第二轮：R2 三对合并，进入 §9.1；GPT 增量 03、04、06、08 修改）。合成数据实现，不读真实数据。

- 排名：每个窗口对，只用 W+1 周一 00:00 UTC 之前发生的成交、未平仓按那一刻的 HELD 估值，算实体在 W 创建队列上的 NET；
  取前十分位：⌈实体数 × 10%⌉ 个，并列按 sha256(实体) 定序。
- 结果：这些实体在 W+1 创建队列上的 IN＋COST 与 OUT＋HELD，按（实体, 币的创建 UTC 日）汇总成现金流行；
  W+1 没有任何成交的实体记“不活跃”，单列，不当作 MR＝0。
- R2（三对合并）：活跃的前十分位实体合计 MR＝Σ(OUT＋HELD)÷Σ(IN＋COST)。
  区间用实体 × 创建日的双向重抽（pigeonhole 自助，Owen 2007）：每次独立地有放回抽实体（按实体编号跨对去重，
  同一实体跨对的行一起进出）和创建日（同一天创建的币一起进出，保留共同冲击），格 (e, d) 的权重＝两边抽中次数之积；
  2,000 次，取 2.5% 分位为下界（单侧 2.5% 水平，GPT 增量 08）。下界 >1 且 P 类实体 ≥20 即成立。
- 人数一律按实体编号跨对去重（GPT 增量 04）；同时报“实体 × 窗口对”数。
  P 类跨对合并规则：实体在任一对里是 P 类（该对 W 与 W+1 全成本净额都为正、不带 L、S、K），就算 1 个 P 类实体。
- 可计算：活跃的前十分位实体（去重）≥20，且现金流行覆盖的创建日 ≥ MIN_DAYS（独立的共同冲击信息够，GPT 增量 06）；
  否则“不可计算”。
"""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction

MIN_ACTIVE = 20
MIN_P = 20


def top_decile(net_w: dict) -> list:
    """net_w：{实体: W 上的 NET（截至 W+1 周一）}。返回前十分位实体。"""
    order = sorted(
        net_w, key=lambda e: (-net_w[e], hashlib.sha256(e.encode()).hexdigest())
    )
    return order[: math.ceil(len(order) * 0.10)]


MIN_DAYS = 10


def r2_pooled(members, flows, n_boot: int = 2000, seed: int = 0) -> dict:
    """members：前十分位实体，每行 {pair, entity, active, p_class}；
    flows：活跃实体在 W+1 的现金流，每行 {pair, entity, day, in_cost, out_held}（day＝币的创建 UTC 日）。"""
    import numpy as np

    act = {(m["pair"], m["entity"]) for m in members if m["active"]}
    n_active = len({e for _, e in act})
    n_p = len({m["entity"] for m in members if m["p_class"]})
    use = [f for f in flows if (f["pair"], f["entity"]) in act]
    days = sorted({f["day"] for f in use})
    out = {
        "n_active": n_active,
        "n_active_pairs": len(act),
        "n_p": n_p,
        "n_days": len(days),
        "mr": None,
        "lower": None,
        "holds": False,
    }
    num = sum(f["out_held"] for f in use)
    den = sum(f["in_cost"] for f in use)
    if n_active < MIN_ACTIVE or len(days) < MIN_DAYS or not den:
        return dict(out, computable=False)
    ents = sorted({f["entity"] for f in use})
    ei = {e: i for i, e in enumerate(ents)}
    di = {d: i for i, d in enumerate(days)}
    o = np.zeros((len(ents), len(days)))
    c = np.zeros((len(ents), len(days)))
    for f in use:
        o[ei[f["entity"]], di[f["day"]]] += f["out_held"]
        c[ei[f["entity"]], di[f["day"]]] += f["in_cost"]
    rng = np.random.Generator(np.random.PCG64(seed))
    we = rng.multinomial(len(ents), [1 / len(ents)] * len(ents), size=n_boot)
    wd = rng.multinomial(len(days), [1 / len(days)] * len(days), size=n_boot)
    bn = np.einsum("be,ed,bd->b", we, o, wd)
    bd = np.einsum("be,ed,bd->b", we, c, wd)
    ok = bd > 0
    boots = np.sort(bn[ok] / bd[ok])
    lower = float(boots[int(0.025 * len(boots))]) if len(boots) else None
    mr = Fraction(num, den)
    holds = lower is not None and lower > 1 and n_p >= MIN_P
    return dict(out, computable=True, mr=mr, lower=lower, holds=holds)


def keep_main_line(s3: dict, r2: dict) -> str:
    """§9.1 v3（GPT 增量 03，总控第三轮）：S3 显著为正，或 R2 可计算且成立，任一满足即保持主线；
    另一项不可计算不否决有效阳性。两项都没有有效阳性则降为观察线。"""
    if s3.get("result") == "positive" or (r2.get("computable") and r2.get("holds")):
        return "keep"
    return "downgrade"
