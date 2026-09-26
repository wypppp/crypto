"""DQ-20 第 0 段 Q0c：履历窗口拉长到 2026-05-21 00:00 至 06-06 23:29:59（用户 09-26 确认；B 周仍不触碰）。

与 Q0a 相同的早买、格与输出口径；赢家标签改在 Dune 上计算：
  p30 = 创建后 30 分钟之前最后一笔成交的价格（曲线用交易后虚拟储备；池用事件中的池储备）；
  max24 = [创建 +30 分钟, +30 分钟 +24 小时) 内成交价的最高值；赢家 = max24 / p30 ≥ 10。
对账：每个钱包另输出 A 周（06-01 起创建）部分的币数、按 Dune 标签的命中、按 F3 名单（96 个）的命中。

python make_q0c.py  → sql/Q0c_history_0521_0606.sql
"""
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
f3 = pd.read_csv(H / "raw" / "A_winners_24h.csv").mint.tolist()
vals = ",\n        ".join(f"('{m}')" for m in f3)
D0, D1, DSCAN = "2026-05-21", "2026-06-06", "2026-06-08"

SQL = f"""/* DQ-20 第 0 段 Q0c：履历窗口 {D0} 00:00 至 {D1} 23:29:59 UTC 创建的 SOL 币。生成：make_q0c.py。B 周不触碰。
   平台单次费用上限：40 credits（请在 Dune 网页设置；本 SQL 无法自行停机）。
   早买、格、输出口径同 Q0a（make_q0a.py）。赢家标签在本查询内计算：max(+30 分钟后 24 小时内成交价) / (+30 分钟前最后一笔成交价) ≥ 10。
   只保留创建后 24.5 小时内的成交。重扫描链：tradeevent、buyevent、sellevent 各只扫描一次；小表 createevent/createpoolevent 可多次引用。 */
WITH
cohort AS (
    SELECT mint, min(evt_block_time) AS created_at, min(evt_block_slot) AS created_slot,
           max(CAST("user" AS varchar)) AS dev, max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{D0}' AND DATE '{D1}'
    GROUP BY 1
),
sol AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
      AND created_at < TIMESTAMP '{D1} 23:30:00'
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '{D0}' AND DATE '{DSCAN}'
      AND base_mint IN (SELECT mint FROM sol)
      AND evt_outer_executing_account = '{PUMP}' AND index = 0
    GROUP BY 1
),
f3win AS (
    SELECT mint FROM (VALUES
        {vals}
    ) AS v(mint)
),
tr AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           COALESCE(t.evt_inner_instruction_index, 0) AS iix, CAST(t."user" AS varchar) AS usr,
           COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt,
           CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr,
           (CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9)
             / NULLIF(CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6, 0) AS price,
           0 AS venue
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '{D0}' AND DATE '{DSCAN}'
      AND t.mint IN (SELECT mint FROM sol)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, COALESCE(e.evt_inner_instruction_index, 0),
           CAST(e."user" AS varchar), true, CAST(e.quote_amount_in AS DOUBLE) / 1e9, CAST(NULL AS DOUBLE),
           (CAST(e.pool_quote_token_reserves AS DOUBLE) / 1e9) / NULLIF(CAST(e.pool_base_token_reserves AS DOUBLE) / 1e6, 0), 1
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '{D0}' AND DATE '{DSCAN}'
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, COALESCE(e.evt_inner_instruction_index, 0),
           CAST(e."user" AS varchar), false, CAST(e.quote_amount_out AS DOUBLE) / 1e9, CAST(NULL AS DOUBLE),
           (CAST(e.pool_quote_token_reserves AS DOUBLE) / 1e9) / NULLIF(CAST(e.pool_base_token_reserves AS DOUBLE) / 1e6, 0), 1
    FROM pumpdotfun_solana.pump_amm_evt_sellevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '{D0}' AND DATE '{DSCAN}'
),
win AS (
    SELECT r.*, s.dev, s.created_at, s.created_slot,
           s.created_at + INTERVAL '30' MINUTE AS c30,
           CAST(r.slot AS DOUBLE) * 1e6 + CAST(r.txi AS DOUBLE) * 1e2 + CAST(r.iix AS DOUBLE) AS ord
    FROM tr r
    JOIN sol s ON s.mint = r.mint
    WHERE r.ts >= s.created_at AND r.ts < s.created_at + INTERVAL '1470' MINUTE
),
lab AS (
    SELECT *,
           max_by(CASE WHEN ts < c30 THEN price END, CASE WHEN ts < c30 THEN ord END) OVER (PARTITION BY mint) AS p30,
           max(CASE WHEN ts >= c30 THEN price END) OVER (PARTITION BY mint) AS max24,
           COALESCE(sum(CASE WHEN ts < c30 AND is_buy THEN sol_amt END)
                    OVER (PARTITION BY mint ORDER BY slot, txi, iix ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prior_sol
    FROM win
),
firsts AS (
    SELECT *, row_number() OVER (PARTITION BY usr, mint ORDER BY slot, txi, iix) AS rn
    FROM lab
    WHERE ts < c30 AND is_buy AND sol_amt >= 0.1 AND usr <> dev AND usr IS NOT NULL
),
cells AS (
    SELECT f.usr, f.mint, f.ts, f.sol_amt, f.created_at,
           date_diff('millisecond', f.created_at, f.ts) / 1000.0 AS age_s,
           f.slot = f.created_slot AS in_create_slot,
           CASE WHEN date_diff('millisecond', f.created_at, f.ts) < 2000 THEN 'a0'
                WHEN date_diff('millisecond', f.created_at, f.ts) < 10000 THEN 'a1'
                WHEN date_diff('millisecond', f.created_at, f.ts) < 60000 THEN 'a2'
                WHEN date_diff('millisecond', f.created_at, f.ts) < 300000 THEN 'a3' ELSE 'a4' END
           || CASE WHEN f.venue = 1 THEN 'P' WHEN f.xr < 1 THEN 'x0' WHEN f.xr < 5 THEN 'x1' WHEN f.xr < 20 THEN 'x2'
                   WHEN f.xr < 60 THEN 'x3' ELSE 'x4' END
           || CASE WHEN f.prior_sol < 1 THEN 'c0' WHEN f.prior_sol < 10 THEN 'c1' WHEN f.prior_sol < 50 THEN 'c2'
                   ELSE 'c3' END AS cell,
           CASE WHEN f.p30 > 0 AND f.max24 / f.p30 >= 10 THEN 1 ELSE 0 END AS hit,
           CASE WHEN w.mint IS NOT NULL THEN 1 ELSE 0 END AS hit_f3
    FROM firsts f
    LEFT JOIN f3win w ON w.mint = f.mint
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
           count_if(created_at >= TIMESTAMP '2026-06-01 00:00:00') AS n_coins_a,
           sum(CASE WHEN created_at >= TIMESTAMP '2026-06-01 00:00:00' THEN hit ELSE 0 END) AS obs_a,
           sum(CASE WHEN created_at >= TIMESTAMP '2026-06-01 00:00:00' THEN hit_f3 ELSE 0 END) AS obs_a_f3,
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
    (H / "sql" / "Q0c_history_0521_0606.sql").write_text(SQL)
    print("chars", len(SQL))
