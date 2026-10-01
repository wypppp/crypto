#!/usr/bin/env python3
"""DQ-26 第一步·G1b 抽样（卡片_v1.md §4）：前 50 个实体的成交交易，按实体分层各抽 20 笔（种子 20261001）。

- 只抽钱包自己签名的曲线成交交易，或 dex_solana.trades 中 trader＝该钱包的交易（签名者在 Helius 端再核）；
- 抽样键：xxhash64(tx_id || '20261001') 排序，每个实体取前 20；
- 每笔输出该钱包在该交易里的事件现金：曲线（交易者一侧，费用用事件实际字段 fee＋creator_fee＋buyback_fee）
  与 dex_solana.trades 的非曲线成交（只计对手为 SOL/WSOL 的 SOL 金额，其余记 usd）。

python sql/build_sample_sql.py 实体钱包.csv → sql/SAMPLE_G1B_R.sql（实体钱包.csv 含 usr, entity）
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import sqlglot

H = Path(__file__).resolve().parent
R0, R1, CUT = "2026-08-03", "2026-08-09", "2026-08-16"
SOL_MINTS = (
    "'So11111111111111111111111111111111111111111', "
    "'So11111111111111111111111111111111111111112'"
)
SOL_RAW = "CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE)"
FEE_EVT = (
    "(COALESCE(CAST(t.fee AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee AS DOUBLE), 0)"
    " + COALESCE(CAST(t.buyback_fee AS DOUBLE), 0))"
)


def build(pairs: pd.DataFrame, k: int = 20) -> str:
    vals = ",\n".join(
        f"        ('{u}', '{e}')" for u, e in zip(pairs.usr, pairs.entity)
    )
    return f"""/* DQ-26 第一步·G1b 抽样；由 sql/build_sample_sql.py 生成。前 50 个实体的钱包 {len(pairs)} 个，
   每个实体抽 {k} 笔成交交易（xxhash64(tx_id||'20261001') 排序）。只读 {R0}～{CUT} 的分区。 */
WITH
sel(usr, entity) AS (
    SELECT usr, entity FROM (VALUES
{vals}
    ) AS v(usr, entity)
),
rm AS (
    SELECT DISTINCT mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{R0}' AND DATE '{R1}'
),
ev AS (
    SELECT
        t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr, t.evt_block_time AS ts,
        'curve' AS src,
        IF(COALESCE(t.is_buy, t.isBuy), -({SOL_RAW} + {FEE_EVT}), {SOL_RAW} - {FEE_EVT}) / 1e9 AS sol_cash,
        0.0 AS usd_other
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '{R0}' AND DATE '{CUT}'
      AND CAST(t."user" AS varchar) IN (SELECT usr FROM sel)
      AND CAST(t."user" AS varchar) = t.evt_tx_signer
      AND t.mint IN (SELECT mint FROM rm)
    UNION ALL
    SELECT
        d.tx_id, d.trader_id, d.block_time, d.project,
        IF(d.token_bought_mint_address IN (SELECT mint FROM rm) AND d.token_sold_mint_address IN ({SOL_MINTS}),
           -d.token_sold_amount, 0)
        + IF(d.token_sold_mint_address IN (SELECT mint FROM rm) AND d.token_bought_mint_address IN ({SOL_MINTS}),
           d.token_bought_amount, 0),
        IF(d.token_bought_mint_address IN ({SOL_MINTS}) OR d.token_sold_mint_address IN ({SOL_MINTS}),
           0.0, COALESCE(d.amount_usd, 0))
    FROM dex_solana.trades d
    WHERE d.block_month = DATE '2026-08-01'
      AND d.block_date BETWEEN DATE '{R0}' AND DATE '{CUT}'
      AND d.project <> 'pumpdotfun'
      AND d.trader_id IN (SELECT usr FROM sel)
      AND (d.token_bought_mint_address IN (SELECT mint FROM rm)
           OR d.token_sold_mint_address IN (SELECT mint FROM rm))
),
tx AS (
    SELECT
        e.tx_id, e.usr, s.entity, min(e.ts) AS ts,
        sum(e.sol_cash) AS sol_cash, sum(e.usd_other) AS usd_other,
        array_join(array_agg(DISTINCT e.src), ',') AS srcs, count(*) AS n_ev
    FROM ev e
    JOIN sel s ON s.usr = e.usr
    GROUP BY 1, 2, 3
),
r AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY entity ORDER BY xxhash64(to_utf8(tx_id || '20261001')), tx_id
        ) AS rk
    FROM tx
)
SELECT tx_id, usr, entity, ts, sol_cash, usd_other, srcs, n_ev
FROM r
WHERE rk <= {k}
"""


def main() -> None:
    pairs = pd.read_csv(sys.argv[1])[["usr", "entity"]]
    sql = build(pairs)
    sqlglot.parse_one(sql, read="trino")
    dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
    assert dates[0] >= "2026-08-01" and dates[-1] <= CUT, dates
    out = H / "SAMPLE_G1B_R.sql"
    out.write_text(sql)
    h = hashlib.sha256(out.read_bytes()).hexdigest()
    with open(H / "sha256.txt", "a") as fh:
        fh.write(f"{out.name} {h}\n")
    print(out.name, h[:12], len(sql))


if __name__ == "__main__":
    main()
