#!/usr/bin/env python3
"""R1a v3 §4–§5：选中集合的经济回收与写死的判据。在取数前与卡片一起冻结。

- 样本：r1a_sample.csv 中已完成取数的 mint_hash 前缀（build_r1a.py 的 complete）；按前缀重算 a、c 与入样概率，权重 = 1/入样概率。
- 分数：Full/fund/light × 服务集合 main/strict × 入场 d5/d30 的强度 S；Zero（同 slot 占比，平手按创建者自买额降序、mint_hash 升序）。
- 方向：high = 分数高者入选（主），low = 分数低者入选（诊断）。缺失分数不能入选，但留在总体权重里。
- 选中集合：排序后累加权重，到总权重的 q（含越过 q 的那一行）。
- 统计量：Hájek 比率均值；影响函数线性化标准误；与全体、与同 q 的 Zero 的配对差。
- 主格：full × main × d30 × high × q=0.10 × 口径 A（b50_ret_d30），A、B 两周合并。

python analyze_r1a.py → raw/r1a/R1A_analysis.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import analyze_s1_dual as m
from analyze_s0_v1_2 import f

HERE = Path(__file__).resolve().parent
OUT = HERE / "raw" / "r1a" / "R1A_analysis.json"
SCORES = HERE / "raw" / "r1a" / "r1a_scores.csv"
N_W, N_SUB = 1591, 2808  # 抽样框：主样本中的 W 数与 2% 子队列数（build_r1a_sample.py）
QS = (0.05, 0.10, 0.20)
Z = 1.96
PRIMARY = {
    "score": "S_full_main_d30",
    "dir": "high",
    "q": 0.10,
    "basis": "A",
    "rule": "b50_ret_d30",
}
RULE = {5: "b50_ret_d5", 30: "b50_ret_d30"}


def frame() -> pd.DataFrame:
    smp = pd.read_csv(HERE / "r1a_sample.csv")
    sc = pd.read_csv(SCORES)
    d = smp.merge(sc, on=["mint", "order"], how="left")
    d["complete"] = d.complete.fillna(False).astype(bool)
    bad = d.loc[~d.complete, "order"]
    stop = int(bad.min()) if len(bad) else len(d)
    d = d[d.order < stop].copy()
    a = d.in_case_draw.sum() / N_W
    c = d.in_cohort_draw.sum() / N_SUB
    pa = np.where(d.is_w == 1, a, 0.0)
    pc = np.where(d.is_sub == 1, c, 0.0)
    d["incl"] = d.p0 * (1 - (1 - pa) * (1 - pc))
    d["w"] = 1 / d.incl
    _, s1 = m.load()
    for rule in RULE.values():
        for basis, col in (("A", rule), ("B", rule + "_b")):
            d[f"y_{rule}_{basis}"] = [f(s1[x], col) for x in d.mint]
    d.attrs.update(
        {"prefix_coins": int(len(d)), "a": float(a), "c": float(c), "stop_order": stop}
    )
    return d


def ratio(d: pd.DataFrame, sel: np.ndarray, y: str) -> tuple[float, np.ndarray, float]:
    """选中集合的 Hájek 比率均值与每币影响函数。"""
    w = d.w.values * sel
    yy = d[y].values
    ok = ~np.isnan(yy)
    w = np.where(ok, w, 0.0)
    W = w.sum()
    R = float((w * np.nan_to_num(yy)).sum() / W)
    inf = w * (np.nan_to_num(yy) - R) / W
    return R, inf, W


def se(inf: np.ndarray) -> float:
    return float(math.sqrt((inf**2).sum()))


def select(d: pd.DataFrame, score: str, direction: str, q: float) -> np.ndarray:
    if score.startswith("zero"):
        dly = score.split("_d")[1]
        key = pd.DataFrame(
            {
                "k1": -d[f"zero_d{dly}"] if direction == "high" else d[f"zero_d{dly}"],
                "k2": -d[f"dev_buy_sol_d{dly}"]
                if direction == "high"
                else d[f"dev_buy_sol_d{dly}"],
                "k3": d.mint_hash_exact.astype(float),
            }
        )
        ok = d[f"zero_d{dly}"].notna().values
    else:
        s = d[score]
        key = pd.DataFrame(
            {
                "k1": -s if direction == "high" else s,
                "k2": 0.0,
                "k3": d.mint_hash_exact.astype(float),
            }
        )
        ok = s.notna().values
    order = key[ok].sort_values(["k1", "k2", "k3"]).index
    total = d.w.sum()
    sel = np.zeros(len(d), bool)
    pos = {ix: i for i, ix in enumerate(d.index)}
    acc = 0.0
    for ix in order:
        if acc >= q * total:
            break
        acc += d.w.loc[ix]
        sel[pos[ix]] = True
    return sel


def cell(
    d: pd.DataFrame, score: str, direction: str, q: float, basis: str, rule: str
) -> dict:
    y = f"y_{rule}_{basis}"
    sel = select(d, score, direction, q)
    Rs, Is, Ws = ratio(d, sel, y)
    Ra, Ia, Wa = ratio(d, np.ones(len(d), bool), y)
    win = (d[y] >= 2).values.astype(float)
    ps = float((d.w.values * sel * win).sum() / Ws)
    pa = float((d.w.values * win).sum() / Wa)
    rest = sel & (win == 0)
    mu_o = (
        float((d.w.values * rest * d[y].values).sum() / (d.w.values * rest).sum())
        if rest.any()
        else None
    )
    dly = int(score.split("_d")[-1])
    zs = select(d, f"zero_d{dly}", direction, q)
    Rz, Iz, _ = ratio(d, zs, y)
    return {
        "R_sel": Rs,
        "se": se(Is),
        "lo95": Rs - Z * se(Is),
        "hi95": Rs + Z * se(Is),
        "R_all": Ra,
        "diff_all": Rs - Ra,
        "diff_all_lo95": Rs - Ra - Z * se(Is - Ia),
        "R_zero_same_q": Rz,
        "diff_zero": Rs - Rz,
        "diff_zero_se": se(Is - Iz),
        "share_ge2x_sel": ps,
        "share_ge2x_all": pa,
        "enrichment": ps / pa if pa else None,
        "mean_below2x_sel": mu_o,
        "n_sel": int(sel.sum()),
        "weight_share_sel": float((d.w.values * sel).sum() / d.w.sum()),
    }


def verdict(p: dict, pb: dict) -> str:
    if p["R_sel"] >= 1.0 and p["diff_all_lo95"] > 0 and p["diff_zero"] > 0:
        return "开发正结果：进入 02 §10.4 准入顺序"
    if pb["hi95"] < 1.0:
        return "停止：只关闭所测实现（Full 层一页出资或控制强度、t3+30 秒、b50、强度高者入选）"
    return "区间跨越 1：第二阶段（须用户批准）或按资源决定停止"


def main() -> None:
    d = frame()
    out: dict = {"card": "卡片_R1a_v3_经济筛查.md", "sample": dict(d.attrs)}
    pa = cell(d, PRIMARY["score"], "high", PRIMARY["q"], "A", PRIMARY["rule"])
    pb = cell(d, PRIMARY["score"], "high", PRIMARY["q"], "B", PRIMARY["rule"])
    out["primary"] = {"A": pa, "B": pb, "verdict": verdict(pa, pb)}
    out["primary_by_week"] = {
        w: {
            b: cell(
                d[d.cohort_week == w],
                PRIMARY["score"],
                "high",
                0.10,
                b,
                PRIMARY["rule"],
            )
            for b in "AB"
        }
        for w in "AB"
    }
    sec = {}
    scores = [
        f"S_{v}_{md}_d{dl}"
        for v in ("full", "fund", "light")
        for md in ("main", "strict")
        for dl in (5, 30)
    ]
    scores += ["zero_d5", "zero_d30"]
    for sc in scores:
        dly = int(sc.split("_d")[-1])
        for di in ("high", "low"):
            for q in QS:
                for b in "AB":
                    sec[f"{sc}|{di}|{q}|{b}"] = cell(d, sc, di, q, b, RULE[dly])
    out["secondary"] = sec
    out["sensitivity_primary"] = {
        name: {b: cell(d, sc, "high", 0.10, b, PRIMARY["rule"]) for b in "AB"}
        for name, sc in (
            ("只用严格交易所标签", "S_full_strict_d30"),
            ("模板化地址当作服务", "S_full_tmpl_d30"),
            ("纯出资（去掉 nonce）", "S_fund_main_d30"),
        )
    }
    out["n_secondary_cells"] = len(sec)
    # 诊断：未解析比例按 W 分组（主口径、d30）
    unres = d["n_unres_full_main_d30"] / d["n_buyers_d30"].replace(0, np.nan)
    out["unresolved_share_by_w"] = {
        str(k): float(np.average(unres[g.index].fillna(0), weights=g.w))
        for k, g in d.groupby("is_w")
    }
    out["missing_score_weight_share"] = float(
        d.loc[d["S_full_main_d30"].isna(), "w"].sum() / d.w.sum()
    )
    # 诊断：创建者“此前 30 天 0 次发币”层（F118）与组合规则
    cr = pd.concat(
        [pd.read_csv(HERE / "raw" / "dune" / f"PROBE_CREATOR_{w}.csv.gz") for w in "AB"]
    )
    d["n_launch_30d"] = d.mint.map(dict(zip(cr.mint, cr.n_launch_30d)))
    z = d[d.n_launch_30d == 0]
    out["creator_zero_stratum_primary"] = {
        b: cell(z, PRIMARY["score"], "high", 0.10, b, PRIMARY["rule"]) for b in "AB"
    }
    sel = select(d, PRIMARY["score"], "high", 0.10) & (d.n_launch_30d == 0).values
    out["creator_and_primary"] = {
        b: {
            "R": ratio(d, sel, f"y_{PRIMARY['rule']}_{b}")[0],
            "se": se(ratio(d, sel, f"y_{PRIMARY['rule']}_{b}")[1]),
            "n": int(sel.sum()),
        }
        for b in "AB"
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float) + "\n")
    print(
        json.dumps(
            {k: out[k] for k in ("sample", "primary")},
            ensure_ascii=False,
            indent=1,
            default=float,
        )
    )


if __name__ == "__main__":
    main()
