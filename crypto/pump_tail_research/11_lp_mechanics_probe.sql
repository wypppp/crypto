-- Small, non-outcome probe to verify PumpSwap LP supply event semantics.
WITH canonical AS (
    SELECT
        evt_block_time, pool, base_mint AS mint,
        CAST(base_amount_in AS DOUBLE) AS base_amount_in,
        CAST(quote_amount_in AS DOUBLE) AS quote_amount_in,
        CAST(initial_liquidity AS DOUBLE) AS initial_liquidity,
        CAST(lp_token_amount_out AS DOUBLE) AS lp_token_amount_out,
        CAST(minimum_liquidity AS DOUBLE) AS minimum_liquidity
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date = DATE '2026-05-01'
      AND evt_outer_executing_account =
          '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    ORDER BY evt_block_time
    LIMIT 20
)
SELECT
    c.*,
    c.lp_token_amount_out + c.minimum_liquidity AS reconstructed_supply,
    c.initial_liquidity - c.lp_token_amount_out AS initial_minus_user_lp,
    min_by(CAST(d.lp_mint_supply AS DOUBLE), d.evt_block_time)
        AS first_deposit_post_supply,
    min_by(CAST(d.lp_token_amount_out AS DOUBLE), d.evt_block_time)
        AS first_deposit_lp_out,
    min_by(CAST(w.lp_mint_supply AS DOUBLE), w.evt_block_time)
        AS first_withdraw_post_supply,
    min_by(CAST(w.lp_token_amount_in AS DOUBLE), w.evt_block_time)
        AS first_withdraw_lp_in
FROM canonical c
LEFT JOIN pumpdotfun_solana.pump_amm_evt_depositevent d
    ON d.pool = c.pool
   AND d.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-08'
LEFT JOIN pumpdotfun_solana.pump_amm_evt_withdrawevent w
    ON w.pool = c.pool
   AND w.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-08'
GROUP BY 1,2,3,4,5,6,7,8
ORDER BY evt_block_time
