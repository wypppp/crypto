#!/usr/bin/env python3
"""Run the frozen Pump T+30s/T+60s execution-target forward experiment."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


RANDOM_STATE = 20260824
BOOTSTRAP_DRAWS = 10_000
STAKE_USD = 250.0
SELECTION_RATE = 0.10

BASE_FEATURES = [
    "quote_is_wsol",
    "initial_quote_reserve_usd",
    "creator_prior_graduations",
    "graduation_hour_sin",
    "graduation_hour_cos",
    "graduation_dow_sin",
    "graduation_dow_cos",
    "trade_count_5m",
    "buy_count_5m",
    "sell_count_5m",
    "unique_traders_5m",
    "unique_buyers_5m",
    "unique_sellers_5m",
    "non_agent_trade_count_5m",
    "non_agent_unique_traders_5m",
    "creator_buy_count_5m",
    "creator_sell_count_5m",
    "volume_usd_5m",
    "buy_volume_usd_5m",
    "sell_volume_usd_5m",
    "non_agent_volume_usd_5m",
    "creator_buy_volume_usd_5m",
    "creator_sell_volume_usd_5m",
    "trade_count_0_1m",
    "trade_count_1_3m",
    "trade_count_3_5m",
    "volume_usd_0_1m",
    "volume_usd_1_3m",
    "volume_usd_3_5m",
    "max_price_ratio_5m",
    "min_price_ratio_5m",
    "seconds_to_peak_5m",
    "price_ratio_30s",
    "price_ratio_1m",
    "price_ratio_3m",
    "price_ratio_5m",
    "quote_reserve_usd_5m",
    "capacity_5pct_usd_5m",
    "quote_reserve_ratio_5m",
    "state_age_seconds_5m",
    "deposit_count_5m",
    "withdraw_count_5m",
    "deposit_quote_usd_5m",
    "withdraw_quote_usd_5m",
    "buy_volume_share_5m",
    "net_buy_share_5m",
    "non_agent_volume_share_5m",
    "max_wallet_volume_share_5m",
    "wallet_volume_hhi_5m",
]

HOLDING_FEATURES = [
    "pretrade_wallet_count",
    "positive_holder_wallet_count",
    "pre_top_wallet_holding_share",
    "pre_wallet_holding_hhi",
    "pre_creator_holding_share",
]

ENTITY_FEATURES = [
    "entity_count",
    "wallet_to_entity_ratio",
    "top_entity_holding_share",
    "entity_holding_hhi",
    "creator_connected_entity_holding_share",
    "atomic_linked_wallet_share",
    "atomic_linked_holding_share",
    "max_component_wallets",
    "top_entity_sellable_to_pool_base_ratio",
    "entity_max_buy_volume_share_5m",
    "entity_buy_volume_hhi_5m",
    "entity_merge_delta_top_holding_share",
    "entity_merge_delta_holding_hhi",
    "entity_atomic_coverage_flag",
]

FEATURE_SETS = {
    "base": BASE_FEATURES,
    "base_plus_holding": BASE_FEATURES + HOLDING_FEATURES,
    "base_plus_holding_plus_entity": BASE_FEATURES + HOLDING_FEATURES + ENTITY_FEATURES,
}

FOLDS = [
    {
        "fold": 1,
        "train_start": "2026-01-01",
        "train_end": "2026-01-08",
        "validation_start": "2026-01-08",
        "validation_end": "2026-01-15",
        "test_start": "2026-01-15",
        "test_end": "2026-02-01",
        "test_month": "2026-01",
    },
    {
        "fold": 2,
        "train_start": "2026-01-01",
        "train_end": "2026-01-15",
        "validation_start": "2026-01-15",
        "validation_end": "2026-02-01",
        "test_start": "2026-02-01",
        "test_end": "2026-03-01",
        "test_month": "2026-02",
    },
    {
        "fold": 3,
        "train_start": "2026-01-01",
        "train_end": "2026-03-01",
        "validation_start": "2026-05-01",
        "validation_end": "2026-05-15",
        "test_start": "2026-05-15",
        "test_end": "2026-06-01",
        "test_month": "2026-05",
    },
    {
        "fold": 4,
        "train_start": "2026-01-01",
        "train_end": "2026-06-01",
        "validation_start": "2026-06-01",
        "validation_end": "2026-06-15",
        "test_start": "2026-06-15",
        "test_end": "2026-07-01",
        "test_month": "2026-06",
    },
    {
        "fold": 5,
        "train_start": "2026-01-01",
        "train_end": "2026-06-15",
        "validation_start": "2026-06-15",
        "validation_end": "2026-07-01",
        "test_start": "2026-07-01",
        "test_end": "2026-07-25",
        "test_month": "2026-07",
    },
]


@dataclass(frozen=True)
class Paths:
    base: Path
    entity: Path
    execution: Path


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
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "t", "yes"}).astype(float)


def require_unique(frame: pd.DataFrame, name: str) -> None:
    if "mint" not in frame or frame["mint"].duplicated().any():
        raise ValueError(f"{name}: mint is missing or duplicated")


def realized_multiple(execution: pd.DataFrame) -> pd.Series:
    tp_order = pd.to_numeric(execution["tp2_order_250"], errors="coerce")
    sl_order = pd.to_numeric(execution["sl05_order_250"], errors="coerce")
    sl_return = pd.to_numeric(execution["sl05_return_250"], errors="coerce")
    timeout_return = pd.to_numeric(execution["timeout_4h_return_250"], errors="coerce")
    tp_first = tp_order.notna() & (sl_order.isna() | (tp_order < sl_order))
    sl_first = sl_order.notna() & ~tp_first
    result = timeout_return.copy()
    result.loc[tp_first] = 2.0
    result.loc[sl_first] = sl_return.loc[sl_first]
    return result


def load_regime(paths: Paths, regime: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    for path in (paths.base, paths.entity, paths.execution):
        if not path.exists():
            raise FileNotFoundError(path)
    base = pd.read_csv(paths.base, na_values=["<nil>"], low_memory=False)
    entity = pd.read_csv(paths.entity, na_values=["<nil>"], low_memory=False)
    execution = pd.read_csv(paths.execution, na_values=["<nil>"], low_memory=False)
    require_unique(base, f"{regime} base")
    require_unique(entity, f"{regime} entity")
    require_unique(execution, f"{regime} execution")
    if set(base.mint) != set(entity.mint):
        raise ValueError(f"{regime}: base/entity universes differ")
    if not set(execution.mint).issubset(set(base.mint)):
        raise ValueError(f"{regime}: execution contains mint absent from features")

    entity_columns = ["mint", *HOLDING_FEATURES, *ENTITY_FEATURES]
    missing_entity = sorted(set(entity_columns) - set(entity.columns))
    if missing_entity:
        raise ValueError(f"{regime}: entity fields missing: {missing_entity}")
    execution_columns = {
        "mint",
        "execution_at",
        "entry_capacity_5pct_usd",
        "entry_chain_fee_bps",
        "entry_state_age_seconds",
        "tp2_order_250",
        "sl05_order_250",
        "sl05_return_250",
        "timeout_4h_return_250",
    }
    missing_execution = sorted(execution_columns - set(execution.columns))
    if missing_execution:
        raise ValueError(f"{regime}: execution fields missing: {missing_execution}")

    execution = execution.copy()
    execution["realized_multiple"] = realized_multiple(execution)
    execution["net_roi"] = execution["realized_multiple"] - 1.0
    execution["label_positive"] = (execution["net_roi"] > 0).astype(int)
    merge_execution = [
        "mint",
        "execution_at",
        "entry_capacity_5pct_usd",
        "entry_chain_fee_bps",
        "entry_state_age_seconds",
        "realized_multiple",
        "net_roi",
        "label_positive",
    ]
    frame = (
        base.merge(entity[entity_columns], on="mint", how="inner", validate="one_to_one")
        .merge(execution[merge_execution], on="mint", how="inner", validate="one_to_one")
    )
    frame["graduated_at"] = pd.to_datetime(frame["graduated_at"], utc=True, errors="raise")
    frame["execution_at"] = pd.to_datetime(frame["execution_at"], utc=True, errors="raise")
    frame["regime"] = regime
    frame["date"] = frame["graduated_at"].dt.floor("D")
    frame["month"] = frame["graduated_at"].dt.strftime("%Y-%m")
    frame["week"] = frame["graduated_at"].dt.to_period("W-SUN").astype(str)
    frame["quote_is_wsol"] = parse_bool(frame["quote_is_wsol"])
    hour = frame["graduated_at"].dt.hour + frame["graduated_at"].dt.minute / 60
    dow = frame["graduated_at"].dt.dayofweek
    frame["graduation_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["graduation_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["graduation_dow_sin"] = np.sin(2 * np.pi * dow / 7)
    frame["graduation_dow_cos"] = np.cos(2 * np.pi * dow / 7)
    for column in set(BASE_FEATURES + HOLDING_FEATURES + ENTITY_FEATURES):
        if column not in frame:
            raise ValueError(f"{regime}: feature missing: {column}")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame[list(set(BASE_FEATURES + HOLDING_FEATURES + ENTITY_FEATURES))] = frame[
        list(set(BASE_FEATURES + HOLDING_FEATURES + ENTITY_FEATURES))
    ].replace([np.inf, -np.inf], np.nan)

    cutoff_seconds = 30 if paths.base.name.endswith("30s.csv") else 60
    state_age = pd.to_numeric(frame["state_age_seconds_5m"], errors="coerce")
    integrity = {
        "base_rows": len(base),
        "entity_rows": len(entity),
        "executable_rows": len(execution),
        "merged_rows": len(frame),
        "all_entry_capacity_ge_250": bool(
            (pd.to_numeric(frame["entry_capacity_5pct_usd"], errors="coerce") >= 250).all()
        ),
        "entry_fee_complete": bool(frame["entry_chain_fee_bps"].notna().all()),
        "realized_return_complete": bool(frame["realized_multiple"].notna().all()),
        "decision_state_age_valid": bool(
            state_age.notna().all() and (state_age >= 0).all() and (state_age <= cutoff_seconds).all()
        ),
        "atomic_entity_coverage_rate": float(frame["entity_atomic_coverage_flag"].mean()),
        "atomic_component_size_p99": native(frame["max_component_wallets"].quantile(0.99)),
        "atomic_component_size_max": native(frame["max_component_wallets"].max()),
    }
    return frame.sort_values(["graduated_at", "mint"]).reset_index(drop=True), integrity


def make_hgb() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.05,
                    max_iter=200,
                    max_leaf_nodes=15,
                    max_depth=3,
                    min_samples_leaf=100,
                    l2_regularization=1.0,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def make_logistic() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    penalty="l2",
                    C=1.0,
                    class_weight="balanced",
                    solver="lbfgs",
                    max_iter=2_000,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def time_mask(frame: pd.DataFrame, start: str, end: str) -> pd.Series:
    return (frame.graduated_at >= pd.Timestamp(start, tz="UTC")) & (
        frame.graduated_at < pd.Timestamp(end, tz="UTC")
    )


def run_models(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    outputs = []
    audits = []
    model_specs = [
        ("hgb_base", "base", make_hgb),
        ("hgb_base_plus_holding", "base_plus_holding", make_hgb),
        ("hgb_primary", "base_plus_holding_plus_entity", make_hgb),
        ("logistic_diagnostic", "base_plus_holding_plus_entity", make_logistic),
    ]
    for spec in FOLDS:
        train = frame[time_mask(frame, spec["train_start"], spec["train_end"])].copy()
        validation = frame[
            time_mask(frame, spec["validation_start"], spec["validation_end"])
        ].copy()
        test = frame[time_mask(frame, spec["test_start"], spec["test_end"])].copy()
        if min(len(train), len(validation), len(test)) < 100:
            raise ValueError(f"fold {spec['fold']} has fewer than 100 rows in a partition")
        if train.label_positive.nunique() < 2 or validation.label_positive.nunique() < 2:
            raise ValueError(f"fold {spec['fold']} has a one-class train or validation")
        audits.append(
            {
                **spec,
                "train_n": len(train),
                "validation_n": len(validation),
                "test_n": len(test),
                "train_positive_rate": float(train.label_positive.mean()),
                "validation_positive_rate": float(validation.label_positive.mean()),
                "test_positive_rate": float(test.label_positive.mean()),
            }
        )
        for model_name, feature_set, factory in model_specs:
            features = FEATURE_SETS[feature_set]
            model = factory()
            fit_kwargs: dict[str, Any] = {}
            if model_name.startswith("hgb_"):
                positives = int(train.label_positive.sum())
                negatives = len(train) - positives
                weights = np.where(
                    train.label_positive.to_numpy() == 1,
                    negatives / positives,
                    1.0,
                )
                fit_kwargs["model__sample_weight"] = weights
            model.fit(train[features], train.label_positive, **fit_kwargs)
            validation_scores = model.predict_proba(validation[features])[:, 1]
            threshold = float(
                np.quantile(validation_scores, 1 - SELECTION_RATE, method="higher")
            )
            test_scores = model.predict_proba(test[features])[:, 1]
            rows = test[
                [
                    "graduated_at",
                    "execution_at",
                    "date",
                    "month",
                    "week",
                    "regime",
                    "mint",
                    "entry_capacity_5pct_usd",
                    "net_roi",
                    "label_positive",
                    "entity_atomic_coverage_flag",
                    "max_component_wallets",
                ]
            ].copy()
            rows["fold"] = spec["fold"]
            rows["model"] = model_name
            rows["feature_set"] = feature_set
            rows["score"] = test_scores
            rows["validation_threshold"] = threshold
            rows["selected"] = test_scores >= threshold
            outputs.append(rows)
    predictions = pd.concat(outputs, ignore_index=True)
    if predictions.groupby(["model", "mint"]).size().max() != 1:
        raise ValueError("a mint appears in more than one OOS test for a model")
    return predictions, audits


def date_block_bootstrap(selected: pd.DataFrame, test_dates: pd.DatetimeIndex) -> dict[str, Any]:
    dates = pd.DatetimeIndex(sorted(pd.unique(test_dates)))
    daily = (
        selected.groupby("date")
        .agg(roi_sum=("net_roi", "sum"), trades=("net_roi", "size"))
        .reindex(dates, fill_value=0)
    )
    if len(dates) == 0 or daily.trades.sum() == 0:
        return {"days": len(dates), "valid_draws": 0, "lower_97_5": None}
    rng = np.random.default_rng(RANDOM_STATE)
    indices = rng.integers(0, len(dates), size=(BOOTSTRAP_DRAWS, len(dates)))
    numerator = daily.roi_sum.to_numpy(float)[indices].sum(axis=1)
    denominator = daily.trades.to_numpy(float)[indices].sum(axis=1)
    valid = denominator > 0
    values = numerator[valid] / denominator[valid]
    return {
        "days": len(dates),
        "draws": BOOTSTRAP_DRAWS,
        "valid_draws": int(valid.sum()),
        "lower_97_5": native(np.quantile(values, 0.025)) if len(values) else None,
        "p50": native(np.quantile(values, 0.50)) if len(values) else None,
        "upper_97_5": native(np.quantile(values, 0.975)) if len(values) else None,
    }


def summarize_model(rows: pd.DataFrame, all_test_dates: pd.DatetimeIndex) -> dict[str, Any]:
    selected = rows[rows.selected].copy()
    month = {
        key: {
            "selected": len(group),
            "mean_net_roi": native(group.net_roi.mean()) if len(group) else None,
        }
        for key, group in selected.groupby("month")
    }
    for key in ("2026-01", "2026-02", "2026-05", "2026-06", "2026-07"):
        month.setdefault(key, {"selected": 0, "mean_net_roi": None})
    regime = {
        key: {"selected": len(group), "mean_net_roi": native(group.net_roi.mean())}
        for key, group in selected.groupby("regime")
    }
    test_weeks = sorted(pd.unique(rows.week))
    weekly = (
        selected.groupby("week").size().mul(STAKE_USD).reindex(test_weeks, fill_value=0)
    )
    pnl = (selected.sort_values(["execution_at", "mint"]).net_roi * STAKE_USD).cumsum()
    equity = 4200.0 + pnl
    drawdown = equity - equity.cummax()
    return {
        "oos_rows": len(rows),
        "selected": len(selected),
        "positive": int(selected.label_positive.sum()),
        "mean_net_roi": native(selected.net_roi.mean()),
        "median_net_roi": native(selected.net_roi.median()),
        "bootstrap": date_block_bootstrap(selected, all_test_dates),
        "capacity_p10": native(selected.entry_capacity_5pct_usd.quantile(0.10)),
        "capacity_p50": native(selected.entry_capacity_5pct_usd.quantile(0.50)),
        "capacity_p90": native(selected.entry_capacity_5pct_usd.quantile(0.90)),
        "weekly_nominal_p50": native(weekly.median()),
        "weekly_nominal_mean": native(weekly.mean()),
        "regime": regime,
        "month": month,
        "account_final_equity_unconstrained": native(equity.iloc[-1]) if len(equity) else 4200.0,
        "account_max_drawdown_usd_unconstrained": native(drawdown.min()) if len(drawdown) else 0.0,
    }


def decision(summary: dict[str, Any], base_summary: dict[str, Any], integrity: dict[str, Any]) -> dict[str, Any]:
    regimes = summary["regime"]
    months = summary["month"]
    positive_months = sum(
        value["mean_net_roi"] is not None and value["mean_net_roi"] > 0
        for value in months.values()
    )
    integrity_pass = all(
        row[key]
        for row in integrity.values()
        for key in (
            "all_entry_capacity_ge_250",
            "entry_fee_complete",
            "realized_return_complete",
            "decision_state_age_valid",
        )
    )
    checks = [
        {
            "name": "selected>=100 and each regime>=20",
            "value": {
                "selected": summary["selected"],
                "janfeb": regimes.get("janfeb", {}).get("selected", 0),
                "mayjul": regimes.get("mayjul", {}).get("selected", 0),
            },
            "passed": summary["selected"] >= 100
            and regimes.get("janfeb", {}).get("selected", 0) >= 20
            and regimes.get("mayjul", {}).get("selected", 0) >= 20,
        },
        {
            "name": "combined mean and Bonferroni 97.5% lower >0",
            "value": {
                "mean": summary["mean_net_roi"],
                "lower": summary["bootstrap"]["lower_97_5"],
            },
            "passed": summary["mean_net_roi"] is not None
            and summary["mean_net_roi"] > 0
            and summary["bootstrap"]["lower_97_5"] is not None
            and summary["bootstrap"]["lower_97_5"] > 0,
        },
        {
            "name": "both regimes mean >0",
            "value": regimes,
            "passed": all(
                regimes.get(name, {}).get("mean_net_roi") is not None
                and regimes[name]["mean_net_roi"] > 0
                for name in ("janfeb", "mayjul")
            ),
        },
        {
            "name": "at least four of five months mean >0",
            "value": {"positive_months": positive_months, "months": months},
            "passed": positive_months >= 4,
        },
        {
            "name": "selected capacity P50 >= $250",
            "value": summary["capacity_p50"],
            "passed": summary["capacity_p50"] is not None and summary["capacity_p50"] >= 250,
        },
        {
            "name": "weekly nominal deployment P50 >= $10,000",
            "value": summary["weekly_nominal_p50"],
            "passed": summary["weekly_nominal_p50"] is not None
            and summary["weekly_nominal_p50"] >= 10_000,
        },
        {
            "name": "point-in-time and execution integrity",
            "value": integrity,
            "passed": integrity_pass,
        },
        {
            "name": "full entity mean ROI increment vs BASE >=0",
            "value": (
                summary["mean_net_roi"] - base_summary["mean_net_roi"]
                if summary["mean_net_roi"] is not None
                and base_summary["mean_net_roi"] is not None
                else None
            ),
            "passed": summary["mean_net_roi"] is not None
            and base_summary["mean_net_roi"] is not None
            and summary["mean_net_roi"] >= base_summary["mean_net_roi"],
        },
    ]
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Pump.fun T+30s/T+60s 终局实验",
        "",
        "> 全部收益来自首次样本外预测；主执行为$250、TP2/SL0.5/4h、真实池冲击、链上费率及双边100bps。",
        "",
        "| 候选 | 选中 | 正收益 | 平均净ROI | 97.5%下界 | 容量P50 | 周部署P50 | 通过 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for delay in ("30s", "60s"):
        primary = result["delays"][delay]["models"]["hgb_primary"]
        verdict = result["delays"][delay]["decision"]["passed"]
        lines.append(
            f"| T+{delay}→entry | {primary['selected']} | {primary['positive']} | "
            f"{pct(primary['mean_net_roi'])} | {pct(primary['bootstrap']['lower_97_5'])} | "
            f"{money(primary['capacity_p50'])} | {money(primary['weekly_nominal_p50'])} | "
            f"{'是' if verdict else '否'} |"
        )
    lines += ["", "## 冻结闸门", ""]
    for delay in ("30s", "60s"):
        lines += [f"### T+{delay}", "", "| 条件 | 是否满足 |", "|---|---:|"]
        for check in result["delays"][delay]["decision"]["checks"]:
            lines.append(f"| {check['name']} | {'是' if check['passed'] else '否'} |")
        lines.append("")
    final = result["terminal_decision"]
    lines += [
        "## 终局裁决",
        "",
        final["message"],
        "",
        "历史通过也不授权交易，只允许冻结规则的唯一未来 E2；两个候选均失败则按预注册承诺永久关闭普通公开数据 Pump 方向。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir", type=Path, default=Path("crypto/pump_tail_research/data")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("crypto/pump_tail_research/output")
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "protocol": {
            "random_state": RANDOM_STATE,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "selection_rate": SELECTION_RATE,
            "stake_usd": STAKE_USD,
            "folds": FOLDS,
            "feature_sets": FEATURE_SETS,
        },
        "delays": {},
    }
    all_prediction_frames = []
    for delay in ("30s", "60s"):
        frames = []
        integrity = {}
        for regime in ("janfeb", "mayjul"):
            paths = Paths(
                base=args.data_dir / f"dune_terminal_base_{regime}_{delay}.csv",
                entity=args.data_dir / f"dune_terminal_entity_{regime}_{delay}.csv",
                execution=args.data_dir / f"dune_terminal_execution_{regime}_{delay}.csv",
            )
            frame, audit = load_regime(paths, regime)
            frames.append(frame)
            integrity[regime] = audit
        frame = pd.concat(frames, ignore_index=True).sort_values(["graduated_at", "mint"])
        predictions, fold_audit = run_models(frame)
        predictions["delay"] = delay
        all_prediction_frames.append(predictions)
        model_summaries = {}
        primary_rows = predictions[predictions.model == "hgb_primary"]
        all_dates = pd.DatetimeIndex(primary_rows.date)
        for model_name in predictions.model.unique():
            model_rows = predictions[predictions.model == model_name]
            model_summaries[model_name] = summarize_model(model_rows, all_dates)
        verdict = decision(
            model_summaries["hgb_primary"], model_summaries["hgb_base"], integrity
        )
        result["delays"][delay] = {
            "rows": len(frame),
            "integrity": integrity,
            "fold_audit": fold_audit,
            "models": model_summaries,
            "decision": verdict,
        }

    passing = [
        delay for delay in ("30s", "60s") if result["delays"][delay]["decision"]["passed"]
    ]
    if passing:
        chosen = "60s" if "60s" in passing else "30s"
        result["terminal_decision"] = {
            "status": "historical_candidate_for_single_future_E2",
            "chosen_delay": chosen,
            "message": f"历史 development 通过；只允许较长的通过候选 T+{chosen} 进入一次未来 E2。",
        }
    else:
        result["terminal_decision"] = {
            "status": "permanently_close_public_pump_post_graduation",
            "chosen_delay": None,
            "message": "两个历史候选均未通过：永久关闭普通公开数据的 Pump 毕业后交易/LP/entity 研究预算。",
        }

    predictions = pd.concat(all_prediction_frames, ignore_index=True)
    predictions.to_csv(args.output_dir / "terminal_oos_predictions.csv", index=False)
    (args.output_dir / "terminal_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=native) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "terminal_report.md").write_text(
        render_report(result), encoding="utf-8"
    )
    print(json.dumps(result["terminal_decision"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
