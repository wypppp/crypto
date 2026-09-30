#!/usr/bin/env python3
"""S1 A/B 双口径分析：按 S1 卡片，A 周、B 周分开，口径 A（保守，原列）与口径 B（乐观，*_b 列）并报。

复用 analyze_s1_baseline.py 的读数与 summarize()：冻结 S0 权重（病例 1、固定 2% 子队列 50），
主样本为适用且非 R0 已看币；有缺失就不给总体 HT 均值。另加：
- 按周 × t3 层的分母取自冻结 S0（n_eligible_week、n_eligible_week_t3_bucket），减去该格 R0 已看适用币；
- 有效样本量（Kish）与非病例样本数，A 周 t3=121–300 秒按卡片标低精度；
- 报价状态年龄超过持有期的加权占比；
- 富集诊断（只作诊断）：≥2 倍币的加权占比与每日个数，以及“其余币均值不变”时回收到 1.00 / 1.03 所需的富集倍数。

python analyze_s1_dual.py → raw/s1/S1_AB_dual_analysis.json
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from analyze_s0_v1_2 import b, f
from analyze_s1_baseline import S0_DEFAULT, STRATEGIES, read_rows, summarize

HERE = Path(__file__).resolve().parent
S1 = HERE / "raw" / "s1"
FILES = {"A": S1 / "S1_A_dual.csv.gz", "B": S1 / "S1_B_dual.csv.gz"}
OUT = S1 / "S1_AB_dual_analysis.json"
HORIZON_S = {"30s": 30, "2m": 120, "10m": 600, "1h": 3600}
BUCKETS = ["000_005", "006_015", "016_030", "031_060", "061_120", "121_300"]
TARGETS = (1.0, 1.03)


def load() -> tuple[dict[str, dict], dict[str, dict]]:
    s0 = read_rows(S0_DEFAULT)
    s1: dict[str, dict] = {}
    for week, path in FILES.items():
        rows = read_rows(path)
        if any(r["cohort_week"] != week for r in rows.values()):
            raise RuntimeError(f"{path.name} 含其他周的行")
        s1.update(rows)
    if set(s1) != set(s0):
        raise RuntimeError("S1 与冻结 S0 的 mint 集合不同")
    for mint, r in s1.items():
        old = s0[mint]
        for col in (
            "eligible",
            "r0_seen",
            "tail420_candidate",
            "cohort_week",
            "t3_bucket",
        ):
            if r[col] != old[col]:
                raise RuntimeError(f"S1 改变了冻结字段 {mint} {col}")
        for col in ("t3_s", "e5_x", "e5_y"):
            x, y = f(r, col), f(old, col)
            if (x is None) != (y is None) or (
                x is not None and not math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-12)
            ):
                raise RuntimeError(f"S1 改变了冻结字段 {mint} {col}")
        # 入样权重只由冻结 S0 决定，不用 S1 重算的 tail10_exec
        r["_frozen_case"] = b(old, "tail420_candidate") or b(old, "tail10_exec")
    return s0, s1


def targets(s0: dict[str, dict]) -> dict[tuple, int]:
    """(周, t3 层) 与 (周,) 的精确适用分母，减去 R0 已看适用币。"""
    out: dict[tuple, int] = {}
    r0 = defaultdict(int)
    for r in s0.values():
        if b(r, "eligible"):
            out[(r["cohort_week"],)] = int(float(r["n_eligible_week"]))
            out[(r["cohort_week"], r["t3_bucket"])] = int(
                float(r["n_eligible_week_t3_bucket"])
            )
            if b(r, "r0_seen"):
                r0[(r["cohort_week"],)] += 1
                r0[(r["cohort_week"], r["t3_bucket"])] += 1
    return {k: v - r0[k] for k, v in out.items()}


def as_basis(rows: list[dict], basis: str) -> list[dict]:
    if basis == "A":
        return rows
    return [{**r, **{s: r[s + "_b"] for s in STRATEGIES}} for r in rows]


def weight(r: dict) -> int:
    return 1 if r["_frozen_case"] else 50


def extras(rows: list[dict], name: str, days: int) -> dict:
    vals = [(weight(r), f(r, name), r) for r in rows]
    vals = [
        (w, v, r) for w, v, r in vals if v is not None and math.isfinite(v) and v >= 0
    ]
    sw = sum(w for w, _, _ in vals)
    if not sw:
        return {}
    win = [(w, v) for w, v, _ in vals if v >= 2]
    rest = [(w, v) for w, v, _ in vals if v < 2]
    p = sum(w for w, _ in win) / sw
    mu_w = sum(w * v for w, v in win) / sum(w for w, _ in win) if win else None
    mu_o = sum(w * v for w, v in rest) / sum(w for w, _ in rest)
    need = {}
    for t in TARGETS:
        # 其余币均值不变时，选中集合里 ≥2 倍币占比须达 p' = (t-μo)/(μw-μo)，富集 = p'/p
        need[str(t)] = (
            None if mu_w is None or mu_w <= t else ((t - mu_o) / (mu_w - mu_o)) / p
        )
    out = {
        "kish_n_eff": sw**2 / sum(w * w for w, _, _ in vals),
        "noncase_rows": sum(1 for w, _, _ in vals if w == 50),
        "share_ge2x_weighted": p,
        "ge2x_per_day_weighted": sum(w for w, _ in win) / days,
        "mean_ge2x": mu_w,
        "mean_below2x": mu_o,
        "enrichment_needed_ge2x": need,
    }
    if name.startswith("ret_"):
        d, h = name[4:].split("_")  # ret_d5_30s → d5, 30s
        ages = [(w, f(r, f"state_age_{d}_{h}")) for w, _, r in vals]
        if any(a is None for _, a in ages):
            raise RuntimeError(f"状态年龄缺失：state_age_{d}_{h}")
        stale = [(w, a) for w, a in ages if a > HORIZON_S[h]]
        out["stale_quote_share_weighted"] = sum(w for w, _ in stale) / sw
        out["stale_quote_rows"] = len(stale)
    return out


def analyse(rows: list[dict], denom: int, days: int) -> dict:
    res = {}
    for basis in ("A", "B"):
        rb = as_basis(rows, basis)
        res[basis] = {
            s: {**summarize(rb, s, denom), **extras(rb, s, days)} for s in STRATEGIES
        }
    return res


def main() -> None:
    s0, s1 = load()
    den = targets(s0)
    primary = [r for r in s1.values() if b(r, "eligible") and not b(r, "r0_seen")]
    out = {
        "files": {k: str(v.relative_to(HERE)) for k, v in FILES.items()},
        "note": "池模型成交，每笔 0.5 SOL；未计优先费、失败交易、MEV。口径 A 保守、口径 B 乐观（F116）。富集为诊断量，不代替净回收。",
        "weeks": {},
    }
    for week in ("A", "B"):
        rows = [r for r in primary if r["cohort_week"] == week]
        days = len({r["created_at"][:10] for r in rows})
        wk = {
            "primary_rows": len(rows),
            "target": den[(week,)],
            "days": days,
            "all": analyse(rows, den[(week,)], days),
        }
        wk["by_t3_bucket"] = {}
        for bk in BUCKETS:
            sub = [r for r in rows if r["t3_bucket"] == bk]
            wk["by_t3_bucket"][bk] = {
                "primary_rows": len(sub),
                "noncase_rows": sum(1 for r in sub if not r["_frozen_case"]),
                "target": den[(week, bk)],
                "low_precision": (week, bk) == ("A", "121_300"),
                "stats": analyse(sub, den[(week, bk)], days),
            }
        out["weeks"][week] = wk
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    for week in ("A", "B"):
        w = out["weeks"][week]
        print(
            f"== {week} 周：主样本 {w['primary_rows']}，目标适用币 {w['target']}，{w['days']} 天"
        )
        for s in STRATEGIES:
            ra, rb = w["all"]["A"][s], w["all"]["B"][s]
            print(
                f"{s:15s} HT A {ra['population_mean_if_no_missing_HT']}  B {rb['population_mean_if_no_missing_HT']}  "
                f"缺失 {ra['missing_rows']}/{rb['missing_rows']}"
            )
    print("saved", OUT)


if __name__ == "__main__":
    main()
