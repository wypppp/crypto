WITH migrations AS (
    SELECT evt_block_time AS graduated_at, evt_tx_id,
        evt_outer_instruction_index, mint, pool, quote_mint
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-24'
      AND evt_block_time >= TIMESTAMP '2026-05-01 00:00:00'
      AND evt_block_time < TIMESTAMP '2026-07-25 00:00:00'
),
creates AS (
    SELECT evt_tx_id, evt_outer_instruction_index, pool, base_mint, quote_mint,
        is_mayhem_mode,
        CAST(quote_amount_in AS DOUBLE) / power(10, quote_mint_decimals)
            AS initial_quote_reserve
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-24'
      AND evt_block_time >= TIMESTAMP '2026-05-01 00:00:00'
      AND evt_block_time < TIMESTAMP '2026-07-25 00:00:00'
      AND index = 0
),
matched AS (
    SELECT m.*, c.is_mayhem_mode, c.initial_quote_reserve
    FROM migrations m
    INNER JOIN creates c
        ON c.evt_tx_id = m.evt_tx_id
       AND c.evt_outer_instruction_index = m.evt_outer_instruction_index
       AND c.pool = m.pool
       AND c.base_mint = m.mint
       AND c.quote_mint = m.quote_mint
)
SELECT count(*) AS matched_rows, count(DISTINCT mint) AS n0_unique_mints,
    count(DISTINCT pool) AS unique_pools, min(graduated_at) AS first_graduation,
    max(graduated_at) AS last_graduation, count_if(is_mayhem_mode) AS mayhem_count,
    count_if(NOT is_mayhem_mode) AS standard_count,
    count(DISTINCT quote_mint) AS quote_mint_count,
    approx_percentile(initial_quote_reserve, 0.5) AS quote_reserve_p50_display,
    min(initial_quote_reserve) AS quote_reserve_min_display,
    max(initial_quote_reserve) AS quote_reserve_max_display
FROM matched
