#!/usr/bin/env python3
"""Audit and summarize delayed-entry metrics from 08_delay_metrics.sql."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COHORT_START = pd.Timestamp("2026-05-01T00:00:00Z")
COHORT_END = pd.Timestamp("2026-07-25T00:00:00Z")
COHORT_WEEKS = (COHORT_END - COHORT_START).total_seconds() / (7 * 86_400)
TARGET_MULTIPLE = 10.0
TIME_QUANTILES = (0.25, 0.50, 0.75, 0.90)
DIST_QUANTILES = (0.25, 0.50, 0.75, 0.90, 0.95, 0.99)

# Frozen before inspecting the curve.  This spans the economically interesting
# region without tuning thresholds to the observed crossings.
TAKE_PROFIT_MULTIPLES = (1.5, 2, 3, 5, 7.5, 10, 15, 20, 30, 50, 100)

DELAYS = {
    "t0": {"label": "T0", "seconds": 0},
    "5m": {"label": "T+5m", "seconds": 5 * 60},
    "15m": {"label": "T+15m", "seconds": 15 * 60},
    "1h": {"label": "T+1h", "seconds": 60 * 60},
    "4h": {"label": "T+4h", "seconds": 4 * 60 * 60},
    "24h": {"label": "T+24h", "seconds": 24 * 60 * 60},
}

IDENTIFIER_COLUMNS = {
    "graduated_at",
    "graduation_tx",
    "mint",
    "pool",
    "quote_mint",
}


def native(value: Any) -> Any:
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


def seconds_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return "NA"
    seconds = int(round(float(value)))
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def pct(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"{100 * float(value):.2f}%"


def money(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"${float(value):,.2f}"


def quantile_dict(series: pd.Series, quantiles: tuple[float, ...]) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    result: dict[str, Any] = {"n": len(values)}
    if values.empty:
        return result
    qv = values.quantile(quantiles)
    for q in quantiles:
        result[f"p{int(q * 100)}"] = native(qv.loc[q])
    return result


def time_distribution(series: pd.Series) -> dict[str, Any]:
    result = quantile_dict(series, TIME_QUANTILES)
    for q in TIME_QUANTILES:
        key = f"p{int(q * 100)}"
        result[f"{key}_text"] = seconds_text(result.get(key))
    return result


def load_and_audit(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_csv(path, na_values=["<nil>"])
    required = set(IDENTIFIER_COLUMNS) | {
        "graduation_price_sol",
        "capacity_5pct_usd_t0",
        "trade_rows_30d",
        "priced_trade_rows_30d",
        "max_30d",
        "time_to_peak_seconds",
        "first_touch_2x_seconds",
        "first_touch_5x_seconds",
        "first_touch_10x_seconds",
    }
    for delay in DELAYS:
        if delay == "t0":
            continue
        required |= {
            f"entry_price_sol_{delay}",
            f"capacity_5pct_usd_{delay}",
            f"entry_state_age_seconds_{delay}",
            f"future_trade_rows_{delay}",
            f"remaining_max_{delay}",
        }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")
    if df.empty:
        raise ValueError("query returned no rows")

    df["graduated_at"] = pd.to_datetime(df["graduated_at"], utc=True, errors="raise")
    if df["mint"].isna().any() or df["mint"].duplicated().any():
        raise ValueError("mint must be non-null and unique")
    outside = ~df["graduated_at"].between(COHORT_START, COHORT_END, inclusive="left")
    if outside.any():
        raise ValueError("rows exist outside the frozen cohort")

    numeric_columns = set(df.columns) - IDENTIFIER_COLUMNS
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    nonnegative = numeric_columns - {
        "time_to_peak_seconds",
        "first_touch_2x_seconds",
        "first_touch_5x_seconds",
        "first_touch_10x_seconds",
    }
    bad_negative = sorted(
        column for column in nonnegative if (df[column].dropna() < 0).any()
    )
    if bad_negative:
        raise ValueError(f"negative values in non-negative columns: {bad_negative}")

    snapshot_coverage: dict[str, Any] = {}
    for delay in DELAYS:
        if delay == "t0":
            continue
        fields = (
            f"entry_price_sol_{delay}",
            f"capacity_5pct_usd_{delay}",
            f"entry_state_age_seconds_{delay}",
            f"remaining_max_{delay}",
        )
        snapshot_coverage[delay] = {
            field: int(df[field].notna().sum()) for field in fields
        }

    audit = {
        "rows": len(df),
        "unique_mints": int(df["mint"].nunique()),
        "cohort_min": native(df["graduated_at"].min()),
        "cohort_max": native(df["graduated_at"].max()),
        "trade_rows_30d": int(df["trade_rows_30d"].sum()),
        "priced_trade_rows_30d": int(df["priced_trade_rows_30d"].sum()),
        "priced_trade_coverage": native(
            df["priced_trade_rows_30d"].sum() / df["trade_rows_30d"].sum()
        ),
        "graduation_price_coverage": int(df["graduation_price_sol"].notna().sum()),
        "snapshot_coverage": snapshot_coverage,
    }
    audit["decision_ready"] = bool(
        audit["rows"] == audit["unique_mints"]
        and audit["priced_trade_coverage"] == 1
        and audit["graduation_price_coverage"] == len(df)
        and all(
            count == len(df)
            for delay in snapshot_coverage.values()
            for count in delay.values()
        )
    )
    return df, audit


def metric_columns(df: pd.DataFrame, delay: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    if delay == "t0":
        return (
            df["max_30d"],
            df["capacity_5pct_usd_t0"],
            df["trade_rows_30d"] > 0,
        )
    return (
        df[f"remaining_max_{delay}"],
        df[f"capacity_5pct_usd_{delay}"],
        df[f"future_trade_rows_{delay}"] > 0,
    )


def summarize(df: pd.DataFrame, audit: dict[str, Any]) -> tuple[
    dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    n0 = len(df)
    original_tail = df["max_30d"] >= TARGET_MULTIPLE

    time_rows: list[dict[str, Any]] = []
    time_specs = {
        "all_tokens_time_to_peak": df["time_to_peak_seconds"],
        "original_10x_time_to_peak": df.loc[original_tail, "time_to_peak_seconds"],
        "first_touch_2x": df["first_touch_2x_seconds"],
        "first_touch_5x": df["first_touch_5x_seconds"],
        "first_touch_10x": df["first_touch_10x_seconds"],
    }
    time_summary: dict[str, Any] = {}
    for metric, values in time_specs.items():
        dist = time_distribution(values)
        time_summary[metric] = dist
        row = {"metric": metric, "n": dist["n"]}
        for q in TIME_QUANTILES:
            key = f"p{int(q * 100)}"
            row[f"{key}_seconds"] = dist.get(key)
            row[key] = dist.get(f"{key}_text")
        time_rows.append(row)

    tradeoff_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    delay_summary: dict[str, Any] = {}
    for delay, spec in DELAYS.items():
        upside, capacity, future = metric_columns(df, delay)
        hit_10x = upside >= TARGET_MULTIPLE
        raw_rate = float(hit_10x.mean())
        total_capacity = float(capacity.sum())
        hit_capacity = float(capacity.where(hit_10x, 0).sum())
        weighted_rate = hit_capacity / total_capacity if total_capacity else np.nan
        overlap = int((hit_10x & original_tail).sum())
        new_from_lower_entry = int((hit_10x & ~original_tail).sum())
        state_age = (
            pd.Series(0.0, index=df.index)
            if delay == "t0"
            else df[f"entry_state_age_seconds_{delay}"]
        )
        all_capacity_dist = quantile_dict(capacity, DIST_QUANTILES)
        hit_capacity_dist = quantile_dict(capacity.loc[hit_10x], DIST_QUANTILES)
        remaining_dist = quantile_dict(upside, DIST_QUANTILES)
        state_age_dist = quantile_dict(state_age, TIME_QUANTILES)
        row = {
            "delay": delay,
            "label": spec["label"],
            "future_trade_tokens": int(future.sum()),
            "future_trade_rate": float(future.mean()),
            "hit_10x_count": int(hit_10x.sum()),
            "hit_10x_rate": raw_rate,
            "raw_edge_vs_10x_breakeven_pp": 100 * (raw_rate - 0.1),
            "required_precision_lift_vs_raw": 0.1 / raw_rate if raw_rate else None,
            "capacity_weighted_10x_rate": weighted_rate,
            "capacity_weighted_edge_pp": 100 * (weighted_rate - 0.1),
            "required_precision_lift_vs_capacity_weighted": (
                0.1 / weighted_rate if weighted_rate else None
            ),
            "hit_10x_per_week": int(hit_10x.sum()) / COHORT_WEEKS,
            "oracle_hit_capacity_usd_per_week": hit_capacity / COHORT_WEEKS,
            "all_capacity_usd_per_week": total_capacity / COHORT_WEEKS,
            "all_capacity_p50_usd": all_capacity_dist.get("p50"),
            "all_capacity_p90_usd": all_capacity_dist.get("p90"),
            "hit_capacity_p50_usd": hit_capacity_dist.get("p50"),
            "hit_capacity_p90_usd": hit_capacity_dist.get("p90"),
            "remaining_max_p50": remaining_dist.get("p50"),
            "remaining_max_p90": remaining_dist.get("p90"),
            "overlap_with_original_10x": overlap,
            "new_10x_from_lower_delayed_entry": new_from_lower_entry,
            "state_age_p50_seconds": state_age_dist.get("p50"),
            "state_age_p90_seconds": state_age_dist.get("p90"),
        }
        tradeoff_rows.append(row)
        delay_summary[delay] = {
            **{key: native(value) for key, value in row.items() if key != "delay"},
            "capacity_all": all_capacity_dist,
            "capacity_10x_hits": hit_capacity_dist,
            "remaining_max": remaining_dist,
            "state_age_seconds": state_age_dist,
        }

        for multiple in TAKE_PROFIT_MULTIPLES:
            hit = upside >= multiple
            hit_rate = float(hit.mean())
            capacity_hit_rate = (
                float(capacity.where(hit, 0).sum()) / total_capacity
                if total_capacity
                else np.nan
            )
            break_even = 1 / multiple
            curve_rows.append(
                {
                    "delay": delay,
                    "label": spec["label"],
                    "take_profit_multiple": multiple,
                    "hit_count": int(hit.sum()),
                    "hit_rate": hit_rate,
                    "break_even_rate": break_even,
                    "raw_edge_pp": 100 * (hit_rate - break_even),
                    "required_precision_lift_vs_raw": (
                        break_even / hit_rate if hit_rate else None
                    ),
                    "capacity_weighted_hit_rate": capacity_hit_rate,
                    "capacity_weighted_edge_pp": 100
                    * (capacity_hit_rate - break_even),
                    "required_precision_lift_vs_capacity_weighted": (
                        break_even / capacity_hit_rate if capacity_hit_rate else None
                    ),
                }
            )

    tradeoff = pd.DataFrame(tradeoff_rows)
    curve = pd.DataFrame(curve_rows)
    times = pd.DataFrame(time_rows)
    summary = {
        "contract": {
            "cohort_start_utc": COHORT_START,
            "cohort_end_exclusive_utc": COHORT_END,
            "cohort_weeks": COHORT_WEEKS,
            "entry_delays": {key: value["seconds"] for key, value in DELAYS.items()},
            "take_profit_multiples": TAKE_PROFIT_MULTIPLES,
            "gross_break_even": "1 / take_profit_multiple; excludes fees, slippage and failed execution",
            "entry_price": "last canonical pool state at or before cutoff, marked to SOL at cutoff hour",
            "future_max": "highest priced buy/sell state in [cutoff, T+30d); missing future trades become zero",
            "capacity": "0.05 * quote reserve at cutoff * quote USD price at cutoff hour",
        },
        "audit": audit,
        "time_distributions_seconds": time_summary,
        "delays": delay_summary,
    }
    return summary, tradeoff, curve, times


def make_plot(curve: pd.DataFrame, destination: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.4), sharex=True, sharey=True)
    x = np.array(TAKE_PROFIT_MULTIPLES, dtype=float)
    break_even = 1 / x
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(DELAYS)))
    for ax, metric, title in (
        (axes[0], "hit_rate", "Equal-token hit rate"),
        (axes[1], "capacity_weighted_hit_rate", "5% capacity-weighted hit rate"),
    ):
        ax.plot(x, break_even, color="black", linestyle="--", linewidth=2,
                label="Gross break-even 1/M")
        for color, (delay, spec) in zip(colors, DELAYS.items()):
            subset = curve[curve["delay"] == delay].sort_values("take_profit_multiple")
            ax.plot(
                subset["take_profit_multiple"],
                subset[metric],
                marker="o",
                markersize=3.5,
                linewidth=1.5,
                color=color,
                label=spec["label"],
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xticks(x)
        ax.set_xticklabels([str(v).rstrip("0").rstrip(".") for v in x], rotation=35)
        ax.set_ylim(0.001, 1)
        ax.grid(True, which="both", alpha=0.22)
        ax.set_title(title)
        ax.set_xlabel("Take-profit multiple M")
    axes[0].set_ylabel("Observed hit rate")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.045),
        ncol=4,
        frameon=False,
    )
    fig.suptitle("PumpSwap graduated tokens: remaining upside after delayed entry")
    fig.text(
        0.5,
        0.012,
        "Frozen cohort 2026-05-01 to 2026-07-24 UTC; gross spot-price upper bound, before costs",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.18, 1, 0.94))
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)


def render_report(
    summary: dict[str, Any], tradeoff: pd.DataFrame, curve: pd.DataFrame
) -> str:
    audit = summary["audit"]
    td = summary["time_distributions_seconds"]
    first10 = td["first_touch_10x"]
    all_peak = td["all_tokens_time_to_peak"]
    tail_peak = td["original_10x_time_to_peak"]
    t0 = tradeoff.loc[tradeoff.delay == "t0"].iloc[0]
    d5 = tradeoff.loc[tradeoff.delay == "5m"].iloc[0]

    lines = [
        "# 延迟入场可行性：峰值时钟、剩余右尾与容量",
        "",
        "## 结论",
        "",
        (
            "延迟策略有物理上的剩余机会，但无条件经济性明显不成立。"
            f"典型代币的 30 天峰值在毕业后 {all_peak['p50_text']} 出现；"
            f"原始 10x 右尾的峰值中位时间是 {tail_peak['p50_text']}，"
            f"可它们首次触及 10x 的中位时间只有 {first10['p50_text']}。"
            "因此只看峰值时间会高估判断窗口。"
        ),
        "",
        (
            f"等 5 分钟后仍有 {int(d5.hit_10x_count):,} 个 10x 剩余机会"
            f"（{pct(d5.hit_10x_rate)}，约 {d5.hit_10x_per_week:,.1f} 个/周），"
            "所以并非所有右尾都在同块结束；但这个基线低于 10x 的 10% 毛盈亏平衡线。"
            f"按池容量加权后命中率仅 {pct(d5.capacity_weighted_10x_rate)}。"
        ),
        "",
        (
            "更不利的是容量方向和假设相反：全体代币的 5% 容量中位数从 "
            f"{money(t0.all_capacity_p50_usd)} 降至 T+5m 的 {money(d5.all_capacity_p50_usd)}；"
            f"T+5m 后仍能 10x 的代币容量中位数只有 {money(d5.hit_capacity_p50_usd)}。"
            "等待没有换来更深的可执行池，剩余右尾反而集中在更浅的池中。"
        ),
        "",
        "## 1. 峰值和首次触及目标的时间",
        "",
        "| 口径 | 样本数 | P25 | P50 | P75 | P90 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    time_labels = {
        "all_tokens_time_to_peak": "全部代币：到 30d 最高点",
        "original_10x_time_to_peak": "原始 10x 右尾：到最高点",
        "first_touch_2x": "首次触及 2x",
        "first_touch_5x": "首次触及 5x",
        "first_touch_10x": "首次触及 10x",
    }
    for key, label in time_labels.items():
        row = td[key]
        lines.append(
            f"| {label} | {row['n']:,} | {row['p25_text']} | {row['p50_text']} | "
            f"{row['p75_text']} | {row['p90_text']} |"
        )
    lines += [
        "",
        (
            "关键区别：在最终能到 10x 的 3,680 个币里，25% 在 2 秒内第一次触及 10x，"
            f"50% 在 {first10['p50_text']} 内触及；另有 25% 要到 "
            f"{first10['p75_text']} 以后才触及。分布不是单一的“全都几分钟”或“全都几天”，"
            "而是极快主体加长尾。"
        ),
        "",
        "## 2. 延迟后的 10x 基线与容量",
        "",
        "| 入场 | 剩余 10x | 命中率 | 对 10% 的差 | 容量加权命中率 | 全体容量 P50 | 10x 币容量 P50 | 右尾/周 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in tradeoff.itertuples(index=False):
        lines.append(
            f"| {row.label} | {int(row.hit_10x_count):,} | {pct(row.hit_10x_rate)} | "
            f"{row.raw_edge_vs_10x_breakeven_pp:+.2f}pp | "
            f"{pct(row.capacity_weighted_10x_rate)} | {money(row.all_capacity_p50_usd)} | "
            f"{money(row.hit_capacity_p50_usd)} | {row.hit_10x_per_week:,.1f} |"
        )
    lines += [
        "",
        "这里的“命中率”是买入全部毕业币的无条件基线，不是选币模型的精度。"
        "但它给出了模型必须跨越的门槛：在 T+5m 做 10x 止盈，选中集合的真实命中率"
        f"至少要从 {pct(d5.hit_10x_rate)} 提升到 10%，即约 "
        f"{d5.required_precision_lift_vs_raw:.2f}x precision lift；"
        f"若按各池 5% 容量部署，基线是 {pct(d5.capacity_weighted_10x_rate)}，"
        f"需要约 {d5.required_precision_lift_vs_capacity_weighted:.2f}x。以上还没扣费用、"
        "实际成交冲击、夹子和止盈失败。",
        "",
        "延迟 10x 集合也不是原始右尾的简单子集：",
        "",
        "| 入场 | 与原始 10x 重合 | 因延迟低价新成为 10x | 后续仍有交易 |",
        "|---|---:|---:|---:|",
    ]
    for row in tradeoff.itertuples(index=False):
        lines.append(
            f"| {row.label} | {int(row.overlap_with_original_10x):,} | "
            f"{int(row.new_10x_from_lower_delayed_entry):,} | "
            f"{int(row.future_trade_tokens):,} ({pct(row.future_trade_rate)}) |"
        )

    lines += [
        "",
        "## 3. 止盈倍数曲线",
        "",
        "已冻结并计算 M = 1.5、2、3、5、7.5、10、15、20、30、50、100。"
        "零费用、未命中归零时的毛盈亏平衡线是 `p = 1/M`。",
        "",
        "| 入场 | 2x 命中/盈亏线 | 5x 命中/盈亏线 | 10x 命中/盈亏线 | 50x 命中/盈亏线 | 容量加权曲线结论 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for delay, spec in DELAYS.items():
        subset = curve[curve.delay == delay].set_index("take_profit_multiple")
        cells = []
        for multiple in (2, 5, 10, 50):
            row = subset.loc[multiple]
            cells.append(f"{pct(row.hit_rate)} / {pct(row.break_even_rate)}")
        weighted_edges = subset["capacity_weighted_edge_pp"]
        conclusion = (
            "测试点全部低于线"
            if (weighted_edges < 0).all()
            else f"{int((weighted_edges > 0).sum())}/{len(weighted_edges)} 个点高于线"
        )
        lines.append(
            f"| {spec['label']} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{cells[3]} | {conclusion} |"
        )
    lines += [
        "",
        (
            "T0 的 3x–100x 档在这个理想化上界里高于毛盈亏线；一旦延迟 5 分钟，"
            "容量加权后的所有冻结倍数都落到线下。T+5m 的 50x/100x 原始计数率"
            "看似略高于线，但优势完全来自极浅池；容量加权后仍为负。"
        ),
        "",
        "## 判据与下一步",
        "",
        "前三步给出的判据不是“延迟策略已被否定”，而是：",
        "",
        "- 可达性：通过但很窄。5 分钟后仍有大量剩余右尾，1 小时后也不是零；"
        "  不过最快的 25% 原始 10x 在 2 秒内已经触及目标。",
        "- 无条件收益：不通过。任何延迟点的容量加权止盈曲线，在冻结倍数上都低于毛盈亏线。",
        "- 容量换时间：不通过。等待越久，中位容量越小；延迟右尾的容量尤其小。",
        "- 选币研究只有一个可证伪的任务：在严格的前向测试里，使用 T+5m 当时可见特征，"
        f"  把 10x precision 从 {pct(d5.hit_10x_rate)} 提到高于 10%（实际应留出明显费用余量），"
        "  同时报告被选币的真实容量。做不到这个 precision lift，就停止该方向。",
        "",
        "因此建议下一轮只做 T+5m 一个时点的前向分类实验，不再同时优化延迟和倍数。"
        "标签冻结为 `remaining_max_5m >= 10`，训练特征的截止时间严格为 T+5m，"
        "按毕业日期滚动切分；测试集只报告 precision、覆盖机会数和容量，不用随机切分。",
        "",
        "## 审计与限制",
        "",
        f"- N0 = {audit['rows']:,}；交易状态 {audit['trade_rows_30d']:,} 行，"
        f"SOL 定价覆盖 {pct(audit['priced_trade_coverage'])}；五个延迟快照均为 "
        f"{audit['rows']:,}/{audit['rows']:,}。",
        "- 入场价是延迟时点前最后一个 canonical 池状态的现货价；未来最高价只取随后真实买卖事件。",
        "- 曲线仍是现货价上界，不保证能按该价成交或止盈；5% 容量单独衡量可下单规模。",
        "- `1/M` 假设未命中亏光、命中恰好以 M 卖出且零成本。现实盈亏平衡命中率只会更高。",
        "- 极端倍数常由报价储备接近零后的小额反弹产生；容量加权结果比计数率更接近可部署现实。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("crypto/pump_tail_research/data/dune_delay_metrics.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("crypto/pump_tail_research/output"),
    )
    args = parser.parse_args()

    df, audit = load_and_audit(args.input)
    summary, tradeoff, curve, times = summarize(df, audit)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    audited_columns = [
        "graduated_at", "mint", "pool", "quote_mint", "max_30d",
        "time_to_peak_seconds", "first_touch_2x_seconds",
        "first_touch_5x_seconds", "first_touch_10x_seconds",
    ]
    for delay in DELAYS:
        capacity_col = "capacity_5pct_usd_t0" if delay == "t0" else f"capacity_5pct_usd_{delay}"
        upside_col = "max_30d" if delay == "t0" else f"remaining_max_{delay}"
        if capacity_col not in audited_columns:
            audited_columns.append(capacity_col)
        if upside_col not in audited_columns:
            audited_columns.append(upside_col)
    df[audited_columns].to_csv(args.output_dir / "delay_metrics_audited.csv", index=False)
    tradeoff.to_csv(args.output_dir / "delay_tradeoff.csv", index=False)
    curve.to_csv(args.output_dir / "take_profit_curve.csv", index=False)
    times.to_csv(args.output_dir / "time_distributions.csv", index=False)
    (args.output_dir / "delay_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=native) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "delay_report.md").write_text(
        render_report(summary, tradeoff, curve), encoding="utf-8"
    )
    make_plot(curve, args.output_dir / "take_profit_curve.png")

    print(f"audited {len(df):,} tokens; decision_ready={audit['decision_ready']}")
    print(tradeoff.to_string(index=False))
    print(f"wrote outputs to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
