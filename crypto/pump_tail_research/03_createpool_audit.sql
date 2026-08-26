SELECT
    quote_mint,
    count(*) AS rows,
    count(DISTINCT base_mint) AS unique_mints,
    count(DISTINCT pool) AS unique_pools,
    min(evt_block_time) AS first_graduation,
    max(evt_block_time) AS last_graduation,
    count_if(is_mayhem_mode) AS mayhem_true,
    count_if(NOT is_mayhem_mode) AS mayhem_false,
    count_if(is_mayhem_mode IS NULL) AS mayhem_null,
    approx_percentile(
        CAST(quote_amount_in AS DOUBLE) / power(10, quote_mint_decimals), 0.5
    ) AS quote_reserve_p50_display,
    min(CAST(quote_amount_in AS DOUBLE) / power(10, quote_mint_decimals))
        AS quote_reserve_min_display,
    max(CAST(quote_amount_in AS DOUBLE) / power(10, quote_mint_decimals))
        AS quote_reserve_max_display
FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
WHERE evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-24'
  AND evt_block_time >= TIMESTAMP '2026-05-01 00:00:00'
  AND evt_block_time < TIMESTAMP '2026-07-25 00:00:00'
  AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
  AND index = 0
GROUP BY 1
ORDER BY rows DESC
