#!/usr/bin/env python3
"""Frozen chronological selection test for T+5m passive-LP returns."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


RANDOM_STATE = 20260824
BOOTSTRAP_DRAWS = 10_000
PRIMARY_RATE = 0.10
RATES = (0.01, 0.02, 0.05, 0.10, 0.20)
TEST_WEEKS = 40 / 7

FEATURES = [
    "quote_is_wsol", "initial_quote_reserve_usd", "creator_prior_graduations",
    "graduation_hour_sin", "graduation_hour_cos", "graduation_dow_sin", "graduation_dow_cos",
    "trade_count_5m", "buy_count_5m", "sell_count_5m", "unique_traders_5m",
    "unique_buyers_5m", "unique_sellers_5m", "non_agent_trade_count_5m",
    "non_agent_unique_traders_5m", "creator_buy_count_5m", "creator_sell_count_5m",
    "volume_usd_5m", "buy_volume_usd_5m", "sell_volume_usd_5m",
    "non_agent_volume_usd_5m", "creator_buy_volume_usd_5m", "creator_sell_volume_usd_5m",
    "trade_count_0_1m", "trade_count_1_3m", "trade_count_3_5m",
    "volume_usd_0_1m", "volume_usd_1_3m", "volume_usd_3_5m",
    "max_price_ratio_5m", "min_price_ratio_5m", "seconds_to_peak_5m",
    "price_ratio_30s", "price_ratio_1m", "price_ratio_3m", "price_ratio_5m",
    "quote_reserve_usd_5m", "capacity_5pct_usd_5m", "quote_reserve_ratio_5m",
    "state_age_seconds_5m", "deposit_count_5m", "withdraw_count_5m",
    "deposit_quote_usd_5m", "withdraw_quote_usd_5m", "buy_volume_share_5m",
    "net_buy_share_5m", "non_agent_volume_share_5m", "max_wallet_volume_share_5m",
    "wallet_volume_hhi_5m",
]

FOLDS = [
    (1, "2026-05-01", "2026-06-01", "2026-06-01", "2026-06-15", "2026-06-15", "2026-06-29"),
    (2, "2026-05-01", "2026-06-15", "2026-06-15", "2026-06-29", "2026-06-29", "2026-07-13"),
    (3, "2026-05-01", "2026-06-29", "2026-06-29", "2026-07-13", "2026-07-13", "2026-07-25"),
]

OUTCOMES = [
    "roi", "fee_yield", "inventory_rebalance_component", "hodl_roi",
    "lp_excess_vs_hodl", "allocated_lp_fee_usd", "trade_count",
]


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


def parse_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "t", "yes"}).astype(float)


def load_data(features_path: Path, positions_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    features = pd.read_csv(features_path, na_values=["<nil>"])
    positions = pd.read_csv(positions_path, na_values=["<nil>"])
    outcome = positions[(positions.position_usd == 500) & (positions.horizon_hours == 1)].copy()
    if features["mint"].duplicated().any() or outcome["mint"].duplicated().any():
        raise ValueError("mint must be unique")
    missing_features = sorted((set(FEATURES) - {
        "graduation_hour_sin", "graduation_hour_cos", "graduation_dow_sin", "graduation_dow_cos",
    }) - set(features.columns))
    if missing_features:
        raise ValueError(f"missing features: {missing_features}")
    if set(OUTCOMES) - set(outcome.columns):
        raise ValueError(f"missing outcomes: {sorted(set(OUTCOMES)-set(outcome.columns))}")
    frame = features.merge(
        outcome[["mint", *OUTCOMES]], on="mint", how="inner", validate="one_to_one"
    )
    if len(frame) != len(outcome):
        raise ValueError("not every eligible LP outcome has a T+5m feature row")
    frame["graduated_at"] = pd.to_datetime(frame["graduated_at"], utc=True, errors="raise")
    frame["date"] = frame["graduated_at"].dt.floor("D")
    frame["quote_is_wsol"] = parse_bool(frame["quote_is_wsol"])
    hour = frame["graduated_at"].dt.hour + frame["graduated_at"].dt.minute / 60
    dow = frame["graduated_at"].dt.dayofweek
    frame["graduation_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["graduation_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["graduation_dow_sin"] = np.sin(2 * np.pi * dow / 7)
    frame["graduation_dow_cos"] = np.cos(2 * np.pi * dow / 7)
    for column in FEATURES + OUTCOMES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[OUTCOMES].isna().any().any():
        raise ValueError("outcome missingness")
    forbidden = set(OUTCOMES) | {"pool_lp_fee_usd", "exit_value_usd", "gross_multiple"}
    if forbidden & set(FEATURES):
        raise ValueError("future leakage in feature list")
    audit = {
        "eligible_rows": len(frame),
        "feature_count": len(FEATURES),
        "feature_missing_cells": int(frame[FEATURES].isna().sum().sum()),
        "mean_base_roi": float(frame["roi"].mean()),
        "cohort_min": native(frame["graduated_at"].min()),
        "cohort_max": native(frame["graduated_at"].max()),
        "features_sha256": hashlib.sha256(features_path.read_bytes()).hexdigest(),
        "positions_sha256": hashlib.sha256(positions_path.read_bytes()).hexdigest(),
    }
    return frame.sort_values(["graduated_at", "mint"]).reset_index(drop=True), audit


def models() -> dict[str, Pipeline]:
    return {
        "hgb_primary": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", HistGradientBoostingRegressor(
                learning_rate=0.05, max_iter=200, max_leaf_nodes=15, max_depth=3,
                min_samples_leaf=100, l2_regularization=1.0,
                early_stopping=False, random_state=RANDOM_STATE,
            )),
        ]),
        "ridge_diagnostic": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ]),
    }


def between(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return frame[(frame.graduated_at >= pd.Timestamp(start, tz="UTC"))
                 & (frame.graduated_at < pd.Timestamp(end, tz="UTC"))].copy()


def selection_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "selected_count": len(frame),
        "mean_roi": native(frame.roi.mean()),
        "median_roi": native(frame.roi.median()),
        "positive_roi_rate": native((frame.roi > 0).mean()),
        "mean_fee_yield": native(frame.fee_yield.mean()),
        "mean_inventory_component": native(frame.inventory_rebalance_component.mean()),
        "mean_hodl_roi": native(frame.hodl_roi.mean()),
        "mean_excess_vs_hodl": native(frame.lp_excess_vs_hodl.mean()),
        "mean_allocated_fee_usd": native(frame.allocated_lp_fee_usd.mean()),
        "mean_trade_count": native(frame.trade_count.mean()),
    }


def fit_forward(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    predictions = []
    fold_rows = []
    importance_rows = []
    audit = {}
    for fold, tr0, tr1, va0, va1, te0, te1 in FOLDS:
        train, validation, test = between(df, tr0, tr1), between(df, va0, va1), between(df, te0, te1)
        if min(map(len, (train, validation, test))) == 0:
            raise ValueError(f"empty fold {fold}")
        audit[str(fold)] = {
            "train_n": len(train), "validation_n": len(validation), "test_n": len(test),
            "train_mean_roi": float(train.roi.mean()), "validation_mean_roi": float(validation.roi.mean()),
            "test_mean_roi": float(test.roi.mean()),
            "train": [tr0, tr1], "validation": [va0, va1], "test": [te0, te1],
        }
        for model_name, model in models().items():
            model.fit(train[FEATURES], train.roi)
            validation_score = model.predict(validation[FEATURES])
            test_score = model.predict(test[FEATURES])
            prediction = test[["graduated_at", "date", "mint", *OUTCOMES]].copy()
            prediction["fold"] = fold
            prediction["model"] = model_name
            prediction["score"] = test_score
            for rate in RATES:
                threshold = float(np.quantile(validation_score, 1 - rate, method="higher"))
                key = f"selected_top_{int(rate*100):02d}pct"
                prediction[key] = test_score >= threshold
                metrics = selection_metrics(prediction[prediction[key]])
                fold_rows.append({
                    "fold": fold, "model": model_name, "selection_rate": rate,
                    "validation_threshold": threshold, "test_n": len(test),
                    "test_mean_roi": float(test.roi.mean()), **metrics,
                })
            predictions.append(prediction)
            if model_name == "hgb_primary":
                importance = permutation_importance(
                    model, test[FEATURES], test.roi, scoring="neg_mean_squared_error",
                    n_repeats=3, random_state=RANDOM_STATE + fold, n_jobs=1,
                )
                importance_rows.extend({
                    "fold": fold, "feature": feature,
                    "importance_mean": float(mean), "importance_std": float(std),
                } for feature, mean, std in zip(
                    FEATURES, importance.importances_mean, importance.importances_std
                ))
    return (
        pd.concat(predictions, ignore_index=True), pd.DataFrame(fold_rows),
        pd.DataFrame(importance_rows), audit,
    )


def daily_bootstrap(frame: pd.DataFrame) -> dict[str, Any]:
    daily = frame.groupby("date").roi.agg(["sum", "count"])
    rng = np.random.default_rng(RANDOM_STATE)
    indices = rng.integers(0, len(daily), size=(BOOTSTRAP_DRAWS, len(daily)))
    values = (daily["sum"].to_numpy()[indices].sum(axis=1)
              / daily["count"].to_numpy()[indices].sum(axis=1))
    return {
        "days": len(daily), "draws": BOOTSTRAP_DRAWS,
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def pool_results(predictions: pd.DataFrame, fold_metrics: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    details = {}
    for model_name in ("hgb_primary", "ridge_diagnostic"):
        model_predictions = predictions[predictions.model == model_name]
        for rate in RATES:
            key = f"selected_top_{int(rate*100):02d}pct"
            selected = model_predictions[model_predictions[key]].copy()
            metrics = selection_metrics(selected)
            bootstrap = daily_bootstrap(selected)
            folds = fold_metrics[(fold_metrics.model == model_name) & (fold_metrics.selection_rate == rate)]
            positive_folds = int((folds.mean_roi > 0).sum())
            weekly_capital = len(selected) * 500 / TEST_WEEKS
            qualifies = bool(
                metrics["mean_roi"] is not None and metrics["mean_roi"] > 0
                and bootstrap["p05"] > 0 and positive_folds >= 2
                and metrics["mean_excess_vs_hodl"] is not None
                and metrics["mean_excess_vs_hodl"] > 0
            )
            rows.append({
                "model": model_name, "selection_rate": rate, **metrics,
                "bootstrap_lower": bootstrap["p05"], "positive_folds": positive_folds,
                "weekly_capital_usd": weekly_capital,
                "diagnostic_qualifies_for_fresh_test": qualifies,
            })
            details[f"{model_name}_{rate:.2f}"] = bootstrap
    grid = pd.DataFrame(rows)
    primary = grid[(grid.model == "hgb_primary") & (grid.selection_rate == PRIMARY_RATE)].iloc[0]
    checks = [
        {"name": "selected_at_least_100", "value": int(primary.selected_count), "passed": primary.selected_count >= 100},
        {"name": "mean_roi_above_zero", "value": float(primary.mean_roi), "passed": primary.mean_roi > 0},
        {"name": "bootstrap_lower_above_zero", "value": float(primary.bootstrap_lower), "passed": primary.bootstrap_lower > 0},
        {"name": "at_least_two_positive_test_folds", "value": int(primary.positive_folds), "passed": primary.positive_folds >= 2},
        {"name": "weekly_capital_at_least_10000", "value": float(primary.weekly_capital_usd), "passed": primary.weekly_capital_usd >= 10_000},
        {"name": "mean_excess_vs_hodl_above_zero", "value": float(primary.mean_excess_vs_hodl), "passed": primary.mean_excess_vs_hodl > 0},
    ]
    primary_dict = {key: native(value) for key, value in primary.to_dict().items()}
    primary_dict["checks"] = checks
    primary_dict["passed"] = bool(all(check["passed"] for check in checks))
    primary_dict["bootstrap"] = details["hgb_primary_0.10"]
    return grid, {"primary": primary_dict, "bootstrap": details}


def make_plot(grid: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for model, marker in (("hgb_primary", "o"), ("ridge_diagnostic", "s")):
        data = grid[grid.model == model]
        ax.plot(100 * data.selection_rate, 100 * data.mean_roi, marker=marker, label=model)
        ax.plot(100 * data.selection_rate, 100 * data.bootstrap_lower, marker=marker,
                linestyle="--", alpha=0.75, label=f"{model} 95% lower")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Validation-targeted selection rate (%)")
    ax.set_ylabel("Forward-test ROI (%)")
    ax.set_title("T+5m LP selection: mean ROI and daily-block lower bound")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def write_report(path: Path, grid: pd.DataFrame, result: dict[str, Any], audit: dict[str, Any]) -> None:
    primary = result["primary"]
    lines = [
        "# T+5m LP选择模型前向结果", "",
        f"> 主策略裁决：**{'通过' if primary['passed'] else '不通过'}**。", "",
        "## 主模型×验证集最高10%", "",
        f"- 前向选中 {primary['selected_count']:,} 个；平均ROI {pct(primary['mean_roi'])}；中位ROI {pct(primary['median_roi'])}；",
        f"- 日block bootstrap单侧95%下界 {pct(primary['bootstrap_lower'])}；3个测试折中 {primary['positive_folds']} 个平均ROI为正；",
        f"- 手续费收益 {pct(primary['mean_fee_yield'])}；库存等项 {pct(primary['mean_inventory_component'])}；",
        f"- 相对同两腿持币超额 {pct(primary['mean_excess_vs_hodl'])}；每周名义本金 {money(primary['weekly_capital_usd'])}。", "",
        "裁决项：", "",
    ]
    lines.extend(
        f"- {'通过' if check['passed'] else '失败'}：`{check['name']}` = {check['value']}；"
        for check in primary["checks"]
    )
    lines += [
        "", "## 所有冻结单元", "",
        "| 模型 | 选择率 | 选中 | 平均ROI | 95%下界 | 手续费 | 库存等项 | 相对持币 | 正测试折 | 候选 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in grid.itertuples():
        lines.append(
            f"| {row.model} | {pct(row.selection_rate)} | {int(row.selected_count):,} | "
            f"{pct(row.mean_roi)} | {pct(row.bootstrap_lower)} | {pct(row.mean_fee_yield)} | "
            f"{pct(row.mean_inventory_component)} | {pct(row.mean_excess_vs_hodl)} | "
            f"{int(row.positive_folds)}/3 | {'是' if row.diagnostic_qualifies_for_fresh_test else '否'} |"
        )
    lines += [
        "", "## 解释", "",
        "模型只看T+5m已经可见的字段，阈值只由紧邻过去的验证段决定。未来实现手续费没有进入特征。若10格都不能取得正且有统计下界的收益，则现有T+5m链上数据不足以把机械LP方向救活；不能用事后最高费池反推可执行策略。",
        "", "## 数据审计", "",
        f"- 容量合格样本 {audit['eligible_rows']:,}；特征 {audit['feature_count']} 个；特征缺失单元 {audit['feature_missing_cells']:,}；",
        f"- T+5m特征CSV SHA-256：`{audit['features_sha256']}`；",
        f"- LP逐仓结果CSV SHA-256：`{audit['positions_sha256']}`。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=root / "data/dune_t5m_features.csv")
    parser.add_argument("--positions", type=Path, default=root / "output/lp_positions.csv")
    parser.add_argument("--output-dir", type=Path, default=root / "output")
    args = parser.parse_args()
    expected = {}
    for line in (root / "LP_SELECTION_EXPERIMENT.sha256").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        expected[name.strip()] = digest
    for name, digest in expected.items():
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError(f"freeze hash mismatch: {name}")
    df, audit = load_data(args.features, args.positions)
    predictions, fold_metrics, importance, fold_audit = fit_forward(df)
    grid, result = pool_results(predictions, fold_metrics)
    audit["folds"] = fold_audit
    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.output_dir / "lp_selection_predictions.csv", index=False)
    fold_metrics.to_csv(args.output_dir / "lp_selection_fold_metrics.csv", index=False)
    importance.to_csv(args.output_dir / "lp_selection_importance.csv", index=False)
    grid.to_csv(args.output_dir / "lp_selection_grid.csv", index=False)
    make_plot(grid, args.output_dir / "lp_selection_curve.png")
    payload = {"audit": audit, **result,
               "qualifying_cells": int(grid.diagnostic_qualifies_for_fresh_test.sum())}
    (args.output_dir / "lp_selection_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=native) + "\n",
        encoding="utf-8",
    )
    write_report(args.output_dir / "lp_selection_report.md", grid, result, audit)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=native))


if __name__ == "__main__":
    main()
