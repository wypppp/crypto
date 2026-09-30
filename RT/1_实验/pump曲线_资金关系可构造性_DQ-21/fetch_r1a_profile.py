#!/usr/bin/env python3
"""R1a v3 画像阶段取数：冻结后的记账修正（09-30），只改“已用预算”的来源，不改取数规则。

问题：fetch_r1a.py（冻结 b1eb28b6…）pages 阶段 8 线程并发，逐页记的 calls 是共享计数器的前后差，
其他线程的请求被重复计入：raw/r1a/r1a_fetch_index.csv 的 pages 行 calls 合计 93,199，真实请求 11,655
（脚本最终计数；控制台 101,916 → 218,416，即计费 11,650 次）。其 profile 阶段用该列推算已用预算，会误判超限。

修正：已用预算以 raw/r1a/r1a_fetch_runs.csv（每次运行一行：phase, calls, credits）的合计为准；
缺该文件时按 pages 阶段脚本最终计数 11,655 次建立。画像候选、规则、缓存、输出与上限
（30 万 credits、10 credits/次）全部沿用 fetch_r1a.run_profile；本阶段顺序执行，逐行 calls 准确。

python fetch_r1a_profile.py
"""

from __future__ import annotations

import pandas as pd

import fetch_r1a as FR

RUNS = FR.HERE / "raw" / "r1a" / "r1a_fetch_runs.csv"
PAGES_CALLS = 11_655  # fetch_r1a.py pages 最终打印：calls 11655 credits 116550 errors 0


def spent_before() -> int:
    if not RUNS.exists():
        pd.DataFrame(
            [
                {
                    "phase": "pages",
                    "calls": PAGES_CALLS,
                    "credits": PAGES_CALLS * FR.HL.CREDITS_PER_CALL,
                }
            ]
        ).to_csv(RUNS, index=False)
    return int(pd.read_csv(RUNS).calls.sum())


def main() -> None:
    FR.spent_before = spent_before
    used = spent_before()
    FR.run_profile()
    n = FR.HL.STATE["calls"] - used
    pd.DataFrame(
        [{"phase": "profile", "calls": n, "credits": n * FR.HL.CREDITS_PER_CALL}]
    ).to_csv(RUNS, mode="a", header=False, index=False)
    print("runs ledger calls", int(pd.read_csv(RUNS).calls.sum()))


if __name__ == "__main__":
    main()
