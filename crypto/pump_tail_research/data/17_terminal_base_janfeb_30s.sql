-- Frozen T+5m feature extraction.  This query intentionally contains no label
-- and no event after T+5m.  Labels are joined locally from 08_delay_metrics.sql.

WITH
constants AS (
    SELECT
        TIMESTAMP '2026-01-01 00:00:00' AS cohort_start,
        TIMESTAMP '2026-03-01 00:00:00' AS cohort_end,
        'So11111111111111111111111111111111111111112' AS wsol_mint,
        'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' AS usdc_mint,
        'BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s' AS mayhem_agent
),
price_hours AS (
    SELECT timestamp, contract_address, max(price) AS price_usd
    FROM prices_external.hour
    CROSS JOIN constants c
    WHERE blockchain = 'solana'
      AND timestamp >= TIMESTAMP '2026-01-01 00:00:00'
      AND timestamp < TIMESTAMP '2026-03-02 00:00:00'
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
        coin_creator,
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
    WHERE evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-02-28'
      AND evt_block_time >= c.cohort_start
      AND evt_block_time < c.cohort_end
      AND evt_outer_executing_account =
          '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
),
graduations_raw AS (
    SELECT * FROM create_ranked WHERE mint_creation_number = 1
),
graduations AS (
    SELECT
        g.*,
        g.base_amount_raw / power(10, g.base_decimals) AS initial_base_reserve,
        g.quote_amount_raw / power(10, g.quote_decimals) AS initial_quote_reserve,
        g.quote_amount_raw / power(10, g.quote_decimals)
            / NULLIF(g.base_amount_raw / power(10, g.base_decimals), 0)
            AS graduation_price_quote,
        quote_hour.price_usd AS quote_usd_at_graduation,
        sol_hour.price_usd AS sol_usd_at_graduation
    FROM graduations_raw g
    CROSS JOIN constants c
    LEFT JOIN price_hours quote_hour
        ON quote_hour.timestamp = date_trunc('hour', g.graduated_at)
       AND quote_hour.contract_address = from_base58(g.quote_mint)
    LEFT JOIN price_hours sol_hour
        ON sol_hour.timestamp = date_trunc('hour', g.graduated_at)
       AND sol_hour.contract_address = from_base58(c.wsol_mint)
),
graduations_priced AS (
    SELECT
        g.*,
        graduation_price_quote
            * CASE WHEN quote_mint = c.wsol_mint THEN 1.0
                   ELSE quote_usd_at_graduation / NULLIF(sol_usd_at_graduation, 0) END
            AS graduation_price_sol,
        initial_quote_reserve * quote_usd_at_graduation AS initial_quote_reserve_usd
    FROM graduations g
    CROSS JOIN constants c
),
creator_history AS (
    SELECT
        current.mint,
        count(previous.mint) AS creator_prior_graduations
    FROM graduations_priced current
    LEFT JOIN graduations_priced previous
        ON previous.coin_creator = current.coin_creator
       AND previous.graduated_at < current.graduated_at
    GROUP BY 1
),
buy_legs AS (
    SELECT
        g.mint,
        g.pool,
        g.quote_mint,
        g.coin_creator,
        g.graduated_at,
        g.graduation_price_sol,
        g.base_decimals,
        g.quote_decimals,
        b.evt_block_time AS block_time,
        b.evt_block_slot AS block_slot,
        b.evt_tx_index AS tx_index,
        b.evt_outer_instruction_index AS outer_index,
        b.evt_inner_instruction_index AS inner_index,
        b.user,
        true AS is_buy,
        CAST(b.user_quote_amount_in AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_amount,
        CAST(b.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS post_base_reserve,
        CAST(b.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS post_quote_reserve
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_buyevent b
        ON b.pool = g.pool
       AND b.evt_block_time >= g.graduated_at
       AND b.evt_block_time <= g.graduated_at + INTERVAL '30' SECOND
    WHERE b.evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-01'
),
sell_legs AS (
    SELECT
        g.mint,
        g.pool,
        g.quote_mint,
        g.coin_creator,
        g.graduated_at,
        g.graduation_price_sol,
        g.base_decimals,
        g.quote_decimals,
        s.evt_block_time AS block_time,
        s.evt_block_slot AS block_slot,
        s.evt_tx_index AS tx_index,
        s.evt_outer_instruction_index AS outer_index,
        s.evt_inner_instruction_index AS inner_index,
        s.user,
        false AS is_buy,
        CAST(s.user_quote_amount_out AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_amount,
        CAST(s.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS post_base_reserve,
        CAST(s.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS post_quote_reserve
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_sellevent s
        ON s.pool = g.pool
       AND s.evt_block_time >= g.graduated_at
       AND s.evt_block_time <= g.graduated_at + INTERVAL '30' SECOND
    WHERE s.evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-01'
),
trade_legs AS (
    SELECT * FROM buy_legs
    UNION ALL
    SELECT * FROM sell_legs
),
trades AS (
    SELECT
        t.*,
        date_diff('second', t.graduated_at, t.block_time) AS seconds_since_graduation,
        t.post_quote_reserve / NULLIF(t.post_base_reserve, 0)
            * CASE WHEN t.quote_mint = c.wsol_mint THEN 1.0
                   ELSE quote_hour.price_usd / NULLIF(sol_hour.price_usd, 0) END
            AS trade_price_sol,
        t.quote_amount * quote_hour.price_usd AS volume_usd,
        t.user <> c.mayhem_agent AS is_non_agent,
        t.user = t.coin_creator AS is_creator
    FROM trade_legs t
    CROSS JOIN constants c
    LEFT JOIN price_hours quote_hour
        ON quote_hour.timestamp = date_trunc('hour', t.block_time)
       AND quote_hour.contract_address = from_base58(t.quote_mint)
    LEFT JOIN price_hours sol_hour
        ON sol_hour.timestamp = date_trunc('hour', t.block_time)
       AND sol_hour.contract_address = from_base58(c.wsol_mint)
    WHERE t.post_base_reserve > 0
      AND t.post_quote_reserve >= 0
      AND t.quote_amount >= 0
),
trade_rollup AS (
    SELECT
        mint,
        count(*) AS trade_count_5m,
        count_if(is_buy) AS buy_count_5m,
        count_if(NOT is_buy) AS sell_count_5m,
        count(DISTINCT user) AS unique_traders_5m,
        count(DISTINCT user) FILTER (WHERE is_buy) AS unique_buyers_5m,
        count(DISTINCT user) FILTER (WHERE NOT is_buy) AS unique_sellers_5m,
        count_if(is_non_agent) AS non_agent_trade_count_5m,
        count(DISTINCT user) FILTER (WHERE is_non_agent) AS non_agent_unique_traders_5m,
        count_if(is_creator AND is_buy) AS creator_buy_count_5m,
        count_if(is_creator AND NOT is_buy) AS creator_sell_count_5m,
        sum(volume_usd) AS volume_usd_5m,
        sum(volume_usd) FILTER (WHERE is_buy) AS buy_volume_usd_5m,
        sum(volume_usd) FILTER (WHERE NOT is_buy) AS sell_volume_usd_5m,
        sum(volume_usd) FILTER (WHERE is_non_agent) AS non_agent_volume_usd_5m,
        sum(volume_usd) FILTER (WHERE is_creator AND is_buy) AS creator_buy_volume_usd_5m,
        sum(volume_usd) FILTER (WHERE is_creator AND NOT is_buy) AS creator_sell_volume_usd_5m,

        count_if(seconds_since_graduation <= 60) AS trade_count_0_1m,
        count_if(seconds_since_graduation > 60 AND seconds_since_graduation <= 180)
            AS trade_count_1_3m,
        count_if(seconds_since_graduation > 180) AS trade_count_3_5m,
        sum(volume_usd) FILTER (WHERE seconds_since_graduation <= 60)
            AS volume_usd_0_1m,
        sum(volume_usd) FILTER (
            WHERE seconds_since_graduation > 60 AND seconds_since_graduation <= 180
        ) AS volume_usd_1_3m,
        sum(volume_usd) FILTER (WHERE seconds_since_graduation > 180)
            AS volume_usd_3_5m,

        max(trade_price_sol / NULLIF(graduation_price_sol, 0)) AS max_price_ratio_5m,
        min(trade_price_sol / NULLIF(graduation_price_sol, 0)) AS min_price_ratio_5m,
        max_by(
            seconds_since_graduation,
            ROW(
                trade_price_sol / NULLIF(graduation_price_sol, 0),
                -block_slot, -tx_index, -COALESCE(outer_index, -1),
                -COALESCE(inner_index, -1)
            )
        ) AS seconds_to_peak_5m
    FROM trades
    GROUP BY 1
),
wallet_rollup AS (
    SELECT mint, user, sum(volume_usd) AS wallet_volume_usd
    FROM trades
    GROUP BY 1, 2
),
wallet_features AS (
    SELECT
        mint,
        max(wallet_volume_usd) AS max_wallet_volume_usd,
        sum(power(wallet_volume_usd, 2)) AS wallet_volume_squared_sum
    FROM wallet_rollup
    GROUP BY 1
),
create_states AS (
    SELECT
        mint, pool, quote_mint, graduated_at,
        graduation_block_slot AS block_slot,
        graduation_tx_index AS tx_index,
        graduation_outer_index AS outer_index,
        graduation_inner_index AS inner_index,
        graduated_at AS state_time,
        graduation_price_quote AS state_price_quote,
        initial_quote_reserve AS state_quote_reserve
    FROM graduations_priced
),
trade_states AS (
    SELECT
        mint, pool, quote_mint, graduated_at, block_slot, tx_index,
        outer_index, inner_index, block_time AS state_time,
        post_quote_reserve / NULLIF(post_base_reserve, 0) AS state_price_quote,
        post_quote_reserve AS state_quote_reserve
    FROM trade_legs
),
deposit_states AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.graduated_at,
        d.evt_block_slot AS block_slot, d.evt_tx_index AS tx_index,
        d.evt_outer_instruction_index AS outer_index,
        d.evt_inner_instruction_index AS inner_index,
        d.evt_block_time AS state_time,
        (CAST(d.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals))
            / NULLIF(CAST(d.pool_base_token_reserves AS DOUBLE)
                / power(10, g.base_decimals), 0) AS state_price_quote,
        CAST(d.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS state_quote_reserve
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_depositevent d
        ON d.pool = g.pool
       AND d.evt_block_time >= g.graduated_at
       AND d.evt_block_time <= g.graduated_at + INTERVAL '30' SECOND
    WHERE d.evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-01'
),
withdraw_states AS (
    SELECT
        g.mint, g.pool, g.quote_mint, g.graduated_at,
        w.evt_block_slot AS block_slot, w.evt_tx_index AS tx_index,
        w.evt_outer_instruction_index AS outer_index,
        w.evt_inner_instruction_index AS inner_index,
        w.evt_block_time AS state_time,
        (CAST(w.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals))
            / NULLIF(CAST(w.pool_base_token_reserves AS DOUBLE)
                / power(10, g.base_decimals), 0) AS state_price_quote,
        CAST(w.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS state_quote_reserve
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_withdrawevent w
        ON w.pool = g.pool
       AND w.evt_block_time >= g.graduated_at
       AND w.evt_block_time <= g.graduated_at + INTERVAL '30' SECOND
    WHERE w.evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-01'
),
pool_states AS (
    SELECT * FROM create_states
    UNION ALL SELECT * FROM trade_states
    UNION ALL SELECT * FROM deposit_states
    UNION ALL SELECT * FROM withdraw_states
),
state_snapshots AS (
    SELECT
        mint,
        max_by(state_price_quote, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1))) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '30' SECOND
        ) AS price_quote_30s,
        max_by(state_price_quote, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1))) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '1' MINUTE
        ) AS price_quote_1m,
        max_by(state_price_quote, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1))) FILTER (
            WHERE state_time <= graduated_at + INTERVAL '3' MINUTE
        ) AS price_quote_3m,
        max_by(state_price_quote, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1))) AS price_quote_5m,
        max_by(state_quote_reserve, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1))) AS quote_reserve_5m,
        max_by(state_time, ROW(block_slot, tx_index,
            COALESCE(outer_index, -1), COALESCE(inner_index, -1))) AS state_time_5m
    FROM pool_states
    WHERE state_price_quote IS NOT NULL
      AND state_quote_reserve >= 0
    GROUP BY 1
),
liquidity_rollup AS (
    SELECT
        mint,
        sum(deposit_count) AS deposit_count_5m,
        sum(withdraw_count) AS withdraw_count_5m,
        sum(deposit_quote_amount) AS deposit_quote_amount_5m,
        sum(withdraw_quote_amount) AS withdraw_quote_amount_5m
    FROM (
        SELECT
            g.mint, 1 AS deposit_count, 0 AS withdraw_count,
            CAST(d.quote_amount_in AS DOUBLE) / power(10, g.quote_decimals)
                AS deposit_quote_amount,
            0.0 AS withdraw_quote_amount
        FROM graduations_priced g
        INNER JOIN pumpdotfun_solana.pump_amm_evt_depositevent d
            ON d.pool = g.pool
           AND d.evt_block_time >= g.graduated_at
           AND d.evt_block_time <= g.graduated_at + INTERVAL '30' SECOND
        WHERE d.evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-01'
        UNION ALL
        SELECT
            g.mint, 0, 1, 0.0,
            CAST(w.quote_amount_out AS DOUBLE) / power(10, g.quote_decimals)
        FROM graduations_priced g
        INNER JOIN pumpdotfun_solana.pump_amm_evt_withdrawevent w
            ON w.pool = g.pool
           AND w.evt_block_time >= g.graduated_at
           AND w.evt_block_time <= g.graduated_at + INTERVAL '30' SECOND
        WHERE w.evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-01'
    ) x
    GROUP BY 1
),
features_raw AS (
    SELECT
        g.graduated_at, g.mint, g.pool, g.quote_mint,
        g.quote_mint = c.wsol_mint AS quote_is_wsol,
        g.initial_quote_reserve_usd,
        h.creator_prior_graduations,
        COALESCE(t.trade_count_5m, 0) AS trade_count_5m,
        COALESCE(t.buy_count_5m, 0) AS buy_count_5m,
        COALESCE(t.sell_count_5m, 0) AS sell_count_5m,
        COALESCE(t.unique_traders_5m, 0) AS unique_traders_5m,
        COALESCE(t.unique_buyers_5m, 0) AS unique_buyers_5m,
        COALESCE(t.unique_sellers_5m, 0) AS unique_sellers_5m,
        COALESCE(t.non_agent_trade_count_5m, 0) AS non_agent_trade_count_5m,
        COALESCE(t.non_agent_unique_traders_5m, 0) AS non_agent_unique_traders_5m,
        COALESCE(t.creator_buy_count_5m, 0) AS creator_buy_count_5m,
        COALESCE(t.creator_sell_count_5m, 0) AS creator_sell_count_5m,
        COALESCE(t.volume_usd_5m, 0) AS volume_usd_5m,
        COALESCE(t.buy_volume_usd_5m, 0) AS buy_volume_usd_5m,
        COALESCE(t.sell_volume_usd_5m, 0) AS sell_volume_usd_5m,
        COALESCE(t.non_agent_volume_usd_5m, 0) AS non_agent_volume_usd_5m,
        COALESCE(t.creator_buy_volume_usd_5m, 0) AS creator_buy_volume_usd_5m,
        COALESCE(t.creator_sell_volume_usd_5m, 0) AS creator_sell_volume_usd_5m,
        COALESCE(t.trade_count_0_1m, 0) AS trade_count_0_1m,
        COALESCE(t.trade_count_1_3m, 0) AS trade_count_1_3m,
        COALESCE(t.trade_count_3_5m, 0) AS trade_count_3_5m,
        COALESCE(t.volume_usd_0_1m, 0) AS volume_usd_0_1m,
        COALESCE(t.volume_usd_1_3m, 0) AS volume_usd_1_3m,
        COALESCE(t.volume_usd_3_5m, 0) AS volume_usd_3_5m,
        COALESCE(t.max_price_ratio_5m, 1) AS max_price_ratio_5m,
        COALESCE(t.min_price_ratio_5m, 1) AS min_price_ratio_5m,
        COALESCE(t.seconds_to_peak_5m, 0) AS seconds_to_peak_5m,
        COALESCE(w.max_wallet_volume_usd, 0) AS max_wallet_volume_usd,
        COALESCE(w.wallet_volume_squared_sum, 0) AS wallet_volume_squared_sum,
        s.price_quote_30s / NULLIF(g.graduation_price_quote, 0) AS price_ratio_30s,
        s.price_quote_1m / NULLIF(g.graduation_price_quote, 0) AS price_ratio_1m,
        s.price_quote_3m / NULLIF(g.graduation_price_quote, 0) AS price_ratio_3m,
        s.price_quote_5m / NULLIF(g.graduation_price_quote, 0) AS price_ratio_5m,
        s.quote_reserve_5m * quote_5m.price_usd AS quote_reserve_usd_5m,
        date_diff('second', s.state_time_5m,
            g.graduated_at + INTERVAL '30' SECOND) AS state_age_seconds_5m,
        COALESCE(l.deposit_count_5m, 0) AS deposit_count_5m,
        COALESCE(l.withdraw_count_5m, 0) AS withdraw_count_5m,
        COALESCE(l.deposit_quote_amount_5m, 0) * quote_5m.price_usd
            AS deposit_quote_usd_5m,
        COALESCE(l.withdraw_quote_amount_5m, 0) * quote_5m.price_usd
            AS withdraw_quote_usd_5m
    FROM graduations_priced g
    CROSS JOIN constants c
    INNER JOIN creator_history h ON h.mint = g.mint
    INNER JOIN state_snapshots s ON s.mint = g.mint
    LEFT JOIN trade_rollup t ON t.mint = g.mint
    LEFT JOIN wallet_features w ON w.mint = g.mint
    LEFT JOIN liquidity_rollup l ON l.mint = g.mint
    LEFT JOIN price_hours quote_5m
        ON quote_5m.timestamp = date_trunc('hour', g.graduated_at + INTERVAL '30' SECOND)
       AND quote_5m.contract_address = from_base58(g.quote_mint)
),
features AS (
    SELECT
        *,
        0.05 * quote_reserve_usd_5m AS capacity_5pct_usd_5m,
        quote_reserve_usd_5m / NULLIF(initial_quote_reserve_usd, 0)
            AS quote_reserve_ratio_5m,
        buy_volume_usd_5m / NULLIF(volume_usd_5m, 0) AS buy_volume_share_5m,
        (buy_volume_usd_5m - sell_volume_usd_5m) / NULLIF(volume_usd_5m, 0)
            AS net_buy_share_5m,
        non_agent_volume_usd_5m / NULLIF(volume_usd_5m, 0)
            AS non_agent_volume_share_5m,
        max_wallet_volume_usd / NULLIF(volume_usd_5m, 0)
            AS max_wallet_volume_share_5m,
        wallet_volume_squared_sum / NULLIF(power(volume_usd_5m, 2), 0)
            AS wallet_volume_hhi_5m
    FROM features_raw
)
SELECT *
FROM features
ORDER BY graduated_at, mint
