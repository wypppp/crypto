-- DQ-1 · A：pump_evt_tradeevent 新旧字段在抽样日的覆盖、单位与 quote_mint 取值
-- 只扫 6 个单日分区；不读取任何价格结局。
SELECT
    evt_block_date AS day,
    count(*) AS rows_total,
    count(DISTINCT mint) AS mints,
    count(sol_amount) AS n_sol_amount,
    count(solAmount) AS n_solAmount_camel,
    count(virtual_sol_reserves) AS n_virtual_sol_reserves,
    count(virtualSolReserves) AS n_virtualSolReserves_camel,
    count(real_sol_reserves) AS n_real_sol_reserves,
    count(virtual_token_reserves) AS n_virtual_token_reserves,
    count(virtualTokenReserves) AS n_virtualTokenReserves_camel,
    count(real_token_reserves) AS n_real_token_reserves,
    count(is_buy) AS n_is_buy,
    count(isBuy) AS n_isBuy_camel,
    count(quote_mint) AS n_quote_mint,
    count(quote_amount) AS n_quote_amount,
    count(ix_name) AS n_ix_name,
    count_if(virtual_sol_reserves IS NULL AND virtualSolReserves IS NULL) AS n_no_virtual_sol_any,
    count_if(real_sol_reserves IS NULL) AS n_no_real_sol,
    count_if(quote_mint = '11111111111111111111111111111111') AS n_quote_default,
    count_if(quote_mint = 'So11111111111111111111111111111111111111112') AS n_quote_wsol,
    count_if(quote_mint = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v') AS n_quote_usdc,
    count_if(quote_mint IS NOT NULL
             AND quote_mint NOT IN ('11111111111111111111111111111111',
                                    'So11111111111111111111111111111111111111112',
                                    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v')) AS n_quote_other,
    count_if(quote_amount IS NOT NULL AND sol_amount IS NOT NULL
             AND quote_amount <> sol_amount) AS n_quote_amount_ne_sol_amount,
    array_join(slice(array_agg(DISTINCT quote_mint), 1, 6), ',') AS quote_mint_values,
    array_join(slice(array_agg(DISTINCT ix_name), 1, 8), ',') AS ix_name_values,
    approx_percentile(CAST(COALESCE(virtual_sol_reserves, virtualSolReserves) AS DOUBLE), 0.01) / 1e9 AS vsr_p01_div1e9,
    approx_percentile(CAST(COALESCE(virtual_sol_reserves, virtualSolReserves) AS DOUBLE), 0.50) / 1e9 AS vsr_p50_div1e9,
    max(CAST(COALESCE(virtual_sol_reserves, virtualSolReserves) AS DOUBLE)) / 1e9 AS vsr_max_div1e9,
    approx_percentile(CAST(COALESCE(virtual_token_reserves, virtualTokenReserves) AS DOUBLE), 0.50) / 1e6 AS vtr_p50_div1e6,
    approx_percentile(CAST(real_sol_reserves AS DOUBLE), 0.99) / 1e9 AS rsr_p99_div1e9,
    approx_percentile(CASE WHEN quote_mint = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
                           THEN CAST(virtual_sol_reserves AS DOUBLE) END, 0.50) AS usdc_coin_vsr_p50_raw,
    approx_percentile(CASE WHEN quote_mint = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
                           THEN CAST(quote_amount AS DOUBLE) END, 0.50) AS usdc_coin_quote_amount_p50_raw,
    count_if(evt_outer_executing_account ='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P') AS n_outer_is_pump,
    min(evt_block_time) AS first_time,
    max(evt_block_time) AS last_time
FROM pumpdotfun_solana.pump_evt_tradeevent
WHERE evt_block_date IN (DATE '2024-03-01', DATE '2024-09-01', DATE '2025-03-01',
                         DATE '2025-09-01', DATE '2026-03-01', DATE '2026-09-01')
GROUP BY 1
ORDER BY 1
