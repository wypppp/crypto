"""DQ-20 第 0 段 Q0a：A 周早买履历（只看 A 周，不碰 B 周）。

输出每个钱包（A 周早买过 ≥3 个币）的：早买币数、实际命中（24 小时 ≥10× 赢家）、期望命中（按买入时状态格的赢家率之和）、
狙击/同槽画像。期望命中的格 = 币龄档 × 曲线进度档 × 此前累计买入额档（卡片 v2 §4，档位在此固定）。
为控制下载量：实际命中 = 0 的钱包按地址哈希保留 1/4（本地按 ×4 还原其在“预期幸运入选数”中的权重）。

python make_q0a.py  → sql/Q0a_A_wallet_history.sql
"""
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
winners = pd.read_csv(H / "raw" / "A_winners_24h.csv").mint.tolist()
vals = ",\n        ".join(f"('{m}')" for m in winners)

SQL = f"""/* DQ-20 第 0 段 Q0a：A 周早买履历。生成：make_q0a.py。只看 A 周（创建于 2026-06-01 00:00 至 06-06 23:29:59 UTC 的 SOL 币）。
   平台单次费用上限：40 credits（请在 Dune 网页设置；本 SQL 无法自行停机）。
   早买 = 创建后 30 分钟内、≥0.1 SOL、非创建者的买入（曲线 TradeEvent + pump 创建的 PumpSwap 池 BuyEvent）。
   赢家 = F3 面板中入场（+30 分钟）后 24 小时内路径最高 ≥10× 的币（{len(winners)} 个，VALUES 传入）。
   格：币龄 [0,2)/[2,10)/[10,60)/[60,300)/[300,1800) 秒 × 曲线 real_sol_reserves [0,1)/[1,5)/[5,20)/[20,60)/≥60 SOL（池买入单列 P）
       × 此前累计买入额（全部买家，含 <0.1 SOL 与创建者）[0,1)/[1,10)/[10,50)/≥50 SOL。
   每个 (钱包, 币) 只取第一笔合格早买。重扫描链：tradeevent 与 buyevent 各只扫描一次；小表 createevent/createpoolevent 可多次引用。 */
WITH
cohort AS (
    SELECT mint, min(evt_block_time) AS created_at, min(evt_block_slot) AS created_slot,
           max(CAST("user" AS varchar)) AS dev, max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-06'
    GROUP BY 1
),
sol AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
      AND created_at < TIMESTAMP '2026-06-06 23:30:00'
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
      AND base_mint IN (SELECT mint FROM sol)
      AND evt_outer_executing_account = '{PUMP}' AND index = 0
    GROUP BY 1
),
win AS (
    SELECT mint FROM (VALUES
        {vals}
    ) AS v(mint)
),
buys AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           t.evt_inner_instruction_index AS iix, CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt,
           CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr, 0 AS venue
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.mint IN (SELECT mint FROM sol)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, e.evt_inner_instruction_index,
           CAST(e."user" AS varchar), CAST(e.quote_amount_in AS DOUBLE) / 1e9, CAST(NULL AS DOUBLE), 1
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
),
early AS (
    SELECT b.*, s.dev, date_diff('millisecond', s.created_at, b.ts) / 1000.0 AS age_s,
           b.slot = s.created_slot AS in_create_slot
    FROM buys b
    JOIN sol s ON s.mint = b.mint
    WHERE b.ts >= s.created_at AND b.ts < s.created_at + INTERVAL '30' MINUTE
),
cum AS (
    SELECT *,
           COALESCE(sum(sol_amt) OVER (PARTITION BY mint ORDER BY slot, txi, iix
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prior_sol
    FROM early
),
firsts AS (
    SELECT *, row_number() OVER (PARTITION BY usr, mint ORDER BY slot, txi, iix) AS rn
    FROM cum
    WHERE sol_amt >= 0.1 AND usr <> dev AND usr IS NOT NULL
),
cells AS (
    SELECT f.usr, f.mint, f.ts, f.sol_amt, f.age_s, f.in_create_slot,
           CASE WHEN f.age_s < 2 THEN 'a0' WHEN f.age_s < 10 THEN 'a1' WHEN f.age_s < 60 THEN 'a2'
                WHEN f.age_s < 300 THEN 'a3' ELSE 'a4' END
           || CASE WHEN f.venue = 1 THEN 'P' WHEN f.xr < 1 THEN 'x0' WHEN f.xr < 5 THEN 'x1' WHEN f.xr < 20 THEN 'x2'
                   WHEN f.xr < 60 THEN 'x3' ELSE 'x4' END
           || CASE WHEN f.prior_sol < 1 THEN 'c0' WHEN f.prior_sol < 10 THEN 'c1' WHEN f.prior_sol < 50 THEN 'c2'
                   ELSE 'c3' END AS cell,
           CASE WHEN w.mint IS NOT NULL THEN 1 ELSE 0 END AS hit
    FROM firsts f
    LEFT JOIN win w ON w.mint = f.mint
    WHERE f.rn = 1
),
rated AS (
    SELECT *, avg(CAST(hit AS DOUBLE)) OVER (PARTITION BY cell) AS cell_rate,
           count(*) OVER (PARTITION BY cell) AS cell_n
    FROM cells
),
per_wallet AS (
    SELECT usr,
           count(*) AS n_coins,
           sum(hit) AS obs,
           sum(cell_rate) AS expct,
           sum(sol_amt) AS sol_total,
           count_if(age_s < 2) AS n_age_lt2s,
           count_if(in_create_slot) AS n_create_slot,
           count(DISTINCT date(ts)) AS n_days,
           min(ts) AS first_ts, max(ts) AS last_ts,
           array_join(array_agg(CASE WHEN hit = 1 THEN mint END) FILTER (WHERE hit = 1), ',') AS hit_mints,
           min(cell_n) AS min_cell_n
    FROM rated
    GROUP BY 1
)
SELECT *
FROM per_wallet
WHERE n_coins >= 3
  AND (obs >= 1 OR mod(from_big_endian_64(xxhash64(to_utf8(usr))), 4) = 0)
ORDER BY obs DESC, expct
"""

if __name__ == "__main__":
    (H / "sql").mkdir(exist_ok=True)
    (H / "sql" / "Q0a_A_wallet_history.sql").write_text(SQL)
    print("winners", len(winners), "chars", len(SQL))
