#!/usr/bin/env python3
"""Run the preregistered low-cost MELT entity-feature ablation.

This experiment tests whether MELT's group4 bundle/entity features add
information beyond context, address-level holdings, activity, and fixed
summaries of the pre-migration price/volume sequence.  The outcome is MELT's
non-high-risk label, not a trading return; a positive result only authorizes
the later 2026 trading-outcome experiment.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SEED = 42
TRAIN_RATIO = 0.70
BOOTSTRAPS = 1_000
TOP_FRACTION = 0.10


def sequence_summaries(series: pd.Series, lengths: np.ndarray) -> np.ndarray:
    """Make a fixed, label-independent summary of each 360 x 5 sequence."""
    output = np.full((len(series), 50), np.nan, dtype=np.float32)
    quantiles = (0.10, 0.50, 0.90)
    for row_index, (raw, raw_length) in enumerate(zip(series, lengths)):
        values = np.asarray(raw.tolist(), dtype=np.float64)
        length = max(1, min(int(raw_length), len(values)))
        values = values[:length]
        x = np.arange(length, dtype=np.float64)
        x_centered = x - x.mean()
        denominator = float(np.dot(x_centered, x_centered))
        features = []
        for channel in range(values.shape[1]):
            channel_values = values[:, channel]
            slope = (
                float(np.dot(x_centered, channel_values - channel_values.mean()) / denominator)
                if denominator > 0
                else 0.0
            )
            features.extend(
                [
                    channel_values[0],
                    channel_values[-1],
                    channel_values.min(),
                    channel_values.max(),
                    channel_values.mean(),
                    channel_values.std(),
                    *np.quantile(channel_values, quantiles),
                    slope,
                ]
            )
        output[row_index] = features
    return output


def build_models() -> dict[str, Any]:
    return {
        "logistic_l2": make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True),
            StandardScaler(),
            LogisticRegression(
                C=1.0,
                penalty="l2",
                solver="lbfgs",
                max_iter=1_000,
                class_weight="balanced",
                random_state=SEED,
            ),
        ),
        "hist_gradient_boosting": make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True),
            HistGradientBoostingClassifier(
                learning_rate=0.05,
                max_iter=300,
                max_leaf_nodes=31,
                min_samples_leaf=50,
                l2_regularization=1.0,
                class_weight="balanced",
                random_state=SEED,
            ),
        ),
    }


def metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    selected = max(1, int(np.ceil(len(y) * TOP_FRACTION)))
    order = np.argsort(-probability, kind="stable")[:selected]
    return {
        "auprc": float(average_precision_score(y, probability)),
        "log_loss": float(log_loss(y, probability, labels=[0, 1])),
        "top10_precision": float(y[order].mean()),
        "top10_selected": int(selected),
    }


def block_bootstrap(
    y: np.ndarray,
    dates: np.ndarray,
    base_probability: np.ndarray,
    combined_probability: np.ndarray,
) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(SEED)
    unique_dates = np.unique(dates)
    by_date = {date: np.flatnonzero(dates == date) for date in unique_dates}
    deltas = {"auprc": [], "log_loss": [], "top10_precision": []}
    for _ in range(BOOTSTRAPS):
        sampled_dates = rng.choice(unique_dates, size=len(unique_dates), replace=True)
        indices = np.concatenate([by_date[date] for date in sampled_dates])
        base = metrics(y[indices], base_probability[indices])
        combined = metrics(y[indices], combined_probability[indices])
        deltas["auprc"].append(combined["auprc"] - base["auprc"])
        # Lower log loss is better, so improvement has the opposite sign.
        deltas["log_loss"].append(base["log_loss"] - combined["log_loss"])
        deltas["top10_precision"].append(
            combined["top10_precision"] - base["top10_precision"]
        )
    return {
        name: {
            "mean": float(np.mean(values)),
            "p2_5": float(np.quantile(values, 0.025)),
            "p50": float(np.quantile(values, 0.50)),
            "p97_5": float(np.quantile(values, 0.975)),
        }
        for name, values in deltas.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    base_dir = Path(__file__).resolve().parent
    parser.add_argument("--features", type=Path, default=base_dir / "data/melt_feat.parquet")
    parser.add_argument("--labels", type=Path, default=base_dir / "data/melt_label.parquet")
    parser.add_argument("--out-dir", type=Path, default=base_dir / "output")
    args = parser.parse_args()

    features = pd.read_parquet(args.features)
    labels = pd.read_parquet(args.labels)
    merged = features.merge(labels, on="mint_address", how="inner", validate="one_to_one")
    merged = merged.loc[
        (merged["group3_time_span_valid"] >= 60) & (merged["group3_holder_num"] >= 100)
    ].sort_values(["mint_ts", "mint_address"], kind="stable").reset_index(drop=True)

    group1 = [column for column in merged if column.startswith("group1_")]
    group2 = [column for column in merged if column.startswith("group2_")]
    group3 = [column for column in merged if column.startswith("group3_")]
    group4 = [column for column in merged if column.startswith("group4_")]
    sequence = sequence_summaries(merged["ts"], merged["ts_len"].to_numpy())
    base_tabular = merged[group1 + group2 + group3].to_numpy(dtype=np.float32)
    entity = merged[group4].to_numpy(dtype=np.float32)
    feature_sets = {
        "BASE": np.column_stack([base_tabular, sequence]),
        "ENTITY_ONLY": entity,
        "BASE_PLUS_ENTITY": np.column_stack([base_tabular, sequence, entity]),
    }
    feature_sets = {
        name: np.where(np.isfinite(values), values, np.nan).astype(np.float32)
        for name, values in feature_sets.items()
    }

    # This matches the official repository's useful/safe orientation: high=0,
    # medium or low=1.  It does not claim medium/low is a profitable token.
    y = (merged["label"].to_numpy() != "high").astype(np.int8)
    split = int(len(merged) * TRAIN_RATIO)
    dates = pd.to_datetime(merged["mint_ts"], unit="s", utc=True).dt.date.astype(str).to_numpy()
    results: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "train_ratio": TRAIN_RATIO,
        "bootstrap_replicates": BOOTSTRAPS,
        "target": "1 if MELT label is medium/low; 0 if high",
        "filter": "group3_time_span_valid >= 60 and group3_holder_num >= 100",
        "rows_before_filter": int(len(features)),
        "rows_after_filter": int(len(merged)),
        "train_rows": int(split),
        "test_rows": int(len(merged) - split),
        "train_time": [dates[0], dates[split - 1]],
        "test_time": [dates[split], dates[-1]],
        "train_positive_rate": float(y[:split].mean()),
        "test_positive_rate": float(y[split:].mean()),
        "feature_counts": {name: int(values.shape[1]) for name, values in feature_sets.items()},
        "models": {},
        "interpretation_limit": "Risk-label information only; not a trading-return result.",
    }

    for model_name, model_template in build_models().items():
        probabilities = {}
        model_results = {}
        for set_name, values in feature_sets.items():
            # Create a fresh deterministic estimator for every feature set.
            model = build_models()[model_name]
            model.fit(values[:split], y[:split])
            probability = model.predict_proba(values[split:])[:, 1]
            probabilities[set_name] = probability
            model_results[set_name] = metrics(y[split:], probability)

        test_dates = dates[split:]
        fold_results = []
        for fold_number, fold_dates in enumerate(np.array_split(np.unique(test_dates), 3), 1):
            fold_indices = np.flatnonzero(np.isin(test_dates, fold_dates))
            base_fold = metrics(y[split:][fold_indices], probabilities["BASE"][fold_indices])
            combined_fold = metrics(
                y[split:][fold_indices], probabilities["BASE_PLUS_ENTITY"][fold_indices]
            )
            fold_results.append(
                {
                    "fold": fold_number,
                    "dates": [str(fold_dates[0]), str(fold_dates[-1])],
                    "rows": int(len(fold_indices)),
                    "delta_auprc": combined_fold["auprc"] - base_fold["auprc"],
                    "delta_log_loss_improvement": base_fold["log_loss"] - combined_fold["log_loss"],
                    "delta_top10_precision": (
                        combined_fold["top10_precision"] - base_fold["top10_precision"]
                    ),
                }
            )
        model_results["BASE_PLUS_ENTITY_minus_BASE"] = {
            "auprc": (
                model_results["BASE_PLUS_ENTITY"]["auprc"] - model_results["BASE"]["auprc"]
            ),
            "log_loss_improvement": (
                model_results["BASE"]["log_loss"]
                - model_results["BASE_PLUS_ENTITY"]["log_loss"]
            ),
            "top10_precision": (
                model_results["BASE_PLUS_ENTITY"]["top10_precision"]
                - model_results["BASE"]["top10_precision"]
            ),
            "date_block_bootstrap": block_bootstrap(
                y[split:],
                test_dates,
                probabilities["BASE"],
                probabilities["BASE_PLUS_ENTITY"],
            ),
            "three_test_time_blocks": fold_results,
        }
        results["models"][model_name] = model_results

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "melt_entity_ablation.json"
    markdown_path = args.out_dir / "melt_entity_ablation.md"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# MELT entity 特征增量消融",
        "",
        f"- 样本：{results['rows_after_filter']:,}（train {results['train_rows']:,} / test {results['test_rows']:,}）",
        f"- 测试窗口：{results['test_time'][0]} 至 {results['test_time'][1]}",
        f"- 测试集 medium/low 比例：{results['test_positive_rate']:.2%}",
        "- 注意：这是风险标签，不是 10x 或交易收益。",
        "",
        "| 模型 | 特征 | AUPRC | log loss | top 10% precision |",
        "|---|---|---:|---:|---:|",
    ]
    for model_name, model_result in results["models"].items():
        for set_name in ("BASE", "ENTITY_ONLY", "BASE_PLUS_ENTITY"):
            value = model_result[set_name]
            lines.append(
                f"| {model_name} | {set_name} | {value['auprc']:.4f} | "
                f"{value['log_loss']:.4f} | {value['top10_precision']:.2%} |"
            )
        delta = model_result["BASE_PLUS_ENTITY_minus_BASE"]
        bootstrap = delta["date_block_bootstrap"]
        lines.extend(
            [
                "",
                f"{model_name} 增量：ΔAUPRC {delta['auprc']:+.4f}；"
                f"log-loss 改善 {delta['log_loss_improvement']:+.4f}；"
                f"Δtop10 precision {delta['top10_precision']:+.2%}。",
                "",
                "按日 block bootstrap 95% 区间："
                f"ΔAUPRC [{bootstrap['auprc']['p2_5']:+.4f}, {bootstrap['auprc']['p97_5']:+.4f}]；"
                f"log-loss 改善 [{bootstrap['log_loss']['p2_5']:+.4f}, "
                f"{bootstrap['log_loss']['p97_5']:+.4f}]；"
                f"Δtop10 precision [{bootstrap['top10_precision']['p2_5']:+.2%}, "
                f"{bootstrap['top10_precision']['p97_5']:+.2%}]。",
                "",
            ]
        )
    markdown_path.write_text("\n".join(lines) + "\n")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path)}, indent=2))


if __name__ == "__main__":
    main()
