#!/usr/bin/env python3
"""Compare the frozen Jan-Feb 2026 execution replication with May-Jul."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import analyze_first_passage as fp  # noqa: E402
import analyze_lp as lp  # noqa: E402


COHORT_WEEKS = 59 / 7


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
    return "NA" if value is None or pd.isna(value) else f"{100*float(value):.2f}%"


def money(value: Any) -> str:
    return "NA" if value is None or pd.isna(value) else f"${float(value):,.2f}"


def janfeb_segments(frame: pd.DataFrame, column: str = "roi") -> dict[str, float | None]:
    bounds = {
        "january": ("2026-01-01", "2026-02-01"),
        "february": ("2026-02-01", "2026-03-01"),
    }
    result = {}
    for name, (start, end) in bounds.items():
        mask = (
            (frame["graduated_at"] >= pd.Timestamp(start, tz="UTC"))
            & (frame["graduated_at"] < pd.Timestamp(end, tz="UTC"))
        )
        result[name] = native(frame.loc[mask, column].mean())
    return result


def verify_hashes() -> dict[str, str]:
    expected = {}
    for line in (ROOT / "REGIME_REPLICATION_2026_JANFEB.sha256").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        expected[name.strip()] = digest
    actual = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in expected}
    mismatch = {name: (expected[name], actual[name]) for name in expected if expected[name] != actual[name]}
    if mismatch:
        raise ValueError(f"replication hash mismatch: {mismatch}")
    return actual


def analyze_first_passage(path: Path) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame, dict[str, Any]]:
    fp.COHORT_WEEKS = COHORT_WEEKS
    fp.segment_rois = lambda frame: janfeb_segments(frame, "roi")
    frame, audit = fp.load_and_audit(path)
    grid, primary, trades = fp.analyze_grid(frame)
    return grid, primary, trades, audit


def analyze_lp(path: Path) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame, dict[str, Any]]:
    lp.COHORT_WEEKS = COHORT_WEEKS
    lp.segment_means = janfeb_segments
    frame, audit = lp.load_and_audit(path)
    cells, rows, details = [], [], {}
    for position in lp.POSITIONS:
        for horizon in lp.HORIZONS:
            cell, missing = lp.make_cell(frame, position, horizon)
            summary, bootstrap = lp.summarize_cell(cell, missing)
            qualifies = bool(
                summary["mean_roi"] > 0
                and summary["bootstrap_95_one_sided_lower"] > 0
                and summary["positive_segments"] >= 2
                and summary["mean_lp_excess_vs_hodl"] > 0
            )
            rows.append({
                "position_usd": position,
                "capacity_floor_usd": position / 2,
                "horizon_hours": horizon,
                **summary,
                "diagnostic_qualifies_for_fresh_test": qualifies,
            })
            cells.append(cell)
            details[f"{position}_{horizon}h"] = bootstrap
    grid = pd.DataFrame(rows).sort_values(["position_usd", "horizon_hours"])
    row = grid[(grid.position_usd == 500) & (grid.horizon_hours == 1)].iloc[0]
    checks = [
        {"name": "entries_at_least_100", "value": int(row.entries), "passed": row.entries >= 100},
        {"name": "mean_roi_above_zero", "value": float(row.mean_roi), "passed": row.mean_roi > 0},
        {"name": "bootstrap_lower_above_zero", "value": float(row.bootstrap_95_one_sided_lower), "passed": row.bootstrap_95_one_sided_lower > 0},
        {"name": "both_months_positive", "value": int(row.positive_segments), "passed": row.positive_segments >= 2},
        {"name": "weekly_capital_at_least_10000", "value": float(row.capital_usd_per_week), "passed": row.capital_usd_per_week >= 10_000},
        {"name": "mean_excess_vs_hodl_above_zero", "value": float(row.mean_lp_excess_vs_hodl), "passed": row.mean_lp_excess_vs_hodl > 0},
    ]
    primary = {key: native(value) for key, value in row.to_dict().items()}
    primary["checks"] = checks
    primary["passed"] = bool(all(check["passed"] for check in checks))
    primary["bootstrap"] = details["500_1h"]
    return grid, primary, pd.concat(cells, ignore_index=True), audit


def make_comparison_plot(comparison: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    x = np.arange(len(comparison))
    width = 0.34
    ax.bar(x - width/2, 100*comparison.janfeb_mean_roi, width, label="Jan-Feb 2026")
    ax.bar(x + width/2, 100*comparison.mayjul_mean_roi, width, label="May-Jul 2026")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x, comparison.strategy)
    ax.set_ylabel("Mean net ROI (%)")
    ax.set_title("Frozen execution strategies across regimes")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def render_report(
    fp_grid: pd.DataFrame,
    fp_primary: dict[str, Any],
    lp_grid: pd.DataFrame,
    lp_primary: dict[str, Any],
    prior_fp: dict[str, Any],
    prior_lp: dict[str, Any],
    verdict: str,
    hashes: dict[str, str],
    executions: dict[str, Any],
) -> str:
    lines = [
        "# 2026年1–2月跨周期执行复验", "",
        f"> 跨周期裁决：**{verdict}**。", "",
        "## 同口径主策略对比", "",
        "| 方向 | 时期 | 样本 | 平均ROI | 95%下界 | 分段 | 每周本金 | 通过 |",
        "|---|---|---:|---:|---:|---|---:|:---:|",
        f"| 首触发 TP2/SL0.5/4h | 1–2月 | {fp_primary['entries']:,} | {pct(fp_primary['mean_roi'])} | {pct(fp_primary['bootstrap_95_one_sided_lower'])} | 1月 {pct(fp_primary['segments']['january'])} / 2月 {pct(fp_primary['segments']['february'])} | {money(fp_primary['capital_usd_per_week'])} | {'是' if fp_primary['passed'] else '否'} |",
        f"| 首触发 TP2/SL0.5/4h | 5–7月 | {prior_fp['entries']:,} | {pct(prior_fp['mean_roi'])} | {pct(prior_fp['bootstrap_95_one_sided_lower'])} | 0/3正月份 | {money(prior_fp['capital_usd_per_week'])} | {'是' if prior_fp['passed'] else '否'} |",
        f"| 被动LP $500/1h | 1–2月 | {lp_primary['entries']:,} | {pct(lp_primary['mean_roi'])} | {pct(lp_primary['bootstrap_95_one_sided_lower'])} | 1月 {pct(lp_primary['segments']['january'])} / 2月 {pct(lp_primary['segments']['february'])} | {money(lp_primary['capital_usd_per_week'])} | {'是' if lp_primary['passed'] else '否'} |",
        f"| 被动LP $500/1h | 5–7月 | {prior_lp['entries']:,} | {pct(prior_lp['mean_roi'])} | {pct(prior_lp['bootstrap_95_one_sided_lower'])} | 0/3正月份 | {money(prior_lp['capital_usd_per_week'])} | {'是' if prior_lp['passed'] else '否'} |",
        "", "## 首触发96格", "",
        f"- 1–2月符合平均ROI>0、bootstrap下界>0、两个月均正的格子：{int(fp_grid.diagnostic_qualifies_for_fresh_test.sum())}/96；",
        f"- 网格最好平均ROI：{pct(fp_grid.mean_roi.max())}；最好bootstrap下界：{pct(fp_grid.bootstrap_95_one_sided_lower.max())}。",
        "", "## LP八格", "",
        f"- 主策略手续费收益 {pct(lp_primary['mean_fee_yield'])}；库存等项 {pct(lp_primary['mean_inventory_rebalance_component'])}；相对持币 {pct(lp_primary['mean_lp_excess_vs_hodl'])}；",
        f"- 符合正收益标准的格子：{int(lp_grid.diagnostic_qualifies_for_fresh_test.sum())}/8。", "",
        "| 本金 | 持有 | 平均ROI | 95%下界 | 手续费 | 库存等项 | 相对持币 | 两月正 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in lp_grid.itertuples():
        lines.append(
            f"| ${int(row.position_usd):,} | {int(row.horizon_hours)}h | {pct(row.mean_roi)} | "
            f"{pct(row.bootstrap_95_one_sided_lower)} | {pct(row.mean_fee_yield)} | "
            f"{pct(row.mean_inventory_rebalance_component)} | {pct(row.mean_lp_excess_vs_hodl)} | "
            f"{int(row.positive_segments)}/2 |"
        )
    lines += [
        "", "## 审计", "",
        f"- 首触发Dune执行：`{executions['first_passage']['id']}`，{executions['first_passage']['credits']} credits；",
        f"- LP Dune执行：`{executions['lp']['id']}`，{executions['lp']['credits']} credits；",
        f"- 复验协议SHA-256：`{hashes['REGIME_REPLICATION_2026_JANFEB.md']}`；",
        f"- 首触发SQL SHA-256：`{hashes['13_first_passage_janfeb.sql']}`；",
        f"- LP SQL SHA-256：`{hashes['14_lp_returns_janfeb.sql']}`。", "",
        "1–2月是在后期失败后有目的选择的有利时期。若结果为正，它可以否定“周期无关”的强结论，但仍需未来预注册的相似制度期确认；若两套及全部诊断格仍为负，则结构性失败解释明显增强。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-passage", type=Path, default=ROOT / "data/dune_first_passage_janfeb.csv")
    parser.add_argument("--lp", type=Path, default=ROOT / "data/dune_lp_returns_janfeb.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--fp-execution-id", required=True)
    parser.add_argument("--fp-credits", type=float, required=True)
    parser.add_argument("--lp-execution-id", required=True)
    parser.add_argument("--lp-credits", type=float, required=True)
    args = parser.parse_args()
    hashes = verify_hashes()
    fp_grid, fp_primary, fp_trades, fp_audit = analyze_first_passage(args.first_passage)
    lp_grid, lp_primary, lp_positions, lp_audit = analyze_lp(args.lp)
    prior_fp = json.loads((ROOT / "output/first_passage_summary.json").read_text())["primary"]
    prior_lp = json.loads((ROOT / "output/lp_summary.json").read_text())["primary"]

    structural = bool(
        fp_primary["mean_roi"] < 0
        and fp_primary["bootstrap_95_one_sided_lower"] <= 0
        and not fp_grid.diagnostic_qualifies_for_fresh_test.any()
        and lp_primary["mean_roi"] < 0
        and lp_primary["bootstrap_95_one_sided_lower"] <= 0
        and not lp_grid.diagnostic_qualifies_for_fresh_test.any()
    )
    regime_dependent = bool(fp_primary["passed"] or lp_primary["passed"])
    if structural:
        verdict = "支持结构性失败，与周期无关的解释明显增强"
        verdict_code = "supports_structural_failure"
    elif regime_dependent:
        verdict = "支持周期依赖；不能关闭方向，只能关闭萎缩期版本"
        verdict_code = "supports_regime_dependence"
    else:
        verdict = "混合结果；存在周期候选但未达到主策略显著为正标准"
        verdict_code = "mixed"

    comparison = pd.DataFrame([
        {"strategy": "First passage", "janfeb_mean_roi": fp_primary["mean_roi"], "mayjul_mean_roi": prior_fp["mean_roi"]},
        {"strategy": "Passive LP", "janfeb_mean_roi": lp_primary["mean_roi"], "mayjul_mean_roi": prior_lp["mean_roi"]},
    ])
    executions = {
        "first_passage": {"id": args.fp_execution_id, "credits": args.fp_credits},
        "lp": {"id": args.lp_execution_id, "credits": args.lp_credits},
    }
    payload = {
        "verdict": verdict_code,
        "verdict_text": verdict,
        "hashes": hashes,
        "executions": executions,
        "first_passage": {"audit": fp_audit, "primary": fp_primary,
                          "qualifying_grid_cells": int(fp_grid.diagnostic_qualifies_for_fresh_test.sum())},
        "lp": {"audit": lp_audit, "primary": lp_primary,
               "qualifying_grid_cells": int(lp_grid.diagnostic_qualifies_for_fresh_test.sum())},
        "prior_may_july": {"first_passage": prior_fp, "lp": prior_lp},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fp_grid.to_csv(args.output_dir / "janfeb_first_passage_grid.csv", index=False)
    fp_trades.to_csv(args.output_dir / "janfeb_first_passage_primary_trades.csv", index=False)
    lp_grid.to_csv(args.output_dir / "janfeb_lp_grid.csv", index=False)
    lp_positions.to_csv(args.output_dir / "janfeb_lp_positions.csv", index=False)
    comparison.to_csv(args.output_dir / "regime_comparison.csv", index=False)
    make_comparison_plot(comparison, args.output_dir / "regime_comparison.png")
    (args.output_dir / "regime_replication_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=native) + "\n", encoding="utf-8"
    )
    (args.output_dir / "regime_replication_report.md").write_text(
        render_report(fp_grid, fp_primary, lp_grid, lp_primary, prior_fp, prior_lp,
                      verdict, hashes, executions), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=native))


if __name__ == "__main__":
    main()
