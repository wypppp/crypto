#!/usr/bin/env python3
"""DQ-34 数据保全：xStocks 在 Solana DEX 的 15 分钟价格与成交，按月从 Dune 取（10-02；只存不分析）。

python xs_dune.py 2025-06 2026-09 → sql/XS_SOL_{YYYYMM}.sql、raw/dune/XS_SOL_{YYYYMM}.csv.gz、runs/dune_ledger.csv
每月一条公开查询（按 2026-09 第一周实测 5.67 credits 估，每月约 25，低于单条审批阈值 100）；
建查询 → 执行 → 轮询 → 流式下载（dune_get_stream.py）→ 台账。单条费用 >100 时停止后续月份。
官方 xStocks 的识别：tokens_solana.fungible 中铸币地址以 Xs 开头、名称以 xStock 结尾。
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from dune_get import API, H, KEY, get

TEMPLATE = """/* DQ-34 数据保全：xStocks（官方 Xs* 铸币地址）在 Solana DEX 的 15 分钟价格与成交；只读 {m0} 月分区；由 xs_dune.py 生成 */
WITH xs AS (
    SELECT token_mint_address AS mint, symbol
    FROM tokens_solana.fungible
    WHERE token_mint_address LIKE 'Xs%' AND name LIKE '%xStock'
),
legs AS (
    SELECT t.block_time, xs.symbol, t.project, t.amount_usd,
           t.token_bought_amount AS qty, 1 AS buy
    FROM dex_solana.trades t JOIN xs ON t.token_bought_mint_address = xs.mint
    WHERE t.block_month = DATE '{m0}'
    UNION ALL
    SELECT t.block_time, xs.symbol, t.project, t.amount_usd,
           t.token_sold_amount AS qty, 0 AS buy
    FROM dex_solana.trades t JOIN xs ON t.token_sold_mint_address = xs.mint
    WHERE t.block_month = DATE '{m0}'
)
SELECT from_unixtime(floor(to_unixtime(block_time) / 900) * 900) AS t15, symbol,
       count(*) AS n, sum(buy) AS n_buy, sum(amount_usd) AS usd, sum(qty) AS qty,
       min_by(amount_usd / qty, block_time) AS px_open, max_by(amount_usd / qty, block_time) AS px_close,
       max(amount_usd / qty) AS px_high, min(amount_usd / qty) AS px_low, count(DISTINCT project) AS n_venues
FROM legs
WHERE qty > 0 AND amount_usd > 0
GROUP BY 1, 2
ORDER BY 1, 2
"""


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"X-Dune-API-Key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def ledger(row: list) -> None:
    with open(H / "runs" / "dune_ledger.csv", "a", newline="") as f:
        csv.writer(f).writerow(row)


def months(a: str, b: str) -> list[dt.date]:
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        out.append(dt.date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main() -> None:
    for m0 in months(sys.argv[1], sys.argv[2]):
        label = f"XS_SOL_{m0:%Y%m}"
        if (H / "raw" / "dune" / f"{label}.csv.gz").exists():
            continue
        sql_file = Path("sql") / f"{label}.sql"
        (H / sql_file).write_text(TEMPLATE.format(m0=m0.isoformat()))
        sql = (H / sql_file).read_text()
        qid = call(
            "POST",
            "/query",
            {"name": f"DQ-34 {label}", "query_sql": sql, "is_private": False},
        )["query_id"]
        eid = call("POST", f"/query/{qid}/execute", {"performance": "large"})[
            "execution_id"
        ]
        while True:
            st = get(f"/execution/{eid}/status")
            if st["state"] not in ("QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING"):
                break
            time.sleep(15)
        cost = st.get("execution_cost_credits")
        ledger([qid, str(sql_file), eid, st["state"], cost, "", "公开查询"])
        print(label, qid, st["state"], cost, flush=True)
        if st["state"] != "QUERY_STATE_COMPLETED":
            continue
        subprocess.run(
            [sys.executable, "dune_get_stream.py", str(qid), label, str(sql_file)],
            cwd=H,
            check=True,
        )
        if cost is not None and float(cost) > 100:
            print("单条费用超过 100，停止后续月份", flush=True)
            break


if __name__ == "__main__":
    main()
