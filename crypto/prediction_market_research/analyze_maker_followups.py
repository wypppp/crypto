#!/usr/bin/env python3
"""Reproduce maker early-performance, capacity, and concentration diagnostics."""

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def quantiles(series: pd.Series) -> dict:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return {
        key: float(value)
        for key, value in values.quantile(
            [0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
        ).items()
    }


def performance_summary(frame: pd.DataFrame) -> dict:
    valid = frame[frame["resolved_collateral_turnover"] > 0].copy()
    valid["edge"] = (
        valid["resolved_trade_pnl"] / valid["resolved_collateral_turnover"]
    )
    return {
        "wallets_n": int(len(valid)),
        "positive_wallets_n": int((valid["resolved_trade_pnl"] > 0).sum()),
        "positive_wallet_share": float((valid["resolved_trade_pnl"] > 0).mean()),
        "resolved_turnover": float(valid["resolved_collateral_turnover"].sum()),
        "resolved_trade_pnl": float(valid["resolved_trade_pnl"].sum()),
        "weighted_edge": float(
            valid["resolved_trade_pnl"].sum()
            / valid["resolved_collateral_turnover"].sum()
        ),
        "wallet_edge_quantiles": quantiles(valid["edge"]),
    }


def capacity_summary(
    frame: pd.DataFrame,
    ratio_column: str = "daily_maker_turnover_per_capital",
    turnover_column: str = "daily_maker_turnover",
) -> dict:
    valid = frame.replace([np.inf, -np.inf], np.nan).dropna(
        subset=[ratio_column]
    )
    ratio = valid[ratio_column]
    return {
        "wallets_n": int(len(valid)),
        "capital_median": float(valid["capital_upper_bound"].median()),
        "daily_maker_turnover_median": float(valid[turnover_column].median()),
        "daily_maker_turnover_per_capital_quantiles": quantiles(ratio),
        "share_ge_3_16x_per_day": float((ratio >= 3.16).mean()),
        "share_ge_6_33x_per_day": float((ratio >= 6.33).mean()),
        "share_ge_10x_per_day": float((ratio >= 10).mean()),
    }


def main() -> dict:
    cohort = pd.read_csv(DATA / "dune_v2_may01_07_cohort_90d_final.csv")
    causal = pd.read_csv(DATA / "dune_all_high_activity_causal_persistence.csv")
    roles = pd.read_csv(DATA / "dune_all_high_activity_order_role.csv")
    cohort["wallet"] = cohort["wallet"].astype(str).str.upper()
    causal["wallet"] = causal["wallet"].astype(str).str.upper()
    roles["wallet"] = roles["wallet"].astype(str).str.upper()

    high_ids = set(causal["wallet"])
    high = cohort[cohort["wallet"].isin(high_ids)].copy()

    first_half_all = causal[causal["period"] == "days_0_45"]
    first_half_maker = roles[
        (roles["period"] == "days_0_45")
        & (roles["order_role"] == "resting_maker_row")
    ]
    second_half_maker = roles[
        (roles["period"] == "days_45_90")
        & (roles["order_role"] == "resting_maker_row")
    ]

    first_half_rank = first_half_all.copy()
    first_half_rank["edge"] = (
        first_half_rank["resolved_trade_pnl"]
        / first_half_rank["resolved_collateral_turnover"].replace(0, np.nan)
    )
    first_half_rank["quintile"] = pd.qcut(
        first_half_rank["edge"].rank(method="first"),
        5,
        labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
    )
    selected_ids = set(
        first_half_rank.loc[first_half_rank["quintile"] == "Q5", "wallet"]
    )

    maker_90 = (
        roles[roles["order_role"] == "resting_maker_row"]
        .groupby("wallet", as_index=False)
        .agg(
            maker_resolved_turnover=("resolved_collateral_turnover", "sum"),
            maker_resolved_trade_pnl=("resolved_trade_pnl", "sum"),
            maker_resolved_fills=("resolved_fill_events_n", "sum"),
            crypto_5m_maker_turnover=("crypto_5m_collateral_turnover", "sum"),
        )
    )
    capacity = high.merge(maker_90, on="wallet", how="left")
    capacity["daily_maker_turnover"] = capacity["maker_resolved_turnover"] / 90
    capacity["daily_maker_turnover_per_capital"] = (
        capacity["daily_maker_turnover"]
        / capacity["capital_upper_bound"].replace(0, np.nan)
    )
    capacity["daily_crypto_5m_maker_turnover"] = (
        capacity["crypto_5m_maker_turnover"] / 90
    )
    capacity["daily_crypto_5m_maker_turnover_per_capital"] = (
        capacity["daily_crypto_5m_maker_turnover"]
        / capacity["capital_upper_bound"].replace(0, np.nan)
    )
    capacity["maker_edge_90d"] = (
        capacity["maker_resolved_trade_pnl"]
        / capacity["maker_resolved_turnover"].replace(0, np.nan)
    )
    capacity["selected_by_first_45d_q5"] = capacity["wallet"].isin(selected_ids)

    selected_forward_maker = second_half_maker[
        second_half_maker["wallet"].isin(selected_ids)
    ].sort_values("resolved_trade_pnl", ascending=False)
    total_selected_profit = selected_forward_maker["resolved_trade_pnl"].sum()

    required_daily_return_10x_year = 10 ** (1 / 365) - 1
    required_30d_return_10x_year = 10 ** (30 / 365) - 1
    economic_gate = {
        "target": "Grow 1 unit of capital to 10 units in 365 days before adding capital",
        "required_net_daily_compound_return": required_daily_return_10x_year,
        "required_net_30d_compound_return": required_30d_return_10x_year,
        "required_net_edge_by_daily_turnover": {
            str(turnover): required_daily_return_10x_year / turnover
            for turnover in (0.31, 1.0, 3.16, 10.0)
        },
        "old_joint_gate_implied_arithmetic_daily_return": 0.002 * 10,
    }

    result = {
        "scope_warning": (
            "The 212 wallets were selected ex post for exceeding 10,000 fills over "
            "their full 90-day horizon. Early-period statistics are conditional on "
            "later high activity and are not an unbiased new-entrant baseline."
        ),
        "later_high_frequency_wallets_n": int(len(high)),
        "early_performance": {
            "days_0_45_all_roles": performance_summary(first_half_all),
            "days_0_45_resting_maker": performance_summary(first_half_maker),
            "days_45_90_resting_maker_all_continuers": performance_summary(
                second_half_maker
            ),
        },
        "capacity": {
            "definition": (
                "90-day resolved resting-maker turnover / 90 / full-horizon "
                "cash-path capital upper bound; descriptive, not an executable queue estimate"
            ),
            "all_212": capacity_summary(capacity),
            "capital_1000_2000_all_markets": capacity_summary(
                capacity[capacity["capital_upper_bound"].between(1000, 2000)]
            ),
            "capital_1000_2000_crypto_5m": capacity_summary(
                capacity[capacity["capital_upper_bound"].between(1000, 2000)],
                ratio_column="daily_crypto_5m_maker_turnover_per_capital",
                turnover_column="daily_crypto_5m_maker_turnover",
            ),
            "first_45d_q5_selected": capacity_summary(
                capacity[capacity["selected_by_first_45d_q5"]]
            ),
        },
        "selected_forward_maker_profit_concentration": {
            "wallets_n": int(len(selected_forward_maker)),
            "total_profit": float(total_selected_profit),
            "top_1_share": float(
                selected_forward_maker["resolved_trade_pnl"].head(1).sum()
                / total_selected_profit
            ),
            "top_5_share": float(
                selected_forward_maker["resolved_trade_pnl"].head(5).sum()
                / total_selected_profit
            ),
            "top_10_share": float(
                selected_forward_maker["resolved_trade_pnl"].head(10).sum()
                / total_selected_profit
            ),
        },
        "economic_gate": economic_gate,
    }

    out_json = DATA / "maker_followup_existing_data_2026-08-26.json"
    out_csv = DATA / "maker_capacity_wallets_2026-08-26.csv"
    out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    capacity.sort_values("wallet").to_csv(out_csv, index=False)
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    main()
