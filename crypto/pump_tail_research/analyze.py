#!/usr/bin/env python3
"""Audit and summarize token-level output from 01_token_metrics.sql."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


COHORT_START = pd.Timestamp("2026-05-01T00:00:00Z")
COHORT_END = pd.Timestamp("2026-07-25T00:00:00Z")
EXPECTED_DAYS = (COHORT_END - COHORT_START).total_seconds() / 86_400
SURVIVAL_VOLUME_USD = 1_000.0
RIGHT_TAIL_MULTIPLE = 10.0
AVERAGE_EXECUTION_IMPACT = 0.05
STRICT_SPOT_IMPACT_CAPACITY_FACTOR = math.sqrt(1.05) - 1.0
QUANTILES = (0.50, 0.90, 0.95, 0.99)

REQUIRED_COLUMNS = {
    "graduated_at",
    "mint",
    "pool",
    "quote_mint",
    "is_mayhem_mode",
    "initial_quote_reserve_usd",
    "max_30d",
    "max_30d_non_agent",
    "max_30d_min_001sol",
    "p7d",
    "p30d",
    "p7d_observed",
    "p30d_observed",
    "day30_volume_usd",
    "day30_volume_usd_non_agent",
    "day30_unique_traders",
    "day30_unique_non_agent_traders",
    "trade_rows_30d",
    "priced_trade_rows_30d",
    "usd_priced_trade_rows_30d",
    "day30_trade_rows",
    "day30_usd_priced_trade_rows",
}


def native(value: Any) -> Any:
    """Convert pandas/numpy scalars into JSON-serializable Python values."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "t"})


