#!/usr/bin/env python3
"""Analyze the frozen T+5m15s first-passage execution experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RANDOM_STATE = 20260824
BOOTSTRAP_DRAWS = 10_000
POSITIONS = (250, 500)
TAKE_PROFITS = (1.5, 2.0, 3.0, 5.0)
STOP_FLOORS = (0.7, 0.6, 0.5, 0.4)
TIMEOUTS = {"1h": 3_600, "4h": 14_400, "24h": 86_400}
COHORT_WEEKS = 85 / 7

TP_KEY = {1.5: "15", 2.0: "2", 3.0: "3", 5.0: "5"}
SL_KEY = {0.7: "07", 0.6: "06", 0.5: "05", 0.4: "04"}


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


def pct(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"{100 * float(value):.2f}%"


def money(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"${float(value):,.2f}"


def load_and_audit(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    header = pd.read_csv(path, nrows=0)
    order_columns = [column for column in header.columns if column.endswith("_order_250") or column.endswith("_order_500")]
    dtype = {column: "string" for column in order_columns}
    df = pd.read_csv(path, na_values=["<nil>"], dtype=dtype)
    if df.empty or df["mint"].duplicated().any() or df["mint"].isna().any():
        raise ValueError("first-passage rows must be non-empty with unique, non-null mints")
    df["graduated_at"] = pd.to_datetime(df["graduated_at"], utc=True, errors="raise")
    df["execution_at"] = pd.to_datetime(df["execution_at"], utc=True, errors="raise")
    df["date"] = df["graduated_at"].dt.floor("D")
    for column in order_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
    identifier_columns = {"graduated_at", "execution_at", "date", "mint", "pool", "quote_mint", *order_columns}
    for column in set(df.columns) - identifier_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if (df["entry_capacity_5pct_usd"] < 250).any():
        raise ValueError("query emitted an entry below the frozen $250 capacity floor")
    core = [
        "entry_capacity_5pct_usd", "entry_chain_fee_bps",
        "entry_state_age_seconds", "immediate_roundtrip_250",
        "path_event_rows_24h", "timeout_1h_return_250",
        "timeout_4h_return_250", "timeout_24h_return_250",
    ]
    if df[core].isna().any().any():
        raise ValueError("missing core entry/path fields")
    if (df["path_event_rows_24h"] <= 0).any():
        raise ValueError("an eligible entry has no post-entry path events")
    eligible_500 = df["entry_capacity_5pct_usd"] >= 500
    if df.loc[eligible_500, "immediate_roundtrip_500"].isna().any():
        raise ValueError("missing $500 entry value for a $500-capacity token")

    return_columns = [column for column in df.columns if "return_" in column or column.startswith("immediate_roundtrip")]
    if any((df[column].dropna() < 0).any() for column in return_columns):
        raise ValueError("negative liquidation return found")

    audit = {
        "rows_capacity_ge_250": len(df),
        "rows_capacity_ge_500": int(eligible_500.sum()),
        "unique_mints": int(df["mint"].nunique()),
        "path_event_rows_24h": int(df["path_event_rows_24h"].sum()),
        "zero_path_tokens": int((df["path_event_rows_24h"] == 0).sum()),
        "entry_state_age_seconds": {
            "p50": native(df["entry_state_age_seconds"].quantile(0.5)),
            "p90": native(df["entry_state_age_seconds"].quantile(0.9)),
            "p99": native(df["entry_state_age_seconds"].quantile(0.99)),
            "max": native(df["entry_state_age_seconds"].max()),
        },
        "entry_chain_fee_bps": {
            "p50": native(df["entry_chain_fee_bps"].quantile(0.5)),
            "p90": native(df["entry_chain_fee_bps"].quantile(0.9)),
            "min": native(df["entry_chain_fee_bps"].min()),
            "max": native(df["entry_chain_fee_bps"].max()),
        },
        "immediate_roundtrip": {
            "position_250_p50": native(df["immediate_roundtrip_250"].median()),
            "position_500_p50": native(df.loc[eligible_500, "immediate_roundtrip_500"].median()),
        },
    }
    return df, audit


def simulate_combo(
    df: pd.DataFrame,
    position: int,
    take_profit: float,
    stop_floor: float,
    timeout_name: str,
) -> pd.DataFrame:
    eligible = df[df["entry_capacity_5pct_usd"] >= position].copy()
    tp_key = TP_KEY[take_profit]
    sl_key = SL_KEY[stop_floor]
    horizon_seconds = TIMEOUTS[timeout_name]
    tp_order = eligible[f"tp{tp_key}_order_{position}"]
    tp_seconds = eligible[f"tp{tp_key}_seconds_{position}"]
    sl_order = eligible[f"sl{sl_key}_order_{position}"]
    sl_seconds = eligible[f"sl{sl_key}_seconds_{position}"]

    tp_valid = tp_order.notna() & tp_seconds.notna() & (tp_seconds <= horizon_seconds)
    sl_valid = sl_order.notna() & sl_seconds.notna() & (sl_seconds <= horizon_seconds)
    # A strict comparison gives the frozen tie-break to the stop.
    tp_first = tp_valid & (~sl_valid | (tp_order < sl_order))
    sl_first = sl_valid & (~tp_first)
    timeout = ~(tp_first | sl_first)

    realized = pd.Series(np.nan, index=eligible.index, dtype=float)
    realized.loc[tp_first] = take_profit
    realized.loc[sl_first] = eligible.loc[sl_first, f"sl{sl_key}_return_{position}"]
    realized.loc[timeout] = eligible.loc[timeout, f"timeout_{timeout_name}_return_{position}"]
    if realized.isna().any() or (realized < 0).any():
        raise ValueError("invalid realized return after trigger resolution")

    exit_reason = pd.Series("timeout", index=eligible.index, dtype="string")
    exit_reason.loc[tp_first] = "take_profit"
    exit_reason.loc[sl_first] = "stop_loss"
    exit_seconds = pd.Series(horizon_seconds, index=eligible.index, dtype=float)
    exit_seconds.loc[tp_first] = tp_seconds.loc[tp_first]
    exit_seconds.loc[sl_first] = sl_seconds.loc[sl_first]

    result = eligible[
        ["graduated_at", "date", "mint", "entry_capacity_5pct_usd"]
    ].copy()
    result["position_usd"] = position
    result["take_profit"] = take_profit
    result["stop_floor"] = stop_floor
    result["timeout"] = timeout_name
    result["exit_reason"] = exit_reason
    result["exit_seconds"] = exit_seconds
    result["gross_multiple"] = realized
    result["roi"] = realized - 1.0
    return result


def daily_block_bootstrap(frame: pd.DataFrame) -> tuple[float, dict[str, Any]]:
    dates = pd.DatetimeIndex(sorted(pd.unique(frame["date"])))
    daily = (
        frame.groupby("date")["roi"]
        .agg(["sum", "count"])
        .reindex(dates, fill_value=0)
    )
    sums = daily["sum"].to_numpy(float)
    counts = daily["count"].to_numpy(float)
    rng = np.random.default_rng(RANDOM_STATE)
    indices = rng.integers(0, len(dates), size=(BOOTSTRAP_DRAWS, len(dates)))
    boot_sum = sums[indices].sum(axis=1)
    boot_count = counts[indices].sum(axis=1)
    values = boot_sum / boot_count
    lower = float(np.quantile(values, 0.05))
    return lower, {
        "draws": BOOTSTRAP_DRAWS,
        "days": len(dates),
        "p05": lower,
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def segment_rois(frame: pd.DataFrame) -> dict[str, float | None]:
    segments = {
        "may": ("2026-05-01", "2026-06-01"),
        "june": ("2026-06-01", "2026-07-01"),
        "july": ("2026-07-01", "2026-07-25"),
    }
    result: dict[str, float | None] = {}
    for name, (start, end) in segments.items():
        mask = (
            (frame["graduated_at"] >= pd.Timestamp(start, tz="UTC"))
            & (frame["graduated_at"] < pd.Timestamp(end, tz="UTC"))
        )
        result[name] = native(frame.loc[mask, "roi"].mean())
    return result


def summarize_strategy(frame: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    lower, bootstrap = daily_block_bootstrap(frame)
    segments = segment_rois(frame)
    reason_counts = frame["exit_reason"].value_counts()
    summary = {
        "entries": len(frame),
        "mean_gross_multiple": float(frame["gross_multiple"].mean()),
        "mean_roi": float(frame["roi"].mean()),
        "median_roi": float(frame["roi"].median()),
        "roi_p10": float(frame["roi"].quantile(0.10)),
        "roi_p90": float(frame["roi"].quantile(0.90)),
        "bootstrap_95_one_sided_lower": lower,
        "segments": segments,
        "positive_segments": int(sum(value is not None and value > 0 for value in segments.values())),
        "take_profit_count": int(reason_counts.get("take_profit", 0)),
        "stop_loss_count": int(reason_counts.get("stop_loss", 0)),
        "timeout_count": int(reason_counts.get("timeout", 0)),
        "take_profit_rate": float((frame["exit_reason"] == "take_profit").mean()),
        "stop_loss_rate": float((frame["exit_reason"] == "stop_loss").mean()),
        "timeout_rate": float((frame["exit_reason"] == "timeout").mean()),
        "exit_seconds_p50": float(frame["exit_seconds"].median()),
        "exit_seconds_p90": float(frame["exit_seconds"].quantile(0.90)),
        "capital_usd_per_week": float(
            len(frame) * float(frame["position_usd"].iloc[0]) / COHORT_WEEKS
        ),
    }
    return summary, bootstrap


def analyze_grid(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    primary_trades: pd.DataFrame | None = None
    primary_summary: dict[str, Any] | None = None
    primary_bootstrap: dict[str, Any] | None = None
    for position in POSITIONS:
        for take_profit in TAKE_PROFITS:
            for stop_floor in STOP_FLOORS:
                for timeout_name in TIMEOUTS:
                    trades = simulate_combo(
                        df, position, take_profit, stop_floor, timeout_name
                    )
                    strategy, bootstrap = summarize_strategy(trades)
                    qualifies = bool(
                        strategy["mean_roi"] > 0
                        and strategy["bootstrap_95_one_sided_lower"] > 0
                        and strategy["positive_segments"] >= 2
                    )
                    rows.append(
                        {
                            "position_usd": position,
                            "capacity_floor_usd": position,
                            "take_profit": take_profit,
                            "stop_floor": stop_floor,
                            "timeout": timeout_name,
                            **strategy,
                            "diagnostic_qualifies_for_fresh_test": qualifies,
                        }
                    )
                    if (
                        position == 500
                        and take_profit == 2.0
                        and stop_floor == 0.5
                        and timeout_name == "4h"
                    ):
                        primary_trades = trades
                        primary_summary = strategy
                        primary_bootstrap = bootstrap
    if primary_trades is None or primary_summary is None or primary_bootstrap is None:
        raise AssertionError("frozen primary strategy was not evaluated")

    checks = [
        {
            "name": "entries_at_least_100",
            "value": primary_summary["entries"],
            "passed": primary_summary["entries"] >= 100,
        },
        {
            "name": "mean_roi_above_zero",
            "value": primary_summary["mean_roi"],
            "passed": primary_summary["mean_roi"] > 0,
        },
        {
            "name": "bootstrap_lower_above_zero",
            "value": primary_summary["bootstrap_95_one_sided_lower"],
            "passed": primary_summary["bootstrap_95_one_sided_lower"] > 0,
        },
        {
            "name": "at_least_two_positive_segments",
            "value": primary_summary["positive_segments"],
            "passed": primary_summary["positive_segments"] >= 2,
        },
        {
            "name": "weekly_capital_at_least_10000",
            "value": primary_summary["capital_usd_per_week"],
            "passed": primary_summary["capital_usd_per_week"] >= 10_000,
        },
    ]
    primary = {
        **primary_summary,
        "bootstrap": primary_bootstrap,
        "checks": checks,
        "passed": bool(all(check["passed"] for check in checks)),
    }
    return pd.DataFrame(rows), primary, primary_trades


def make_plot(grid: pd.DataFrame, destination: Path) -> None:
    subset = grid[(grid.position_usd == 500) & (grid.timeout == "4h")]
    mean_pivot = subset.pivot(index="stop_floor", columns="take_profit", values="mean_roi")
    lower_pivot = subset.pivot(
        index="stop_floor", columns="take_profit",
        values="bootstrap_95_one_sided_lower",
    )
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharex=True, sharey=True)
    for ax, data, title in (
        (axes[0], mean_pivot, "Mean net ROI"),
        (axes[1], lower_pivot, "One-sided 95% bootstrap lower"),
    ):
        image = ax.imshow(data.to_numpy() * 100, cmap="RdYlGn", vmin=-30, vmax=30,
                          aspect="auto", origin="lower")
        ax.set_xticks(range(len(data.columns)), [f"{v:g}x" for v in data.columns])
        ax.set_yticks(range(len(data.index)), [f"{100*(1-v):.0f}%" for v in data.index])
        ax.set_xlabel("Take profit")
        ax.set_title(title)
        for i in range(len(data.index)):
            for j in range(len(data.columns)):
                ax.text(j, i, f"{100*data.iloc[i,j]:.1f}%", ha="center", va="center",
                        fontsize=9)
    axes[0].set_ylabel("Stop loss")
    fig.subplots_adjust(left=0.08, right=0.87, bottom=0.14, top=0.78, wspace=0.18)
    colorbar_axis = fig.add_axes([0.90, 0.18, 0.018, 0.56])
    fig.colorbar(image, cax=colorbar_axis, label="ROI (%)")
    fig.suptitle("Position USD 500, capacity at least USD 500, 4h timeout")
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)


def render_report(
    audit: dict[str, Any], grid: pd.DataFrame, primary: dict[str, Any]
) -> str:
    verdict = "通过（仍须新样本确认）" if primary["passed"] else "不通过"
    qualified = grid[grid.diagnostic_qualifies_for_fresh_test].sort_values(
        "bootstrap_95_one_sided_lower", ascending=False
    )
    top = grid.sort_values("mean_roi", ascending=False).head(10)
    lines = [
        "# T+5m 首触发止盈/止损执行实验",
        "",
        f"## 主策略结论：{verdict}",
        "",
        (
            f"主策略共 {primary['entries']:,} 个可执行入场，平均净ROI "
            f"{pct(primary['mean_roi'])}，按UTC日期block bootstrap的单侧95%下界 "
            f"{pct(primary['bootstrap_95_one_sided_lower'])}。"
        ),
        "",
        (
            f"退出构成：止盈 {primary['take_profit_count']:,}"
            f"（{pct(primary['take_profit_rate'])}），止损 {primary['stop_loss_count']:,}"
            f"（{pct(primary['stop_loss_rate'])}），超时 {primary['timeout_count']:,}"
            f"（{pct(primary['timeout_rate'])}）。每周名义可部署本金约 "
            f"{money(primary['capital_usd_per_week'])}。"
        ),
        "",
        "## 冻结主策略",
        "",
        "`T+5m15s / $500 / 容量≥$500 / TP 2x / SL -50% / 4h超时`",
        "",
        "| 裁决条件 | 数值 | 通过 |",
        "|---|---:|---:|",
    ]
    for check in primary["checks"]:
        value = check["value"]
        formatted = pct(value) if "roi" in check["name"] or "bootstrap" in check["name"] else f"{value:,.2f}"
        lines.append(f"| `{check['name']}` | {formatted} | {'是' if check['passed'] else '否'} |")
    lines += [
        "",
        "| 时间段 | 平均ROI |",
        "|---|---:|",
    ]
    for segment, value in primary["segments"].items():
        lines.append(f"| {segment} | {pct(value)} |")

    lines += [
        "",
        "## 96格诊断",
        "",
        f"同时满足平均ROI>0、bootstrap下界>0、至少两段为正的组合：{len(qualified)}/96。"
        "这些组合只能登记为新样本候选，不能在当前已用于提出止损假设的样本上确认为策略。",
        "",
        "| 仓位 | TP | SL | 超时 | 入场数 | 平均ROI | Bootstrap下界 | 正收益月份 | 候选 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in top.itertuples(index=False):
        lines.append(
            f"| ${int(row.position_usd)} | {row.take_profit:g}x | "
            f"-{100*(1-row.stop_floor):.0f}% | {row.timeout} | {int(row.entries):,} | "
            f"{pct(row.mean_roi)} | {pct(row.bootstrap_95_one_sided_lower)} | "
            f"{int(row.positive_segments)}/3 | "
            f"{'是' if row.diagnostic_qualifies_for_fresh_test else '否'} |"
        )

    lines += [
        "",
        "## 执行审计",
        "",
        f"- 容量≥$250：{audit['rows_capacity_ge_250']:,}；容量≥$500："
        f"{audit['rows_capacity_ge_500']:,}。",
        f"- 聚合了 {audit['path_event_rows_24h']:,} 个入场后交易状态；无路径样本 "
        f"{audit['zero_path_tokens']}。",
        f"- 入场状态年龄P50/P90/P99为 "
        f"{audit['entry_state_age_seconds']['p50']:.0f}s/"
        f"{audit['entry_state_age_seconds']['p90']:.0f}s/"
        f"{audit['entry_state_age_seconds']['p99']:.0f}s。",
        f"- 实际链上费率中位数 {audit['entry_chain_fee_bps']['p50']:.0f} bps，"
        "另在入场和退出各扣100 bps执行损耗。",
        f"- 仅立即买入再卖出的中位剩余价值：$250仓位 "
        f"{pct(audit['immediate_roundtrip']['position_250_p50'])}，$500仓位 "
        f"{pct(audit['immediate_roundtrip']['position_500_p50'])}。",
        "",
        "## 限制",
        "",
        "- 触发后按该链上状态立即成交；真实机器人可能在下一块才成交，止损结果可能更差。",
        "- 模拟计入双边池冲击、逐事件链上费率和额外双边100 bps，但没有把我们的入场永久写入后续历史状态。",
        "- 当前样本已参与策略形成；任何正结果都必须在2026-07-25之后的新成熟样本上复验。",
        "- 96格最佳值存在多重比较偏差，只有冻结主策略可以直接裁决。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path,
        default=Path("crypto/pump_tail_research/data/dune_first_passage.csv"),
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("crypto/pump_tail_research/output"),
    )
    args = parser.parse_args()
    df, audit = load_and_audit(args.input)
    grid, primary, primary_trades = analyze_grid(df)
    summary = {
        "protocol": {
            "execution_delay_seconds_after_t5m": 15,
            "execution_haircut_bps_each_side": 100,
            "positions": POSITIONS,
            "take_profits": TAKE_PROFITS,
            "stop_floors": STOP_FLOORS,
            "timeouts_seconds": TIMEOUTS,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "primary": {
                "position_usd": 500,
                "capacity_floor_usd": 500,
                "take_profit": 2.0,
                "stop_floor": 0.5,
                "timeout": "4h",
            },
        },
        "audit": audit,
        "primary": primary,
        "diagnostic_qualified_count": int(
            grid.diagnostic_qualifies_for_fresh_test.sum()
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    grid.to_csv(args.output_dir / "first_passage_grid.csv", index=False)
    primary_trades.to_csv(
        args.output_dir / "first_passage_primary_trades.csv", index=False
    )
    (args.output_dir / "first_passage_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=native) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "first_passage_report.md").write_text(
        render_report(audit, grid, primary), encoding="utf-8"
    )
    make_plot(grid, args.output_dir / "first_passage_heatmap.png")
    print(json.dumps(primary, ensure_ascii=False, indent=2, default=native))
    print(
        grid.sort_values("mean_roi", ascending=False).head(12).to_string(index=False)
    )
    print(f"wrote outputs to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
