-- DQ-18 A 段普查（P1 主口径）：2024-05～2024-06
-- 生成器 make_census_a.py；口径同 S2_A_P1_202512_四口径验收.sql 的 p1 变体。
-- 只输出区间内每币每门槛的首个 P1 小时；不含信号后路径或收益。
-- 运行时在 Dune 设单条费用上限 100 credits（用户 09-24）。

WITH created AS (
    SELECT mint, MIN(evt_block_time) AS created_at
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date < DATE '2024-07-01'
    GROUP BY mint
), complete AS (
    SELECT mint, MIN(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date < DATE '2024-07-01'
    GROUP BY mint
), grads AS (
    SELECT c.mint, c.created_at, g.completed_at
    FROM created c JOIN complete g ON g.mint = c.mint
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd
    FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '2024-05-01 00:00:00'
      AND minute < TIMESTAMP '2024-07-01 00:00:00'
    GROUP BY minute
), month_trades AS (
    SELECT block_time,
           token_bought_mint_address, token_sold_mint_address,
           token_bought_amount, token_sold_amount
    FROM dex_solana.trades
    WHERE block_month >= DATE '2024-05-01' AND block_month < DATE '2024-07-01'
      AND block_time >= TIMESTAMP '2024-05-01 00:00:00'
      AND block_time < TIMESTAMP '2024-07-01 00:00:00'
      AND project <> 'pumpdotfun'
      AND token_bought_mint_address <> token_sold_mint_address
), legs AS (
    SELECT g.mint, g.created_at, g.completed_at, t.block_time,
           IF(t.token_bought_mint_address = g.mint,
              t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = g.mint,
              t.token_bought_amount, t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = g.mint,
              t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM month_trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address,
                            t.token_sold_mint_address]) AS leg(mint)
    JOIN grads g ON g.mint = leg.mint
    WHERE t.block_time >= g.completed_at
), valued AS (
    SELECT l.*,
           CASE
             WHEN l.quote_mint = 'So11111111111111111111111111111111111111112'
               THEN l.quote_amount * s.sol_usd
             WHEN l.quote_mint IN (
               'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
               'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB')
               THEN l.quote_amount
             ELSE NULL
           END AS quote_usd,
           CASE
             WHEN l.quote_mint = 'So11111111111111111111111111111111111111112'
               THEN l.quote_amount >= 0.001
             WHEN l.quote_mint IN (
               'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
               'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB')
               THEN l.quote_amount >= 0.10
             ELSE FALSE
           END AS size_ok
    FROM legs l
    LEFT JOIN sol_minute s
      ON l.quote_mint = 'So11111111111111111111111111111111111111112'
     AND s.minute = date_trunc('minute', l.block_time)
), p1 AS (
    SELECT * FROM valued
    WHERE token_amount > 0 AND quote_usd > 0 AND size_ok
), hourly AS (
    SELECT mint, MIN(created_at) AS created_at, MIN(completed_at) AS completed_at,
           date_trunc('hour', block_time) AS hour_start,
           COUNT(*) AS n_p1_valid,
           SUM(token_amount) AS p1_token_volume,
           SUM(quote_usd) AS p1_usd_volume,
           array_sort(array_agg(quote_usd / token_amount)) AS p1_prices_sorted
    FROM p1
    GROUP BY mint, date_trunc('hour', block_time)
), priced_hours AS (
    SELECT mint, created_at, completed_at, hour_start, n_p1_valid, p1_usd_volume,
           1000000000.0 * p1_usd_volume / NULLIF(p1_token_volume, 0) AS p1_vwap_cap_usd,
           1000000000.0 * (
             element_at(p1_prices_sorted,
                 CAST(floor((cardinality(p1_prices_sorted) + 1) / 2.0) AS BIGINT))
             + element_at(p1_prices_sorted,
                 CAST(floor((cardinality(p1_prices_sorted) + 2) / 2.0) AS BIGINT))
           ) / 2.0 AS p1_median_cap_usd
    FROM hourly
    WHERE n_p1_valid >= 5 AND p1_usd_volume >= 100.0
), thresholds(threshold_usd) AS (
    VALUES (1000000.0), (5000000.0), (20000000.0), (100000000.0)
), crossing AS (
    SELECT h.*, t.threshold_usd,
           ROW_NUMBER() OVER (PARTITION BY h.mint, t.threshold_usd
                              ORDER BY h.hour_start) AS rk
    FROM priced_hours h CROSS JOIN thresholds t
    WHERE h.p1_vwap_cap_usd >= t.threshold_usd
      AND h.p1_median_cap_usd >= t.threshold_usd
)
SELECT mint, threshold_usd, created_at, completed_at,
       hour_start, hour_start + INTERVAL '1' HOUR AS signal_time,
       n_p1_valid, p1_usd_volume, p1_vwap_cap_usd, p1_median_cap_usd
FROM crossing
WHERE rk = 1
ORDER BY threshold_usd, mint
