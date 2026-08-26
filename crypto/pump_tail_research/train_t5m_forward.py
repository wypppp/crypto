#!/usr/bin/env python3
"""Run the frozen T+5m time-forward classification experiment."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


RANDOM_STATE = 20260824
TARGET_MULTIPLE = 10.0
BREAKEVEN_PRECISION = 1 / TARGET_MULTIPLE
PRIMARY_SELECTION_RATE = 0.10
DIAGNOSTIC_SELECTION_RATES = (0.01, 0.02, 0.05, 0.10, 0.20)
BOOTSTRAP_DRAWS = 10_000

FEATURE_COLUMNS = [
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

FOLDS = [
    {
        "fold": 1,
        "train_start": "2026-05-01",
        "train_end": "2026-06-01",
        "validation_start": "2026-06-01",
        "validation_end": "2026-06-15",
        "test_start": "2026-06-15",
        "test_end": "2026-06-29",
    },
    {
        "fold": 2,
        "train_start": "2026-05-01",
        "train_end": "2026-06-15",
        "validation_start": "2026-06-15",
        "validation_end": "2026-06-29",
        "test_start": "2026-06-29",
        "test_end": "2026-07-13",
    },
    {
        "fold": 3,
        "train_start": "2026-05-01",
        "train_end": "2026-06-29",
        "validation_start": "2026-06-29",
        "validation_end": "2026-07-13",
        "test_start": "2026-07-13",
        "test_end": "2026-07-25",
    },
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
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "t", "yes"}).astype(float)


def load_data(features_path: Path, outcomes_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    features = pd.read_csv(features_path, na_values=["<nil>"])
    outcomes = pd.read_csv(outcomes_path, na_values=["<nil>"])
    required_features = {"graduated_at", "mint", *FEATURE_COLUMNS} - {
        "graduation_hour_sin", "graduation_hour_cos",
        "graduation_dow_sin", "graduation_dow_cos",
    }
    missing_features = sorted(required_features - set(features.columns))
    if missing_features:
        raise ValueError(f"feature CSV missing: {missing_features}")
    required_outcomes = {"mint", "remaining_max_5m", "capacity_5pct_usd_5m"}
    missing_outcomes = sorted(required_outcomes - set(outcomes.columns))
    if missing_outcomes:
        raise ValueError(f"outcome CSV missing: {missing_outcomes}")
    if features["mint"].duplicated().any() or outcomes["mint"].duplicated().any():
        raise ValueError("mint must be unique in both inputs")

    df = features.merge(
        outcomes[["mint", "remaining_max_5m", "capacity_5pct_usd_5m"]],
        on="mint",
        how="inner",
        suffixes=("", "_outcome"),
        validate="one_to_one",
    )
    if len(df) != len(features) or len(df) != len(outcomes):
        raise ValueError("feature/outcome universes do not match exactly")
    df["graduated_at"] = pd.to_datetime(df["graduated_at"], utc=True, errors="raise")
    df["quote_is_wsol"] = parse_bool(df["quote_is_wsol"])

    hour = df["graduated_at"].dt.hour + df["graduated_at"].dt.minute / 60
    dow = df["graduated_at"].dt.dayofweek
    df["graduation_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["graduation_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["graduation_dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["graduation_dow_cos"] = np.cos(2 * np.pi * dow / 7)

    for column in FEATURE_COLUMNS + [
        "remaining_max_5m", "capacity_5pct_usd_5m_outcome"
    ]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    if not np.allclose(
        df["capacity_5pct_usd_5m"],
        df["capacity_5pct_usd_5m_outcome"],
        rtol=1e-10,
        atol=1e-8,
        equal_nan=True,
    ):
        raise ValueError("independent feature/outcome capacity calculations disagree")
    df["label_10x"] = (df["remaining_max_5m"] >= TARGET_MULTIPLE).astype(int)
    df["date"] = df["graduated_at"].dt.floor("D")

    forbidden = {
        "remaining_max_5m", "max_30d", "p7d", "p30d",
        "future_trade_rows_5m",
    }
    if forbidden & set(FEATURE_COLUMNS):
        raise ValueError("outcome leakage found in FEATURE_COLUMNS")

    audit = {
        "rows": len(df),
        "unique_mints": int(df["mint"].nunique()),
        "feature_count": len(FEATURE_COLUMNS),
        "label_positive_count": int(df["label_10x"].sum()),
        "label_positive_rate": float(df["label_10x"].mean()),
        "feature_missing_cells": int(df[FEATURE_COLUMNS].isna().sum().sum()),
        "capacity_match": True,
        "cohort_min": native(df["graduated_at"].min()),
        "cohort_max": native(df["graduated_at"].max()),
    }
    return df.sort_values(["graduated_at", "mint"]).reset_index(drop=True), audit


def make_models() -> dict[str, Pipeline]:
    imputer = SimpleImputer(strategy="median", add_indicator=True)
    hgb = Pipeline(
        [
            ("imputer", imputer),
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
    logistic = Pipeline(
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
    return {"hgb_primary": hgb, "logistic_diagnostic": logistic}


def wilson_lower(hits: int, total: int, confidence: float = 0.95) -> float | None:
    if total <= 0:
        return None
    z = float(norm.ppf(confidence))
    p = hits / total
    denominator = 1 + z * z / total
    center = p + z * z / (2 * total)
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (center - radius) / denominator


def selection_metrics(frame: pd.DataFrame, selected: pd.Series) -> dict[str, Any]:
    chosen = frame.loc[selected]
    selected_count = len(chosen)
    hits = int(chosen["label_10x"].sum())
    precision = hits / selected_count if selected_count else None
    total_capacity = float(chosen["capacity_5pct_usd_5m"].sum())
    hit_capacity = float(
        chosen.loc[chosen["label_10x"] == 1, "capacity_5pct_usd_5m"].sum()
    )
    capacity_precision = hit_capacity / total_capacity if total_capacity else None
    return {
        "selected_count": selected_count,
        "hits": hits,
        "precision": precision,
        "wilson_95_one_sided_lower": wilson_lower(hits, selected_count),
        "selected_rate": selected_count / len(frame) if len(frame) else None,
        "capacity_weighted_precision": capacity_precision,
        "selected_capacity_usd": total_capacity,
        "hit_capacity_usd": hit_capacity,
        "selected_capacity_p50_usd": native(
            chosen["capacity_5pct_usd_5m"].median()
        ),
    }


def capacity_block_bootstrap_lower(
    selected: pd.DataFrame,
    all_test_dates: pd.DatetimeIndex,
    draws: int = BOOTSTRAP_DRAWS,
) -> tuple[float | None, dict[str, Any]]:
    dates = pd.DatetimeIndex(sorted(pd.unique(all_test_dates)))
    daily = (
        selected.assign(
            hit_capacity=lambda x: x["capacity_5pct_usd_5m"] * x["label_10x"]
        )
        .groupby("date")
        .agg(
            hit_capacity=("hit_capacity", "sum"),
            total_capacity=("capacity_5pct_usd_5m", "sum"),
        )
        .reindex(dates, fill_value=0)
    )
    hit = daily["hit_capacity"].to_numpy(float)
    total = daily["total_capacity"].to_numpy(float)
    if total.sum() <= 0 or len(dates) == 0:
        return None, {"days": len(dates), "valid_draws": 0}
    rng = np.random.default_rng(RANDOM_STATE)
    indices = rng.integers(0, len(dates), size=(draws, len(dates)))
    numerator = hit[indices].sum(axis=1)
    denominator = total[indices].sum(axis=1)
    valid = denominator > 0
    ratios = numerator[valid] / denominator[valid]
    lower = float(np.quantile(ratios, 0.05)) if len(ratios) else None
    return lower, {
        "days": len(dates),
        "draws": draws,
        "valid_draws": len(ratios),
        "bootstrap_p50": native(np.quantile(ratios, 0.50)) if len(ratios) else None,
        "bootstrap_p95": native(np.quantile(ratios, 0.95)) if len(ratios) else None,
    }


def fit_and_score(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    prediction_frames: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    fold_audits: dict[str, Any] = {}

    for fold_spec in FOLDS:
        fold = fold_spec["fold"]
        train = df[
            (df.graduated_at >= pd.Timestamp(fold_spec["train_start"], tz="UTC"))
            & (df.graduated_at < pd.Timestamp(fold_spec["train_end"], tz="UTC"))
        ].copy()
        validation = df[
            (df.graduated_at >= pd.Timestamp(fold_spec["validation_start"], tz="UTC"))
            & (df.graduated_at < pd.Timestamp(fold_spec["validation_end"], tz="UTC"))
        ].copy()
        test = df[
            (df.graduated_at >= pd.Timestamp(fold_spec["test_start"], tz="UTC"))
            & (df.graduated_at < pd.Timestamp(fold_spec["test_end"], tz="UTC"))
        ].copy()
        if min(len(train), len(validation), len(test)) == 0:
            raise ValueError(f"fold {fold} contains an empty partition")
        fold_audits[str(fold)] = {
            "train_n": len(train),
            "train_rate": float(train.label_10x.mean()),
            "validation_n": len(validation),
            "validation_rate": float(validation.label_10x.mean()),
            "test_n": len(test),
            "test_rate": float(test.label_10x.mean()),
            **fold_spec,
        }

        for model_name, model in make_models().items():
            fit_kwargs: dict[str, Any] = {}
            if model_name == "hgb_primary":
                positives = int(train.label_10x.sum())
                negatives = len(train) - positives
                positive_weight = negatives / positives
                weights = np.where(train.label_10x.to_numpy() == 1, positive_weight, 1.0)
                fit_kwargs["model__sample_weight"] = weights
            model.fit(train[FEATURE_COLUMNS], train["label_10x"], **fit_kwargs)
            validation_score = model.predict_proba(validation[FEATURE_COLUMNS])[:, 1]
            test_score = model.predict_proba(test[FEATURE_COLUMNS])[:, 1]

            prediction = test[
                [
                    "graduated_at", "date", "mint", "label_10x",
                    "remaining_max_5m", "capacity_5pct_usd_5m",
                ]
            ].copy()
            prediction["fold"] = fold
            prediction["model"] = model_name
            prediction["score"] = test_score

            for rate in DIAGNOSTIC_SELECTION_RATES:
                threshold = float(np.quantile(validation_score, 1 - rate, method="higher"))
                rate_name = str(int(rate * 100)).zfill(2)
                prediction[f"selected_top_{rate_name}pct"] = test_score >= threshold
                metrics = selection_metrics(
                    prediction, prediction[f"selected_top_{rate_name}pct"]
                )
                fold_rows.append(
                    {
                        "fold": fold,
                        "model": model_name,
                        "validation_target_selection_rate": rate,
                        "validation_threshold": threshold,
                        "test_n": len(test),
                        "test_base_rate": float(test.label_10x.mean()),
                        **metrics,
                    }
                )
            prediction_frames.append(prediction)

            if model_name == "hgb_primary":
                importance = permutation_importance(
                    model,
                    test[FEATURE_COLUMNS],
                    test["label_10x"],
                    scoring="average_precision",
                    n_repeats=3,
                    random_state=RANDOM_STATE + fold,
                    n_jobs=1,
                )
                for feature, mean, std in zip(
                    FEATURE_COLUMNS,
                    importance.importances_mean,
                    importance.importances_std,
                ):
                    importance_rows.append(
                        {
                            "fold": fold,
                            "feature": feature,
                            "ap_importance_mean": mean,
                            "ap_importance_std": std,
                        }
                    )

    predictions = pd.concat(prediction_frames, ignore_index=True)
    fold_metrics = pd.DataFrame(fold_rows)
    importance = pd.DataFrame(importance_rows)
    return predictions, fold_metrics, importance, fold_audits


def pooled_metrics(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for model_name in predictions.model.unique():
        model_rows = predictions[predictions.model == model_name].copy()
        model_summary: dict[str, Any] = {
            "oos_n": len(model_rows),
            "oos_base_rate": float(model_rows.label_10x.mean()),
            "average_precision": float(
                average_precision_score(model_rows.label_10x, model_rows.score)
            ),
            "roc_auc": float(roc_auc_score(model_rows.label_10x, model_rows.score)),
            "cutoffs": {},
        }
        for rate in DIAGNOSTIC_SELECTION_RATES:
            rate_name = str(int(rate * 100)).zfill(2)
            selected_col = f"selected_top_{rate_name}pct"
            metrics = selection_metrics(model_rows, model_rows[selected_col])
            row = {
                "model": model_name,
                "validation_target_selection_rate": rate,
                **metrics,
            }
            rows.append(row)
            model_summary["cutoffs"][str(rate)] = {
                key: native(value) for key, value in metrics.items()
            }
        summary[model_name] = model_summary
    return pd.DataFrame(rows), summary


def make_plot(pooled: pd.DataFrame, destination: Path, oos_base_rate: float) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), sharex=True)
    for model_name, label, color in (
        ("hgb_primary", "HGB primary", "#4c78a8"),
        ("logistic_diagnostic", "Logistic diagnostic", "#f58518"),
    ):
        subset = pooled[pooled.model == model_name].sort_values(
            "validation_target_selection_rate"
        )
        x = 100 * subset.validation_target_selection_rate
        axes[0].plot(x, 100 * subset.precision, marker="o", label=label, color=color)
        axes[1].plot(
            x,
            100 * subset.capacity_weighted_precision,
            marker="o",
            label=label,
            color=color,
        )
    for ax, title in zip(
        axes,
        ("Equal-token precision", "5% capacity-weighted precision"),
    ):
        ax.axhline(10, color="black", linestyle="--", linewidth=1.8,
                   label="10x gross break-even")
        ax.axhline(100 * oos_base_rate, color="gray", linestyle=":", linewidth=1.5,
                   label="OOS unconditional base rate")
        ax.set_title(title)
        ax.set_xlabel("Validation target selection rate (%)")
        ax.set_xticks([1, 2, 5, 10, 20])
        ax.grid(True, alpha=0.25)
    axes[0].set_ylabel("Out-of-sample precision (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False)
    fig.suptitle("T+5m frozen time-forward selection test")
    fig.tight_layout(rect=(0, 0.12, 1, 0.94))
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)


def render_report(
    audit: dict[str, Any],
    fold_audits: dict[str, Any],
    fold_metrics: pd.DataFrame,
    pooled: pd.DataFrame,
    summary: dict[str, Any],
    importance: pd.DataFrame,
) -> str:
    primary = summary["primary_decision"]
    primary_pooled = pooled[
        (pooled.model == "hgb_primary")
        & (pooled.validation_target_selection_rate == PRIMARY_SELECTION_RATE)
    ].iloc[0]
    verdict = "通过" if primary["passed"] else "不通过"
    lines = [
        "# T+5m 延迟选币：冻结时间前向检验",
        "",
        f"## 结论：{verdict}",
        "",
        (
            f"主模型在三个从未参与拟合或阈值确定的测试窗口共选中 "
            f"{int(primary_pooled.selected_count):,} 个币，命中 "
            f"{int(primary_pooled.hits):,} 个；precision = {pct(primary_pooled.precision)}，"
            f"单侧95% Wilson下界 = {pct(primary_pooled.wilson_95_one_sided_lower)}。"
        ),
        "",
        (
            f"按每个池 T+5m 的5%容量部署，precision = "
            f"{pct(primary_pooled.capacity_weighted_precision)}，按日期 block bootstrap 的"
            f"单侧95%下界 = {pct(primary['capacity_bootstrap_95_lower'])}。"
            f"被选币容量中位数为 {money(primary_pooled.selected_capacity_p50_usd)}。"
        ),
        "",
        "主判定要求逐币和容量加权 precision 的置信下界都严格高于10%，并满足样本量、"
        "跨fold稳定性和容量门槛。以下结果按冻结规则机械裁决，不能用诊断模型或其他选择率翻案。",
        "",
        "## 主模型分折结果（validation最高10%阈值）",
        "",
        "| Fold | Train | Validation | Test | 测试基线 | 选中 | 命中 | Precision | 容量加权 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    primary_folds = fold_metrics[
        (fold_metrics.model == "hgb_primary")
        & (fold_metrics.validation_target_selection_rate == PRIMARY_SELECTION_RATE)
    ].sort_values("fold")
    for row in primary_folds.itertuples(index=False):
        fa = fold_audits[str(row.fold)]
        lines.append(
            f"| {row.fold} | {fa['train_n']:,} | {fa['validation_n']:,} | "
            f"{fa['test_n']:,} | {pct(row.test_base_rate)} | {int(row.selected_count):,} | "
            f"{int(row.hits):,} | {pct(row.precision)} | "
            f"{pct(row.capacity_weighted_precision)} |"
        )
    lines += [
        "",
        "## 冻结通过条件",
        "",
        "| 条件 | 结果 | 是否满足 |",
        "|---|---:|---:|",
    ]
    for check in primary["checks"]:
        lines.append(
            f"| {check['name']} | {check['value']} | "
            f"{'是' if check['passed'] else '否'} |"
        )

    lines += [
        "",
        "## 选择率诊断（合并样本外测试）",
        "",
        "| 模型 | 验证期目标选择率 | 选中 | Precision | Wilson下界 | 容量加权Precision | 容量P50 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in pooled.sort_values(["model", "validation_target_selection_rate"]).itertuples(index=False):
        label = "HGB主模型" if row.model == "hgb_primary" else "Logistic诊断"
        lines.append(
            f"| {label} | {pct(row.validation_target_selection_rate)} | "
            f"{int(row.selected_count):,} | {pct(row.precision)} | "
            f"{pct(row.wilson_95_one_sided_lower)} | "
            f"{pct(row.capacity_weighted_precision)} | "
            f"{money(row.selected_capacity_p50_usd)} |"
        )

    top_importance = (
        importance.groupby("feature", as_index=False)
        .agg(ap_importance_mean=("ap_importance_mean", "mean"))
        .sort_values("ap_importance_mean", ascending=False)
        .head(12)
    )
    lines += [
        "",
        "## 主模型诊断",
        "",
        f"合并OOS AUPRC = {summary['models']['hgb_primary']['average_precision']:.4f}，"
        f"ROC AUC = {summary['models']['hgb_primary']['roc_auc']:.4f}。"
        "下面是各fold测试集 permutation AUPRC importance 的平均值，只用于解释，不用于改模型：",
        "",
        "| 特征 | ΔAUPRC |",
        "|---|---:|",
    ]
    for row in top_importance.itertuples(index=False):
        lines.append(f"| `{row.feature}` | {row.ap_importance_mean:.5f} |")

    test_start = pd.Timestamp(FOLDS[0]["test_start"])
    test_end = pd.Timestamp(FOLDS[-1]["test_end"])
    test_weeks = (test_end - test_start).days / 7
    lines += [
        "",
        "## 可部署量与限制",
        "",
        f"测试期共 {test_weeks:.2f} 周；主集合约 "
        f"{primary_pooled.selected_count / test_weeks:,.1f} 个候选/周，"
        f"5%容量合计约 {money(primary_pooled.selected_capacity_usd / test_weeks)}/周，"
        f"其中事后命中容量约 {money(primary_pooled.hit_capacity_usd / test_weeks)}/周。",
        "",
        "- 这是历史时间前向检验，不是实时前向采集；它防止未来日期进入训练，但仍可能受市场制度漂移影响。",
        "- 标签仍是未来最高现货价上界。实际按容量买入会推高成本，退出也未必能在10x成交。",
        "- 模型只证明或否定这份冻结特征与规则；测试后再挑选择率或特征属于新实验。",
        "- 钱包独立数不等于独立主体，创建者也可能控制未识别关联钱包。",
        "",
        "## 数据审计",
        "",
        f"- 全集 {audit['rows']:,} 个唯一mint，冻结特征 {audit['feature_count']} 个。",
        f"- 标签正例 {audit['label_positive_count']:,}，率 {pct(audit['label_positive_rate'])}。",
        f"- 特征缺失单元 {audit['feature_missing_cells']:,}，仅来自零成交币的比例字段，"
        "按当期train中位数加缺失指示器处理。",
        "- 特征SQL和结果SQL独立计算的逐币T+5m容量完全一致。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("crypto/pump_tail_research/data/dune_t5m_features.csv"),
    )
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=Path("crypto/pump_tail_research/data/dune_delay_metrics.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("crypto/pump_tail_research/output"),
    )
    args = parser.parse_args()

    df, audit = load_data(args.features, args.outcomes)
    predictions, fold_metrics, importance, fold_audits = fit_and_score(df)
    pooled, model_summary = pooled_metrics(predictions)

    primary_predictions = predictions[predictions.model == "hgb_primary"].copy()
    primary_selected = primary_predictions["selected_top_10pct"]
    selected_frame = primary_predictions.loc[primary_selected].copy()
    cap_lower, cap_bootstrap = capacity_block_bootstrap_lower(
        selected_frame, pd.DatetimeIndex(primary_predictions["date"])
    )
    primary_row = pooled[
        (pooled.model == "hgb_primary")
        & (pooled.validation_target_selection_rate == PRIMARY_SELECTION_RATE)
    ].iloc[0]
    fold_primary = fold_metrics[
        (fold_metrics.model == "hgb_primary")
        & (fold_metrics.validation_target_selection_rate == PRIMARY_SELECTION_RATE)
    ]
    folds_above = int((fold_primary.precision > BREAKEVEN_PRECISION).sum())
    checks = [
        {
            "name": "选中至少100且命中至少10",
            "value": f"selected={int(primary_row.selected_count)}, hits={int(primary_row.hits)}",
            "passed": bool(primary_row.selected_count >= 100 and primary_row.hits >= 10),
        },
        {
            "name": "逐币precision单侧95%下界 > 10%",
            "value": pct(primary_row.wilson_95_one_sided_lower),
            "passed": bool(primary_row.wilson_95_one_sided_lower > BREAKEVEN_PRECISION),
        },
        {
            "name": "容量加权precision block-bootstrap下界 > 10%",
            "value": pct(cap_lower),
            "passed": bool(cap_lower is not None and cap_lower > BREAKEVEN_PRECISION),
        },
        {
            "name": "至少2/3 fold precision > 10%",
            "value": f"{folds_above}/3",
            "passed": bool(folds_above >= 2),
        },
        {
            "name": "被选容量P50 >= $100",
            "value": money(primary_row.selected_capacity_p50_usd),
            "passed": bool(primary_row.selected_capacity_p50_usd >= 100),
        },
    ]
    primary_decision = {
        "passed": bool(all(check["passed"] for check in checks)),
        "checks": checks,
        "capacity_bootstrap_95_lower": cap_lower,
        "capacity_bootstrap": cap_bootstrap,
        "folds_above_10pct": folds_above,
    }
    summary = {
        "protocol": {
            "target": "remaining_max_5m >= 10",
            "primary_model": "hgb_primary",
            "primary_validation_selection_rate": PRIMARY_SELECTION_RATE,
            "breakeven_precision": BREAKEVEN_PRECISION,
            "random_state": RANDOM_STATE,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "feature_columns": FEATURE_COLUMNS,
            "folds": FOLDS,
        },
        "audit": audit,
        "fold_audits": fold_audits,
        "models": model_summary,
        "primary_decision": primary_decision,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.output_dir / "t5m_oos_predictions.csv", index=False)
    fold_metrics.to_csv(args.output_dir / "t5m_fold_metrics.csv", index=False)
    pooled.to_csv(args.output_dir / "t5m_pooled_cutoffs.csv", index=False)
    importance.to_csv(args.output_dir / "t5m_feature_importance.csv", index=False)
    (args.output_dir / "t5m_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=native) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "t5m_forward_report.md").write_text(
        render_report(audit, fold_audits, fold_metrics, pooled, summary, importance),
        encoding="utf-8",
    )
    make_plot(
        pooled,
        args.output_dir / "t5m_precision_curve.png",
        model_summary["hgb_primary"]["oos_base_rate"],
    )

    print(json.dumps(primary_decision, ensure_ascii=False, indent=2, default=native))
    print(pooled.to_string(index=False))
    print(f"wrote outputs to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
