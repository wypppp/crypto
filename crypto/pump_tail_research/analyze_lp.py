#!/usr/bin/env python3
"""Analyze the frozen T+5m15s passive-LP fee-income experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RANDOM_STATE = 20260824
BOOTSTRAP_DRAWS = 10_000
COHORT_WEEKS = 85 / 7
EXECUTION_HAIRCUT_BPS = 100.0
POSITIONS = (500, 1000)
HORIZONS = (1, 4, 24, 168)


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze(root: Path) -> dict[str, str]:
    expected = {}
    for line in (root / "LP_EXPERIMENT.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        expected[name.strip()] = digest
    actual = {name: sha256(root / name) for name in expected}
    mismatches = {name: (expected[name], actual[name]) for name in expected if actual[name] != expected[name]}
    if mismatches:
        raise ValueError(f"frozen protocol/SQL hash mismatch: {mismatches}")
    return actual


def load_and_audit(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_csv(path, na_values=["<nil>"])
    if df.empty or df["mint"].isna().any() or df["mint"].duplicated().any():
        raise ValueError("LP result must have unique, non-null mints")
    time_columns = [column for column in df.columns if column.endswith("_at") or "state_time" in column]
    for column in time_columns:
        df[column] = pd.to_datetime(df[column], utc=True, errors="coerce")
    identifier_columns = {"mint", "pool", "quote_mint", *time_columns}
    for column in set(df.columns) - identifier_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["date"] = df["graduated_at"].dt.floor("D")

    if df["graduated_at"].isna().any() or df["execution_at"].isna().any():
        raise ValueError("invalid graduation/execution timestamp")
    if (df["entry_capacity_5pct_usd"] < 250).any():
        raise ValueError("query emitted an entry below the frozen $250 quote-leg capacity")
    core = [
        "entry_base_reserve", "entry_quote_reserve", "entry_lp_supply",
        "entry_quote_usd", "quote_deposit_500", "base_deposit_500", "lp_tokens_500",
    ]
    if df[core].isna().any().any() or (df[core] <= 0).any().any():
        raise ValueError("missing/nonpositive core LP entry field")
    entry_fraction = df["quote_deposit_500"] / df["entry_quote_reserve"]
    if (entry_fraction > 0.050000001).any():
        raise ValueError("$500 strategy exceeds frozen 5% quote-reserve contribution")
    eligible_1000 = df["entry_capacity_5pct_usd"] >= 500
    cols_1000 = ["quote_deposit_1000", "base_deposit_1000", "lp_tokens_1000"]
    if df.loc[eligible_1000, cols_1000].isna().any().any():
        raise ValueError("missing $1,000 position fields for an eligible pool")

    missing_by_horizon = {}
    for horizon in HORIZONS:
        needed = [
            f"exit_base_reserve_{horizon}h", f"exit_quote_reserve_{horizon}h",
            f"exit_lp_supply_{horizon}h", f"exit_quote_usd_{horizon}h",
            f"exit_chain_fee_bps_{horizon}h",
        ]
        missing_by_horizon[f"{horizon}h"] = int(df[needed].isna().any(axis=1).sum())
        if (df[f"exit_lp_supply_{horizon}h"].dropna() <= 0).any():
            raise ValueError("nonpositive exit LP supply")
        if (df[f"exit_base_reserve_{horizon}h"].dropna() <= 0).any():
            raise ValueError("nonpositive exit base reserve")
        if (df[f"exit_quote_reserve_{horizon}h"].dropna() < 0).any():
            raise ValueError("negative exit quote reserve")

    audit = {
        "rows_capacity_ge_250": len(df),
        "rows_capacity_ge_500": int(eligible_1000.sum()),
        "unique_mints": int(df["mint"].nunique()),
        "missing_exit_fields": missing_by_horizon,
        "entry_quote_contribution_fraction": {
            "p50": native(entry_fraction.median()),
            "p90": native(entry_fraction.quantile(0.90)),
            "max": native(entry_fraction.max()),
        },
        "entry_capacity_usd": {
            "p50": native(df["entry_capacity_5pct_usd"].median()),
            "p90": native(df["entry_capacity_5pct_usd"].quantile(0.90)),
            "max": native(df["entry_capacity_5pct_usd"].max()),
        },
        "entry_chain_fee_bps": {
            "p50": native(df["entry_chain_fee_bps"].median()),
            "p90": native(df["entry_chain_fee_bps"].quantile(0.90)),
            "min": native(df["entry_chain_fee_bps"].min()),
            "max": native(df["entry_chain_fee_bps"].max()),
        },
    }
    return df, audit


def make_cell(df: pd.DataFrame, position: int, horizon: int) -> tuple[pd.DataFrame, int]:
    suffix = str(position)
    eligible = df[df[f"lp_tokens_{suffix}"].notna()].copy()
    required = [
        f"exit_base_reserve_{horizon}h", f"exit_quote_reserve_{horizon}h",
        f"exit_lp_supply_{horizon}h", f"exit_quote_usd_{horizon}h",
        f"exit_chain_fee_bps_{horizon}h", f"exit_state_time_{horizon}h",
    ]
    missing = int(eligible[required].isna().any(axis=1).sum())
    eligible = eligible.dropna(subset=required).copy()

    x_pool = eligible[f"exit_base_reserve_{horizon}h"]
    y_pool = eligible[f"exit_quote_reserve_{horizon}h"]
    lp_supply = eligible[f"exit_lp_supply_{horizon}h"]
    quote_usd = eligible[f"exit_quote_usd_{horizon}h"]
    lp_tokens = eligible[f"lp_tokens_{suffix}"]
    base_deposit = eligible[f"base_deposit_{suffix}"]
    quote_deposit = eligible[f"quote_deposit_{suffix}"]
    haircut = np.maximum(
        0.0,
        1.0
        - (eligible[f"exit_chain_fee_bps_{horizon}h"] + EXECUTION_HAIRCUT_BPS)
        / 10_000.0,
    )

    # Scalable-counterfactual claim: our added LP tokens are absent from the
    # historical supply and reserves, so l/L_hist times historical reserves
    # recovers the added proportional slice in the no-path-change limit.
    claim_scale = lp_tokens / lp_supply
    base_claim = claim_scale * x_pool
    quote_claim = claim_scale * y_pool
    base_liquidation_quote = y_pool * base_claim / (x_pool + base_claim) * haircut
    exit_value = (quote_claim + base_liquidation_quote) * quote_usd

    hodl_base_quote = y_pool * base_deposit / (x_pool + base_deposit) * haircut
    hodl_value = (quote_deposit + hodl_base_quote) * quote_usd
    allocated_fee = eligible[f"allocated_lp_fee_usd_{suffix}_{horizon}h"]

    out = eligible[["graduated_at", "date", "mint", "pool", "entry_capacity_5pct_usd"]].copy()
    out["position_usd"] = position
    out["horizon_hours"] = horizon
    out["claim_scale_vs_historical_pool"] = claim_scale
    out["trade_count"] = eligible[f"trade_count_{horizon}h"]
    out["pool_lp_fee_usd"] = eligible[f"pool_lp_fee_usd_{horizon}h"]
    out["allocated_lp_fee_usd"] = allocated_fee
    out["fee_yield"] = allocated_fee / position
    out["exit_value_usd"] = exit_value
    out["gross_multiple"] = exit_value / position
    out["roi"] = out["gross_multiple"] - 1.0
    out["inventory_rebalance_component"] = out["roi"] - out["fee_yield"]
    out["hodl_value_usd"] = hodl_value
    out["hodl_roi"] = hodl_value / position - 1.0
    out["lp_excess_vs_hodl"] = (exit_value - hodl_value) / position
    out["lp_relative_to_hodl"] = exit_value / hodl_value.replace(0, np.nan) - 1.0
    horizon_time = eligible["execution_at"] + pd.to_timedelta(horizon, unit="h")
    out["exit_state_age_seconds"] = (
        horizon_time - eligible[f"exit_state_time_{horizon}h"]
    ).dt.total_seconds()
    numeric = out.select_dtypes(include=[np.number])
    if np.isinf(numeric.to_numpy()).any() or out[["exit_value_usd", "roi"]].isna().any().any():
        raise ValueError(f"invalid calculated value for ${position}/{horizon}h")
    if (out[["exit_value_usd", "hodl_value_usd", "allocated_lp_fee_usd"]] < 0).any().any():
        raise ValueError("negative exit/HODL/fee value")
    return out, missing


def daily_bootstrap(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    daily = frame.groupby("date")[column].agg(["sum", "count"])
    sums = daily["sum"].to_numpy(float)
    counts = daily["count"].to_numpy(float)
    rng = np.random.default_rng(RANDOM_STATE)
    indices = rng.integers(0, len(daily), size=(BOOTSTRAP_DRAWS, len(daily)))
    values = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    return {
        "draws": BOOTSTRAP_DRAWS,
        "days": len(daily),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def segment_means(frame: pd.DataFrame, column: str) -> dict[str, float | None]:
    bounds = {
        "may": ("2026-05-01", "2026-06-01"),
        "june": ("2026-06-01", "2026-07-01"),
        "july": ("2026-07-01", "2026-07-25"),
    }
    result = {}
    for name, (start, end) in bounds.items():
        mask = (
            (frame["graduated_at"] >= pd.Timestamp(start, tz="UTC"))
            & (frame["graduated_at"] < pd.Timestamp(end, tz="UTC"))
        )
        result[name] = native(frame.loc[mask, column].mean())
    return result


def summarize_cell(frame: pd.DataFrame, missing: int) -> tuple[dict[str, Any], dict[str, Any]]:
    bootstrap = daily_bootstrap(frame, "roi")
    excess_bootstrap = daily_bootstrap(frame, "lp_excess_vs_hodl")
    segments = segment_means(frame, "roi")
    positive_segments = sum(value is not None and value > 0 for value in segments.values())
    row = {
        "entries": len(frame),
        "missing_entries": missing,
        "mean_roi": float(frame["roi"].mean()),
        "median_roi": float(frame["roi"].median()),
        "roi_p10": float(frame["roi"].quantile(0.10)),
        "roi_p25": float(frame["roi"].quantile(0.25)),
        "roi_p75": float(frame["roi"].quantile(0.75)),
        "roi_p90": float(frame["roi"].quantile(0.90)),
        "roi_max": float(frame["roi"].max()),
        "positive_roi_rate": float((frame["roi"] > 0).mean()),
        "bootstrap_95_one_sided_lower": bootstrap["p05"],
        "mean_fee_yield": float(frame["fee_yield"].mean()),
        "median_fee_yield": float(frame["fee_yield"].median()),
        "mean_inventory_rebalance_component": float(frame["inventory_rebalance_component"].mean()),
        "mean_hodl_roi": float(frame["hodl_roi"].mean()),
        "mean_lp_excess_vs_hodl": float(frame["lp_excess_vs_hodl"].mean()),
        "median_lp_excess_vs_hodl": float(frame["lp_excess_vs_hodl"].median()),
        "excess_bootstrap_lower": excess_bootstrap["p05"],
        "mean_allocated_lp_fee_usd": float(frame["allocated_lp_fee_usd"].mean()),
        "median_allocated_lp_fee_usd": float(frame["allocated_lp_fee_usd"].median()),
        "mean_trade_count": float(frame["trade_count"].mean()),
        "zero_future_trade_rate": float((frame["trade_count"] == 0).mean()),
        "claim_scale_p50": float(frame["claim_scale_vs_historical_pool"].median()),
        "claim_scale_p99": float(frame["claim_scale_vs_historical_pool"].quantile(0.99)),
        "claim_scale_max": float(frame["claim_scale_vs_historical_pool"].max()),
        "exit_state_age_seconds_p50": float(frame["exit_state_age_seconds"].median()),
        "exit_state_age_seconds_p90": float(frame["exit_state_age_seconds"].quantile(0.90)),
        "segments": segments,
        "positive_segments": int(positive_segments),
        "capital_usd_per_week": float(
            len(frame) * float(frame["position_usd"].iloc[0]) / COHORT_WEEKS
        ),
    }
    detail = {"roi_bootstrap": bootstrap, "excess_bootstrap": excess_bootstrap}
    return row, detail


def make_plot(grid: pd.DataFrame, destination: Path) -> None:
    labels = [f"${int(row.position_usd)}\n{int(row.horizon_hours)}h" for row in grid.itertuples()]
    x = np.arange(len(grid))
    fees = grid["mean_fee_yield"].to_numpy(float)
    inventory = grid["mean_inventory_rebalance_component"].to_numpy(float)
    total = grid["mean_roi"].to_numpy(float)
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar(x, fees, label="Allocated LP fee yield", color="#2a9d8f")
    ax.bar(x, inventory, bottom=fees, label="Inventory/rebalancing + quote-USD component", color="#e76f51")
    ax.scatter(x, total, color="black", s=24, zorder=3, label="Mean net ROI")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Mean return contribution")
    ax.set_title("Passive LP return decomposition (frozen cells)")
    ax.legend(frameon=False, ncol=2)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(destination, dpi=170)
    plt.close(fig)


def write_report(
    destination: Path,
    grid: pd.DataFrame,
    primary: dict[str, Any],
    audit: dict[str, Any],
    hashes: dict[str, str],
    execution_id: str | None,
    credits: float | None,
) -> None:
    lines = [
        "# 毕业后被动做市手续费收入实验",
        "",
        f"> 裁决：**{'通过' if primary['passed'] else '不通过'}**。这是历史探索性检验，不授权实盘。",
        "",
        "## 冻结主策略（总本金$500、报价腿容量≥$250、持有1小时）",
        "",
        f"- 可执行样本：{primary['entries']:,}；数据缺失排除：{primary['missing_entries']:,}；",
        f"- 平均净ROI：{pct(primary['mean_roi'])}；中位ROI：{pct(primary['median_roi'])}；正收益率：{pct(primary['positive_roi_rate'])}；",
        f"- 日block bootstrap单侧95%下界：{pct(primary['bootstrap_95_one_sided_lower'])}；",
        f"- 平均分配手续费：{money(primary['mean_allocated_lp_fee_usd'])}，即本金的{pct(primary['mean_fee_yield'])}；",
        f"- 平均库存/再平衡及报价币美元波动项：{pct(primary['mean_inventory_rebalance_component'])}；",
        f"- 同两腿持币平均ROI：{pct(primary['mean_hodl_roi'])}；LP相对持币超额：{pct(primary['mean_lp_excess_vs_hodl'])}；",
        f"- 月段ROI：5月 {pct(primary['segments']['may'])}，6月 {pct(primary['segments']['june'])}，7月 {pct(primary['segments']['july'])}；",
        f"- 每周可部署名义本金：{money(primary['capital_usd_per_week'])}。",
        "",
        "裁决项：",
        "",
    ]
    for check in primary["checks"]:
        lines.append(f"- {'通过' if check['passed'] else '失败'}：`{check['name']}` = {check['value']}；")
    lines += [
        "",
        "## 八个冻结单元",
        "",
        "| 总本金 | 持有 | 样本 | 平均ROI | 95%下界 | 手续费收益 | 库存等项 | 相对持币 | 月段正数 | 候选 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in grid.itertuples():
        lines.append(
            f"| ${int(row.position_usd):,} | {int(row.horizon_hours)}h | {int(row.entries):,} | "
            f"{pct(row.mean_roi)} | {pct(row.bootstrap_95_one_sided_lower)} | "
            f"{pct(row.mean_fee_yield)} | {pct(row.mean_inventory_rebalance_component)} | "
            f"{pct(row.mean_lp_excess_vs_hodl)} | {int(row.positive_segments)}/3 | "
            f"{'是' if row.diagnostic_qualifies_for_fresh_test else '否'} |"
        )
    lines += [
        "",
        "## 口径与审计",
        "",
        "- 手续费直接来自每笔 PumpSwap buy/sell 解码事件的 `lp_fee`，并按事件前最近历史LP供应分配；",
        "- 手续费已包含在期末储备和净ROI内，归因时没有二次相加；",
        "- 入场基础币取得被假设为无摩擦，因此结果是偏乐观上界；退出基础币按整仓池冲击、实际链上费率及额外100bps损耗清算；",
        "- LP仓位没有写回历史链，未来路径采用可缩放的一阶反事实；",
        f"- 容量≥$250行数 {audit['rows_capacity_ge_250']:,}；容量≥$500行数 {audit['rows_capacity_ge_500']:,}；",
        f"- Dune执行ID：`{execution_id or '未记录'}`；credits：{credits if credits is not None else '未记录'}；",
        f"- 协议SHA-256：`{hashes['LP_EXPERIMENT.md']}`；",
        f"- SQL SHA-256：`{hashes['12_lp_returns.sql']}`。",
        "",
        "## 解释边界",
        "",
        "本实验回答的是“对所有容量合格的毕业池机械做市是否有正收益”，不是“能否事先筛出少数高费池”。如果无选择策略失败，但费用与可实时观测特征存在稳定横截面关系，下一步才值得冻结LP选择模型并做严格前向验证。",
    ]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=root / "data/dune_lp_returns.csv")
    parser.add_argument("--output-dir", type=Path, default=root / "output")
    parser.add_argument("--execution-id")
    parser.add_argument("--credits", type=float)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    hashes = verify_freeze(root)
    df, audit = load_and_audit(args.input)
    frames = []
    rows = []
    details = {}
    for position in POSITIONS:
        for horizon in HORIZONS:
            frame, missing = make_cell(df, position, horizon)
            summary, bootstrap = summarize_cell(frame, missing)
            qualifies = bool(
                summary["mean_roi"] > 0
                and summary["bootstrap_95_one_sided_lower"] > 0
                and summary["positive_segments"] >= 2
                and summary["mean_lp_excess_vs_hodl"] > 0
            )
            row = {
                "position_usd": position,
                "capacity_floor_usd": position / 2,
                "horizon_hours": horizon,
                **summary,
                "diagnostic_qualifies_for_fresh_test": qualifies,
            }
            rows.append(row)
            frames.append(frame)
            details[f"{position}_{horizon}h"] = bootstrap

    grid = pd.DataFrame(rows).sort_values(["position_usd", "horizon_hours"])
    primary_row = grid[(grid.position_usd == 500) & (grid.horizon_hours == 1)].iloc[0]
    checks = [
        {"name": "entries_at_least_100", "value": int(primary_row.entries), "passed": primary_row.entries >= 100},
        {"name": "mean_roi_above_zero", "value": float(primary_row.mean_roi), "passed": primary_row.mean_roi > 0},
        {"name": "bootstrap_lower_above_zero", "value": float(primary_row.bootstrap_95_one_sided_lower), "passed": primary_row.bootstrap_95_one_sided_lower > 0},
        {"name": "at_least_two_positive_segments", "value": int(primary_row.positive_segments), "passed": primary_row.positive_segments >= 2},
        {"name": "weekly_capital_at_least_10000", "value": float(primary_row.capital_usd_per_week), "passed": primary_row.capital_usd_per_week >= 10_000},
        {"name": "mean_excess_vs_hodl_above_zero", "value": float(primary_row.mean_lp_excess_vs_hodl), "passed": primary_row.mean_lp_excess_vs_hodl > 0},
    ]
    primary = {key: native(value) for key, value in primary_row.to_dict().items()}
    primary["checks"] = checks
    primary["passed"] = bool(all(check["passed"] for check in checks))
    primary["bootstrap"] = details["500_1h"]

    positions = pd.concat(frames, ignore_index=True)
    grid.to_csv(args.output_dir / "lp_grid.csv", index=False)
    positions.to_csv(args.output_dir / "lp_positions.csv", index=False)
    make_plot(grid, args.output_dir / "lp_decomposition.png")
    summary_json = {
        "audit": audit,
        "hashes": hashes,
        "dune_execution_id": args.execution_id,
        "dune_credits": args.credits,
        "primary": primary,
        "bootstrap_details": details,
        "qualifying_diagnostic_cells": int(grid["diagnostic_qualifies_for_fresh_test"].sum()),
    }
    (args.output_dir / "lp_summary.json").write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2, default=native) + "\n",
        encoding="utf-8",
    )
    write_report(
        args.output_dir / "lp_report.md", grid, primary, audit, hashes,
        args.execution_id, args.credits,
    )
    print(json.dumps(summary_json, ensure_ascii=False, indent=2, default=native))


if __name__ == "__main__":
    main()
