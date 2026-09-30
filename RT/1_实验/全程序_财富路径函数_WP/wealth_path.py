#!/usr/bin/env python3
"""账户级财富路径函数（确定性上界；02 §10.4 第 1 步；形式见工作日志 09-18）。

形式：现金流+时间戳 → 容量 → 并发 → 资金约束 → 财富路径 → 是否在期限内达到目标。
本实现只算均值路径，不做 Monte Carlo，不计波动、回撤与 2 万/3 万亏损线：给出的是乐观上界，
所以由它反推的容量是**必要下限**（达不到则一定不行；达到也不保证行）。

一个优势用四个量描述：
- r：每次事件的净收益率（扣手续费、滑点后，在单次规模 ≤ K 时成立）；
- lam：每年可参与的事件数；
- hold_days：每次持仓天数；
- K：单次事件的名义容量（超过 K 收益率会下降，此处视为不可部署）。
下注比例 s：单次事件占可用资金的上限（确定性上界取 1）。
并发 N = lam·hold_days/365；每次可部署 = min(K, s·W/max(1, N))。
dW/dt = lam·r·min(K, s·W/max(1, N))（忽略持仓期的滞后，偏乐观）。
推论：资本增速 g = r·lam·s/max(1, N)（容量不约束时按 e^{gt} 增长）；年利润容量 P = lam·K·r；
容量开始约束的财富点 W* = P/g，此后按 P 线性增长。

阶段（背景.md 2026-09-30 条目与第 2 条资金规则）：
- 第一阶段：12 个月内 1 万 → 10 万；
- 一年内到 10 万则追加 2 万：第二阶段起点净值 12 万，累计外部入金 3 万；
- 最终成功：累计净投资收益 ≥100 万 → 净值 ≥103 万（未提款时），第二阶段最多 24 个月。

python wealth_path.py → 阶段二容量下限.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAN = 1e4


def time_to_target(w0: float, wt: float, g: float, p: float) -> float:
    """容量不约束时按 e^{gt}，到 W* = p/g 后按 p 线性增长；返回到达 wt 的年数。"""
    if w0 >= wt:
        return 0.0
    if g <= 0 and p <= 0:
        return math.inf
    if math.isinf(g):
        return (wt - w0) / p if p > 0 else math.inf
    w_star = p / g if g > 0 else 0.0
    if w_star >= wt:
        return math.log(wt / w0) / g
    if w0 >= w_star:
        return (wt - w0) / p
    return math.log(w_star / w0) / g + (wt - w_star) / p


def simulate(
    w0: float,
    wt: float,
    years: float,
    r: float,
    lam: float,
    hold_days: float,
    K: float,
    s: float = 1.0,
):
    """按日数值积分，核对解析解；返回（到达年数或 None, 期末净值）。"""
    n = max(1.0, lam * hold_days / 365)
    w, dt = w0, 1 / 365
    for i in range(int(years * 365) + 1):
        if w >= wt:
            return i / 365, w
        w += lam * r * min(K, s * w / n) * dt
    return None, w


def min_profit_capacity(w0: float, wt: float, years: float, g: float) -> float:
    """在给定资本增速 g 下，期限内到达 wt 所需的最小年利润容量 P（二分）。"""
    if not math.isinf(g) and math.log(wt / w0) / g > years:
        return math.inf
    lo, hi = 0.0, 1e12
    for _ in range(200):
        mid = (lo + hi) / 2
        if time_to_target(w0, wt, g, mid) <= years:
            hi = mid
        else:
            lo = mid
    return hi


def main() -> None:
    stage2 = {"w0": 12 * WAN, "wt": 103 * WAN, "years": 2.0}
    stage1 = {"w0": 1 * WAN, "wt": 10 * WAN, "years": 1.0}
    out: dict = {"stages": {"第一阶段": stage1, "第二阶段": stage2}}
    g_min2 = math.log(stage2["wt"] / stage2["w0"]) / stage2["years"]
    g_min1 = math.log(stage1["wt"] / stage1["w0"]) / stage1["years"]
    out["最低资本增速_连续复利"] = {"第一阶段": g_min1, "第二阶段": g_min2}
    gs = [g_min2 * 1.0001, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0, math.inf]
    table = []
    for g in gs:
        p = min_profit_capacity(stage2["w0"], stage2["wt"], stage2["years"], g)
        row = {"g_per_year": g, "P_min_wan_per_year": p / WAN}
        for r in (0.02, 0.05, 0.10, 0.20, 0.50):
            row[f"年名义量下限_万_r{int(r * 100)}%"] = p / r / WAN
        table.append(row)
    out["第二阶段_最小年利润容量"] = table
    # 数值核对：几个示例优势按日积分，与解析解对比
    checks = []
    for r, lam, hold, K in (
        (0.05, 200, 1, 5 * WAN),
        (0.10, 50, 3, 20 * WAN),
        (0.02, 1000, 0.5, 3 * WAN),
        (0.30, 12, 30, 50 * WAN),
    ):
        n = max(1.0, lam * hold / 365)
        g, P = r * lam / n, lam * K * r
        t_an = time_to_target(stage2["w0"], stage2["wt"], g, P)
        t_num, w_end = simulate(
            stage2["w0"], stage2["wt"], stage2["years"], r, lam, hold, K
        )
        checks.append(
            {
                "r": r,
                "lam": lam,
                "hold_days": hold,
                "K_wan": K / WAN,
                "g": g,
                "P_wan": P / WAN,
                "t_analytic_years": t_an,
                "t_numeric_years": t_num,
                "w_end_wan": w_end / WAN,
            }
        )
    out["示例核对"] = checks
    (HERE / "阶段二容量下限.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
