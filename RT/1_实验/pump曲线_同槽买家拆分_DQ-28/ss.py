#!/usr/bin/env python3
"""DQ-28 同槽买家拆分评分（卡片_v1.md §2～§3；与卡片一起冻结，读数之前）。

python ss.py → runs/ss.json、runs/ss_cells.csv
输入 raw/dune/SS_{CELLS,FEES,XFER,LINK}.csv.gz。
类别按顺序判定：B 同交易 → L 创建前 7 天与创建者有原生 SOL 直接往来 → X 筹码转移（转账口径的转出或转入
超过成交量 0.1%＋1 枚，或卖出量超过买入量 0.1%） → I 独立。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RAW = H / "raw" / "dune"
SEED, NBOOT = 20261002, 10_000


def load() -> pd.DataFrame:
    a = pd.read_csv(RAW / "SS_CELLS.csv.gz")
    b = pd.read_csv(RAW / "SS_FEES.csv.gz")
    x = pd.read_csv(RAW / "SS_XFER.csv.gz")
    lk = pd.read_csv(RAW / "SS_LINK.csv.gz")
    assert not a.duplicated(["mint", "usr"]).any()
    t = (
        a.merge(b, on=["mint", "usr"], how="left", validate="1:1")
        .merge(x, on=["mint", "usr"], how="left", validate="1:1")
        .merge(lk, on=["mint", "usr"], how="left", validate="1:1")
    )
    for c in ("fee_sol", "tip_sol", "tok_out", "tok_in", "n_link", "liq_sol"):
        t[c] = t[c].fillna(0.0)
    return t


def classify(t: pd.DataFrame) -> pd.Series:
    xo = t.tok_out > t.tok_s * 1.001 + 1
    xi = t.tok_in > t.tok_b * 1.001 + 1
    xs = t.tok_s > t.tok_b * 1.001
    return pd.Series(
        np.select(
            [t.same_tx.astype(bool), t.n_link > 0, xo | xi | xs],
            ["B", "L", "X"],
            default="I",
        ),
        index=t.index,
    )


def boot(t: pd.DataFrame, by: str, num: str, den: str, rng) -> list[float]:
    g = t.groupby(by)[[num, den]].sum()
    n, d = g[num].to_numpy(), g[den].to_numpy()
    idx = rng.integers(0, len(g), size=(NBOOT, len(g)))
    r = n[idx].sum(1) / d[idx].sum(1)
    return [
        round(float(np.quantile(r, 0.025)), 4),
        round(float(np.quantile(r, 0.975)), 4),
    ]


def main() -> None:
    t = load()
    t["cls"] = classify(t)
    t["pay_full"] = t.pay + t.fee_sol + t.tip_sol
    t["recv_full"] = t.recv + t.liq_sol
    t["net_full"] = t.recv_full - t.pay_full
    rng = np.random.default_rng(SEED)
    out: dict = {"n_cells": int(len(t)), "classes": {}}
    for c in ("B", "L", "X", "I", "ALL"):
        s = t if c == "ALL" else t[t.cls == c]
        if s.empty:
            out["classes"][c] = {"n_cells": 0}
            continue
        d = {
            "n_cells": int(len(s)),
            "n_wallets": int(s.usr.nunique()),
            "n_coins": int(s.mint.nunique()),
            "pay_sol": round(float(s.pay.sum()), 2),
            "fee_sol": round(float(s.fee_sol.sum()), 2),
            "tip_sol": round(float(s.tip_sol.sum()), 2),
            "recv_sol": round(float(s.recv.sum()), 2),
            "liq_sol": round(float(s.liq_sol.sum()), 2),
            "R_before_costs": round(float(s.recv_full.sum() / s.pay.sum()), 4),
            "R_full": round(float(s.recv_full.sum() / s.pay_full.sum()), 4),
            "net_full_sol": round(float(s.net_full.sum()), 2),
        }
        if c != "ALL":
            d["R_full_ci95_by_wallet"] = boot(s, "usr", "recv_full", "pay_full", rng)
            d["R_full_ci95_by_coin"] = boot(s, "mint", "recv_full", "pay_full", rng)
            w = s.groupby("usr").net_full.sum().sort_values(ascending=False)
            d["top10_wallets_net_sol"] = round(float(w.head(10).sum()), 2)
            d["share_cells_R_gt1"] = round(float((s.recv_full > s.pay_full).mean()), 4)
        out["classes"][c] = d
    ci = out["classes"]["I"].get("R_full_ci95_by_wallet")
    if ci is None:
        reading = "无独立格"
    elif ci[1] < 1:
        reading = "读法 1（停）：独立同槽买家全成本回收上界 <1"
    elif ci[0] > 1:
        reading = (
            "读法 2（只说明要再测）：独立同槽买家下界 >1，须按狙击钱包全部尝试记账"
        )
    else:
        reading = "读法 3（不定）"
    out["reading"] = reading
    out["coverage"] = {
        "fee_rows_found_share": round(
            float(t.n_fee_found.fillna(0).sum() / t.n_tx.fillna(0).sum()), 4
        )
        if t.n_tx.fillna(0).sum()
        else None,
        "cells_with_amm_trades": int((t.n_amm > 0).sum()),
    }
    t.to_csv(H / "runs" / "ss_cells.csv", index=False)
    (H / "runs" / "ss.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
