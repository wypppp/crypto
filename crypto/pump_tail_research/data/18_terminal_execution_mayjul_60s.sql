-- Event-ordered, executable-liquidation first-passage data for the frozen
-- T+5m15s experiment.  One row per entry-capacity-eligible token.

WITH
constants AS (
    SELECT
        TIMESTAMP '2026-05-01 00:00:00' AS cohort_start,
        TIMESTAMP '2026-07-25 00:00:00' AS cohort_end,
        'So11111111111111111111111111111111111111112' AS wsol_mint,
        'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' AS usdc_mint,
        100.0 AS execution_haircut_bps,
        100.0 AS missing_chain_fee_bps
),
price_hours AS (
    SELECT timestamp, contract_address, max(price) AS price_usd
    FROM prices_external.hour
    CROSS JOIN constants c
    WHERE blockchain = 'solana'
      AND timestamp >= TIMESTAMP '2026-05-01 00:00:00'
      AND timestamp < TIMESTAMP '2026-07-27 00:00:00'
      AND contract_address IN (from_base58(c.wsol_mint), from_base58(c.usdc_mint))
    GROUP BY 1, 2
),
create_ranked AS (
    SELECT
        evt_block_time AS graduated_at,
        evt_block_slot AS graduation_block_slot,
        evt_tx_index AS graduation_tx_index,
        evt_outer_instruction_index AS graduation_outer_index,
        evt_inner_instruction_index AS graduation_inner_index,
        evt_tx_id AS graduation_tx,
        pool,
        base_mint AS mint,
        quote_mint,
        base_mint_decimals AS base_decimals,
        quote_mint_decimals AS quote_decimals,
        CAST(base_amount_in AS DOUBLE) AS base_amount_raw,
        CAST(quote_amount_in AS DOUBLE) AS quote_amount_raw,
        row_number() OVER (
            PARTITION BY base_mint
            ORDER BY evt_block_time, evt_block_slot, evt_tx_index,
                     evt_outer_instruction_index, evt_inner_instruction_index, evt_tx_id
        ) AS mint_creation_number
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    CROSS JOIN constants c
    WHERE evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-24'
      AND evt_block_time >= c.cohort_start
      AND evt_block_time < c.cohort_end
      AND evt_outer_executing_account =
          '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
),
graduations AS (
    SELECT
        graduated_at,
        graduated_at + INTERVAL '1' MINUTE + INTERVAL '15' SECOND AS execution_at,
        graduation_block_slot, graduation_tx_index, graduation_outer_index,
        graduation_inner_index, graduation_tx, pool, mint, quote_mint,
        base_decimals, quote_decimals,
        base_amount_raw / power(10, base_decimals) AS initial_base_reserve,
        quote_amount_raw / power(10, quote_decimals) AS initial_quote_reserve
    FROM create_ranked
    WHERE mint_creation_number = 1
),
create_states AS (
    SELECT
        mint, pool, quote_mint, base_decimals, quote_decimals,
        graduated_at, execution_at,
        graduated_at AS state_time,
        graduation_block_slot AS block_slot,
        graduation_tx_index AS tx_index,
        graduation_outer_index AS outer_index,
        graduation_inner_index AS inner_index,
        initial_base_reserve AS base_reserve,
        initial_quote_reserve AS quote_reserve,
        CAST(NULL AS DOUBLE) AS chain_fee_bps,
        false AS is_trade
    FROM graduations
),
buy_states_24h AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.base_decimals, g.quote_decimals,
        g.graduated_at, g.execution_at,
        b.evt_block_time AS state_time,
        b.evt_block_slot AS block_slot,
        b.evt_tx_index AS tx_index,
        b.evt_outer_instruction_index AS outer_index,
        b.evt_inner_instruction_index AS inner_index,
        CAST(b.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(b.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(COALESCE(b.lp_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(b.protocol_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(b.coin_creator_fee_basis_points, 0) AS DOUBLE)
            AS chain_fee_bps,
        true AS is_trade
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_buyevent b
        ON b.pool = g.pool
       AND b.evt_block_time >= g.graduated_at
       AND b.evt_block_time <= g.execution_at + INTERVAL '4' HOUR
    WHERE b.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-26'
),
sell_states_24h AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.base_decimals, g.quote_decimals,
        g.graduated_at, g.execution_at,
        s.evt_block_time AS state_time,
        s.evt_block_slot AS block_slot,
        s.evt_tx_index AS tx_index,
        s.evt_outer_instruction_index AS outer_index,
        s.evt_inner_instruction_index AS inner_index,
        CAST(s.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(s.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(COALESCE(s.lp_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(s.protocol_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(s.coin_creator_fee_basis_points, 0) AS DOUBLE)
            AS chain_fee_bps,
        true AS is_trade
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_sellevent s
        ON s.pool = g.pool
       AND s.evt_block_time >= g.graduated_at
       AND s.evt_block_time <= g.execution_at + INTERVAL '4' HOUR
    WHERE s.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-26'
),
trade_states_24h AS (
    SELECT * FROM buy_states_24h
    UNION ALL
    SELECT * FROM sell_states_24h
),
deposit_states_entry AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.base_decimals, g.quote_decimals,
        g.graduated_at, g.execution_at,
        d.evt_block_time AS state_time, d.evt_block_slot AS block_slot,
        d.evt_tx_index AS tx_index,
        d.evt_outer_instruction_index AS outer_index,
        d.evt_inner_instruction_index AS inner_index,
        CAST(d.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(d.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(NULL AS DOUBLE) AS chain_fee_bps,
        false AS is_trade
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_depositevent d
        ON d.pool = g.pool
       AND d.evt_block_time >= g.graduated_at
       AND d.evt_block_time <= g.execution_at
    WHERE d.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-25'
),
withdraw_states_entry AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.base_decimals, g.quote_decimals,
        g.graduated_at, g.execution_at,
        w.evt_block_time AS state_time, w.evt_block_slot AS block_slot,
        w.evt_tx_index AS tx_index,
        w.evt_outer_instruction_index AS outer_index,
        w.evt_inner_instruction_index AS inner_index,
        CAST(w.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(w.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(NULL AS DOUBLE) AS chain_fee_bps,
        false AS is_trade
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_withdrawevent w
        ON w.pool = g.pool
       AND w.evt_block_time >= g.graduated_at
       AND w.evt_block_time <= g.execution_at
    WHERE w.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-07-25'
),
entry_state_candidates AS (
    SELECT * FROM create_states
    UNION ALL
    SELECT * FROM trade_states_24h WHERE state_time <= execution_at
    UNION ALL
    SELECT * FROM deposit_states_entry
    UNION ALL
    SELECT * FROM withdraw_states_entry
),
entry_reserves AS (
    SELECT
        mint,
        max_by(base_reserve, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1)))
            AS entry_base_reserve,
        max_by(quote_reserve, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1)))
            AS entry_quote_reserve,
        max_by(state_time, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1)))
            AS entry_state_time
    FROM entry_state_candidates
    WHERE base_reserve > 0 AND quote_reserve >= 0
    GROUP BY 1
),
entry_fees AS (
    SELECT
        mint,
        max_by(chain_fee_bps, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1)))
            FILTER (WHERE state_time <= execution_at) AS entry_chain_fee_bps
    FROM trade_states_24h
    GROUP BY 1
),
entries_raw AS (
    SELECT
        g.graduated_at, g.execution_at, g.mint, g.pool, g.quote_mint,
        r.entry_base_reserve, r.entry_quote_reserve, r.entry_state_time,
        COALESCE(f.entry_chain_fee_bps, c.missing_chain_fee_bps)
            AS entry_chain_fee_bps,
        quote_hour.price_usd AS entry_quote_usd,
        0.05 * r.entry_quote_reserve * quote_hour.price_usd
            AS entry_capacity_5pct_usd
    FROM graduations g
    CROSS JOIN constants c
    INNER JOIN entry_reserves r ON r.mint = g.mint
    LEFT JOIN entry_fees f ON f.mint = g.mint
    LEFT JOIN price_hours quote_hour
        ON quote_hour.timestamp = date_trunc('hour', g.execution_at)
       AND quote_hour.contract_address = from_base58(g.quote_mint)
),
entries AS (
    SELECT
        e.*,
        (250.0 / entry_quote_usd)
            / (1.0 + (entry_chain_fee_bps + c.execution_haircut_bps) / 10000.0)
            AS curve_quote_in_250,
        (500.0 / entry_quote_usd)
            / (1.0 + (entry_chain_fee_bps + c.execution_haircut_bps) / 10000.0)
            AS curve_quote_in_500
    FROM entries_raw e
    CROSS JOIN constants c
    WHERE entry_capacity_5pct_usd >= 250
      AND entry_quote_usd > 0
      AND entry_base_reserve > 0
      AND entry_quote_reserve > 0
),
entry_positions AS (
    SELECT
        e.*,
        entry_base_reserve * curve_quote_in_250
            / (entry_quote_reserve + curve_quote_in_250) AS base_tokens_250,
        CASE WHEN entry_capacity_5pct_usd >= 500 THEN
            entry_base_reserve * curve_quote_in_500
                / (entry_quote_reserve + curve_quote_in_500)
        END AS base_tokens_500
    FROM entries e
),
path_states AS (
    SELECT
        e.graduated_at, e.execution_at, e.mint, e.pool, e.quote_mint,
        e.entry_capacity_5pct_usd, e.entry_chain_fee_bps,
        e.entry_base_reserve, e.entry_quote_reserve, e.entry_quote_usd,
        e.base_tokens_250, e.base_tokens_500,
        t.state_time, t.block_slot, t.tx_index, t.outer_index, t.inner_index,
        t.base_reserve, t.quote_reserve,
        COALESCE(t.chain_fee_bps, c.missing_chain_fee_bps) AS exit_chain_fee_bps,
        quote_hour.price_usd AS exit_quote_usd,
        date_diff('second', e.execution_at, t.state_time) AS seconds_after_entry,
        CAST(t.block_slot AS BIGINT) * 1000000000
          + CAST(t.tx_index AS BIGINT) * 100000
          + CAST(COALESCE(t.outer_index, -1) + 1 AS BIGINT) * 1000
          + CAST(COALESCE(t.inner_index, -1) + 1 AS BIGINT)
            AS event_order
    FROM entry_positions e
    CROSS JOIN constants c
    INNER JOIN trade_states_24h t
        ON t.mint = e.mint
       AND t.state_time > e.execution_at
       AND t.state_time <= e.execution_at + INTERVAL '4' HOUR
    LEFT JOIN price_hours quote_hour
        ON quote_hour.timestamp = date_trunc('hour', t.state_time)
       AND quote_hour.contract_address = from_base58(e.quote_mint)
    WHERE t.base_reserve > 0
      AND t.quote_reserve >= 0
),
liquidation_values AS (
    SELECT
        *,
        quote_reserve * base_tokens_250 / NULLIF(base_reserve + base_tokens_250, 0)
            * greatest(0.0,
                1.0 - (exit_chain_fee_bps + c.execution_haircut_bps) / 10000.0)
            * exit_quote_usd / 250.0 AS liquidation_multiple_250,
        quote_reserve * base_tokens_500 / NULLIF(base_reserve + base_tokens_500, 0)
            * greatest(0.0,
                1.0 - (exit_chain_fee_bps + c.execution_haircut_bps) / 10000.0)
            * exit_quote_usd / 500.0 AS liquidation_multiple_500
    FROM path_states
    CROSS JOIN constants c
    WHERE exit_quote_usd > 0
),
path_rollup AS (
    SELECT
        mint,
        count(*) AS path_event_rows_24h,
        -- $250 first upper barriers.
        min(event_order) FILTER (WHERE liquidation_multiple_250 >= 1.5)
            AS tp15_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 >= 1.5) AS tp15_seconds_250,
        min(event_order) FILTER (WHERE liquidation_multiple_250 >= 2.0)
            AS tp2_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 >= 2.0) AS tp2_seconds_250,
        min(event_order) FILTER (WHERE liquidation_multiple_250 >= 3.0)
            AS tp3_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 >= 3.0) AS tp3_seconds_250,
        min(event_order) FILTER (WHERE liquidation_multiple_250 >= 5.0)
            AS tp5_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 >= 5.0) AS tp5_seconds_250,
        -- $250 first lower barriers, preserving gap return.
        min(event_order) FILTER (WHERE liquidation_multiple_250 <= 0.7)
            AS sl07_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.7) AS sl07_seconds_250,
        min_by(liquidation_multiple_250, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.7) AS sl07_return_250,
        min(event_order) FILTER (WHERE liquidation_multiple_250 <= 0.6)
            AS sl06_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.6) AS sl06_seconds_250,
        min_by(liquidation_multiple_250, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.6) AS sl06_return_250,
        min(event_order) FILTER (WHERE liquidation_multiple_250 <= 0.5)
            AS sl05_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.5) AS sl05_seconds_250,
        min_by(liquidation_multiple_250, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.5) AS sl05_return_250,
        min(event_order) FILTER (WHERE liquidation_multiple_250 <= 0.4)
            AS sl04_order_250,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.4) AS sl04_seconds_250,
        min_by(liquidation_multiple_250, event_order)
            FILTER (WHERE liquidation_multiple_250 <= 0.4) AS sl04_return_250,
        max_by(liquidation_multiple_250, event_order)
            FILTER (WHERE seconds_after_entry <= 3600) AS timeout_1h_return_250,
        max_by(liquidation_multiple_250, event_order)
            FILTER (WHERE seconds_after_entry <= 14400) AS timeout_4h_return_250,
        max_by(liquidation_multiple_250, event_order)
            FILTER (WHERE seconds_after_entry <= 86400) AS timeout_24h_return_250,

        -- $500 first upper barriers.
        min(event_order) FILTER (WHERE liquidation_multiple_500 >= 1.5)
            AS tp15_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 >= 1.5) AS tp15_seconds_500,
        min(event_order) FILTER (WHERE liquidation_multiple_500 >= 2.0)
            AS tp2_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 >= 2.0) AS tp2_seconds_500,
        min(event_order) FILTER (WHERE liquidation_multiple_500 >= 3.0)
            AS tp3_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 >= 3.0) AS tp3_seconds_500,
        min(event_order) FILTER (WHERE liquidation_multiple_500 >= 5.0)
            AS tp5_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 >= 5.0) AS tp5_seconds_500,
        -- $500 lower barriers.
        min(event_order) FILTER (WHERE liquidation_multiple_500 <= 0.7)
            AS sl07_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.7) AS sl07_seconds_500,
        min_by(liquidation_multiple_500, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.7) AS sl07_return_500,
        min(event_order) FILTER (WHERE liquidation_multiple_500 <= 0.6)
            AS sl06_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.6) AS sl06_seconds_500,
        min_by(liquidation_multiple_500, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.6) AS sl06_return_500,
        min(event_order) FILTER (WHERE liquidation_multiple_500 <= 0.5)
            AS sl05_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.5) AS sl05_seconds_500,
        min_by(liquidation_multiple_500, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.5) AS sl05_return_500,
        min(event_order) FILTER (WHERE liquidation_multiple_500 <= 0.4)
            AS sl04_order_500,
        min_by(seconds_after_entry, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.4) AS sl04_seconds_500,
        min_by(liquidation_multiple_500, event_order)
            FILTER (WHERE liquidation_multiple_500 <= 0.4) AS sl04_return_500,
        max_by(liquidation_multiple_500, event_order)
            FILTER (WHERE seconds_after_entry <= 3600) AS timeout_1h_return_500,
        max_by(liquidation_multiple_500, event_order)
            FILTER (WHERE seconds_after_entry <= 14400) AS timeout_4h_return_500,
        max_by(liquidation_multiple_500, event_order)
            FILTER (WHERE seconds_after_entry <= 86400) AS timeout_24h_return_500
    FROM liquidation_values
    GROUP BY 1
),
entry_roundtrip AS (
    SELECT
        e.*,
        entry_quote_reserve * base_tokens_250
            / NULLIF(entry_base_reserve + base_tokens_250, 0)
            * greatest(0.0,
                1.0 - (entry_chain_fee_bps + c.execution_haircut_bps) / 10000.0)
            * entry_quote_usd / 250.0 AS immediate_roundtrip_250,
        entry_quote_reserve * base_tokens_500
            / NULLIF(entry_base_reserve + base_tokens_500, 0)
            * greatest(0.0,
                1.0 - (entry_chain_fee_bps + c.execution_haircut_bps) / 10000.0)
            * entry_quote_usd / 500.0 AS immediate_roundtrip_500
    FROM entry_positions e
    CROSS JOIN constants c
)
SELECT
    e.graduated_at, e.execution_at, e.mint, e.pool, e.quote_mint,
    e.entry_capacity_5pct_usd, e.entry_chain_fee_bps,
    date_diff('second', e.entry_state_time, e.execution_at) AS entry_state_age_seconds,
    e.immediate_roundtrip_250, e.immediate_roundtrip_500,
    COALESCE(p.path_event_rows_24h, 0) AS path_event_rows_24h,
    p.tp15_order_250, p.tp15_seconds_250,
    p.tp2_order_250, p.tp2_seconds_250,
    p.tp3_order_250, p.tp3_seconds_250,
    p.tp5_order_250, p.tp5_seconds_250,
    p.sl07_order_250, p.sl07_seconds_250, p.sl07_return_250,
    p.sl06_order_250, p.sl06_seconds_250, p.sl06_return_250,
    p.sl05_order_250, p.sl05_seconds_250, p.sl05_return_250,
    p.sl04_order_250, p.sl04_seconds_250, p.sl04_return_250,
    COALESCE(p.timeout_1h_return_250, e.immediate_roundtrip_250)
        AS timeout_1h_return_250,
    COALESCE(p.timeout_4h_return_250, e.immediate_roundtrip_250)
        AS timeout_4h_return_250,
    COALESCE(p.timeout_24h_return_250, e.immediate_roundtrip_250)
        AS timeout_24h_return_250,
    p.tp15_order_500, p.tp15_seconds_500,
    p.tp2_order_500, p.tp2_seconds_500,
    p.tp3_order_500, p.tp3_seconds_500,
    p.tp5_order_500, p.tp5_seconds_500,
    p.sl07_order_500, p.sl07_seconds_500, p.sl07_return_500,
    p.sl06_order_500, p.sl06_seconds_500, p.sl06_return_500,
    p.sl05_order_500, p.sl05_seconds_500, p.sl05_return_500,
    p.sl04_order_500, p.sl04_seconds_500, p.sl04_return_500,
    COALESCE(p.timeout_1h_return_500, e.immediate_roundtrip_500)
        AS timeout_1h_return_500,
    COALESCE(p.timeout_4h_return_500, e.immediate_roundtrip_500)
        AS timeout_4h_return_500,
    COALESCE(p.timeout_24h_return_500, e.immediate_roundtrip_500)
        AS timeout_24h_return_500
FROM entry_roundtrip e
LEFT JOIN path_rollup p ON p.mint = e.mint
ORDER BY e.graduated_at, e.mint
