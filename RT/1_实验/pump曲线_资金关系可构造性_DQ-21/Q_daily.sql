/* DQ-21 持续索引成本估算（过程/R0b_预算与门槛.md）。生成：make_q_daily.py。平台单次费用上限：5 credits（请在 Dune 网页设置）。
   B 周（06-08～06-14 创建）每天的早买钱包数，以及前 30 名中“此前 7 天从未进入前 30 名”的钱包数；05-31～06-07 只作回看。
   09-27 复核后修正：新旧按前 30 名的历史判断（原版按全部排名，会低估冷启动）。每个重 CTE 只引用一次。不触碰封存周。 */
WITH
cohort AS (
    SELECT mint, min(evt_block_time) AS created_at, max(CAST("user" AS varchar)) AS dev, max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-05-31' AND DATE '2026-06-14'
    GROUP BY 1
),
sol AS (
    SELECT mint, created_at, dev FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-05-31' AND DATE '2026-06-15'
      AND base_mint IN (SELECT mint FROM sol)
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0
    GROUP BY 1
),
buys AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           COALESCE(t.evt_inner_instruction_index, 0) AS iix, CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-05-31' AND DATE '2026-06-15'
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.mint IN (SELECT mint FROM sol)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, COALESCE(e.evt_inner_instruction_index, 0),
           CAST(e."user" AS varchar), CAST(e.quote_amount_in AS DOUBLE) / 1e9
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-05-31' AND DATE '2026-06-15'
),
early AS (
    SELECT b.mint, b.usr, b.slot, b.txi, b.iix, s.created_at,
           row_number() OVER (PARTITION BY b.usr, b.mint ORDER BY b.slot, b.txi, b.iix) AS rn
    FROM buys b
    JOIN sol s ON s.mint = b.mint
    WHERE b.ts >= s.created_at AND b.ts < s.created_at + INTERVAL '30' MINUTE
      AND b.sol_amt >= 0.1 AND b.usr <> s.dev AND b.usr IS NOT NULL
),
firsts AS (
    SELECT mint, usr, created_at, date(created_at) AS d,
           row_number() OVER (PARTITION BY mint ORDER BY slot, txi, iix) AS buyer_rank
    FROM early
    WHERE rn = 1
),
wd AS (
    SELECT usr, d, count(*) AS n_pairs, sum(CASE WHEN buyer_rank <= 30 THEN 1 ELSE 0 END) AS n_pairs_k30
    FROM firsts
    GROUP BY 1, 2
),
hist AS (
    SELECT w.*,
           max(CASE WHEN n_pairs_k30 > 0 THEN d END)
               OVER (PARTITION BY usr ORDER BY d ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_d_k30
    FROM wd w
)
SELECT d,
       sum(n_pairs) AS n_pairs,
       count(*) AS n_wallets,
       sum(n_pairs_k30) AS n_pairs_k30,
       sum(CASE WHEN n_pairs_k30 > 0 THEN 1 ELSE 0 END) AS n_wallets_k30,
       sum(CASE WHEN n_pairs_k30 > 0 AND (prev_d_k30 IS NULL OR prev_d_k30 < d - INTERVAL '7' DAY) THEN 1 ELSE 0 END) AS n_new_7d_k30,
       sum(CASE WHEN n_pairs_k30 > 0 AND prev_d_k30 = d - INTERVAL '1' DAY THEN 1 ELSE 0 END) AS n_back_1d_k30,
       sum(CASE WHEN n_pairs_k30 > 0 AND prev_d_k30 < d - INTERVAL '1' DAY AND prev_d_k30 >= d - INTERVAL '7' DAY THEN 1 ELSE 0 END) AS n_back_2to7d_k30
FROM hist
WHERE d BETWEEN DATE '2026-06-08' AND DATE '2026-06-14'
GROUP BY 1
ORDER BY 1
