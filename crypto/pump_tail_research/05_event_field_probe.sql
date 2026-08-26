SELECT * FROM (
    SELECT
        'buy' AS side,
        evt_block_time,
        CAST(base_amount_out AS DOUBLE) AS base_amount,
        CAST(quote_amount_in AS DOUBLE) AS quote_core,
        CAST(quote_amount_in_with_lp_fee AS DOUBLE) AS quote_with_lp_fee,
        CAST(user_quote_amount_in AS DOUBLE) AS quote_user,
        CAST(pool_base_token_reserves AS DOUBLE) AS pool_base,
        CAST(pool_quote_token_reserves AS DOUBLE) AS pool_quote
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date = DATE '2026-07-09'
      AND pool = '9pju7scVfBaH7y6xD9jEvaAXzggu7CQyW5Pq5bxcHaMy'
    ORDER BY evt_block_slot, evt_tx_index, evt_inner_instruction_index
    LIMIT 5
)
UNION ALL
SELECT * FROM (
    SELECT
        'sell' AS side,
        evt_block_time,
        CAST(base_amount_in AS DOUBLE) AS base_amount,
        CAST(quote_amount_out AS DOUBLE) AS quote_core,
        CAST(quote_amount_out_without_lp_fee AS DOUBLE) AS quote_with_lp_fee,
        CAST(user_quote_amount_out AS DOUBLE) AS quote_user,
        CAST(pool_base_token_reserves AS DOUBLE) AS pool_base,
        CAST(pool_quote_token_reserves AS DOUBLE) AS pool_quote
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date = DATE '2026-07-09'
      AND pool = '9pju7scVfBaH7y6xD9jEvaAXzggu7CQyW5Pq5bxcHaMy'
    ORDER BY evt_block_slot, evt_tx_index, evt_inner_instruction_index
    LIMIT 5
)
