-- DQ-18 Step 2, December 2025 P1 acceptance. No returns or post-signal paths.
-- One dex_solana.trades month scan, four first-in-month price definitions.
-- Run with Dune per-query cost cap <= 50 credits. Do not download CSV in UI.
-- IMPORTANT: the frozen P1 taskbook asks both for original-rule comparison and
-- an early project <> 'pumpdotfun' scan filter. Those conflict: the original
-- rule includes curve trades. This query keeps the original once, and applies
-- the P1 project/graduation filter before P1 aggregation instead. The execution
-- cost therefore measures the combined acceptance query, not a P1-only scan.
-- Historical first crossing is NOT claimed here. This is December-only.

WITH created AS (
    SELECT mint, MIN(evt_block_time) AS created_at,
           MIN_BY(is_mayhem_mode, evt_block_time) AS is_mayhem_mode
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date < DATE '2026-01-01'
    GROUP BY mint
), complete AS (
    SELECT mint, MIN(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date < DATE '2026-01-01'
    GROUP BY mint
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd
    FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '2025-12-01 00:00:00'
      AND minute < TIMESTAMP '2026-01-01 00:00:00'
    GROUP BY minute
), month_trades AS (
    SELECT block_time, project,
           token_bought_mint_address, token_sold_mint_address,
           token_bought_amount, token_sold_amount
    FROM dex_solana.trades
    WHERE block_month = DATE '2025-12-01'
      AND block_time >= TIMESTAMP '2025-12-01 00:00:00'
      AND block_time < TIMESTAMP '2026-01-01 00:00:00'
      AND token_bought_mint_address <> token_sold_mint_address
), legs AS (
    SELECT c.mint, c.created_at, c.is_mayhem_mode, g.completed_at,
           t.block_time, t.project,
           IF(t.token_bought_mint_address = c.mint,
              t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = c.mint,
              t.token_bought_amount, t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = c.mint,
              t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM month_trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address,
                            t.token_sold_mint_address]) AS leg(mint)
    JOIN created c ON c.mint = leg.mint
    LEFT JOIN complete g ON g.mint = c.mint
    WHERE t.block_time >= c.created_at
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
), marked AS (
    SELECT *,
           token_amount > 0 AND quote_usd > 0 AS original_valid,
           token_amount > 0 AND quote_usd > 0
             AND project <> 'pumpdotfun'
             AND completed_at IS NOT NULL
             AND block_time >= completed_at AS graduated_valid,
           token_amount > 0 AND quote_usd > 0
             AND project <> 'pumpdotfun'
             AND completed_at IS NOT NULL
             AND block_time >= completed_at
             AND size_ok AS p1_valid
    FROM valued
), hourly AS (
    SELECT mint, MIN(created_at) AS created_at,
           MAX_BY(is_mayhem_mode, created_at) AS is_mayhem_mode,
           date_trunc('hour', block_time) AS hour_start,
           COUNT(*) AS n_all_trades,
           COUNT_IF(original_valid) AS n_original_valid,
           COUNT_IF(original_valid AND project = 'pumpdotfun') AS n_curve_valid,
           COUNT_IF(graduated_valid) AS n_graduated_before_size,
           COUNT_IF(p1_valid) AS n_p1_valid,
           SUM(IF(original_valid, token_amount, 0)) AS original_token_volume,
           SUM(IF(original_valid, quote_usd, 0)) AS original_usd_volume,
           SUM(IF(p1_valid, token_amount, 0)) AS p1_token_volume,
           SUM(IF(p1_valid, quote_usd, 0)) AS p1_usd_volume,
           array_sort(array_agg(quote_usd / NULLIF(token_amount, 0))
               FILTER (WHERE p1_valid)) AS p1_prices_sorted
    FROM marked
    GROUP BY mint, date_trunc('hour', block_time)
), priced_hours AS (
    SELECT *,
           1000000000.0 * original_usd_volume
             / NULLIF(original_token_volume, 0) AS original_cap_usd,
           1000000000.0 * p1_usd_volume
             / NULLIF(p1_token_volume, 0) AS p1_vwap_cap_usd,
           1000000000.0 * (
             element_at(p1_prices_sorted,
                 CAST(floor((cardinality(p1_prices_sorted) + 1) / 2.0) AS BIGINT))
             + element_at(p1_prices_sorted,
                 CAST(floor((cardinality(p1_prices_sorted) + 2) / 2.0) AS BIGINT))
           ) / 2.0 AS p1_median_cap_usd
    FROM hourly
), thresholds(threshold_usd) AS (
    VALUES (1000000.0), (5000000.0), (20000000.0), (100000000.0)
), variants(variant_name, min_trades, min_usd) AS (
    VALUES ('original', 0, 0.0),
           ('loose', 3, 20.0),
           ('p1', 5, 100.0),
           ('strict', 10, 1000.0)
), crossing AS (
    SELECT h.*, t.threshold_usd, v.variant_name,
           ROW_NUMBER() OVER (
             PARTITION BY h.mint, t.threshold_usd, v.variant_name
             ORDER BY h.hour_start
           ) AS rank_in_month
    FROM priced_hours h
    CROSS JOIN thresholds t
    CROSS JOIN variants v
    WHERE (v.variant_name = 'original'
               AND h.original_cap_usd >= t.threshold_usd)
       OR (v.variant_name <> 'original'
               AND h.n_p1_valid >= v.min_trades
               AND h.p1_usd_volume >= v.min_usd
               AND h.p1_vwap_cap_usd >= t.threshold_usd
               AND h.p1_median_cap_usd >= t.threshold_usd)
)
SELECT variant_name, mint, threshold_usd, created_at, is_mayhem_mode,
       hour_start, hour_start + INTERVAL '1' HOUR AS signal_time,
       n_all_trades, n_original_valid, original_usd_volume,
       original_cap_usd, n_curve_valid, n_graduated_before_size,
       n_p1_valid, p1_usd_volume, p1_vwap_cap_usd, p1_median_cap_usd
FROM crossing
WHERE rank_in_month = 1
ORDER BY variant_name, threshold_usd, mint
