#!/usr/bin/env python3
"""组合门探针 P-H1（09-30）：Helius getTransactionsForAddress 同参数计费小批。

重放 R0 已查过的地址与时间窗（raw/helius_index.csv），参数与 R0/R1a v2 卡相同（完整交易、json、
只要成功的、limit=100），共 100 次请求（含重试）。不保存交易内容，只记每次返回的笔数与分页；
不看任何关系信号或收益。单价以用户读取的控制台增量为准，合约见 探针_组合门_2026-09-30.md。

请求上限：helius.py 按 100 credits/次预留，cap = 100 × 100，第 101 次请求（含重试）前即停。

python probe_helius_billing.py → raw/probe/PROBE_HELIUS_billing.json
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import helius as HL

HERE = Path(__file__).resolve().parent
OUT = HERE / "raw" / "probe" / "PROBE_HELIUS_billing.json"
N_REQUESTS = 100
ORDER = {"coin": "asc", "fwd": "asc", "back": "desc", "back_ext": "desc"}


def plan() -> list[dict]:
    rows = list(csv.DictReader((HERE / "raw" / "helius_index.csv").open()))
    rows.sort(key=lambda r: hashlib.sha256(r["key"].encode()).hexdigest())
    return rows


def main() -> None:
    HL.STATE["cap"] = N_REQUESTS * HL.CREDITS_PER_CALL
    started = dt.datetime.now(dt.UTC).isoformat()
    calls, keys = [], []
    for r in plan():
        if HL.STATE["calls"] >= N_REQUESTS:
            break
        token, got, pages = None, 0, 0
        while pages < int(r["pages"]) and HL.STATE["calls"] < N_REQUESTS:
            before = HL.STATE["calls"]
            try:
                res = HL.gtfa(r["addr"], r["gte"], r["lt"], ORDER[r["kind"]], token)
            except HL.BudgetExceeded:
                break
            data = res.get("data", [])
            pages += 1
            got += len(data)
            token = res.get("paginationToken")
            calls.append(
                {
                    "key": r["key"],
                    "page": pages,
                    "n_tx": len(data),
                    "requests_used": HL.STATE["calls"] - before,
                    "has_token": bool(token),
                }
            )
            if not token or len(data) < 100:
                break
        keys.append(
            {
                "key": r["key"],
                "kind": r["kind"],
                "pages_r0": int(r["pages"]),
                "pages_now": pages,
                "n_tx_r0": int(r["n_tx"]),
                "n_tx_now": got,
                "same_as_r0": pages == int(r["pages"]) and got == int(r["n_tx"]),
            }
        )
    finished = dt.datetime.now(dt.UTC).isoformat()
    n_ok = len(calls)
    per100 = sum(max(10, 10 * math.ceil(c["n_tx"] / 100)) for c in calls)
    out = {
        "contract": "探针_组合门_2026-09-30.md",
        "started_utc": started,
        "finished_utc": finished,
        "http_requests": HL.STATE["calls"],
        "successful_calls": n_ok,
        "returned_tx": sum(c["n_tx"] for c in calls),
        "full_pages": sum(c["n_tx"] == 100 for c in calls),
        "expected_console_increment": {
            "文档规则（每返回 100 笔 10，最低 10；失败不计）": per100,
            "每次 10": 10 * n_ok,
            "每次 100": 100 * n_ok,
        },
        "console_before": {
            "value": 100916,
            "source": "用户 09-28 控制台读数（总入口 §1 资源）；此后本 repo 无 Helius 调用记录",
        },
        "keys_replayed": len(keys),
        "keys_fully_replayed_same_as_r0": sum(k["same_as_r0"] for k in keys),
        "latency_s_median": sorted(HL.STATE["lat"])[len(HL.STATE["lat"]) // 2]
        if HL.STATE["lat"]
        else None,
        "keys": keys,
        "calls": calls,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(
        json.dumps(
            {k: v for k, v in out.items() if k not in ("keys", "calls")},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
