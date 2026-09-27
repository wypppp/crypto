"""DQ-21 §7 早买名单 SQL（v1.2）：sample.csv 中 105 个不同币的创建者与全部早买者。

早买者沿用 DQ-20：创建后 30 分钟内、>=0.1 SOL、非创建者（曲线 + pump 创建的 PumpSwap 池）；每个（钱包, 币）取第一笔。
输出两类行：kind='create'（创建者、创建时刻、创建交易）；kind='buy'（每个早买者的首笔，含时间顺序 buyer_rank 与当时价格）。
价格只用于 §8 的“首次可观察时刻”描述，不算收益。

python make_q_buyers.py → Q_buyers.sql（Dune 网页运行，平台单次上限 10 credits）
"""
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
mints = sorted(pd.read_csv(H / "sample.csv").mint.unique())
vals = ",\n        ".join(f"('{m}')" for m in mints)

SQL = f"""/* DQ-21 R0 早买名单（README v1.2 §7）。生成：make_q_buyers.py。平台单次费用上限：10 credits（请在 Dune 网页设置）。
   {len(mints)} 个 A/B 周样本币（06-01～06-14 创建），不触碰封存周（06-15 起创建的币）；成交扫描到 06-15 只为覆盖 06-14 深夜创建的币的前 30 分钟。
   早买 = 创建后 30 分钟内、>=0.1 SOL、非创建者（曲线 + pump 创建的 PumpSwap 池）；每个（钱包, 币）取第一笔。 */
WITH
s AS (
    SELECT mint FROM (VALUES
        {vals}
    ) AS v(mint)
),
cohort AS (
    SELECT mint, min(evt_block_time) AS created_at, min(evt_block_slot) AS create_slot,
           min_by(evt_tx_id, evt_block_slot) AS create_tx, max(CAST("user" AS varchar)) AS dev
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'
      AND mint IN (SELECT mint FROM s)
    GROUP BY 1
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-15'
      AND base_mint IN (SELECT mint FROM s)
      AND evt_outer_executing_account = '{PUMP}' AND index = 0
    GROUP BY 1
),
buys AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           COALESCE(t.evt_inner_instruction_index, 0) AS iix, t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt, 'curve' AS venue,
           (CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9)
             / NULLIF(CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6, 0) AS price
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-15'
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.mint IN (SELECT mint FROM s)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, COALESCE(e.evt_inner_instruction_index, 0),
           e.evt_tx_id, CAST(e."user" AS varchar), CAST(e.quote_amount_in AS DOUBLE) / 1e9, 'pumpswap',
           (CAST(e.pool_quote_token_reserves AS DOUBLE) / 1e9) / NULLIF(CAST(e.pool_base_token_reserves AS DOUBLE) / 1e6, 0)
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-15'
),
early AS (
    SELECT b.*, c.created_at,
           row_number() OVER (PARTITION BY b.usr, b.mint ORDER BY b.slot, b.txi, b.iix) AS rn
    FROM buys b
    JOIN cohort c ON c.mint = b.mint
    WHERE b.ts >= c.created_at AND b.ts < c.created_at + INTERVAL '30' MINUTE
      AND b.sol_amt >= 0.1 AND b.usr <> c.dev AND b.usr IS NOT NULL
),
firsts AS (
    SELECT *, row_number() OVER (PARTITION BY mint ORDER BY slot, txi, iix) AS buyer_rank,
           count(*) OVER (PARTITION BY mint) AS n_early
    FROM early
    WHERE rn = 1
)
SELECT 'create' AS kind, mint, dev AS usr, created_at AS ts, create_slot AS slot, CAST(NULL AS BIGINT) AS txi,
       CAST(NULL AS BIGINT) AS iix, create_tx AS tx_id, CAST(NULL AS DOUBLE) AS sol_amt, CAST(NULL AS VARCHAR) AS venue,
       CAST(NULL AS DOUBLE) AS price, CAST(NULL AS BIGINT) AS buyer_rank, CAST(NULL AS BIGINT) AS n_early
FROM cohort
UNION ALL
SELECT 'buy', mint, usr, ts, slot, CAST(txi AS BIGINT), CAST(iix AS BIGINT), tx_id, sol_amt, venue, price,
       buyer_rank, n_early
FROM firsts
"""

if __name__ == "__main__":
    (H / "Q_buyers.sql").write_text(SQL)
    print("mints", len(mints), "chars", len(SQL))
