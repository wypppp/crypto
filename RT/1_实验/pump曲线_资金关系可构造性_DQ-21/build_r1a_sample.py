#!/usr/bin/env python3
"""R1a v3 §6：生成小样本名单（病例 300 + 子队列 600，均按 mint_hash 升序），写入样概率。

总体 = S1 A/B 主样本（适用且非 R0 已看）。W = b50_ret_d30 口径 A ≥2（只用于抽样）。
入样概率 = S0 冻结概率 p0 × [1 − (1 − a·W)(1 − c·子队列)]，a = 300/|W|，c = 600/|子队列|。
取数按 mint_hash 升序；若预算先到，分析时按实际完成的前缀重算 a、c（analyze_r1a.py）。

python build_r1a_sample.py → r1a_sample.csv
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import analyze_s1_dual as m
from analyze_s0_v1_2 import b, f

HERE = Path(__file__).resolve().parent
OUT = HERE / "r1a_sample.csv"
RULE = "b50_ret_d30"
N_CASE, N_COH = 300, 600
SUB = 200  # mint_hash % 10000 < 200：2% 子队列（S0 冻结）


def main() -> None:
    _, s1 = m.load()
    rows = [r for r in s1.values() if b(r, "eligible") and not b(r, "r0_seen")]
    for r in rows:
        v = f(r, RULE)
        r["_w"] = v is not None and v >= 2
        r["_sub"] = int(r["mint_hash_exact"]) % 10000 < SUB
        r["_p0"] = 1.0 if r["_frozen_case"] else 0.02
    key = lambda r: int(r["mint_hash_exact"])  # noqa: E731
    wins = sorted((r for r in rows if r["_w"]), key=key)
    sub = sorted((r for r in rows if r["_sub"]), key=key)
    case_set = {r["mint"] for r in wins[:N_CASE]}
    coh_set = {r["mint"] for r in sub[:N_COH]}
    a, c = N_CASE / len(wins), N_COH / len(sub)
    chosen = sorted((r for r in rows if r["mint"] in case_set | coh_set), key=key)
    cols = [
        "order",
        "mint",
        "cohort_week",
        "created_at",
        "t3_s",
        "mint_hash_exact",
        "is_w",
        "is_sub",
        "in_case_draw",
        "in_cohort_draw",
        "p0",
        "a",
        "c",
        "incl_prob",
    ]
    with OUT.open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(cols)
        for i, r in enumerate(chosen):
            pa = a if r["_w"] else 0.0
            pc = c if r["_sub"] else 0.0
            wr.writerow(
                [
                    i,
                    r["mint"],
                    r["cohort_week"],
                    r["created_at"],
                    r["t3_s"],
                    r["mint_hash_exact"],
                    int(r["_w"]),
                    int(r["_sub"]),
                    int(r["mint"] in case_set),
                    int(r["mint"] in coh_set),
                    r["_p0"],
                    a,
                    c,
                    r["_p0"] * (1 - (1 - pa) * (1 - pc)),
                ]
            )
    print(
        "frame W",
        len(wins),
        "subcohort",
        len(sub),
        "chosen",
        len(chosen),
        "overlap",
        len(case_set & coh_set),
        "sha256",
        hashlib.sha256(OUT.read_bytes()).hexdigest(),
    )


if __name__ == "__main__":
    main()
