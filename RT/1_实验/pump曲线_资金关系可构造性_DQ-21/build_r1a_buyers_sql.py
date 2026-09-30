#!/usr/bin/env python3
"""R1a v3：生成早买者名单查询（Dune），覆盖 r1a_sample.csv 的 892 币。

输出每币的创建事件一行，加创建后至 t3+30 秒（另留 5 秒余量，本地按 S0 的 clock_ts 规则再截）的全部曲线成交。
本地（build_r1a.py）按 S0 v1.3 的定义重算合格早买者（≥0.1 SOL、非创建者、每钱包第一笔合格买入）与 t3，
并与 S1 的 t3_s 逐币核对。只读 06-01～06-15 分区（06-15 只为覆盖 06-14 深夜创建币的前几分钟），不读 06-15 起创建的币。

python build_r1a_buyers_sql.py → sql/R1A_BUYERS.sql
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARGIN_S = 5

TEMPLATE = """/* R1a v3 早买者名单（09-30）：r1a_sample.csv 的 {n} 币。由 build_r1a_buyers_sql.py 生成。
   每币：创建事件一行 + 创建后至 created_at + t3_s + 30 + {margin} 秒的全部曲线成交（TradeEvent）。
   合格早买者、t3 与 Zero 层在本地按 S0 v1.3 口径重算。只读 2026-06-01～06-15 分区，不读 06-15 起创建的币。 */
WITH
s(mint, t3_s) AS (
    SELECT mint, t3_s FROM (VALUES
{values}
    ) AS t(mint, t3_s)
),
cr AS (
    SELECT mint, dev, creator_field, created_at, created_slot, created_txi, create_tx
    FROM (
        SELECT
            c.mint,
            CAST(c."user" AS varchar) AS dev,
            CAST(c.creator AS varchar) AS creator_field,
            c.evt_block_time AS created_at,
            c.evt_block_slot AS created_slot,
            c.evt_tx_index AS created_txi,
            c.evt_tx_id AS create_tx,
            row_number() OVER (
                PARTITION BY c.mint
                ORDER BY c.evt_block_slot, c.evt_tx_index, c.evt_outer_instruction_index
            ) AS rn
        FROM pumpdotfun_solana.pump_evt_createevent c
        WHERE c.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'
          AND c.mint IN (SELECT mint FROM s)
    )
    WHERE rn = 1
),
tr AS (
    SELECT
        t.mint,
        t.evt_block_time AS ts,
        t.evt_block_slot AS slot,
        t.evt_tx_index AS txi,
        COALESCE(t.evt_outer_instruction_index, 0) AS oix,
        COALESCE(t.evt_inner_instruction_index, -1) AS iix,
        t.evt_tx_id AS tx_id,
        CAST(t."user" AS varchar) AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN s ON s.mint = t.mint
    JOIN cr ON cr.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-15'
      AND t.evt_block_time >= cr.created_at
      AND t.evt_block_time <= date_add('second', s.t3_s + 30 + {margin}, cr.created_at)
)
SELECT
    'create' AS kind, mint, created_at AS ts, created_slot AS slot, created_txi AS txi,
    0 AS oix, -1 AS iix, create_tx AS tx_id, dev AS usr, creator_field,
    CAST(NULL AS boolean) AS is_buy, CAST(NULL AS DOUBLE) AS sol_amt
FROM cr
UNION ALL
SELECT
    'trade', mint, ts, slot, txi, oix, iix, tx_id, usr, CAST(NULL AS varchar), is_buy, sol_amt
FROM tr
ORDER BY 2, 4, 5, 6, 7
"""


def main() -> None:
    rows = list(csv.DictReader((HERE / "r1a_sample.csv").open()))
    vals = ",\n".join(
        f"        ('{r['mint']}', {int(float(r['t3_s']))})"
        for r in sorted(rows, key=lambda r: r["mint"])
    )
    sql = TEMPLATE.format(n=len(rows), values=vals, margin=MARGIN_S)
    out = HERE / "sql" / "R1A_BUYERS.sql"
    out.write_text(sql)
    print(out.name, len(rows), hashlib.sha256(sql.encode()).hexdigest())


if __name__ == "__main__":
    main()
