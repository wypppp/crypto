#!/usr/bin/env python3
"""DQ-31 狙击钱包全成本评分（卡片_v1.md §2～§3；与卡片一起冻结，读数之前）。

python sn.py → runs/sn.json、runs/sn_wallets.csv
输入 raw/dune/SN_{TRADES,FEES,XFER}.csv.gz。
筹码转移的格（转入或转出超过成交量 0.1%＋1 枚，或卖出量超过买入量 0.1%）整格剔除并计数。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RAW = H / "raw" / "dune"
SEED, NBOOT = 20261003, 10_000


def boot(w: pd.DataFrame, num: str, den: str, rng) -> list[float]:
    n, d = w[num].to_numpy(), w[den].to_numpy()
    idx = rng.integers(0, len(w), size=(NBOOT, len(w)))
    r = n[idx].sum(1) / d[idx].sum(1)
    return [
        round(float(np.quantile(r, 0.025)), 4),
        round(float(np.quantile(r, 0.975)), 4),
    ]


def main() -> None:
    s = pd.read_csv(H / "runs" / "snipers_S.csv")
    tr = pd.read_csv(RAW / "SN_TRADES.csv.gz")
    fe = pd.read_csv(RAW / "SN_FEES.csv.gz")
    xf = pd.read_csv(RAW / "SN_XFER.csv.gz")
    assert not tr.duplicated(["mint", "usr"]).any()
    tok = xf[xf.kind == "TOK"].rename(columns={"a1": "tok_out", "a2": "tok_in"})
    tip = xf[xf.kind == "TIP"].rename(columns={"a1": "tip_all", "a2": "tip_trade"})
    tr = tr.merge(
        tok[["mint", "usr", "tok_out", "tok_in"]], on=["mint", "usr"], how="left"
    )
    tr[["tok_out", "tok_in"]] = tr[["tok_out", "tok_in"]].fillna(0.0)
    x = (
        (tr.tok_out > tr.tok_s * 1.001 + 1)
        | (tr.tok_in > tr.tok_b * 1.001 + 1)
        | (tr.tok_s > tr.tok_b * 1.001)
    )
    tr["xfer"] = x
    c = tr[~x].copy()
    c["recv_full"] = c.recv + c.liq_sol.fillna(0.0)
    w = (
        c.groupby("usr")
        .agg(
            pay=("pay", "sum"), recv_full=("recv_full", "sum"), n_coins=("mint", "size")
        )
        .reset_index()
    )
    w = s[["usr"]].merge(w, on="usr", how="left")
    w = w.merge(fe, on="usr", how="left").merge(
        tip[["usr", "tip_all", "tip_trade"]], on="usr", how="left"
    )
    for k in (
        "pay",
        "recv_full",
        "n_coins",
        "fee_all",
        "fee_trade",
        "tip_all",
        "tip_trade",
        "n_tx_all",
        "n_tx_trade",
    ):
        w[k] = w[k].fillna(0.0)
    w["cost_lo"] = w.pay + w.fee_all + w.tip_all
    w["cost_hi"] = w.pay + w.fee_trade + w.tip_trade
    w["net_lo"] = w.recv_full - w.cost_lo
    act = w[w.cost_lo > 0]
    rng = np.random.default_rng(SEED)
    r_lo_ci = boot(act, "recv_full", "cost_lo", rng)
    r_hi_ci = boot(act, "recv_full", "cost_hi", rng)
    if r_lo_ci[0] > 1:
        reading = "读法 1：存活的独立狙击钱包扣全部尝试成本后仍赚钱（R_lo 下界 >1）"
    elif r_hi_ci[1] < 1:
        reading = "读法 2（停）：即使只算成交交易的费用也不赚钱（R_hi 上界 <1）"
    else:
        reading = "读法 3（不定）"
    tr["gap_grp"] = pd.cut(
        tr.first_buy_slot_gap, [-1, 0, 2, 10, 1e12], labels=["0", "1-2", "3-10", ">10"]
    )
    cg = tr[~tr.xfer].assign(rf=lambda d: d.recv + d.liq_sol.fillna(0.0))
    grp = cg.groupby("gap_grp", observed=True).agg(
        n=("mint", "size"), pay=("pay", "sum"), rf=("rf", "sum")
    )
    grp["R_before_costs"] = (grp.rf / grp.pay).round(4)
    nets = act.sort_values("net_lo", ascending=False)
    out = {
        "n_wallets_list": int(len(s)),
        "n_wallets_active": int(len(act)),
        "n_wallets_traded_window_coins": int((w.n_coins > 0).sum()),
        "n_cells": int(len(tr)),
        "n_cells_xfer_excluded": int(x.sum()),
        "pay_sol": round(float(act.pay.sum()), 1),
        "recv_full_sol": round(float(act.recv_full.sum()), 1),
        "fee_all_sol": round(float(act.fee_all.sum()), 1),
        "fee_trade_sol": round(float(act.fee_trade.sum()), 1),
        "tip_all_sol": round(float(act.tip_all.sum()), 1),
        "tip_trade_sol": round(float(act.tip_trade.sum()), 1),
        "share_tx_trade": round(float(act.n_tx_trade.sum() / act.n_tx_all.sum()), 4)
        if act.n_tx_all.sum()
        else None,
        "R_lo": round(float(act.recv_full.sum() / act.cost_lo.sum()), 4),
        "R_lo_ci95_by_wallet": r_lo_ci,
        "R_hi": round(float(act.recv_full.sum() / act.cost_hi.sum()), 4),
        "R_hi_ci95_by_wallet": r_hi_ci,
        "reading": reading,
        "wallets_net_lo_positive": int((act.net_lo > 0).sum()),
        "top10_wallets_share_of_positive_net_lo": round(
            float(nets.net_lo.head(10).sum() / nets.net_lo[nets.net_lo > 0].sum()), 4
        )
        if (nets.net_lo > 0).any()
        else None,
        "by_first_buy_slot_gap": grp.reset_index()
        .astype({"gap_grp": str})
        .to_dict("records"),
    }
    w.to_csv(H / "runs" / "sn_wallets.csv", index=False)
    (H / "runs" / "sn.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
