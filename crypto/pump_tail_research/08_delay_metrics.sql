-- Delayed-entry feasibility for the frozen Pump.fun -> PumpSwap cohort.
--
-- This query measures a strategy that deliberately waits after graduation.
-- Frozen entry delays: T+5m, T+15m, T+1h, T+4h, T+24h.
-- At each cutoff the entry quote is the last canonical pool state at or before
-- the cutoff. Pool state includes create, buy, sell, deposit, and withdraw
-- events. Future upside, however, is measured only from executable buy/sell
-- events in [cutoff, T+30d).
--
-- The price clock is in SOL. SOL-quoted pools need no per-trade conversion;
-- non-SOL pools are converted with hourly external quote/SOL prices. Capacity
-- is 5% of the quote reserve marked to USD at the delayed cutoff.

WITH
constants AS (
    SELECT
        TIMESTAMP '2026-05-01 00:00:00' AS cohort_start,
        TIMESTAMP '2026-07-25 00:00:00' AS cohort_end,
        'So11111111111111111111111111111111111111112' AS wsol_mint,
        'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' AS usdc_mint
),
price_hours AS (
    SELECT
        timestamp,
        contract_address,
        max(price) AS price_usd
    FROM prices_external.hour
    CROSS JOIN constants c
    WHERE blockchain = 'solana'
      AND timestamp >= TIMESTAMP '2026-05-01 00:00:00'
      AND timestamp < TIMESTAMP '2026-08-25 00:00:00'
      AND contract_address IN (
          from_base58(c.wsol_mint),
          from_base58(c.usdc_mint)
      )
    GROUP BY 1, 2
),
create_pool_events_ranked AS (
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
        CAST(base_amount_in AS DOUBLE) AS base_amount_in_raw,
        CAST(quote_amount_in AS DOUBLE) AS quote_amount_in_raw,
        row_number() OVER (
            PARTITION BY base_mint
            ORDER BY evt_block_time, evt_block_slot, evt_tx_index,
                     evt_outer_instruction_index, evt_inner_instruction_index,
                     evt_tx_id
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
graduations_raw AS (
    SELECT *
    FROM create_pool_events_ranked
    WHERE mint_creation_number = 1
),
graduations AS (
    SELECT
        g.graduated_at,
        g.graduation_block_slot,
        g.graduation_tx_index,
        g.graduation_outer_index,
        g.graduation_inner_index,
        g.graduation_tx,
        g.mint,
        g.pool,
        g.quote_mint,
        g.base_decimals,
        g.quote_decimals,
        g.base_amount_in_raw / power(10, g.base_decimals)
            AS initial_base_reserve,
        g.quote_amount_in_raw / power(10, g.quote_decimals)
            AS initial_quote_reserve,
        g.quote_amount_in_raw / power(10, g.quote_decimals)
            / NULLIF(g.base_amount_in_raw / power(10, g.base_decimals), 0)
            AS graduation_price_quote,
        quote_at_grad.price_usd AS quote_usd_at_graduation,
        sol_at_grad.price_usd AS sol_usd_at_graduation
    FROM graduations_raw g
    CROSS JOIN constants c
    LEFT JOIN price_hours quote_at_grad
        ON quote_at_grad.timestamp = date_trunc('hour', g.graduated_at)
       AND quote_at_grad.contract_address = from_base58(g.quote_mint)
    LEFT JOIN price_hours sol_at_grad
        ON sol_at_grad.timestamp = date_trunc('hour', g.graduated_at)
       AND sol_at_grad.contract_address = from_base58(c.wsol_mint)
),
graduations_priced AS (
    SELECT
        g.*,
        graduation_price_quote
            * CASE
                WHEN g.quote_mint = c.wsol_mint THEN 1.0
                ELSE quote_usd_at_graduation / NULLIF(sol_usd_at_graduation, 0)
              END AS graduation_price_sol,
        initial_quote_reserve * quote_usd_at_graduation
            AS initial_quote_reserve_usd
    FROM graduations g
    CROSS JOIN constants c
),

-- Every decoded event below exposes the post-event reserve state.
create_states AS (
    SELECT
        g.mint,
        g.pool,
        g.quote_mint,
        g.graduated_at,
        g.graduation_price_sol,
        g.graduated_at AS state_time,
        g.graduation_block_slot AS state_block_slot,
        g.graduation_tx_index AS state_tx_index,
        g.graduation_outer_index AS outer_instruction_index,
        g.graduation_inner_index AS inner_instruction_index,
        g.graduation_price_quote AS state_price_quote,
        g.initial_quote_reserve AS state_quote_reserve,
        false AS is_trade
    FROM graduations_priced g
),
buy_states AS (
    SELECT
        g.mint,
        g.pool,
        g.quote_mint,
        g.graduated_at,
        g.graduation_price_sol,
        b.evt_block_time AS state_time,
        b.evt_block_slot AS state_block_slot,
        b.evt_tx_index AS state_tx_index,
        b.evt_outer_instruction_index AS outer_instruction_index,
        b.evt_inner_instruction_index AS inner_instruction_index,
        (CAST(b.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals))
            / NULLIF(
                CAST(b.pool_base_token_reserves AS DOUBLE)
                    / power(10, g.base_decimals),
                0
            ) AS state_price_quote,
        CAST(b.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS state_quote_reserve,
        true AS is_trade
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_buyevent b
        ON b.pool = g.pool
       AND b.evt_block_time >= g.graduated_at
       AND b.evt_block_time < g.graduated_at + INTERVAL '30' DAY
    WHERE b.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-23'
),
sell_states AS (
    SELECT
        g.mint,
        g.pool,
        g.quote_mint,
        g.graduated_at,
        g.graduation_price_sol,
        s.evt_block_time AS state_time,
        s.evt_block_slot AS state_block_slot,
        s.evt_tx_index AS state_tx_index,
        s.evt_outer_instruction_index AS outer_instruction_index,
        s.evt_inner_instruction_index AS inner_instruction_index,
        (CAST(s.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals))
            / NULLIF(
                CAST(s.pool_base_token_reserves AS DOUBLE)
                    / power(10, g.base_decimals),
                0
            ) AS state_price_quote,
        CAST(s.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS state_quote_reserve,
        true AS is_trade
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_sellevent s
        ON s.pool = g.pool
       AND s.evt_block_time >= g.graduated_at
       AND s.evt_block_time < g.graduated_at + INTERVAL '30' DAY
    WHERE s.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-23'
),
deposit_states AS (
    SELECT
        g.mint,
        g.pool,
        g.quote_mint,
        g.graduated_at,
        g.graduation_price_sol,
        d.evt_block_time AS state_time,
        d.evt_block_slot AS state_block_slot,
        d.evt_tx_index AS state_tx_index,
        d.evt_outer_instruction_index AS outer_instruction_index,
        d.evt_inner_instruction_index AS inner_instruction_index,
        (CAST(d.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals))
            / NULLIF(
                CAST(d.pool_base_token_reserves AS DOUBLE)
                    / power(10, g.base_decimals),
                0
            ) AS state_price_quote,
        CAST(d.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS state_quote_reserve,
        false AS is_trade
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_depositevent d
        ON d.pool = g.pool
       AND d.evt_block_time >= g.graduated_at
       AND d.evt_block_time < g.graduated_at + INTERVAL '30' DAY
    WHERE d.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-23'
),
withdraw_states AS (
    SELECT
        g.mint,
        g.pool,
        g.quote_mint,
        g.graduated_at,
        g.graduation_price_sol,
        w.evt_block_time AS state_time,
        w.evt_block_slot AS state_block_slot,
        w.evt_tx_index AS state_tx_index,
        w.evt_outer_instruction_index AS outer_instruction_index,
        w.evt_inner_instruction_index AS inner_instruction_index,
        (CAST(w.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals))
            / NULLIF(
                CAST(w.pool_base_token_reserves AS DOUBLE)
                    / power(10, g.base_decimals),
                0
            ) AS state_price_quote,
        CAST(w.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS state_quote_reserve,
        false AS is_trade
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_withdrawevent w
        ON w.pool = g.pool
       AND w.evt_block_time >= g.graduated_at
       AND w.evt_block_time < g.graduated_at + INTERVAL '30' DAY
    WHERE w.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-23'
),
pool_states AS (
    SELECT * FROM create_states
    UNION ALL
    SELECT * FROM buy_states
    UNION ALL
    SELECT * FROM sell_states
    UNION ALL
    SELECT * FROM deposit_states
    UNION ALL
    SELECT * FROM withdraw_states
),
valid_states AS (
    SELECT *
    FROM pool_states
    WHERE state_price_quote IS NOT NULL
      AND state_price_quote >= 0
      AND state_quote_reserve >= 0
),

-- Snapshot last-known pool state at each frozen delay.  The same total ordering
-- is used for price, reserve and timestamp so those fields describe one event.
delay_snapshots AS (
    SELECT
        mint,
        max_by(state_price_quote, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '5' MINUTE
        ) AS entry_price_quote_5m,
        max_by(state_quote_reserve, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '5' MINUTE
        ) AS entry_quote_reserve_5m,
        max_by(state_time, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '5' MINUTE
        ) AS entry_state_time_5m,

        max_by(state_price_quote, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '15' MINUTE
        ) AS entry_price_quote_15m,
        max_by(state_quote_reserve, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '15' MINUTE
        ) AS entry_quote_reserve_15m,
        max_by(state_time, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '15' MINUTE
        ) AS entry_state_time_15m,

        max_by(state_price_quote, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '1' HOUR
        ) AS entry_price_quote_1h,
        max_by(state_quote_reserve, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '1' HOUR
        ) AS entry_quote_reserve_1h,
        max_by(state_time, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '1' HOUR
        ) AS entry_state_time_1h,

        max_by(state_price_quote, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '4' HOUR
        ) AS entry_price_quote_4h,
        max_by(state_quote_reserve, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '4' HOUR
        ) AS entry_quote_reserve_4h,
        max_by(state_time, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '4' HOUR
        ) AS entry_state_time_4h,

        max_by(state_price_quote, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '24' HOUR
        ) AS entry_price_quote_24h,
        max_by(state_quote_reserve, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '24' HOUR
        ) AS entry_quote_reserve_24h,
        max_by(state_time, ROW(
            state_block_slot, state_tx_index,
            COALESCE(outer_instruction_index, -1),
            COALESCE(inner_instruction_index, -1)
        )) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '24' HOUR
        ) AS entry_state_time_24h
    FROM valid_states
    GROUP BY 1
),

-- Convert only trade states to SOL.  This split avoids joining hourly prices
-- onto the overwhelming majority of WSOL-denominated trades.
sol_trade_states AS (
    SELECT
        s.*,
        s.state_price_quote AS trade_price_sol
    FROM valid_states s
    CROSS JOIN constants c
    WHERE s.is_trade
      AND s.quote_mint = c.wsol_mint
),
non_sol_trade_states AS (
    SELECT
        s.*,
        s.state_price_quote * quote_hour.price_usd
            / NULLIF(sol_hour.price_usd, 0) AS trade_price_sol
    FROM valid_states s
    CROSS JOIN constants c
    LEFT JOIN price_hours quote_hour
        ON quote_hour.timestamp = date_trunc('hour', s.state_time)
       AND quote_hour.contract_address = from_base58(s.quote_mint)
    LEFT JOIN price_hours sol_hour
        ON sol_hour.timestamp = date_trunc('hour', s.state_time)
       AND sol_hour.contract_address = from_base58(c.wsol_mint)
    WHERE s.is_trade
      AND s.quote_mint <> c.wsol_mint
),
trade_states AS (
    SELECT * FROM sol_trade_states
    UNION ALL
    SELECT * FROM non_sol_trade_states
),
trade_rollup AS (
    SELECT
        mint,
        count(*) AS trade_rows_30d,
        count_if(trade_price_sol IS NOT NULL) AS priced_trade_rows_30d,
        max(trade_price_sol / NULLIF(graduation_price_sol, 0)) AS max_30d,
        max_by(
            date_diff('second', graduated_at, state_time),
            ROW(
                trade_price_sol / NULLIF(graduation_price_sol, 0),
                -state_block_slot,
                -state_tx_index,
                -COALESCE(outer_instruction_index, -1),
                -COALESCE(inner_instruction_index, -1)
            )
        ) FILTER (WHERE trade_price_sol IS NOT NULL) AS time_to_peak_seconds,
        min(date_diff('second', graduated_at, state_time)) FILTER (
            WHERE trade_price_sol / NULLIF(graduation_price_sol, 0) >= 2
        ) AS first_touch_2x_seconds,
        min(date_diff('second', graduated_at, state_time)) FILTER (
            WHERE trade_price_sol / NULLIF(graduation_price_sol, 0) >= 5
        ) AS first_touch_5x_seconds,
        min(date_diff('second', graduated_at, state_time)) FILTER (
            WHERE trade_price_sol / NULLIF(graduation_price_sol, 0) >= 10
        ) AS first_touch_10x_seconds,
        max(trade_price_sol) FILTER (
            WHERE state_time >= graduated_at + INTERVAL '5' MINUTE
        ) AS future_max_price_sol_5m,
        max(trade_price_sol) FILTER (
            WHERE state_time >= graduated_at + INTERVAL '15' MINUTE
        ) AS future_max_price_sol_15m,
        max(trade_price_sol) FILTER (
            WHERE state_time >= graduated_at + INTERVAL '1' HOUR
        ) AS future_max_price_sol_1h,
        max(trade_price_sol) FILTER (
            WHERE state_time >= graduated_at + INTERVAL '4' HOUR
        ) AS future_max_price_sol_4h,
        max(trade_price_sol) FILTER (
            WHERE state_time >= graduated_at + INTERVAL '24' HOUR
        ) AS future_max_price_sol_24h,
        count_if(state_time >= graduated_at + INTERVAL '5' MINUTE)
            AS future_trade_rows_5m,
        count_if(state_time >= graduated_at + INTERVAL '15' MINUTE)
            AS future_trade_rows_15m,
        count_if(state_time >= graduated_at + INTERVAL '1' HOUR)
            AS future_trade_rows_1h,
        count_if(state_time >= graduated_at + INTERVAL '4' HOUR)
            AS future_trade_rows_4h,
        count_if(state_time >= graduated_at + INTERVAL '24' HOUR)
            AS future_trade_rows_24h
    FROM trade_states
    GROUP BY 1
),

-- Mark each delayed reserve to USD and each delayed entry quote to SOL at the
-- cutoff hour (not the timestamp of the last state change).
snapshot_fx AS (
    SELECT
        g.*,
        d.entry_price_quote_5m,
        d.entry_quote_reserve_5m,
        d.entry_state_time_5m,
        d.entry_price_quote_15m,
        d.entry_quote_reserve_15m,
        d.entry_state_time_15m,
        d.entry_price_quote_1h,
        d.entry_quote_reserve_1h,
        d.entry_state_time_1h,
        d.entry_price_quote_4h,
        d.entry_quote_reserve_4h,
        d.entry_state_time_4h,
        d.entry_price_quote_24h,
        d.entry_quote_reserve_24h,
        d.entry_state_time_24h,
        q5.price_usd AS quote_usd_5m,
        sol5.price_usd AS sol_usd_5m,
        q15.price_usd AS quote_usd_15m,
        sol15.price_usd AS sol_usd_15m,
        q1h.price_usd AS quote_usd_1h,
        sol1h.price_usd AS sol_usd_1h,
        q4h.price_usd AS quote_usd_4h,
        sol4h.price_usd AS sol_usd_4h,
        q24h.price_usd AS quote_usd_24h,
        sol24h.price_usd AS sol_usd_24h
    FROM graduations_priced g
    INNER JOIN delay_snapshots d ON d.mint = g.mint
    CROSS JOIN constants c
    LEFT JOIN price_hours q5
        ON q5.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '5' MINUTE)
       AND q5.contract_address = from_base58(g.quote_mint)
    LEFT JOIN price_hours sol5
        ON sol5.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '5' MINUTE)
       AND sol5.contract_address = from_base58(c.wsol_mint)
    LEFT JOIN price_hours q15
        ON q15.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '15' MINUTE)
       AND q15.contract_address = from_base58(g.quote_mint)
    LEFT JOIN price_hours sol15
        ON sol15.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '15' MINUTE)
       AND sol15.contract_address = from_base58(c.wsol_mint)
    LEFT JOIN price_hours q1h
        ON q1h.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '1' HOUR)
       AND q1h.contract_address = from_base58(g.quote_mint)
    LEFT JOIN price_hours sol1h
        ON sol1h.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '1' HOUR)
       AND sol1h.contract_address = from_base58(c.wsol_mint)
    LEFT JOIN price_hours q4h
        ON q4h.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '4' HOUR)
       AND q4h.contract_address = from_base58(g.quote_mint)
    LEFT JOIN price_hours sol4h
        ON sol4h.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '4' HOUR)
       AND sol4h.contract_address = from_base58(c.wsol_mint)
    LEFT JOIN price_hours q24h
        ON q24h.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '24' HOUR)
       AND q24h.contract_address = from_base58(g.quote_mint)
    LEFT JOIN price_hours sol24h
        ON sol24h.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '24' HOUR)
       AND sol24h.contract_address = from_base58(c.wsol_mint)
),
delayed_entries AS (
    SELECT
        s.*,
        entry_price_quote_5m
            * CASE WHEN quote_mint = c.wsol_mint THEN 1.0
                   ELSE quote_usd_5m / NULLIF(sol_usd_5m, 0) END
            AS entry_price_sol_5m,
        0.05 * entry_quote_reserve_5m * quote_usd_5m AS capacity_5pct_usd_5m,
        entry_price_quote_15m
            * CASE WHEN quote_mint = c.wsol_mint THEN 1.0
                   ELSE quote_usd_15m / NULLIF(sol_usd_15m, 0) END
            AS entry_price_sol_15m,
        0.05 * entry_quote_reserve_15m * quote_usd_15m AS capacity_5pct_usd_15m,
        entry_price_quote_1h
            * CASE WHEN quote_mint = c.wsol_mint THEN 1.0
                   ELSE quote_usd_1h / NULLIF(sol_usd_1h, 0) END
            AS entry_price_sol_1h,
        0.05 * entry_quote_reserve_1h * quote_usd_1h AS capacity_5pct_usd_1h,
        entry_price_quote_4h
            * CASE WHEN quote_mint = c.wsol_mint THEN 1.0
                   ELSE quote_usd_4h / NULLIF(sol_usd_4h, 0) END
            AS entry_price_sol_4h,
        0.05 * entry_quote_reserve_4h * quote_usd_4h AS capacity_5pct_usd_4h,
        entry_price_quote_24h
            * CASE WHEN quote_mint = c.wsol_mint THEN 1.0
                   ELSE quote_usd_24h / NULLIF(sol_usd_24h, 0) END
            AS entry_price_sol_24h,
        0.05 * entry_quote_reserve_24h * quote_usd_24h AS capacity_5pct_usd_24h
    FROM snapshot_fx s
    CROSS JOIN constants c
),
token_metrics AS (
    SELECT
        e.graduated_at,
        e.graduation_tx,
        e.mint,
        e.pool,
        e.quote_mint,
        e.graduation_price_sol,
        e.initial_quote_reserve_usd,
        0.05 * e.initial_quote_reserve_usd AS capacity_5pct_usd_t0,
        COALESCE(t.trade_rows_30d, 0) AS trade_rows_30d,
        COALESCE(t.priced_trade_rows_30d, 0) AS priced_trade_rows_30d,
        COALESCE(t.max_30d, 0) AS max_30d,
        t.time_to_peak_seconds,
        t.first_touch_2x_seconds,
        t.first_touch_5x_seconds,
        t.first_touch_10x_seconds,

        e.entry_price_sol_5m,
        e.capacity_5pct_usd_5m,
        date_diff('second', e.entry_state_time_5m,
            e.graduated_at + INTERVAL '5' MINUTE) AS entry_state_age_seconds_5m,
        COALESCE(t.future_trade_rows_5m, 0) AS future_trade_rows_5m,
        COALESCE(t.future_max_price_sol_5m / NULLIF(e.entry_price_sol_5m, 0), 0)
            AS remaining_max_5m,

        e.entry_price_sol_15m,
        e.capacity_5pct_usd_15m,
        date_diff('second', e.entry_state_time_15m,
            e.graduated_at + INTERVAL '15' MINUTE) AS entry_state_age_seconds_15m,
        COALESCE(t.future_trade_rows_15m, 0) AS future_trade_rows_15m,
        COALESCE(t.future_max_price_sol_15m / NULLIF(e.entry_price_sol_15m, 0), 0)
            AS remaining_max_15m,

        e.entry_price_sol_1h,
        e.capacity_5pct_usd_1h,
        date_diff('second', e.entry_state_time_1h,
            e.graduated_at + INTERVAL '1' HOUR) AS entry_state_age_seconds_1h,
        COALESCE(t.future_trade_rows_1h, 0) AS future_trade_rows_1h,
        COALESCE(t.future_max_price_sol_1h / NULLIF(e.entry_price_sol_1h, 0), 0)
            AS remaining_max_1h,

        e.entry_price_sol_4h,
        e.capacity_5pct_usd_4h,
        date_diff('second', e.entry_state_time_4h,
            e.graduated_at + INTERVAL '4' HOUR) AS entry_state_age_seconds_4h,
        COALESCE(t.future_trade_rows_4h, 0) AS future_trade_rows_4h,
        COALESCE(t.future_max_price_sol_4h / NULLIF(e.entry_price_sol_4h, 0), 0)
            AS remaining_max_4h,

        e.entry_price_sol_24h,
        e.capacity_5pct_usd_24h,
        date_diff('second', e.entry_state_time_24h,
            e.graduated_at + INTERVAL '24' HOUR) AS entry_state_age_seconds_24h,
        COALESCE(t.future_trade_rows_24h, 0) AS future_trade_rows_24h,
        COALESCE(t.future_max_price_sol_24h / NULLIF(e.entry_price_sol_24h, 0), 0)
            AS remaining_max_24h
    FROM delayed_entries e
    LEFT JOIN trade_rollup t ON t.mint = e.mint
)
SELECT *
FROM token_metrics
ORDER BY graduated_at, mint
