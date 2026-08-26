SELECT
    evt_block_time,
    evt_tx_id,
    evt_outer_executing_account,
    pool,
    base_mint,
    quote_mint,
    typeof(base_amount_in) AS base_type,
    CAST(base_amount_in AS DOUBLE) AS base_raw,
    typeof(quote_amount_in) AS quote_type,
    CAST(quote_amount_in AS DOUBLE) AS quote_raw,
    base_mint_decimals,
    quote_mint_decimals,
    is_mayhem_mode
FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
WHERE evt_block_date BETWEEN DATE '2026-08-23' AND DATE '2026-08-24'
  AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
  AND index = 0
ORDER BY evt_block_slot DESC, evt_tx_index DESC, evt_inner_instruction_index DESC
LIMIT 5
