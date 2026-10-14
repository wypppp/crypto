#!/usr/bin/env python3
"""DQ-43 冻结卡 v4 的两条新规则（10-14，总控第四轮第二、三节）。合成数据实现，不读真实数据。

1. 成本上下界（第二节）：
   - COST_lo＝成功交易的链上费用（签名费、优先费、Jito 小费）；
   - COST_hi＝COST_lo＋失败交易费用＋范围完整的成交交易里所有未解释的负残差（全部当作成本）。
   R2（与描述用的 T3）在两种口径下各算一次。§9.1 在两种口径下结论相同，就按它判定；
   不同，才对翻转涉及的实体补完整的资金路径映射，再判定（返回 needs_mapping 与实体名单）。
   S3 不含成本，两种口径相同。
2. 抽样阶梯（第三节）：抽样率按 10% → 25% → 50% → 100% 的阶梯。
   §9.1 的结果若因“不可计算”而降级，且不可计算是人数不足造成的，先在本期额度内扩大到下一档重算；
   扩到 100% 仍不可计算，才按 §9.1 降级。
"""

from __future__ import annotations

import t3_persist as P

LADDER = (0.10, 0.25, 0.50, 1.00)


def decide_with_bounds(
    s3: dict, r2_lo: dict, r2_hi: dict, members_lo=(), members_hi=()
) -> dict:
    """返回 {decision: keep／downgrade／needs_mapping, keep_lo, keep_hi, flip_entities}。
    members_lo、members_hi：两种口径下 R2 用到的实体（前十分位活跃实体与 P 类）。R2 是合并比率，翻转时每个成员的
    成本差都起作用，所以补映射的范围是两者的并集（不是对称差）。"""
    k_lo = P.keep_main_line(s3, r2_lo)
    k_hi = P.keep_main_line(s3, r2_hi)
    if k_lo == k_hi:
        return {"decision": k_lo, "keep_lo": k_lo, "keep_hi": k_hi, "flip_entities": []}
    flip = sorted(set(members_lo) | set(members_hi))
    return {
        "decision": "needs_mapping",
        "keep_lo": k_lo,
        "keep_hi": k_hi,
        "flip_entities": flip,
    }


def short_of_people(s3: dict, r2: dict) -> bool:
    """有没有阳性以外的“不可计算”是人数不足造成的（S3 入选活跃实体、R2 活跃实体或创建日不足）。"""
    s3_short = s3.get("result") == "not_computable"
    r2_short = not r2.get("computable")
    return s3_short or r2_short


def next_sampling_step(p: float, s3: dict, r2: dict) -> float | None:
    """§9.1 已是保持主线，或不可计算与人数无关时，返回 None（按当前结果判定）；
    否则返回阶梯上的下一档抽样率；已在 100% 时返回 None（按 §9.1 降级）。"""
    if P.keep_main_line(s3, r2) == "keep":
        return None
    if not short_of_people(s3, r2):
        return None
    i = LADDER.index(p)
    return LADDER[i + 1] if i + 1 < len(LADDER) else None
