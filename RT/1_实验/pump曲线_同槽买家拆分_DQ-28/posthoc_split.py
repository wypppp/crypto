#!/usr/bin/env python3
"""DQ-28 看结果后的分拆（不改冻结读法）：把“创建即迁移”的币（格里有 PumpSwap 成交）与只在曲线上成交的格分开。

python posthoc_split.py → runs/posthoc_split.json
口径是看过 ss.py 结果后才定的：冻结主统计量被少数钱包在创建 slot 内对“创建即迁移”薄池的巨额买入主导（见结果 §2）。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
SEED, NBOOT = 20261002, 10_000


def ci(s: pd.DataFrame, by: str, rng) -> list[float]:
    g = s.groupby(by)[["recv_full", "pay_full"]].sum()
    n, d = g.recv_full.to_numpy(), g.pay_full.to_numpy()
    idx = rng.integers(0, len(g), size=(NBOOT, len(g)))
    r = n[idx].sum(1) / d[idx].sum(1)
    return [
        round(float(np.quantile(r, 0.025)), 4),
        round(float(np.quantile(r, 0.975)), 4),
    ]


def main() -> None:
    t = pd.read_csv(H / "runs" / "ss_cells.csv")
    coin_amm = t.groupby("mint").n_amm.max() > 0
    t["mig_coin"] = t.mint.map(coin_amm)
    rng = np.random.default_rng(SEED)
    out = {}
    for name, s in (
        ("I_curve_only_coins", t[(t.cls == "I") & ~t.mig_coin]),
        ("I_migrated_coins", t[(t.cls == "I") & t.mig_coin]),
        ("ALL_curve_only_coins", t[~t.mig_coin]),
    ):
        w = s.groupby("usr").net_full.sum().sort_values(ascending=False)
        out[name] = {
            "n_cells": int(len(s)),
            "n_wallets": int(s.usr.nunique()),
            "n_coins": int(s.mint.nunique()),
            "pay_sol": round(float(s.pay.sum()), 1),
            "fee_tip_sol": round(float((s.fee_sol + s.tip_sol).sum()), 1),
            "R_before_costs": round(float(s.recv_full.sum() / s.pay.sum()), 4),
            "R_full": round(float(s.recv_full.sum() / s.pay_full.sum()), 4),
            "R_full_ci95_by_wallet": ci(s, "usr", rng),
            "R_full_ci95_by_coin": ci(s, "mint", rng),
            "net_full_sol": round(float(s.net_full.sum()), 1),
            "top10_wallets_share_of_positive_net": round(
                float(w.head(10).sum() / w[w > 0].sum()), 4
            )
            if (w > 0).any()
            else None,
            "share_cells_R_gt1": round(float((s.recv_full > s.pay_full).mean()), 4),
        }
    out["coins_migrated_share"] = round(float(coin_amm.mean()), 4)
    (H / "runs" / "posthoc_split.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
