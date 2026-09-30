#!/usr/bin/env python3
"""组合门探针 P-C1（09-30）：创建者滚动 30 天履历与 S1 A/B 本地连接，报选中集合回收。

在看结果之前与合约（探针_组合门_2026-09-30.md）一起提交。主样本、权重同 analyze_s1_dual.py：
适用且非 R0 已看；病例权重 1、2% 子队列 50（冻结 S0）。

- 打分 S_launch（主）：此前 30 天发币数升序，平手按此前毕业数降序、再按 mint_hash 升序；
  S_grad（诊断）：此前毕业数降序，平手按发币数升序、mint_hash 升序。
- 选中集合：按打分排序后累加权重，到加权总体的 q 为止（含越过 q 的那一行）。
- 回收：Hájek 比率均值，线性化标准误 sqrt(Σw²(v−R)²)/Σw；口径 A、B 并报；A 周、B 周分开。
- 主判定：S_launch × b50_ret_d5 × q=10%。两周口径 A 的 95% 下界都 >1 → 通过；
  两周口径 B 的 95% 上界都 <1 → 不通过（只关闭该实现）；其余 → 先解决再说（无便宜后续测量，留候选池）。

python analyze_probe_creator.py → raw/probe/PROBE_CREATOR_analysis.json
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import analyze_s1_dual as m
from analyze_s0_v1_2 import b, f
from analyze_s1_baseline import read_rows

HERE = Path(__file__).resolve().parent
CSV = {w: HERE / "raw" / "dune" / f"PROBE_CREATOR_{w}.csv.gz" for w in "AB"}
OUT = HERE / "raw" / "probe" / "PROBE_CREATOR_analysis.json"
PRIMARY = ("S_launch", "b50_ret_d5", 0.10)
RULES = ("b50_ret_d5", "b50_ret_d30")
QS = (0.05, 0.10, 0.20)
BINS = ((0, 0), (1, 1), (2, 5), (6, 20), (21, 100), (101, 10**9))
Z = 1.96


def ts(s: str) -> dt.datetime:
    return dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def attach() -> tuple[list[dict], dict]:
    _, s1 = m.load()
    checks: dict = {}
    for w, path in CSV.items():
        rows = read_rows(path)
        frame = {k for k, r in s1.items() if r["cohort_week"] == w}
        if set(rows) != frame:
            raise RuntimeError(f"{path.name} 的 mint 集合与 S1 {w} 周框架不同")
        dts = []
        for mint, c in rows.items():
            r = s1[mint]
            r["_nl"] = int(float(c["n_launch_30d"]))
            r["_ng"] = int(float(c["n_grad_30d"]))
            dts.append(
                abs((ts(c["created_at_evt"]) - ts(r["created_at"])).total_seconds())
            )
            r["_dev_eq_creator"] = c["dev"] == c["creator_field"]
            r["_dev_eq_signer"] = c["dev"] == c["signer"]
            r["_dev_missing"] = not c["dev"]
        checks[w] = {
            "rows": len(rows),
            "created_at_abs_diff_s_max": max(dts),
            "created_at_exact_share": sum(d == 0 for d in dts) / len(dts),
            "dev_missing": sum(s1[k]["_dev_missing"] for k in rows),
            "dev_eq_creator_share": sum(s1[k]["_dev_eq_creator"] for k in rows)
            / len(rows),
            "dev_eq_signer_share": sum(s1[k]["_dev_eq_signer"] for k in rows)
            / len(rows),
        }
    primary = [r for r in s1.values() if b(r, "eligible") and not b(r, "r0_seen")]
    return primary, checks


def key(score: str):
    if score == "S_launch":
        return lambda r: (r["_nl"], -r["_ng"], int(r["mint_hash_exact"]))
    return lambda r: (-r["_ng"], r["_nl"], int(r["mint_hash_exact"]))


def valid(rows: list[dict], rule: str) -> list[tuple[int, float]]:
    out = []
    for r in rows:
        v = f(r, rule)
        if v is not None and math.isfinite(v) and v >= 0:
            out.append((m.weight(r), v))
    return out


def stats(vals: list[tuple[int, float]]) -> dict:
    sw = sum(w for w, _ in vals)
    mu = sum(w * v for w, v in vals) / sw
    se = math.sqrt(sum(w * w * (v - mu) ** 2 for w, v in vals)) / sw
    win = sum(w for w, v in vals if v >= 2) / sw
    rest = [(w, v) for w, v in vals if v < 2]
    mu_o = sum(w * v for w, v in rest) / sum(w for w, _ in rest) if rest else None
    return {
        "rows": len(vals),
        "weight": sw,
        "ratio_mean": mu,
        "se": se,
        "lo95": mu - Z * se,
        "hi95": mu + Z * se,
        "share_ge2x": win,
        "mean_below2x": mu_o,
    }


def select(rows: list[dict], score: str, q: float) -> list[dict]:
    order = sorted(rows, key=key(score))
    total = sum(m.weight(r) for r in rows)
    acc, out = 0.0, []
    for r in order:
        if acc >= q * total:
            break
        acc += m.weight(r)
        out.append(r)
    return out


def week_block(rows: list[dict]) -> dict:
    res: dict = {"primary_rows": len(rows), "by_basis": {}}
    for basis in "AB":
        rb = m.as_basis(rows, basis)
        blk: dict = {}
        for rule in RULES:
            base = stats(valid(rb, rule))
            cell = {"all": base, "scores": {}, "bins_launch_30d": {}}
            for score in ("S_launch", "S_grad"):
                cell["scores"][score] = {}
                for q in QS:
                    sel = select(rb, score, q)
                    s = stats(valid(sel, rule))
                    s["enrichment_ge2x"] = s["share_ge2x"] / base["share_ge2x"]
                    s["delta_vs_all"] = s["ratio_mean"] - base["ratio_mean"]
                    s["max_launch_30d_in_set"] = max(r["_nl"] for r in sel)
                    cell["scores"][score][str(q)] = s
            for lo, hi in BINS:
                sub = [r for r in rb if lo <= r["_nl"] <= hi]
                if sub:
                    s = stats(valid(sub, rule))
                    s["pop_share"] = s["weight"] / base["weight"]
                    cell["bins_launch_30d"][f"{lo}-{hi}"] = s
            blk[rule] = cell
        res["by_basis"][basis] = blk
    return res


def verdict(weeks: dict) -> dict:
    score, rule, q = PRIMARY
    cells = {
        (w, basis): weeks[w]["by_basis"][basis][rule]["scores"][score][str(q)]
        for w in "AB"
        for basis in "AB"
    }
    if all(cells[(w, "A")]["lo95"] > 1 for w in "AB"):
        v = "通过"
    elif all(cells[(w, "B")]["hi95"] < 1 for w in "AB"):
        v = "不通过（只关闭该实现）"
    else:
        v = "先解决再说（无便宜后续测量，留候选池）"
    return {
        "primary": {"score": score, "rule": rule, "q": q},
        "cells": {f"{w}周_口径{basis}": c for (w, basis), c in cells.items()},
        "verdict": v,
    }


def main() -> None:
    primary, checks = attach()
    weeks = {w: week_block([r for r in primary if r["cohort_week"] == w]) for w in "AB"}
    out = {
        "contract": "探针_组合门_2026-09-30.md",
        "checks": checks,
        "weeks": weeks,
        "verdict": verdict(weeks),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(
        json.dumps(
            {"checks": checks, "verdict": out["verdict"]}, ensure_ascii=False, indent=1
        )
    )


if __name__ == "__main__":
    main()
