#!/usr/bin/env python3
"""DQ-31（F131）评分 v2：代码审计 10-03 第 6、8 处（与 SN2_* 查询的第 1、3 处一起）。原 sn.py 不改。

python sn_v2.py → runs/sn_v2.json、runs/sn_v2_wallets.csv
与 v1 的不同只有费用与小费的归属：
- 第 6 处：被剔除的筹码转移格（X）连同它们的成交交易费用与小费一起去掉（v1 只删现金、按钱包合计的费用留着）；
- 第 8 处：“成交交易”包含只含 PumpSwap 的交易（SN2_FEES、SN2_TIP 已按曲线＋PumpSwap 构造）。
R_lo＝收回 ÷（付出＋全部交易费用与小费 − X 格的成交费用与小费）；R_hi＝收回 ÷（付出＋非 X 格的成交费用与小费）。
X 格的判定与 v1 相同（v1 SN_XFER 的 TOK 部分）；自助法、种子、读法与 v1 相同。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import sn as S1  # noqa: E402


def score(
    s: pd.DataFrame,
    tr: pd.DataFrame,
    fe: pd.DataFrame,
    tp: pd.DataFrame,
    xf: pd.DataFrame,
) -> tuple[dict, pd.DataFrame]:
    """s：名单（usr）；tr：SN2_TRADES；fe：SN2_FEES（usr, mint, fee）；tp：SN2_TIP（usr, mint, tip）；xf：SN_XFER（v1）。"""
    assert not tr.duplicated(["mint", "usr"]).any()
    tok = xf[xf.kind == "TOK"].rename(columns={"a1": "tok_out", "a2": "tok_in"})
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
    cell_cost = (
        fe[fe.mint.notna()].groupby(["usr", "mint"]).fee.sum().rename("fee_cell").to_frame()
        .join(tp[tp.mint.notna()].groupby(["usr", "mint"]).tip.sum().rename("tip_cell"), how="outer")
        .fillna(0.0).reset_index()
    )  # fmt: skip
    cell_cost = cell_cost.merge(
        tr[["usr", "mint", "xfer"]], on=["usr", "mint"], how="left"
    )
    cell_cost["xfer"] = cell_cost.xfer.fillna(False).astype(bool)
    cell_cost["c"] = cell_cost.fee_cell + cell_cost.tip_cell
    x_cost = cell_cost[cell_cost.xfer].groupby("usr").c.sum()
    keep_cost = cell_cost[~cell_cost.xfer].groupby("usr").c.sum()
    all_cost = (
        fe.groupby("usr").fee.sum().add(tp.groupby("usr").tip.sum(), fill_value=0.0)
    )
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
    for k in ("pay", "recv_full", "n_coins"):
        w[k] = w[k].fillna(0.0)
    w["cost_all"] = w.usr.map(all_cost).fillna(0.0)
    w["cost_x"] = w.usr.map(x_cost).fillna(0.0)
    w["cost_trade_keep"] = w.usr.map(keep_cost).fillna(0.0)
    w["cost_lo"] = w.pay + w.cost_all - w.cost_x
    w["cost_hi"] = w.pay + w.cost_trade_keep
    w["net_lo"] = w.recv_full - w.cost_lo
    act = w[w.cost_lo > 0]
    rng = np.random.default_rng(S1.SEED)
    r_lo_ci = S1.boot(act, "recv_full", "cost_lo", rng)
    r_hi_ci = S1.boot(act, "recv_full", "cost_hi", rng)
    if r_lo_ci[0] > 1:
        reading = "读法 1：存活的独立狙击钱包扣全部尝试成本后仍赚钱（R_lo 下界 >1）"
    elif r_hi_ci[1] < 1:
        reading = "读法 2（停）：即使只算成交交易的费用也不赚钱（R_hi 上界 <1）"
    else:
        reading = "读法 3（不定）"
    nets = act.sort_values("net_lo", ascending=False)
    out = {
        "n_wallets_list": int(len(s)),
        "n_wallets_active": int(len(act)),
        "n_cells": int(len(tr)),
        "n_cells_xfer_excluded": int(x.sum()),
        "pay_sol": round(float(act.pay.sum()), 1),
        "recv_full_sol": round(float(act.recv_full.sum()), 1),
        "cost_all_fee_tip_sol": round(float(act.cost_all.sum()), 1),
        "cost_x_cells_removed_sol": round(float(act.cost_x.sum()), 1),
        "cost_trade_keep_sol": round(float(act.cost_trade_keep.sum()), 1),
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
    }
    return out, w


def main() -> None:
    raw = HERE / "raw" / "dune"
    s = pd.read_csv(HERE.parent / "runs" / "snipers_S.csv")
    out, w = score(
        s,
        pd.read_csv(raw / "SN2_TRADES.csv.gz"),
        pd.read_csv(raw / "SN2_FEES.csv.gz"),
        pd.read_csv(raw / "SN2_TIP.csv.gz"),
        pd.read_csv(HERE.parent / "raw" / "dune" / "SN_XFER.csv.gz"),
    )
    (HERE / "runs").mkdir(exist_ok=True)
    w.to_csv(HERE / "runs" / "sn_v2_wallets.csv", index=False)
    (HERE / "runs" / "sn_v2.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
