"""DQ-20 第 1 段 Q1（卡片 v3 §6）：历史窗口 + B 周一次扫描，按 B 周币汇总买家构成、合格钱包与安慰剂买入。

python make_q1.py → sql/Q1_B_signals.sql
"""
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
W = pd.read_csv(H / "raw" / "W_final.csv").usr.tolist()
P = pd.read_csv(H / "raw" / "placebo_draws.csv")
wvals = ",\n        ".join(f"('{u}', {i})" for i, u in enumerate(W))
pvals = ",\n        ".join(f"('{r.usr}', {int(r.w_idx)}, {int(r.draw)})" for r in P.itertuples())

SQL = f"""/* DQ-20 第 1 段 Q1（卡片_v3.md）。生成：make_q1.py。平台单次费用上限：40 credits（请在 Dune 网页设置）。
   历史窗口：2026-05-21 00:00 至 06-06 23:29:59 创建；B 周：06-08 00:00 至 06-14 23:59:59 创建（SOL 币）。
   早买 = 创建后 30 分钟内、≥0.1 SOL、非创建者（曲线 + pump 创建的 PumpSwap 池）；每个（钱包, 币）取第一笔。
   h(w) = 钱包在历史窗口早买过的不同币数（只用 B 周之前的数据）。输出：每个有早买的 B 周币一行。
   重扫描链：tradeevent 与 buyevent 各扫描一次（05-21 至 06-15）；扫描 06-15 只为覆盖 06-14 深夜创建的币，结果只含 B 周币。 */
WITH
cohort AS (
    SELECT mint, min(evt_block_time) AS created_at, max(CAST("user" AS varchar)) AS dev, max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-14'
    GROUP BY 1
),
sol AS (
    SELECT mint, created_at, dev,
           CASE WHEN created_at < TIMESTAMP '2026-06-06 23:30:00' THEN 'H'
                WHEN created_at >= TIMESTAMP '2026-06-08 00:00:00' THEN 'B' END AS period
    FROM cohort
    WHERE (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
      AND (created_at < TIMESTAMP '2026-06-06 23:30:00' OR created_at >= TIMESTAMP '2026-06-08 00:00:00')
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-15'
      AND base_mint IN (SELECT mint FROM sol)
      AND evt_outer_executing_account = '{PUMP}' AND index = 0
    GROUP BY 1
),
wl AS (
    SELECT usr, w_idx FROM (VALUES
        {wvals}
    ) AS v(usr, w_idx)
),
pl AS (
    SELECT usr, w_idx, draw FROM (VALUES
        {pvals}
    ) AS v(usr, w_idx, draw)
),
buys AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           COALESCE(t.evt_inner_instruction_index, 0) AS iix, CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-15'
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.mint IN (SELECT mint FROM sol)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, COALESCE(e.evt_inner_instruction_index, 0),
           CAST(e."user" AS varchar), CAST(e.quote_amount_in AS DOUBLE) / 1e9
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-15'
),
early AS (
    SELECT b.*, s.period, s.created_at, s.dev,
           row_number() OVER (PARTITION BY b.usr, b.mint ORDER BY b.slot, b.txi, b.iix) AS rn
    FROM buys b
    JOIN sol s ON s.mint = b.mint
    WHERE b.ts >= s.created_at AND b.ts < s.created_at + INTERVAL '30' MINUTE
      AND b.sol_amt >= 0.1 AND b.usr <> s.dev AND b.usr IS NOT NULL
),
hist AS (
    SELECT *, sum(CASE WHEN period = 'H' THEN 1 ELSE 0 END) OVER (PARTITION BY usr) AS h
    FROM early
    WHERE rn = 1
),
bw AS (
    SELECT x.mint, x.usr, x.ts, x.slot, x.sol_amt, x.h, x.created_at,
           w.w_idx AS w_idx, p.draw AS pdraw
    FROM hist x
    LEFT JOIN wl w ON w.usr = x.usr
    LEFT JOIN pl p ON p.usr = x.usr
    WHERE x.period = 'B'
)
SELECT mint,
       min(created_at) AS created_at,
       count(DISTINCT usr) AS n_buyers,
       sum(sol_amt) AS sol_total,
       count(DISTINCT CASE WHEN h >= 30 THEN usr END) AS n_hi30,
       count(DISTINCT CASE WHEN h >= 10 THEN usr END) AS n_hi10,
       count(DISTINCT CASE WHEN h = 0 THEN usr END) AS n_new,
       sum(CASE WHEN h >= 30 THEN sol_amt ELSE 0 END) AS sol_hi30,
       array_join(array_distinct(array_agg(CAST(w_idx AS varchar)) FILTER (WHERE w_idx IS NOT NULL)), ',') AS w_idx_list,
       min(CASE WHEN w_idx IS NOT NULL THEN ts END) AS w_first_ts,
       array_join(array_distinct(array_agg(CAST(pdraw AS varchar)) FILTER (WHERE pdraw IS NOT NULL)), ',') AS placebo_draws
FROM bw
GROUP BY 1
"""

if __name__ == "__main__":
    (H / "sql" / "Q1_B_signals.sql").write_text(SQL)
    print("chars", len(SQL))
