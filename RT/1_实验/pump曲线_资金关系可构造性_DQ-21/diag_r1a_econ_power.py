#!/usr/bin/env python3
"""组合门诊断（09-30，外部评估后补算）：R1a 主规则的保本线与小样本对经济终点的精度。

只用已下载的 S1 A/B 结果，0 credits；不看任何关系信号。
1. 保本线：选中集合回收 = p′·μ(≥2×) + (1−p′)·μ(<2×)。给定富集 E（p′ = E·p），
   求回收到 1.00 时 <2× 币均值须达到多少，即富集与“其余币变好”两个杠杆的组合。
2. 精度：按 R1a v2 卡 §5 的抽样（病例 300 = 主规则 ≥2× 币按 mint_hash 前 300；
   队列 600 = 2% 子队列按 mint_hash 前 600；入样概率 = S0 冻结概率 × 本次抽取并集概率），
   用随机打分取加权总体前 q，看选中集合回收估计的标准误；另算“第二阶段”（全部病例 + 全子队列）。

python diag_r1a_econ_power.py → raw/s1/S1_r1a_econ_power.json
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import analyze_s1_dual as m
from analyze_s0_v1_2 import b, f

HERE = Path(__file__).resolve().parent
OUT = HERE / "raw" / "s1" / "S1_r1a_econ_power.json"
RULE = "b50_ret_d30"  # R1a v2 主规则：t3+30 秒、b50、口径 A
CALLS_PER_COIN = 25  # R1a v2 卡 §7


def iso_line(analysis: dict) -> dict:
    out = {}
    for wk in "AB":
        for basis in "AB":
            x = analysis["weeks"][wk]["all"][basis][RULE]
            p, mw, mo = x["share_ge2x_weighted"], x["mean_ge2x"], x["mean_below2x"]
            need = {}
            for e in (1, 2, 3, 4):
                pp = e * p
                need[str(e)] = (1 - pp * mw) / (1 - pp)
            out[f"{wk}周_口径{basis}"] = {
                "p_ge2x": p,
                "mean_ge2x": mw,
                "mean_below2x": mo,
                "below2x_mean_needed_for_1": need,
            }
    return out


def build_frame() -> tuple[list[dict], list[dict], list[dict]]:
    _, s1 = m.load()
    rows = [r for r in s1.values() if b(r, "eligible") and not b(r, "r0_seen")]
    for r in rows:
        r["_r"] = f(r, RULE)
        r["_w"] = r["_r"] >= 2
        r["_sub"] = int(r["mint_hash_exact"]) % 10000 < 200
        r["_p0"] = 1.0 if r["_frozen_case"] else 0.02
    key = lambda r: int(r["mint_hash_exact"])  # noqa: E731
    wins = sorted((r for r in rows if r["_w"]), key=key)
    sub = sorted((r for r in rows if r["_sub"]), key=key)
    return rows, wins, sub


def design(
    rows: list[dict], wins: list[dict], sub: list[dict], nw: int, nc: int
) -> list[tuple[dict, float]]:
    cw, cc = {id(r) for r in wins[:nw]}, {id(r) for r in sub[:nc]}
    pw, pc = nw / len(wins), nc / len(sub)
    out = []
    for r in rows:
        if id(r) in cw or id(r) in cc:
            a = pw if r["_w"] else 0.0
            c = pc if r["_sub"] else 0.0
            out.append((r, r["_p0"] * (1 - (1 - a) * (1 - c))))
    return out


def precision(
    smp: list[tuple[dict, float]], q: float, reps: int = 300, seed: int = 1
) -> dict:
    rng = random.Random(seed)
    ests, ses = [], []
    total = sum(1 / p for _, p in smp)
    n_sel = 0
    for _ in range(reps):
        order = sorted(smp, key=lambda _t: rng.random())
        acc, sel = 0.0, []
        for r, p in order:
            if acc >= q * total:
                break
            acc += 1 / p
            sel.append((r["_r"], 1 / p))
        sw = sum(w for _, w in sel)
        mu = sum(w * v for v, w in sel) / sw
        ests.append(mu)
        ses.append(math.sqrt(sum(w * w * (v - mu) ** 2 for v, w in sel)) / sw)
        n_sel = len(sel)
    mean = sum(ests) / reps
    sd = math.sqrt(sum((e - mean) ** 2 for e in ests) / (reps - 1))
    return {
        "null_mean": mean,
        "linearized_se": sum(ses) / reps,
        "sd_across_random_scores": sd,
        "selected_rows": n_sel,
    }


def main() -> None:
    analysis = json.loads(
        (HERE / "raw" / "s1" / "S1_AB_dual_analysis.json").read_text()
    )
    rows, wins, sub = build_frame()
    out = {
        "rule": RULE,
        "iso_line": iso_line(analysis),
        "frame_ge2x_rows": len(wins),
        "subcohort_rows": len(sub),
        "designs": {},
    }
    for name, nw, nc in (("卡片小样本", 300, 600), ("第二阶段", len(wins), len(sub))):
        smp = design(rows, wins, sub, nw, nc)
        out["designs"][name] = {
            "coins": len(smp),
            "gtfa_calls_est": CALLS_PER_COIN * len(smp),
            "by_q": {str(q): precision(smp, q) for q in (0.05, 0.10, 0.20)},
        }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
