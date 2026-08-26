-- Frozen T+5m15s LP-return experiment. One row per entry-capacity-eligible
-- canonical migration; local analysis unfolds two position sizes x four holds.

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
      AND timestamp < TIMESTAMP '2026-08-02 00:00:00'
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
        pool,
        base_mint AS mint,
        quote_mint,
        base_mint_decimals AS base_decimals,
        quote_mint_decimals AS quote_decimals,
        CAST(base_amount_in AS DOUBLE) AS base_amount_raw,
        CAST(quote_amount_in AS DOUBLE) AS quote_amount_raw,
        CAST(initial_liquidity AS DOUBLE) AS initial_lp_supply,
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
        graduated_at + INTERVAL '5' MINUTE + INTERVAL '15' SECOND AS execution_at,
        graduation_block_slot, graduation_tx_index, graduation_outer_index,
        graduation_inner_index, pool, mint, quote_mint,
        base_decimals, quote_decimals,
        base_amount_raw / power(10, base_decimals) AS initial_base_reserve,
        quote_amount_raw / power(10, quote_decimals) AS initial_quote_reserve,
        initial_lp_supply
    FROM create_ranked
    WHERE mint_creation_number = 1
),
create_states AS (
    SELECT
        mint, pool, quote_mint, graduated_at, execution_at,
        graduated_at AS state_time,
        CAST(graduation_block_slot AS BIGINT) * 1000000000
          + CAST(graduation_tx_index AS BIGINT) * 100000
          + CAST(COALESCE(graduation_outer_index, -1) + 1 AS BIGINT) * 1000
          + CAST(COALESCE(graduation_inner_index, -1) + 1 AS BIGINT) AS event_order,
        initial_base_reserve AS base_reserve,
        initial_quote_reserve AS quote_reserve
    FROM graduations
),
buy_states AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.graduated_at, g.execution_at,
        b.evt_block_time AS state_time,
        CAST(b.evt_block_slot AS BIGINT) * 1000000000
          + CAST(b.evt_tx_index AS BIGINT) * 100000
          + CAST(COALESCE(b.evt_outer_instruction_index, -1) + 1 AS BIGINT) * 1000
          + CAST(COALESCE(b.evt_inner_instruction_index, -1) + 1 AS BIGINT)
            AS event_order,
        CAST(b.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(b.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(COALESCE(b.lp_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(b.protocol_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(b.coin_creator_fee_basis_points, 0) AS DOUBLE)
            AS chain_fee_bps,
        CAST(COALESCE(b.lp_fee, 0) AS DOUBLE) / power(10, g.quote_decimals)
            AS lp_fee_quote
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_buyevent b
        ON b.pool = g.pool
       AND b.evt_block_time >= g.graduated_at
       AND b.evt_block_time <= g.execution_at + INTERVAL '7' DAY
    WHERE b.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-01'
),
sell_states AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.graduated_at, g.execution_at,
        s.evt_block_time AS state_time,
        CAST(s.evt_block_slot AS BIGINT) * 1000000000
          + CAST(s.evt_tx_index AS BIGINT) * 100000
          + CAST(COALESCE(s.evt_outer_instruction_index, -1) + 1 AS BIGINT) * 1000
          + CAST(COALESCE(s.evt_inner_instruction_index, -1) + 1 AS BIGINT)
            AS event_order,
        CAST(s.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(s.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(COALESCE(s.lp_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(s.protocol_fee_basis_points, 0) AS DOUBLE)
          + CAST(COALESCE(s.coin_creator_fee_basis_points, 0) AS DOUBLE)
            AS chain_fee_bps,
        CAST(COALESCE(s.lp_fee, 0) AS DOUBLE) / power(10, g.quote_decimals)
            AS lp_fee_quote
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_sellevent s
        ON s.pool = g.pool
       AND s.evt_block_time >= g.graduated_at
       AND s.evt_block_time <= g.execution_at + INTERVAL '7' DAY
    WHERE s.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-01'
),
trade_states AS (
    SELECT * FROM buy_states
    UNION ALL
    SELECT * FROM sell_states
),
deposit_states AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.graduated_at, g.execution_at,
        d.evt_block_time AS state_time,
        CAST(d.evt_block_slot AS BIGINT) * 1000000000
          + CAST(d.evt_tx_index AS BIGINT) * 100000
          + CAST(COALESCE(d.evt_outer_instruction_index, -1) + 1 AS BIGINT) * 1000
          + CAST(COALESCE(d.evt_inner_instruction_index, -1) + 1 AS BIGINT)
            AS event_order,
        CAST(d.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(d.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(d.lp_mint_supply AS DOUBLE) + CAST(d.lp_token_amount_out AS DOUBLE)
            AS post_lp_supply
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_depositevent d
        ON d.pool = g.pool
       AND d.evt_block_time >= g.graduated_at
       AND d.evt_block_time <= g.execution_at + INTERVAL '7' DAY
    WHERE d.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-01'
),
withdraw_states AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.graduated_at, g.execution_at,
        w.evt_block_time AS state_time,
        CAST(w.evt_block_slot AS BIGINT) * 1000000000
          + CAST(w.evt_tx_index AS BIGINT) * 100000
          + CAST(COALESCE(w.evt_outer_instruction_index, -1) + 1 AS BIGINT) * 1000
          + CAST(COALESCE(w.evt_inner_instruction_index, -1) + 1 AS BIGINT)
            AS event_order,
        CAST(w.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS base_reserve,
        CAST(w.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_reserve,
        CAST(w.lp_mint_supply AS DOUBLE) - CAST(w.lp_token_amount_in AS DOUBLE)
            AS post_lp_supply
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_withdrawevent w
        ON w.pool = g.pool
       AND w.evt_block_time >= g.graduated_at
       AND w.evt_block_time <= g.execution_at + INTERVAL '7' DAY
    WHERE w.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-01'
),
reserve_states AS (
    SELECT mint, state_time, event_order, base_reserve, quote_reserve
    FROM create_states
    UNION ALL
    SELECT mint, state_time, event_order, base_reserve, quote_reserve
    FROM trade_states
    UNION ALL
    SELECT mint, state_time, event_order, base_reserve, quote_reserve
    FROM deposit_states
    UNION ALL
    SELECT mint, state_time, event_order, base_reserve, quote_reserve
    FROM withdraw_states
),
liquidity_states AS (
    SELECT
        g.mint, g.graduated_at AS state_time,
        CAST(g.graduation_block_slot AS BIGINT) * 1000000000
          + CAST(g.graduation_tx_index AS BIGINT) * 100000
          + CAST(COALESCE(g.graduation_outer_index, -1) + 1 AS BIGINT) * 1000
          + CAST(COALESCE(g.graduation_inner_index, -1) + 1 AS BIGINT)
            AS event_order,
        g.initial_lp_supply AS post_lp_supply
    FROM graduations g
    UNION ALL
    SELECT mint, state_time, event_order, post_lp_supply FROM deposit_states
    UNION ALL
    SELECT mint, state_time, event_order, post_lp_supply FROM withdraw_states
),
entry_reserves AS (
    SELECT
        g.mint,
        max_by(s.base_reserve, s.event_order) AS entry_base_reserve,
        max_by(s.quote_reserve, s.event_order) AS entry_quote_reserve,
        max_by(s.state_time, s.event_order) AS entry_state_time
    FROM graduations g
    INNER JOIN reserve_states s
        ON s.mint = g.mint AND s.state_time <= g.execution_at
    WHERE s.base_reserve > 0 AND s.quote_reserve > 0
    GROUP BY 1
),
entry_supply AS (
    SELECT
        g.mint,
        max_by(l.post_lp_supply, l.event_order) AS entry_lp_supply
    FROM graduations g
    INNER JOIN liquidity_states l
        ON l.mint = g.mint AND l.state_time <= g.execution_at
    WHERE l.post_lp_supply > 0
    GROUP BY 1
),
entry_fees AS (
    SELECT
        g.mint,
        max_by(t.chain_fee_bps, t.event_order) AS entry_chain_fee_bps
    FROM graduations g
    LEFT JOIN trade_states t
        ON t.mint = g.mint AND t.state_time <= g.execution_at
    GROUP BY 1
),
entries_raw AS (
    SELECT
        g.graduated_at, g.execution_at, g.mint, g.pool, g.quote_mint,
        r.entry_base_reserve, r.entry_quote_reserve, r.entry_state_time,
        l.entry_lp_supply,
        COALESCE(f.entry_chain_fee_bps, c.missing_chain_fee_bps)
            AS entry_chain_fee_bps,
        p.price_usd AS entry_quote_usd,
        0.05 * r.entry_quote_reserve * p.price_usd AS entry_capacity_5pct_usd
    FROM graduations g
    CROSS JOIN constants c
    INNER JOIN entry_reserves r ON r.mint = g.mint
    INNER JOIN entry_supply l ON l.mint = g.mint
    LEFT JOIN entry_fees f ON f.mint = g.mint
    LEFT JOIN price_hours p
        ON p.timestamp = date_trunc('hour', g.execution_at)
       AND p.contract_address = from_base58(g.quote_mint)
),
entries AS (
    SELECT
        e.*,
        250.0 / entry_quote_usd AS quote_deposit_500,
        entry_base_reserve * (250.0 / entry_quote_usd) / entry_quote_reserve
            AS base_deposit_500,
        entry_lp_supply * (250.0 / entry_quote_usd) / entry_quote_reserve
            AS lp_tokens_500,
        CASE WHEN entry_capacity_5pct_usd >= 500 THEN 500.0 / entry_quote_usd END
            AS quote_deposit_1000,
        CASE WHEN entry_capacity_5pct_usd >= 500 THEN
            entry_base_reserve * (500.0 / entry_quote_usd) / entry_quote_reserve
        END AS base_deposit_1000,
        CASE WHEN entry_capacity_5pct_usd >= 500 THEN
            entry_lp_supply * (500.0 / entry_quote_usd) / entry_quote_reserve
        END AS lp_tokens_1000
    FROM entries_raw e
    WHERE entry_capacity_5pct_usd >= 250
      AND entry_quote_usd > 0
      AND entry_base_reserve > 0
      AND entry_quote_reserve > 0
      AND entry_lp_supply > 0
),
exit_reserves AS (
    SELECT
        e.mint,
        max_by(s.base_reserve, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '1' HOUR
        ) AS exit_base_reserve_1h,
        max_by(s.quote_reserve, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '1' HOUR
        ) AS exit_quote_reserve_1h,
        max_by(s.state_time, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '1' HOUR
        ) AS exit_state_time_1h,
        max_by(s.base_reserve, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '4' HOUR
        ) AS exit_base_reserve_4h,
        max_by(s.quote_reserve, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '4' HOUR
        ) AS exit_quote_reserve_4h,
        max_by(s.state_time, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '4' HOUR
        ) AS exit_state_time_4h,
        max_by(s.base_reserve, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '24' HOUR
        ) AS exit_base_reserve_24h,
        max_by(s.quote_reserve, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '24' HOUR
        ) AS exit_quote_reserve_24h,
        max_by(s.state_time, s.event_order) FILTER (
            WHERE s.state_time <= e.execution_at + INTERVAL '24' HOUR
        ) AS exit_state_time_24h,
        max_by(s.base_reserve, s.event_order) AS exit_base_reserve_168h,
        max_by(s.quote_reserve, s.event_order) AS exit_quote_reserve_168h,
        max_by(s.state_time, s.event_order) AS exit_state_time_168h
    FROM entries e
    INNER JOIN reserve_states s
        ON s.mint = e.mint
       AND s.state_time <= e.execution_at + INTERVAL '7' DAY
    WHERE s.base_reserve > 0 AND s.quote_reserve >= 0
    GROUP BY 1
),
exit_supplies AS (
    SELECT
        e.mint,
        max_by(l.post_lp_supply, l.event_order) FILTER (
            WHERE l.state_time <= e.execution_at + INTERVAL '1' HOUR
        ) AS exit_lp_supply_1h,
        max_by(l.post_lp_supply, l.event_order) FILTER (
            WHERE l.state_time <= e.execution_at + INTERVAL '4' HOUR
        ) AS exit_lp_supply_4h,
        max_by(l.post_lp_supply, l.event_order) FILTER (
            WHERE l.state_time <= e.execution_at + INTERVAL '24' HOUR
        ) AS exit_lp_supply_24h,
        max_by(l.post_lp_supply, l.event_order) AS exit_lp_supply_168h
    FROM entries e
    INNER JOIN liquidity_states l
        ON l.mint = e.mint
       AND l.state_time <= e.execution_at + INTERVAL '7' DAY
    WHERE l.post_lp_supply > 0
    GROUP BY 1
),
exit_fees AS (
    SELECT
        e.mint,
        max_by(t.chain_fee_bps, t.event_order) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '1' HOUR
        ) AS exit_chain_fee_bps_1h,
        max_by(t.chain_fee_bps, t.event_order) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '4' HOUR
        ) AS exit_chain_fee_bps_4h,
        max_by(t.chain_fee_bps, t.event_order) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '24' HOUR
        ) AS exit_chain_fee_bps_24h,
        max_by(t.chain_fee_bps, t.event_order) AS exit_chain_fee_bps_168h
    FROM entries e
    LEFT JOIN trade_states t
        ON t.mint = e.mint
       AND t.state_time <= e.execution_at + INTERVAL '7' DAY
    GROUP BY 1
),
future_trade_supply AS (
    SELECT
        t.mint, t.state_time, t.event_order, t.lp_fee_quote,
        p.price_usd AS fee_quote_usd,
        max_by(l.post_lp_supply, l.event_order) AS historical_lp_supply
    FROM trade_states t
    INNER JOIN entries e
        ON e.mint = t.mint
       AND t.state_time > e.execution_at
       AND t.state_time <= e.execution_at + INTERVAL '7' DAY
    INNER JOIN liquidity_states l
        ON l.mint = t.mint AND l.event_order <= t.event_order
    LEFT JOIN price_hours p
        ON p.timestamp = date_trunc('hour', t.state_time)
       AND p.contract_address = from_base58(e.quote_mint)
    GROUP BY 1,2,3,4,5
),
fee_rollup AS (
    SELECT
        e.mint,
        count(t.event_order) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '1' HOUR
        ) AS trade_count_1h,
        count(t.event_order) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '4' HOUR
        ) AS trade_count_4h,
        count(t.event_order) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '24' HOUR
        ) AS trade_count_24h,
        count(t.event_order) AS trade_count_168h,
        sum(t.lp_fee_quote * t.fee_quote_usd) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '1' HOUR
        ) AS pool_lp_fee_usd_1h,
        sum(t.lp_fee_quote * t.fee_quote_usd) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '4' HOUR
        ) AS pool_lp_fee_usd_4h,
        sum(t.lp_fee_quote * t.fee_quote_usd) FILTER (
            WHERE t.state_time <= e.execution_at + INTERVAL '24' HOUR
        ) AS pool_lp_fee_usd_24h,
        sum(t.lp_fee_quote * t.fee_quote_usd) AS pool_lp_fee_usd_168h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_500 / NULLIF(t.historical_lp_supply + e.lp_tokens_500, 0)
        ) FILTER (WHERE t.state_time <= e.execution_at + INTERVAL '1' HOUR)
            AS allocated_lp_fee_usd_500_1h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_500 / NULLIF(t.historical_lp_supply + e.lp_tokens_500, 0)
        ) FILTER (WHERE t.state_time <= e.execution_at + INTERVAL '4' HOUR)
            AS allocated_lp_fee_usd_500_4h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_500 / NULLIF(t.historical_lp_supply + e.lp_tokens_500, 0)
        ) FILTER (WHERE t.state_time <= e.execution_at + INTERVAL '24' HOUR)
            AS allocated_lp_fee_usd_500_24h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_500 / NULLIF(t.historical_lp_supply + e.lp_tokens_500, 0)
        ) AS allocated_lp_fee_usd_500_168h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_1000 / NULLIF(t.historical_lp_supply + e.lp_tokens_1000, 0)
        ) FILTER (WHERE t.state_time <= e.execution_at + INTERVAL '1' HOUR)
            AS allocated_lp_fee_usd_1000_1h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_1000 / NULLIF(t.historical_lp_supply + e.lp_tokens_1000, 0)
        ) FILTER (WHERE t.state_time <= e.execution_at + INTERVAL '4' HOUR)
            AS allocated_lp_fee_usd_1000_4h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_1000 / NULLIF(t.historical_lp_supply + e.lp_tokens_1000, 0)
        ) FILTER (WHERE t.state_time <= e.execution_at + INTERVAL '24' HOUR)
            AS allocated_lp_fee_usd_1000_24h,
        sum(t.lp_fee_quote * t.fee_quote_usd
            * e.lp_tokens_1000 / NULLIF(t.historical_lp_supply + e.lp_tokens_1000, 0)
        ) AS allocated_lp_fee_usd_1000_168h
    FROM entries e
    LEFT JOIN future_trade_supply t ON t.mint = e.mint
    GROUP BY 1
)
SELECT
    e.*,
    r.exit_base_reserve_1h, r.exit_quote_reserve_1h, r.exit_state_time_1h,
    r.exit_base_reserve_4h, r.exit_quote_reserve_4h, r.exit_state_time_4h,
    r.exit_base_reserve_24h, r.exit_quote_reserve_24h, r.exit_state_time_24h,
    r.exit_base_reserve_168h, r.exit_quote_reserve_168h, r.exit_state_time_168h,
    s.exit_lp_supply_1h, s.exit_lp_supply_4h,
    s.exit_lp_supply_24h, s.exit_lp_supply_168h,
    COALESCE(x.exit_chain_fee_bps_1h, e.entry_chain_fee_bps, c.missing_chain_fee_bps)
        AS exit_chain_fee_bps_1h,
    COALESCE(x.exit_chain_fee_bps_4h, e.entry_chain_fee_bps, c.missing_chain_fee_bps)
        AS exit_chain_fee_bps_4h,
    COALESCE(x.exit_chain_fee_bps_24h, e.entry_chain_fee_bps, c.missing_chain_fee_bps)
        AS exit_chain_fee_bps_24h,
    COALESCE(x.exit_chain_fee_bps_168h, e.entry_chain_fee_bps, c.missing_chain_fee_bps)
        AS exit_chain_fee_bps_168h,
    q1.price_usd AS exit_quote_usd_1h,
    q4.price_usd AS exit_quote_usd_4h,
    q24.price_usd AS exit_quote_usd_24h,
    q168.price_usd AS exit_quote_usd_168h,
    COALESCE(f.trade_count_1h, 0) AS trade_count_1h,
    COALESCE(f.trade_count_4h, 0) AS trade_count_4h,
    COALESCE(f.trade_count_24h, 0) AS trade_count_24h,
    COALESCE(f.trade_count_168h, 0) AS trade_count_168h,
    COALESCE(f.pool_lp_fee_usd_1h, 0) AS pool_lp_fee_usd_1h,
    COALESCE(f.pool_lp_fee_usd_4h, 0) AS pool_lp_fee_usd_4h,
    COALESCE(f.pool_lp_fee_usd_24h, 0) AS pool_lp_fee_usd_24h,
    COALESCE(f.pool_lp_fee_usd_168h, 0) AS pool_lp_fee_usd_168h,
    COALESCE(f.allocated_lp_fee_usd_500_1h, 0) AS allocated_lp_fee_usd_500_1h,
    COALESCE(f.allocated_lp_fee_usd_500_4h, 0) AS allocated_lp_fee_usd_500_4h,
    COALESCE(f.allocated_lp_fee_usd_500_24h, 0) AS allocated_lp_fee_usd_500_24h,
    COALESCE(f.allocated_lp_fee_usd_500_168h, 0) AS allocated_lp_fee_usd_500_168h,
    COALESCE(f.allocated_lp_fee_usd_1000_1h, 0) AS allocated_lp_fee_usd_1000_1h,
    COALESCE(f.allocated_lp_fee_usd_1000_4h, 0) AS allocated_lp_fee_usd_1000_4h,
    COALESCE(f.allocated_lp_fee_usd_1000_24h, 0) AS allocated_lp_fee_usd_1000_24h,
    COALESCE(f.allocated_lp_fee_usd_1000_168h, 0) AS allocated_lp_fee_usd_1000_168h
FROM entries e
CROSS JOIN constants c
INNER JOIN exit_reserves r ON r.mint = e.mint
INNER JOIN exit_supplies s ON s.mint = e.mint
LEFT JOIN exit_fees x ON x.mint = e.mint
LEFT JOIN fee_rollup f ON f.mint = e.mint
LEFT JOIN price_hours q1
    ON q1.timestamp = date_trunc('hour', e.execution_at + INTERVAL '1' HOUR)
   AND q1.contract_address = from_base58(e.quote_mint)
LEFT JOIN price_hours q4
    ON q4.timestamp = date_trunc('hour', e.execution_at + INTERVAL '4' HOUR)
   AND q4.contract_address = from_base58(e.quote_mint)
LEFT JOIN price_hours q24
    ON q24.timestamp = date_trunc('hour', e.execution_at + INTERVAL '24' HOUR)
   AND q24.contract_address = from_base58(e.quote_mint)
LEFT JOIN price_hours q168
    ON q168.timestamp = date_trunc('hour', e.execution_at + INTERVAL '168' HOUR)
   AND q168.contract_address = from_base58(e.quote_mint)
ORDER BY e.graduated_at, e.mint
