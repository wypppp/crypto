#!/usr/bin/env python3
"""WM 谁在赚钱＋阳性对照：卡片_WM_谁在赚钱与阳性对照.md §4 的全部统计量与写死的读法。与卡片一起在看结果前冻结。

输入：raw/dune/WM_{A,B}.csv.gz（build_wm_sql.py 生成的 SQL 结果）；S1 主样本与冻结入样标记（analyze_s1_dual.load）。
权重 w＝1/p0（病例超集 p0＝1，其余 0.02）。方差按泊松抽样：Var(Σ w·z) = Σ (1−p0)/p0² · z²，
比率用线性化 z = (a − R·b)/Σ w·b。

python analyze_wm.py → raw/wm/WM_analysis.json
python analyze_wm.py --smoke → 只做冒烟日核对（raw/dune/WM_SMOKE_20260601.csv.gz）
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import analyze_s1_dual as m
from analyze_s0_v1_2 import f

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "wm"
DUNE = HERE / "raw" / "dune"
Z = 1.96
GROUPS = [
    "creator",
    "sellonly",
    "sameslot",
    "open10",
    "pre",
    "e5",
    "e30",
    "e120",
    "d1",
    "late",
]
COIN_COLS = [
    "n_ev",
    "n_amm",
    "n_rev",
    "fee_proto",
    "fee_creator",
    "fee_lp",
    "curve_in",
    "curve_out",
    "xr_end",
    "p_end",
    "last_venue",
]
DECOMP = {"e5": 5, "e30": 30, "e120": 120}
FIXED = ("30s", "2m", "10m", "1h")


def main_sample(s1: dict[str, dict], week: str | None = None) -> pd.DataFrame:
    rows = []
    for mint, r in s1.items():
        if str(r["eligible"]) != "True" or str(r["r0_seen"]) == "True":
            continue
        if week and r["cohort_week"] != week:
            continue
        p0 = 1.0 if r["_frozen_case"] else 0.02
        rec = {
            "mint": mint,
            "week": r["cohort_week"],
            "p0": p0,
            "created": str(r["created_at"])[:10],
        }
        for d in (5, 30, 120):
            rec[f"b50_A_d{d}"] = f(r, f"b50_ret_d{d}")
            rec[f"b50_B_d{d}"] = f(r, f"b50_ret_d{d}_b")
            vals = [rec[f"b50_A_d{d}"]] + [f(r, f"ret_d{d}_{h}") for h in FIXED]
            vals = [v for v in vals if v is not None]
            rec[f"best_A_d{d}"] = max(vals) if vals else None
        x, y = f(r, "e5_x"), f(r, "e5_y")
        rec["p_e5"] = x / y if x and y else None
        rows.append(rec)
    return pd.DataFrame(rows)


def load(labels: list[str], smp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = pd.concat([pd.read_csv(DUNE / f"WM_{lb}.csv.gz") for lb in labels])
    coin = g.groupby("mint")[COIN_COLS].first().reset_index()
    got, want = set(coin.mint), set(smp.mint)
    if got != want:
        raise RuntimeError(f"mint 集合不同：缺 {len(want - got)}，多 {len(got - want)}")
    coin = coin.merge(smp, on="mint")
    g = g.merge(coin[["mint", "p0", "week"]], on="mint")
    g["held_sol"] = g.held_tok * g.p_end.fillna(0.0)
    return g, coin


def var_ht(z: np.ndarray, p0: np.ndarray) -> float:
    return float(((1 - p0) / p0**2 * z**2).sum())


def ratio(a: np.ndarray, b: np.ndarray, p0: np.ndarray) -> dict:
    w = 1 / p0
    B = (w * b).sum()
    if B <= 0:
        return {"R": None, "se": None, "lo95": None, "hi95": None}
    R = (w * a).sum() / B
    se = math.sqrt(var_ht((a - R * b) / B, p0))
    return {"R": R, "se": se, "lo95": R - Z * se, "hi95": R + Z * se}


def per_coin(g: pd.DataFrame, coin: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    sub = g[g.grp.isin(groups)]
    agg = (
        sub.groupby("mint")[["in_sol", "out_sol", "held_sol", "tok_b"]]
        .sum()
        .reset_index()
    )
    return coin[["mint", "p0"]].merge(agg, on="mint", how="left").fillna(0.0)


def group_table(g: pd.DataFrame, coin: pd.DataFrame) -> dict:
    out = {}
    p0 = coin.p0.values
    for grp in GROUPS + ["sameslot+open10"]:
        members = ["sameslot", "open10"] if grp == "sameslot+open10" else [grp]
        c = per_coin(g, coin, members)
        a_in, a_out, a_held = c.in_sol.values, c.out_sol.values, c.held_sol.values
        net = a_out + a_held - a_in
        nw = g[g.grp.isin(members)].merge(coin[["mint"]], on="mint")
        out[grp] = {
            "n_wallets_w": float((1 / nw.p0 * nw.n_w).sum()),
            "n_oversold_w": float((1 / nw.p0 * nw.n_oversold).sum()),
            "IN": float((a_in / p0).sum()),
            "OUT": float((a_out / p0).sum()),
            "HELD": float((a_held / p0).sum()),
            "NET": float((net / p0).sum()),
            "NET_se": math.sqrt(var_ht(net, p0)),
            "RR": ratio(a_out, a_in, p0),
            "MR": ratio(a_out + a_held, a_in, p0),
        }
    fees = {
        k: float((coin[k].fillna(0) / coin.p0).sum())
        for k in ("fee_proto", "fee_creator", "fee_lp")
    }
    nets = {k: v["NET"] for k, v in out.items() if k in GROUPS}
    pos = sum(v for v in nets.values() if v > 0)
    neg = sum(v for v in nets.values() if v < 0)
    for k in GROUPS:
        v = nets[k]
        out[k]["share_of_pos_net"] = v / pos if v > 0 and pos else 0.0
        out[k]["share_of_neg_net"] = v / neg if v < 0 and neg else 0.0
    buyer_loss = -sum(v for k, v in nets.items() if k != "sellonly" and v < 0)
    return {
        "groups": out,
        "fees": fees,
        "sum_pos_net": pos,
        "sum_neg_net": neg,
        "sellonly_net_over_buyer_loss": nets["sellonly"] / buyer_loss
        if buyer_loss
        else None,
        "creator_sellonly_share_of_pos_net": (
            max(nets["creator"], 0) + max(nets["sellonly"], 0)
        )
        / pos
        if pos
        else None,
    }


def closure(coin: pd.DataFrame) -> dict:
    c = coin[(coin.n_amm == 0) & coin.xr_end.notna()].copy()
    vol = c.curve_in + c.curve_out
    c["rel"] = (c.curve_in - c.curve_out - c.xr_end).abs() / vol.replace(0, np.nan)
    bad = float((c.rel > 0.01).mean())
    return {
        "n_coins": int(len(c)),
        "median_rel_err": float(c.rel.median()),
        "p99_rel_err": float(c.rel.quantile(0.99)),
        "share_rel_gt_1pct": bad,
        "qa_pass": bool(bad <= 0.05),
    }


def decomp(g: pd.DataFrame, coin: pd.DataFrame) -> dict:
    out = {}
    for grp, d in DECOMP.items():
        c = per_coin(g, coin, [grp]).merge(
            coin[["mint", f"b50_A_d{d}", f"b50_B_d{d}", f"best_A_d{d}"]], on="mint"
        )
        c = c[c.in_sol > 0]
        res = {"n_coins_with_group": int(len(c))}
        for key in (f"b50_A_d{d}", f"b50_B_d{d}", f"best_A_d{d}"):
            cc = c[c[key].notna()]
            p0 = cc.p0.values
            a = (cc.out_sol + cc.held_sol).values
            b = cc.in_sol.values
            s = cc[key].values.astype(float) * b
            mr = ratio(a, b, p0)
            pr = ratio(s, b, p0)
            dd = ratio(a - s, b, p0)
            res[key] = {
                "n_coins": int(len(cc)),
                "MR_actual": mr,
                "pipeline": pr,
                "D": dd,
            }
        out[grp] = res
    return out


def readings(tab: dict, dec: dict) -> dict:
    G = tab["groups"]
    r1 = [
        k
        for k in DECOMP
        if (G[k]["MR"]["lo95"] or 0) > 1
        and (dec[k][f"b50_A_d{DECOMP[k]}"]["D"]["lo95"] or 0) > 0
    ]
    r2 = all(G[k]["MR"]["hi95"] is not None and G[k]["MR"]["hi95"] < 1 for k in DECOMP)
    r3 = [k for k in ("sameslot", "open10", "pre") if (G[k]["MR"]["lo95"] or 0) > 1]
    r4 = (tab["creator_sellonly_share_of_pos_net"] or 0) > 0.5
    return {
        "1_真实卖出胜过固定退出": r1,
        "2_决策时点三组上界都小于1": r2,
        "3_速度组下界大于1": r3,
        "4_正净额过半在creator与sellonly": r4,
    }


def diagnostics(g: pd.DataFrame, coin: pd.DataFrame) -> dict:
    out = {"entry_price_ratio_vs_e5": {}, "top10_cell_share_of_group_net": {}}
    for grp in GROUPS:
        if grp == "sellonly":
            continue
        c = per_coin(g, coin, [grp]).merge(coin[["mint", "p_e5"]], on="mint")
        c = c[(c.in_sol > 0) & (c.tok_b > 0) & c.p_e5.notna()]
        ratio_c = c.p_e5 / (c.in_sol / c.tok_b)
        w = c.in_sol / c.p0
        out["entry_price_ratio_vs_e5"][grp] = {
            "money_weighted_mean": float((w * ratio_c).sum() / w.sum())
            if len(c)
            else None,
            "median_coin": float(ratio_c.median()) if len(c) else None,
        }
    for grp in GROUPS:
        sub = g[g.grp == grp]
        net = float(((sub.out_sol + sub.held_sol - sub.in_sol) / sub.p0).sum())
        top = (sub.max_net_w / sub.p0).nlargest(10).sum()
        out["top10_cell_share_of_group_net"][grp] = (
            float(top / net) if net > 0 else None
        )
    out["by_migrated"] = {}
    for flag, cc in coin.groupby(coin.n_amm > 0):
        gg = g[g.mint.isin(cc.mint)]
        t = group_table(gg, cc)
        out["by_migrated"][str(bool(flag))] = {
            k: {"IN": v["IN"], "NET": v["NET"], "MR": v["MR"]["R"]}
            for k, v in t["groups"].items()
        }
    out["p_end_missing_coins"] = int(coin.p_end.isna().sum())
    out["reversed_pool_events"] = int(coin.n_rev.sum())
    return out


def smoke() -> None:
    _, s1 = m.load()
    smp = main_sample(s1, "A")
    smp = smp[smp.created == "2026-06-01"]
    g, coin = load(["SMOKE_20260601"], smp)
    res = {
        "n_coins": int(len(coin)),
        "groups_present": sorted(g.grp.unique().tolist()),
        "rows": int(len(g)),
        "coins_without_events": int((coin.n_ev <= 0).sum()),
        "closure": closure(coin),
        "amm_coins": int((coin.n_amm > 0).sum()),
        "reversed_pool_events": int(coin.n_rev.sum()),
        "p_end_missing": int(coin.p_end.isna().sum()),
        "negative_amounts": int(
            ((g.in_sol < 0) | (g.out_sol < 0) | (g.tok_b < 0) | (g.tok_s < 0)).sum()
        ),
    }
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "WM_SMOKE_check.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    )
    print(json.dumps(res, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    if ap.parse_args().smoke:
        smoke()
        return
    _, s1 = m.load()
    smp = main_sample(s1)
    g, coin = load(["A", "B"], smp)
    out: dict = {"card": "卡片_WM_谁在赚钱与阳性对照.md", "n_coins": int(len(coin))}
    out["C1_closure"] = closure(coin)
    out["pooled"] = group_table(g, coin)
    out["by_week"] = {
        w: group_table(g[g.week == w], coin[coin.week == w]) for w in ("A", "B")
    }
    out["decomposition"] = decomp(g, coin)
    out["decomposition_by_week"] = {
        w: decomp(g[g.week == w], coin[coin.week == w]) for w in ("A", "B")
    }
    out["readings"] = readings(out["pooled"], out["decomposition"])
    out["diagnostics"] = diagnostics(g, coin)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "WM_analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=float) + "\n"
    )
    print(
        json.dumps(
            {k: out[k] for k in ("n_coins", "C1_closure", "readings")},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
