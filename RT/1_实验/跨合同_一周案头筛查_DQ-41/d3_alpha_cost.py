#!/usr/bin/env python3
"""DQ-41 第 3 天：币安 Alpha 积分的成本侧账（10-06）。只用机制与已读的元数据，不读价格。

python d3_alpha_cost.py → results/d3_alpha_cost.json
输入：5_参考/检索记录/参与基础比率_alpha123空投.csv（10-02 检索，只有日期、门槛、每人数量、类型；价格列当时已丢弃）。
入口过滤：日期过 screen_gate.date_ok（开发周或 2025-02-24 之前、不晚于止日）；代号按留出规则判，已遮蔽的 `<留出>` 行整行排除。
积分规则（官方 FAQ，10-06 核对原文，页面更新于 2026-07-14）：
  余额分每日 1/2/3/4（100～1千、1千～1万、1万～10万、≥10万美元）；
  买入量分每日 k 分对应 2^k 美元（2 美元 1 分，每翻一倍加 1 分）；
  总分＝过去 15 天之和；参与活动立即扣分；余额分为 0 时买入量分不计。
每次领取扣 15 分是转述（子 agent B 组），未见 FAQ 原文，作为参数 DEDUCT。
"""

import json
import math
from pathlib import Path

import pandas as pd

import screen_gate as G

H = Path(__file__).resolve().parent
SRC = H.parents[1] / "5_参考" / "检索记录" / "参与基础比率_alpha123空投.csv"
DEDUCT = 15  # 每次参与扣分（转述）
WINDOW = 15


def volume_for_points(k):
    """每日买入量分 k 所需的最小买入额（美元）：2^k。"""
    return 2.0**k


def claims_per_window(p, T, d=DEDUCT):
    """稳态下 15 天内最多领几次：每次领取前总分 ≥ T，领取后扣 d。
    15 天总分＝15p−(窗口内已扣)；第 n 次领取前已扣 (n−1)d，要求 15p−(n−1)d ≥ T。"""
    if 15 * p < T:
        return 0
    return int(math.floor((15 * p - T) / d)) + 1


def load():
    df = pd.read_csv(SRC, dtype=str)
    n0 = len(df)
    ok = [
        (t != "<留出>") and G.date_ok(d) and not G.is_holdout_symbol(t)
        for t, d in zip(df["token"].fillna(""), df["date"])
    ]
    df = df[ok].copy()
    df["T"] = pd.to_numeric(df["points"], errors="coerce")
    df["month"] = df["date"].str[:7]
    return df, n0 - len(df)


def main():
    df, n_out = load()
    yr26 = df[df["date"] >= "2026-01-01"]
    out = {
        "rows_kept": len(df),
        "rows_excluded_by_gate": n_out,
        "kept_per_month": df.groupby("month").size().to_dict(),
        "threshold_2026_dev_quantiles": {
            str(q): float(yr26["T"].quantile(q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)
        },
        "type_2026_dev": yr26["type"].fillna("空").value_counts().to_dict(),
        "phase_2026_dev": yr26["phase"].fillna("空").value_counts().to_dict(),
    }
    # 成本侧：每日积分 p＝余额分 b＋买入量分 k；门槛取 2026 年开发周的中位与第 90 分位
    rows = []
    for T in (
        out["threshold_2026_dev_quantiles"]["0.5"],
        out["threshold_2026_dev_quantiles"]["0.9"],
    ):
        for b in (2, 3, 4):
            for k in range(12, 19):
                p = b + k
                n = claims_per_window(p, T)
                rows.append(
                    {
                        "T": T,
                        "balance_pts": b,
                        "volume_pts": k,
                        "daily_buy_usd": volume_for_points(k),
                        "claims_per_15d": n,
                        "buy_usd_per_claim": None
                        if n == 0
                        else 15 * volume_for_points(k) / n,
                    }
                )
    out["cost_grid"] = rows
    (H / "results").mkdir(exist_ok=True)
    (H / "results" / "d3_alpha_cost.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1)
    )
    print(
        json.dumps(
            {k: v for k, v in out.items() if k != "cost_grid"},
            ensure_ascii=False,
            indent=1,
        )
    )
    g = pd.DataFrame(rows)
    print(g[g["claims_per_15d"] > 0].to_string(index=False))


if __name__ == "__main__":
    main()
