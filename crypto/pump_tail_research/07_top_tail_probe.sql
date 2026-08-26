WITH trades AS (
    SELECT 'buy' AS side, evt_block_time, evt_block_slot, evt_tx_index,
        evt_inner_instruction_index, evt_tx_id, user,
        CAST(pool_base_token_reserves AS DOUBLE) / 1e6 AS base_reserve,
        CAST(pool_quote_token_reserves AS DOUBLE) / 1e9 AS quote_reserve,
        CAST(user_quote_amount_in AS DOUBLE) / 1e9 AS user_quote_amount
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date BETWEEN DATE '2026-07-04' AND DATE '2026-08-03'
      AND pool = 'CF1wLU1mF9KkMgv8LDL6KQwL8cvXVCLGtN4meYwevDJb'
    UNION ALL
    SELECT 'sell' AS side, evt_block_time, evt_block_slot, evt_tx_index,
        evt_inner_instruction_index, evt_tx_id, user,
        CAST(pool_base_token_reserves AS DOUBLE) / 1e6 AS base_reserve,
        CAST(pool_quote_token_reserves AS DOUBLE) / 1e9 AS quote_reserve,
        CAST(user_quote_amount_out AS DOUBLE) / 1e9 AS user_quote_amount
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date BETWEEN DATE '2026-07-04' AND DATE '2026-08-03'
      AND pool = 'CF1wLU1mF9KkMgv8LDL6KQwL8cvXVCLGtN4meYwevDJb'
)
SELECT *,
    quote_reserve / NULLIF(base_reserve, 0) AS spot_sol_per_token,
    quote_reserve / NULLIF(base_reserve, 0)
        / (0.080605135 / 206900000.0) AS multiple_from_graduation
FROM trades
ORDER BY multiple_from_graduation DESC
LIMIT 10
