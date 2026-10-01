#!/usr/bin/env python3
"""DQ-26 第一步：实体记账、排名、G1a（代币闭合）与 G2（进场时差）；G1b 由 g1b.py 另算。卡片_v1.md §3、§4。

python step1.py → runs/step1.json、runs/entity_rank.csv、runs/top50_entities.csv（冻结，记 sha256）

输入（都在 raw/dune/，均只含排名窗口 R 的数据）：
  RANK_D_R   实体钱包×币：曲线与 PumpSwap 成交现金、代币、首买首卖时刻、t3、期末池状态、事件实际费用与 cashback；
  BOOK_BX_R  dex_solana.trades：只取 pumpdotfun、pumpswap 以外的 project 作跨池成交；
  BOOK_BT_R  代币转移（成交腿／非成交转移，含对手地址）与成交交易里的 SOL 转出（小费等）；
  BOOK_BFEE_R 网络费与优先费；BOOK_BBAL_R 2026-08-16 日末余额；RANK_C_R 币级期末状态（补 D 中没有的币）。
口径（卡片 §3）：
  - 现金：交易者一侧；曲线成交的费用按事件里的实际字段（fee＋creator_fee＋buyback_fee）修正推算值，差额记为成本；
    cashback 单列，不计入（是否到账未核）。
  - 无法归因：实体外的非成交转入。按 A÷(A＋X) 拆分卖出所得与期末持仓价值；转出到实体外按 0。
  - 期末持仓：日末余额（余额表）按实体合计后，用该币期末池状态清算一次（不按钱包分别清算，避免同一池子被重复计价）。
  - 小费与附加转出：Jito 小费账户，加“被 ≥3 个实体钱包共用的顶层 System Program 收款方”（服务方）；
    只收自 1～2 个钱包的收款方视为疑似自有账户（如 WSOL 账户）单列，不计成本。网络费与小费按成交笔数分摊到币。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
RAW = H / "raw" / "dune"
RUNS = H / "runs"
JITO = set(
    json.loads((H / "raw" / "jito_tip_accounts_20261001.json").read_text())["result"]
)
N_TOP = 50


def liq(h, v_end, x, y, xr, fee_end, amm_fee):
    """h 枚代币按期末池状态卖出可得（与排名 SQL 的 liq 同式）。"""
    h = np.asarray(h, float)
    out = np.zeros_like(h)
    ok = (h > 0) & (y > 0)
    raw = np.where(ok, x * h / (y + np.where(ok, h, 1)), 0.0)
    curve = np.minimum(raw, np.nan_to_num(xr)) * (1 - np.nan_to_num(fee_end) / 1e4)
    amm = raw * (1 - np.where(np.isnan(amm_fee), 0.0125, amm_fee))
    out = np.where(ok, np.where(v_end == 0, curve, amm), 0.0)
    return out


def main() -> None:
    ent = pd.read_csv(RUNS / "entities_R.csv")
    e_of = dict(zip(ent.usr, ent.entity))
    d = pd.read_csv(RAW / "RANK_D_R.csv.gz")
    x = pd.read_csv(RAW / "BOOK_BX_R.csv.gz")
    bt = pd.read_csv(RAW / "BOOK_BT_R.csv.gz")
    fee = pd.read_csv(RAW / "BOOK_BFEE_R.csv.gz")
    bal = pd.read_csv(RAW / "BOOK_BBAL_R.csv.gz")
    c = pd.read_csv(RAW / "RANK_C_R.csv.gz")
    out: dict = {
        "n_entity_wallets": int(len(ent)),
        "n_entities": int(ent.entity.nunique()),
    }

    # 1 跨池（pump 曲线与 PumpSwap 以外）
    xo = x[~x.project.isin(["pumpdotfun", "pumpswap"])]
    xa = xo.groupby(["usr", "mint"])[
        ["tok_b", "tok_s", "sol_in", "sol_out", "usd_other_in", "usd_other_out", "n_tx"]
    ].sum()
    xa.columns = ["x_" + k for k in xa.columns]
    # 两个来源的成交代币量核对（pump 曲线＋PumpSwap：事件 vs dex_solana.trades）
    xp = (
        x[x.project.isin(["pumpdotfun", "pumpswap"])]
        .groupby(["usr", "mint"])[["tok_b", "tok_s"]]
        .sum()
    )
    chk = (
        d.set_index(["usr", "mint"])[["tok_b", "tok_s"]]
        .join(xp, rsuffix="_dex", how="outer")
        .fillna(0)
    )
    rel = (chk.tok_b - chk.tok_b_dex).abs() / chk.tok_b.clip(lower=1e-9)
    out["events_vs_dex_tok_b"] = {
        "cells": int(len(chk)),
        "share_within_1pct": round(float((rel <= 0.01).mean()), 4),
    }

    # 2 代币转移：成交腿与非成交转移
    tok = bt[bt.kind == "TOK"].copy()
    out["bt_actions"] = tok.groupby("action").n.sum().to_dict()
    tok["ent_o"] = tok.owner.map(e_of)
    tok["ent_c"] = tok.cp.map(e_of)
    tok["internal"] = (~tok.is_trade) & (tok.ent_o == tok.ent_c)
    leg = tok[tok.is_trade].groupby(["owner", "mint"])[["amt_in", "amt_out"]].sum()
    leg.columns = ["leg_in", "leg_out"]
    nt = tok[~tok.is_trade]
    nti = (
        nt.groupby(["owner", "mint", "internal"])[["amt_in", "amt_out"]]
        .sum()
        .unstack(fill_value=0)
    )
    nti.columns = [f"nt_{a}_{'int' if b else 'ext'}" for a, b in nti.columns]
    for k in ("nt_amt_in_int", "nt_amt_out_int", "nt_amt_in_ext", "nt_amt_out_ext"):
        if k not in nti:
            nti[k] = 0.0

    # 3 合并到（钱包, 币）
    w = d.set_index(["usr", "mint"])
    w = w.join(xa, how="outer").join(leg.rename_axis(["usr", "mint"]), how="outer")
    w = w.join(nti.rename_axis(["usr", "mint"]), how="outer")
    b = bal.set_index(["owner", "mint"]).bal.rename_axis(["usr", "mint"]).astype(float)
    w = w.join(b, how="outer")
    w = w[w.index.get_level_values(0).isin(e_of)]
    num = [k for k in w.columns if w[k].dtype != object and k not in ("bal",)]
    w[num] = w[num].fillna(0.0)
    w = w.reset_index()
    w["entity"] = w.usr.map(e_of)
    w["fee_extra"] = (w.fee_evt - w.fee_calc).clip(lower=0)
    w["n_trades"] = w.n_buy + w.n_sell + w.x_n_tx
    w["tok_trade"] = w.tok_b - w.tok_s + w.x_tok_b - w.x_tok_s
    w["nt_in"] = w.nt_amt_in_int + w.nt_amt_in_ext
    w["nt_out"] = w.nt_amt_out_int + w.nt_amt_out_ext
    # 10-01 实现更正（看过 v1 结果后）：成交交易里超出事件成交量的代币转移是“转入/转出”，v1 把它们算作成交腿漏掉了
    w["extra_in"] = (w.leg_in - w.tok_b - w.x_tok_b).clip(lower=0)
    w["extra_out"] = (w.leg_out - w.tok_s - w.x_tok_s).clip(lower=0)
    w["end_calc_v1"] = w.tok_trade + w.nt_in - w.nt_out
    w["end_calc"] = w.end_calc_v1 + w.extra_in - w.extra_out
    w["end_legs"] = w.leg_in - w.leg_out + w.nt_in - w.nt_out

    # 4 网络费与小费（按成交笔数分摊到币）
    sol = bt[bt.kind == "SOL"].copy()
    senders = sol.groupby("cp").owner.nunique()
    service = set(senders[senders >= 3].index) - set(e_of)
    pd.DataFrame({"cp": sorted(service)}).to_csv(
        RUNS / "service_recipients.csv", index=False
    )
    sol["cls"] = np.where(
        sol.cp.isin(JITO),
        "jito",
        np.where(sol.cp.isin(service), "service", "own_or_unknown"),
    )
    tips = sol.pivot_table(
        index="owner", columns="cls", values="amt_out", aggfunc="sum"
    ).fillna(0)
    for k in ("jito", "service", "own_or_unknown"):
        if k not in tips:
            tips[k] = 0.0
    per_w = (
        fee.set_index("usr")[["fee_sol", "n_trade_tx", "n_fee_found"]]
        .join(tips, how="outer")
        .fillna(0)
    )
    per_w["tip_cost"] = per_w.jito + per_w.service
    tot_n = w.groupby("usr").n_trades.transform("sum").replace(0, np.nan)
    share = (w.n_trades / tot_n).fillna(0)
    w["fee_alloc"] = share * w.usr.map(per_w.fee_sol).fillna(0)
    w["tip_alloc"] = share * w.usr.map(per_w.tip_cost).fillna(0)
    out["costs"] = {
        "network_fee_sol": round(float(per_w.fee_sol.sum()), 2),
        "jito_sol": round(float(per_w.jito.sum()), 2),
        "service_sol": round(float(per_w.service.sum()), 2),
        "own_or_unknown_sol_excluded": round(float(per_w.own_or_unknown.sum()), 2),
        "n_service_recipients": int(len(service)),
        "fee_rows_found_share": round(
            float(per_w.n_fee_found.sum() / per_w.n_trade_tx.sum()), 4
        ),
        "fee_extra_sol": round(float(w.fee_extra.sum()), 2),
        "cashback_sol_not_counted": round(float(w.cashback.sum()), 2),
    }

    # 5 实体×币：清算、归因、净额
    coin = c.set_index("mint")[
        ["v_end", "x_end", "y_end", "xr_end", "fee_end", "amm_fee_rate", "created_at"]
    ]
    g = (
        w.groupby(["entity", "mint"])
        .agg(
            cost=("in_sol", "sum"),
            x_cost=("x_sol_in", "sum"),
            proceeds=("out_sol", "sum"),
            x_proceeds=("x_sol_out", "sum"),
            A=("tok_b", "sum"),
            xA=("x_tok_b", "sum"),
            X_nt=("nt_amt_in_ext", "sum"),
            O_nt=("nt_amt_out_ext", "sum"),
            extra_in=("extra_in", "sum"),
            extra_out=("extra_out", "sum"),
            end_calc_v1=("end_calc_v1", "sum"),
            bal=("bal", "sum"),
            bal_n=("bal", "count"),
            end_calc=("end_calc", "sum"),
            end_legs=("end_legs", "sum"),
            fee_alloc=("fee_alloc", "sum"),
            tip_alloc=("tip_alloc", "sum"),
            fee_extra=("fee_extra", "sum"),
            in_t3coin=("in_t3coin", "sum"),
            in_pre_t35=("in_pre_t35", "sum"),
            n_trades=("n_trades", "sum"),
        )
        .reset_index()
    )
    g = g.join(coin, on="mint")
    g["created_day"] = g.created_at.astype(str).str[:10]
    g["hold"] = np.where(g.bal_n > 0, g.bal.clip(lower=0), g.end_calc.clip(lower=0))
    g["liq"] = liq(
        g.hold, g.v_end, g.x_end, g.y_end, g.xr_end, g.fee_end, g.amm_fee_rate
    )
    acq = g.A + g.xA
    # 成交交易内的转移对手未知：实体内先相抵，余额按实体外计（转入算无法归因，转出按 0 收回）
    g["X"] = g.X_nt + (g.extra_in - g.extra_out).clip(lower=0)
    g["O"] = g.O_nt + (g.extra_out - g.extra_in).clip(lower=0)
    g["s"] = np.where(acq + g.X > 0, acq / (acq + g.X).replace(0, np.nan), 1.0)
    g["s"] = g.s.fillna(1.0)
    g["gross"] = g.proceeds + g.x_proceeds + g.liq
    g["attr_in"] = g.s * g.gross
    g["unattr"] = (1 - g.s) * g.gross
    g["all_cost"] = g.cost + g.x_cost + g.fee_alloc + g.tip_alloc + g.fee_extra
    g["net_attr"] = g.attr_in - g.all_cost

    e = g.groupby("entity").agg(
        net_attr=("net_attr", "sum"),
        attr_in=("attr_in", "sum"),
        all_cost=("all_cost", "sum"),
        unattr=("unattr", "sum"),
        gross=("gross", "sum"),
        x_volume=("x_cost", "sum"),
        cost=("cost", "sum"),
        n_coins=("mint", "nunique"),
    )
    e["R_full"] = e.attr_in / e.all_cost.replace(0, np.nan)
    e["n_wallets"] = ent.groupby("entity").usr.size()
    e["n_candidates"] = ent.groupby("entity").is_candidate.sum()
    e = e.sort_values(["net_attr"], ascending=False)
    e["rank"] = np.arange(1, len(e) + 1)
    e.to_csv(RUNS / "entity_rank.csv")
    top = e.head(N_TOP)
    top_ids = list(top.index)
    pd.DataFrame({"entity": top_ids}).to_csv(RUNS / "top50_entities.csv", index=False)
    out["top50_sha256"] = hashlib.sha256(
        (RUNS / "top50_entities.csv").read_bytes()
    ).hexdigest()

    # 6 G1a：代币闭合（实体×币；按买入额加权）
    gt = g[g.entity.isin(top_ids)].copy()
    gt["inflow"] = acq[gt.index] + gt.X
    nz = (gt.end_calc.abs() > 1e-6) | (gt.bal.abs() > 1e-6)
    cov = float((gt.loc[nz, "bal_n"] > 0).mean()) if nz.any() else 1.0
    tol = 0.01 * gt.inflow.clip(lower=1e-9)
    bal_eff = np.where(gt.bal_n > 0, gt.bal, 0.0)
    gt["closed"] = (gt.end_calc - bal_eff).abs() <= tol
    gt["closed_legs"] = (gt.end_legs - bal_eff).abs() <= tol
    gt["closed_v1"] = (gt.end_calc_v1 - bal_eff).abs() <= tol
    gt["wt"] = gt.cost + gt.x_cost
    per_e = gt.groupby("entity").apply(
        lambda t: pd.Series(
            {
                "closed_w": (t.wt * t.closed).sum() / t.wt.sum()
                if t.wt.sum() > 0
                else np.nan,
                "closed_legs_w": (t.wt * t.closed_legs).sum() / t.wt.sum()
                if t.wt.sum() > 0
                else np.nan,
                "closed_n": t.closed.mean(),
                "closed_v1_w": (t.wt * t.closed_v1).sum() / t.wt.sum()
                if t.wt.sum() > 0
                else np.nan,
                "cells": len(t),
            }
        )
    )
    n_ok = int((per_e.closed_w >= 0.95).sum())
    out["G1a"] = {
        "balance_coverage_nonzero_cells": round(cov, 4),
        "entities_closed_ge95": n_ok,
        "pass": bool(n_ok >= 45 and cov >= 0.8),
        "closed_w_median": round(float(per_e.closed_w.median()), 4),
        "closed_w_p10": round(float(per_e.closed_w.quantile(0.1)), 4),
        "transfer_legs_only_entities_ge95": int((per_e.closed_legs_w >= 0.95).sum()),
        "v1_misclassified_entities_ge95": int((per_e.closed_v1_w >= 0.95).sum()),
    }
    per_e.to_csv(RUNS / "g1a_per_entity.csv")
    # 不闭合格的特征（描述）
    bad = gt[~gt.closed & (gt.wt > 0)]
    out["G1a_unclosed_cells"] = {
        "n": int(len(bad)),
        "buy_sol": round(float(bad.wt.sum()), 1),
        "calc_gt_bal_share": round(
            float((bad.end_calc > bal_eff[~gt.closed & (gt.wt > 0)]).mean()), 4
        )
        if len(bad)
        else None,
    }

    # 7 G2：进场时差（只算 t3 ≤300 秒的币，按买入额）
    t3buy = float(gt.in_t3coin.sum())
    after = 1 - float(gt.in_pre_t35.sum()) / t3buy if t3buy > 0 else float("nan")
    pe = gt.groupby("entity")[["in_t3coin", "in_pre_t35"]].sum()
    pe["after"] = 1 - pe.in_pre_t35 / pe.in_t3coin.replace(0, np.nan)
    out["G2"] = {
        "buy_sol_on_t3_coins": round(t3buy, 1),
        "share_buy_at_or_after_t3_plus5": round(after, 4),
        "pass": bool(after >= 0.20),
        "entity_after_median": round(float(pe.after.median()), 4),
        "entities_after_ge50pct": int((pe.after >= 0.5).sum()),
    }

    # 8 描述
    wt = w[w.entity.isin(top_ids)]
    hold = (wt.fs_dt - wt.fb_dt).where(
        (wt.n_buy > 0) & (wt.n_sell > 0) & (wt.fs_dt >= wt.fb_dt)
    )
    tot_net = float(top.net_attr.sum())
    by_coin = gt.groupby("mint").net_attr.sum().sort_values(ascending=False)
    by_day = gt.groupby("created_day").net_attr.sum().sort_values(ascending=False)
    out["describe"] = {
        "top50_net_attr_sol": round(tot_net, 1),
        "top50_R_full_median": round(float(top.R_full.median()), 4),
        "top50_wallets_per_entity": top.n_wallets.describe().round(1).to_dict(),
        "top50_entities_unattr_gt_half_gross": int(
            (top.unattr > 0.5 * top.gross).sum()
        ),
        "all_entities_unattr_share_of_gross": round(
            float(e.unattr.sum() / e.gross.sum()), 4
        ),
        "top50_extra_in_tokens_share_of_inflow": round(
            float(gt.extra_in.sum() / (acq[gt.index].sum() + gt.X.sum())), 4
        ),
        "top50_unattr_share_of_gross": round(
            float(top.unattr.sum() / top.gross.sum()), 4
        ),
        "top50_crosspool_share_of_cost": round(
            float(top.x_volume.sum() / (top.cost + top.x_volume).sum()), 4
        ),
        "holding_seconds_quantiles": hold.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        .round(0)
        .to_dict(),
        "top10_coins_share_of_net": round(float(by_coin.head(10).sum() / tot_net), 4),
        "top_day_share_of_net": round(float(by_day.head(1).sum() / tot_net), 4),
        "same_slot_cells_share": round(float((wt.same_slot == True).mean()), 4),  # noqa: E712
        "giant_entity_in_top50": bool(e.loc[top_ids, "n_wallets"].max() >= 1000),
    }
    (RUNS / "step1.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str)
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