def nullable_truthy(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.lower()
    result = pd.Series(pd.NA, index=series.index, dtype="boolean")
    result.loc[values.isin({"true", "1", "yes", "t"})] = True
    result.loc[values.isin({"false", "0", "no", "f"})] = False
    return result


def distribution(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce")
    quantiles = values.quantile(QUANTILES)
    result: dict[str, Any] = {
        "n": int(values.notna().sum()),
        "missing": int(values.isna().sum()),
    }
    for q in QUANTILES:
        result[f"p{int(q * 100)}"] = native(quantiles.loc[q])
    result["max"] = native(values.max())
    return result


def money(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"${float(value):,.2f}"


def ratio(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"{100 * float(value):.2f}%"


def multiple(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"{float(value):,.4g}x"


def summarize(frame: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    df = frame.copy()
    df["graduated_at"] = pd.to_datetime(df["graduated_at"], utc=True, errors="raise")
    if df.empty:
        raise ValueError("CSV contains no graduations; do not interpret this as N0=0")
    if df["mint"].isna().any() or df["mint"].duplicated().any():
        duplicates = df.loc[df["mint"].duplicated(keep=False), "mint"].tolist()[:10]
        raise ValueError(f"mint must be non-null and unique; examples: {duplicates}")
    outside = ~df["graduated_at"].between(COHORT_START, COHORT_END, inclusive="left")
    if outside.any():
        examples = df.loc[outside, ["mint", "graduated_at"]].head().to_dict("records")
        raise ValueError(f"graduations outside frozen UTC cohort: {examples}")

    df["is_mayhem_mode"] = nullable_truthy(df["is_mayhem_mode"])
    bool_columns = ("p7d_observed", "p30d_observed")
    for column in bool_columns:
        df[column] = truthy(df[column])
    numeric_columns = REQUIRED_COLUMNS - {
        "graduated_at",
        "mint",
        "pool",
        "quote_mint",
        "is_mayhem_mode",
        *bool_columns,
    }
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    invalid_nonnegative = [
        column
        for column in numeric_columns
        if (df[column].dropna() < 0).any()
    ]
    if invalid_nonnegative:
        raise ValueError(f"negative values in non-negative metrics: {invalid_nonnegative}")

    df["survived_day30"] = df["day30_volume_usd"] >= SURVIVAL_VOLUME_USD
    df["survived_day30_non_agent"] = (
        df["day30_volume_usd_non_agent"] >= SURVIVAL_VOLUME_USD
    )
    df["right_tail"] = df["max_30d"] >= RIGHT_TAIL_MULTIPLE
    df["right_tail_non_agent"] = df["max_30d_non_agent"] >= RIGHT_TAIL_MULTIPLE
    df["right_tail_min_001sol"] = df["max_30d_min_001sol"] >= RIGHT_TAIL_MULTIPLE
    df["capacity_5pct_usd"] = (
        AVERAGE_EXECUTION_IMPACT * df["initial_quote_reserve_usd"]
    )
    df["capacity_strict_5pct_spot_usd"] = (
        STRICT_SPOT_IMPACT_CAPACITY_FACTOR * df["initial_quote_reserve_usd"]
    )
    df["right_tail_capacity_5pct_usd"] = df["capacity_5pct_usd"].where(
        df["right_tail"], 0.0
    )
    df["week"] = df["graduated_at"].dt.tz_convert(None).dt.to_period("W-SUN").astype(str)

    n0 = len(df)
    n1 = int(df["survived_day30"].sum())
    n1_non_agent = int(df["survived_day30_non_agent"].sum())
    right = df.loc[df["right_tail"]].copy()
    right_non_agent = df.loc[df["right_tail_non_agent"]].copy()
    right_dust_filtered = df.loc[df["right_tail_min_001sol"]].copy()
    all_capacity = df["capacity_5pct_usd"].sum()
    right_capacity = right["capacity_5pct_usd"].sum()
    capacity_weighted_hit_rate = right_capacity / all_capacity
    idealized_buy_all_ev = 10 * right_capacity - all_capacity

    weekly = (
        df.groupby("week", as_index=False)
        .agg(
            graduations=("mint", "size"),
            right_tail=("right_tail", "sum"),
            right_tail_non_agent=("right_tail_non_agent", "sum"),
            right_tail_min_001sol=("right_tail_min_001sol", "sum"),
            oracle_capacity_5pct_usd=("right_tail_capacity_5pct_usd", "sum"),
        )
        .sort_values("week")
    )

    metric_coverage = {
        "initial_reserve_usd": int(df["initial_quote_reserve_usd"].notna().sum()),
        "priced_trade_rows": int(df["priced_trade_rows_30d"].sum()),
        "usd_priced_trade_rows": int(df["usd_priced_trade_rows_30d"].sum()),
        "all_trade_rows": int(df["trade_rows_30d"].sum()),
        "day30_trade_rows": int(df["day30_trade_rows"].sum()),
        "day30_usd_priced_trade_rows": int(df["day30_usd_priced_trade_rows"].sum()),
        "p7d_observed": int(df["p7d_observed"].sum()),
        "p30d_observed": int(df["p30d_observed"].sum()),
    }
    metric_coverage["priced_trade_row_rate"] = (
        metric_coverage["priced_trade_rows"] / metric_coverage["all_trade_rows"]
        if metric_coverage["all_trade_rows"]
        else None
    )
    metric_coverage["usd_priced_trade_row_rate"] = (
        metric_coverage["usd_priced_trade_rows"] / metric_coverage["all_trade_rows"]
        if metric_coverage["all_trade_rows"]
        else None
    )
    metric_coverage["day30_usd_priced_trade_row_rate"] = (
        metric_coverage["day30_usd_priced_trade_rows"]
        / metric_coverage["day30_trade_rows"]
        if metric_coverage["day30_trade_rows"]
        else None
    )
    metric_coverage["decision_ready"] = (
        metric_coverage["initial_reserve_usd"] == n0
        and metric_coverage["priced_trade_rows"] == metric_coverage["all_trade_rows"]
        and metric_coverage["usd_priced_trade_rows"]
        == metric_coverage["all_trade_rows"]
        and metric_coverage["day30_usd_priced_trade_rows"]
        == metric_coverage["day30_trade_rows"]
    )

    summary: dict[str, Any] = {
        "frozen_contract": {
            "cohort_start_utc": COHORT_START,
            "cohort_end_exclusive_utc": COHORT_END,
            "cohort_days": EXPECTED_DAYS,
            "day7_window": "[T+6d,T+7d)",
            "day30_window": "[T+29d,T+30d)",
            "survival_volume_usd": SURVIVAL_VOLUME_USD,
            "right_tail_multiple": RIGHT_TAIL_MULTIPLE,
            "missing_target_day_price_multiple": 0,
        },
        "n0": n0,
        "n1": {
            "survivors": n1,
            "rate": n1 / n0,
            "non_agent_survivors": n1_non_agent,
            "non_agent_rate": n1_non_agent / n0,
            "survivor_day30_unique_traders": distribution(
                df.loc[df["survived_day30"], "day30_unique_traders"]
            ),
        },
        "n2": {
            "distributions": {
                column: distribution(df[column])
                for column in ("max_30d", "p7d", "p30d")
            },
            "right_tail_count": len(right),
            "right_tail_rate": len(right) / n0,
            "right_tail_non_agent_count": len(right_non_agent),
            "right_tail_non_agent_rate": len(right_non_agent) / n0,
            "right_tail_min_001sol_count": len(right_dust_filtered),
            "right_tail_min_001sol_rate": len(right_dust_filtered) / n0,
            "right_tail_unique_traders_30d": distribution(
                right["unique_traders_30d"]
            ),
            "target_day_rates": {
                column: {
                    "zero_count": int((df[column] == 0).sum()),
                    "zero_rate": float((df[column] == 0).mean()),
                    "ge_1x_count": int((df[column] >= 1).sum()),
                    "ge_1x_rate": float((df[column] >= 1).mean()),
                    "ge_10x_count": int((df[column] >= 10).sum()),
                    "ge_10x_rate": float((df[column] >= 10).mean()),
                    "mean": float(df[column].mean()),
                }
                for column in ("p7d", "p30d")
            },
        },
        "n3": {
            "right_tail_initial_quote_reserve_usd": distribution(
                right["initial_quote_reserve_usd"]
            ),
            "right_tail_capacity_5pct_usd": distribution(right["capacity_5pct_usd"]),
            "right_tail_capacity_strict_5pct_spot_usd": distribution(
                right["capacity_strict_5pct_spot_usd"]
            ),
            "right_tail_opportunities_per_week_85d_average": len(right) / EXPECTED_DAYS * 7,
            "capital_weighted_10x_hit_rate": capacity_weighted_hit_rate,
            "all_candidates_capacity_total_usd": all_capacity,
            "right_tail_capacity_total_usd": right_capacity,
            "all_candidates_deployment_usd_per_week": all_capacity / EXPECTED_DAYS * 7,
            "oracle_deployable_usd_per_week_using_median_capacity": (
                len(right)
                / EXPECTED_DAYS
                * 7
                * right["capacity_5pct_usd"].median()
                if len(right)
                else 0.0
            ),
            "oracle_deployable_usd_per_week_exact_sum": (
                right["capacity_5pct_usd"].sum() / EXPECTED_DAYS * 7
                if len(right)
                else 0.0
            ),
            "calendar_week_right_tail_distribution": distribution(weekly["right_tail"]),
            "right_tail_capacity_below": {
                f"{threshold:g}_usd": {
                    "count": int((right["capacity_5pct_usd"] < threshold).sum()),
                    "rate": float((right["capacity_5pct_usd"] < threshold).mean()),
                }
                for threshold in (1, 10, 50, 100, 200, 300, 400)
            },
            "idealized_buy_all_10x_or_zero": {
                "ev_total_usd": idealized_buy_all_ev,
                "ev_per_week_usd": idealized_buy_all_ev / EXPECTED_DAYS * 7,
                "roi_on_deployed_capital": idealized_buy_all_ev / all_capacity,
            },
        },
        "break_even": {
            "winner_gross_multiple": 10.0,
            "loser_recovery_multiple": 0.0,
            "zero_cost_hit_rate": 0.10,
            "formula": "(1 + all_in_cost_rate - loser_recovery) / (winner_multiple - loser_recovery)",
            "cost_scenarios": {
                f"{int(cost * 100)}pct": (1 + cost) / 10
                for cost in (0.00, 0.01, 0.03, 0.05)
            },
        },
        "coverage": metric_coverage,
        "mode_counts": {
            "standard": int(df["is_mayhem_mode"].eq(False).sum()),
            "mayhem": int(df["is_mayhem_mode"].eq(True).sum()),
            "unknown": int(df["is_mayhem_mode"].isna().sum()),
        },
    }
    return summary, df, weekly


def markdown_report(summary: dict[str, Any]) -> str:
    n1 = summary["n1"]
    n2 = summary["n2"]
    n3 = summary["n3"]
    coverage = summary["coverage"]
    lines = [
        "# Pump.fun 毕业代币右尾研究",
        "",
        "## 冻结口径",
        "",
        "- 毕业区间：`[2026-05-01 00:00 UTC, 2026-07-25 00:00 UTC)`",
        "- 第 7 天：`[T+6d,T+7d)`；第 30 天：`[T+29d,T+30d)`",
        "- 目标日无成交：机械持有倍数记 0，并保留 observed 标记",
        "- 存活阈值：第 30 天窗口成交量 ≥ $1,000",
        "- 右尾阈值：`max_30d >= 10x`",
        "",
        "## N0 / N1",
        "",
        f"- N0：{summary['n0']:,}",
        f"- N1：{n1['survivors']:,} / {summary['n0']:,} = {ratio(n1['rate'])}",
        f"- 剔除 Mayhem 官方机器人钱包后的 N1：{n1['non_agent_survivors']:,} / {summary['n0']:,} = {ratio(n1['non_agent_rate'])}",
        f"- N1 代币第 30 天独立钱包数：P50={n1['survivor_day30_unique_traders']['p50']:.0f}，P90={n1['survivor_day30_unique_traders']['p90']:.1f}",
        "",
        "## N2：倍数分布",
        "",
        "| 指标 | P50 | P90 | P95 | P99 | Max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for column in ("max_30d", "p7d", "p30d"):
        dist = n2["distributions"][column]
        lines.append(
            f"| {column} | {multiple(dist['p50'])} | {multiple(dist['p90'])} | "
            f"{multiple(dist['p95'])} | {multiple(dist['p99'])} | {multiple(dist['max'])} |"
        )
    lines.extend(
        [
            "",
            f"- 原始右尾：{n2['right_tail_count']:,} / {summary['n0']:,} = {ratio(n2['right_tail_rate'])}",
            f"- 剔除 Mayhem 官方机器人后的右尾：{n2['right_tail_non_agent_count']:,} / {summary['n0']:,} = {ratio(n2['right_tail_non_agent_rate'])}",
            f"- 仅计单笔报价端 ≥0.01 SOL 的右尾：{n2['right_tail_min_001sol_count']:,} / {summary['n0']:,} = {ratio(n2['right_tail_min_001sol_rate'])}",
            f"- 右尾代币 30 天独立钱包数：P50={n2['right_tail_unique_traders_30d']['p50']:.0f}，P90={n2['right_tail_unique_traders_30d']['p90']:.1f}",
            f"- 第 7 天仍 ≥1x：{n2['target_day_rates']['p7d']['ge_1x_count']:,} / {summary['n0']:,} = {ratio(n2['target_day_rates']['p7d']['ge_1x_rate'])}",
            f"- 第 30 天仍 ≥1x：{n2['target_day_rates']['p30d']['ge_1x_count']:,} / {summary['n0']:,} = {ratio(n2['target_day_rates']['p30d']['ge_1x_rate'])}",
            "",
            "## N3：毕业时容量（原始右尾集合）",
            "",
            "| 指标 | P50 | P90 | P95 | P99 | Max |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for key, label in (
        ("right_tail_initial_quote_reserve_usd", "报价端初始储备"),
        ("right_tail_capacity_5pct_usd", "5% 平均成交价冲击容量"),
        ("right_tail_capacity_strict_5pct_spot_usd", "5% 末端现货价冲击容量"),
    ):
        dist = n3[key]
        lines.append(
            f"| {label} | {money(dist['p50'])} | {money(dist['p90'])} | "
            f"{money(dist['p95'])} | {money(dist['p99'])} | {money(dist['max'])} |"
        )
    lines.extend(
        [
            "",
            f"- 85 天平均每周右尾机会：{n3['right_tail_opportunities_per_week_85d_average']:.3f}",
            f"- 按入场容量加权的 10x 命中率：{ratio(n3['capital_weighted_10x_hit_rate'])}",
            f"- 若买全部毕业币，每周需部署：{money(n3['all_candidates_deployment_usd_per_week'])}",
            f"- 每周可部署上界（事后右尾数 × 右尾容量中位数）：{money(n3['oracle_deployable_usd_per_week_using_median_capacity'])}",
            f"- 每周可部署上界（逐个右尾容量求和后年化到周）：{money(n3['oracle_deployable_usd_per_week_exact_sum'])}",
            "- 这是知道谁会成为右尾之后的 oracle 上界，不是可执行策略容量；实盘必须用入场前信号的候选数替换右尾数。",
            f"- 右尾中容量低于 $10：{n3['right_tail_capacity_below']['10_usd']['count']:,} / {n2['right_tail_count']:,} = {ratio(n3['right_tail_capacity_below']['10_usd']['rate'])}",
            f"- 乐观的“买全部、触及 10x 即按 10x 全额成交、其余归零”回测 ROI：{ratio(n3['idealized_buy_all_10x_or_zero']['roi_on_deployed_capital'])}；这未计同块抢跑、费用、退出深度或洗量。",
            "",
            "## 盈亏平衡命中率",
            "",
            "10x 总回款、未命中归零、暂不计费用时，命中净赚 9 份，未命中亏 1 份，故盈亏平衡命中率正好是 **10%**。",
            "",
            "| 全部费用/滑点（占本金） | 盈亏平衡命中率 |",
            "|---:|---:|",
        ]
    )
    for cost, rate_value in summary["break_even"]["cost_scenarios"].items():
        lines.append(f"| {cost} | {ratio(rate_value)} |")
    lines.extend(
        [
            "",
            "## 完整性检查",
            "",
            f"- 初始储备美元值覆盖：{coverage['initial_reserve_usd']:,} / {summary['n0']:,}",
            f"- 成交价格覆盖：{coverage['priced_trade_rows']:,} / {coverage['all_trade_rows']:,} = {ratio(coverage['priced_trade_row_rate'])}",
            f"- 成交美元量覆盖：{coverage['usd_priced_trade_rows']:,} / {coverage['all_trade_rows']:,} = {ratio(coverage['usd_priced_trade_row_rate'])}",
            f"- 第 30 天美元量覆盖：{coverage['day30_usd_priced_trade_rows']:,} / {coverage['day30_trade_rows']:,} = {ratio(coverage['day30_usd_priced_trade_row_rate'])}",
            f"- 第 7 天有价格观测：{coverage['p7d_observed']:,} / {summary['n0']:,}",
            f"- 第 30 天有价格观测：{coverage['p30d_observed']:,} / {summary['n0']:,}",
            f"- Standard / Mayhem / 未知：{summary['mode_counts']['standard']:,} / {summary['mode_counts']['mayhem']:,} / {summary['mode_counts']['unknown']:,}",
            f"- 决策级覆盖闸门：{'通过' if coverage['decision_ready'] else '未通过'}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path, help="CSV exported from 01_token_metrics.sql")
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    summary, audited, weekly = summarize(pd.read_csv(args.csv, na_values=["<nil>"]))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=native) + "\n",
        encoding="utf-8",
    )
    (args.out_dir / "report.md").write_text(markdown_report(summary), encoding="utf-8")
    audited.to_csv(args.out_dir / "token_metrics_audited.csv", index=False)
    weekly.to_csv(args.out_dir / "weekly.csv", index=False)
    print(markdown_report(summary))


if __name__ == "__main__":
    main()
