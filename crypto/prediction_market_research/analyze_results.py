#!/usr/bin/env python3
"""Reproduce the decision metrics used in FINDINGS_2026-08-25.md."""

from pathlib import Path
from typing import List

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def numeric(frame: pd.DataFrame, columns: List[str]) -> None:
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")


def cohort_metrics() -> None:
    d = pd.read_csv(DATA / "dune_v2_may01_07_cohort_90d_final.csv")
    clean = d[(~d["touched_v3"].astype(bool)) & (d["capital_upper_bound"] > 0)].copy()
    print(f"cohort total={len(d):,} clean={len(clean):,}")
    for cap in (500, 1_500, 5_000):
        x = clean[clean["capital_upper_bound"] <= cap]
        print(
            "cap<=${:,}: n={:,} capital=${:,.2f} profit=${:,.2f} "
            "weighted_roi={:.4%} hit5={:.4%} hit10={:.4%} median={:.4f}x".format(
                cap,
                len(x),
                x["capital_upper_bound"].sum(),
                x["net_profit_lower"].sum(),
                x["net_profit_lower"].sum() / x["capital_upper_bound"].sum(),
                (x["return_multiple_lower"] >= 5).mean(),
                (x["return_multiple_lower"] >= 10).mean(),
                x["return_multiple_lower"].median(),
            )
        )

    high = clean[clean["trade_events_n"] > 10_000]
    print(
        "all >10k fills: n={:,} capital=${:,.2f} profit=${:,.2f} "
        "weighted_roi={:.4%} positive={:.4%} hit5={:.4%} median={:.4f}x".format(
            len(high),
            high["capital_upper_bound"].sum(),
            high["net_profit_lower"].sum(),
            high["net_profit_lower"].sum() / high["capital_upper_bound"].sum(),
            (high["net_profit_lower"] > 0).mean(),
            (high["return_multiple_lower"] >= 5).mean(),
            high["return_multiple_lower"].median(),
        )
    )


def one_fill_metrics() -> None:
    d = pd.read_csv(DATA / "dune_one_fill_longshot_baseline.csv")
    numeric(d, ["net_profit", "return_multiple"])
    x = d[
        d["resolved_by_horizon"].astype(bool)
        & (d["capital_at_risk"] > 0)
        & d["return_multiple"].notna()
    ].copy()
    mstr = x["question"].str.contains(
        "MicroStrategy sells any Bitcoin by", na=False
    )
    print(
        "one-fill exact: n={:,} capital=${:,.2f} profit=${:,.2f} "
        "weighted_roi={:.4%} hit5={}/{} ({:.4%}) hit10={}/{} ({:.4%})".format(
            len(x),
            x["capital_at_risk"].sum(),
            x["net_profit"].sum(),
            x["net_profit"].sum() / x["capital_at_risk"].sum(),
            int((x["return_multiple"] >= 5).sum()),
            len(x),
            (x["return_multiple"] >= 5).mean(),
            int((x["return_multiple"] >= 10).sum()),
            len(x),
            (x["return_multiple"] >= 10).mean(),
        )
    )
    y = x[~mstr]
    print(
        "one-fill ex-MSTR cluster: n={:,} weighted_roi={:.4%} "
        "hit5={}/{} ({:.4%}) hit10={}/{} ({:.4%})".format(
            len(y),
            y["net_profit"].sum() / y["capital_at_risk"].sum(),
            int((y["return_multiple"] >= 5).sum()),
            len(y),
            (y["return_multiple"] >= 5).mean(),
            int((y["return_multiple"] >= 10).sum()),
            len(y),
            (y["return_multiple"] >= 10).mean(),
        )
    )


def causal_market_maker_metrics() -> None:
    causal = pd.read_csv(DATA / "dune_all_high_activity_causal_persistence.csv")
    causal["edge"] = causal["resolved_trade_pnl"] / causal[
        "resolved_collateral_turnover"
    ].replace(0, np.nan)
    h1 = causal[causal["period"] == "days_0_45"].set_index("wallet")
    h2 = causal[causal["period"] == "days_45_90"].set_index("wallet")
    h1["quintile"] = pd.qcut(
        h1["edge"].rank(method="first"),
        5,
        labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
    )
    selected = h1.index[h1["quintile"] == "Q5"]
    forward = h2.reindex(selected).dropna(subset=["resolved_trade_pnl"])
    print(
        "causal H1 top quintile: selected={} continued={} H2-positive={}/{} "
        "median_edge={:.4%} weighted_edge={:.4%}".format(
            len(selected),
            len(forward),
            int((forward["resolved_trade_pnl"] > 0).sum()),
            len(forward),
            forward["edge"].median(),
            forward["resolved_trade_pnl"].sum()
            / forward["resolved_collateral_turnover"].sum(),
        )
    )

    roles = pd.read_csv(DATA / "dune_all_high_activity_order_role.csv")
    roles = roles[
        (roles["period"] == "days_45_90") & roles["wallet"].isin(selected)
    ]
    summary = roles.groupby("order_role").agg(
        wallets=("wallet", "nunique"),
        fills=("fill_events_n", "sum"),
        turnover=("resolved_collateral_turnover", "sum"),
        profit=("resolved_trade_pnl", "sum"),
        crypto5m_profit=("crypto_5m_resolved_trade_pnl", "sum"),
        after_resolution=("after_resolution_fills_n", "sum"),
        within_60s=("within_60s_fills_n", "sum"),
        one_to_five_min=("one_to_five_min_fills_n", "sum"),
        over_five_min=("over_five_min_fills_n", "sum"),
    )
    summary["edge"] = summary["profit"] / summary["turnover"]
    summary["fill_share"] = summary["fills"] / summary["fills"].sum()
    print(summary.to_string())


if __name__ == "__main__":
    cohort_metrics()
    one_fill_metrics()
    causal_market_maker_metrics()
