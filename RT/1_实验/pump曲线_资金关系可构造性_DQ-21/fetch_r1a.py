#!/usr/bin/env python3
"""R1a v3 §7：Helius 取数。两个阶段，共用一道预算。

- pages：按 raw/r1a/r1a_fetch_plan.csv（plan_r1a.py），每个（钱包, 锚点时刻）取锚点前的最近 1 页：
  getTransactionsForAddress(W, blockTime ∈ [t − 7 天, t + 1), desc, limit=100, 完整交易, 只要成功的)。
  顺序 = 样本 order（mint_hash 升序），同币内创建者在前、早买者按名次。
- profile：按 raw/r1a/r1a_profile_candidates.csv（build_r1a.py 生成），用 R0 的 profile_funders.profile（同一规则、同一缓存）。
- 预算：本账户实扣 10 credits/次（F119）。运行时设 helius.CREDITS_PER_CALL = 10（不改 R0a 冻结的 helius.py），
  硬上限 30,000 次、300,000 credits，先到先停；重试计入。已有缓存不再调用。

python fetch_r1a.py pages|profile [--threads 8]
"""

from __future__ import annotations

import argparse
import gzip
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import helius as HL

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "helius" / "r1a"
IDX = HERE / "raw" / "r1a" / "r1a_fetch_index.csv"
WEEK = 7 * 86400
MAX_CALLS = 30_000
MAX_CREDITS = 300_000
HL.CREDITS_PER_CALL = 10  # F119：本账户实测
HL.STATE["cap"] = MAX_CREDITS
_lock = threading.Lock()


def spent_before() -> int:
    if not IDX.exists():
        return 0
    return int(pd.read_csv(IDX).calls.sum())


def fetch_page(row: dict) -> dict:
    f = RAW / f"{row['key']}.jsonl.gz"
    if f.exists():
        return {
            "key": row["key"],
            "calls": 0,
            "n_tx": None,
            "has_token": None,
            "error": "",
        }
    before = HL.STATE["calls"]
    try:
        r = HL.gtfa(row["W"], int(row["t"]) - WEEK, int(row["t"]) + 1, "desc")
    except HL.BudgetExceeded as e:
        return {
            "key": row["key"],
            "calls": 0,
            "n_tx": None,
            "has_token": None,
            "error": f"budget: {e}",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "key": row["key"],
            "calls": HL.STATE["calls"] - before,
            "n_tx": None,
            "has_token": None,
            "error": str(e)[:200],
        }
    data = r.get("data", [])
    tmp = f.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as g:
        for x in data:
            g.write(json.dumps(x) + "\n")
    tmp.rename(f)
    return {
        "key": row["key"],
        "calls": HL.STATE["calls"] - before,
        "n_tx": len(data),
        "has_token": bool(r.get("paginationToken")),
        "error": "",
    }


def run_pages(threads: int) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    plan = pd.read_csv(HERE / "raw" / "r1a" / "r1a_fetch_plan.csv")
    plan = plan.drop_duplicates("key")
    used = spent_before()
    HL.STATE["calls"] = used
    HL.STATE["credits"] = used * HL.CREDITS_PER_CALL
    todo = [
        r
        for r in plan.to_dict("records")
        if not (RAW / f"{r['key']}.jsonl.gz").exists()
    ]
    print("plan pages", len(plan), "to fetch", len(todo), "calls already", used)
    out = []
    with ThreadPoolExecutor(threads) as ex:
        for i, res in enumerate(ex.map(fetch_page, todo), 1):
            out.append(res)
            if HL.STATE["calls"] >= MAX_CALLS:
                print("call cap reached")
            if i % 500 == 0:
                print(
                    i,
                    "done; calls",
                    HL.STATE["calls"],
                    "credits",
                    HL.STATE["credits"],
                    flush=True,
                )
    df = pd.DataFrame(out)
    df["phase"] = "pages"
    df.to_csv(IDX, mode="a", header=not IDX.exists(), index=False)
    print(
        "calls",
        HL.STATE["calls"],
        "credits (10/次)",
        HL.STATE["credits"],
        "errors",
        int((df.error != "").sum()),
    )


def run_profile() -> None:
    import profile_funders as PF

    cand = pd.read_csv(HERE / "raw" / "r1a" / "r1a_profile_candidates.csv")
    used = spent_before()
    HL.STATE["calls"] = used
    HL.STATE["credits"] = used * HL.CREDITS_PER_CALL
    rows, log = [], []
    PF.RAW.mkdir(parents=True, exist_ok=True)
    for r in cand.itertuples():
        before = HL.STATE["calls"]
        try:
            p = PF.profile(r.address, int(r.first_ts))
            rows.append(p)
            err = ""
        except HL.BudgetExceeded as e:
            rows.append({"address": r.address, "error": "budget"})
            err = f"budget: {e}"
        log.append(
            {
                "key": f"profile__{r.address}",
                "calls": HL.STATE["calls"] - before,
                "n_tx": None,
                "has_token": None,
                "error": err,
                "phase": "profile",
            }
        )
    pd.DataFrame(rows).to_csv(
        HERE / "raw" / "r1a" / "r1a_service_profiles.csv", index=False
    )
    pd.DataFrame(log).to_csv(IDX, mode="a", header=not IDX.exists(), index=False)
    print("profiled", len(rows), "calls now", HL.STATE["calls"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["pages", "profile"])
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    if a.phase == "pages":
        run_pages(a.threads)
    else:
        run_profile()


if __name__ == "__main__":
    main()
