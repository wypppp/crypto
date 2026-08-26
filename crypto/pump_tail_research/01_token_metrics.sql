-- Pump.fun -> PumpSwap graduated-token universe and 30-day token-level metrics.
--
-- Frozen cohort: [2026-05-01 00:00:00 UTC, 2026-07-25 00:00:00 UTC).
-- Graduation requires a successful canonical PumpSwap CreatePoolEvent (index == 0)
-- emitted by a CPI whose outer executing program is Pump. The later-added
-- CompletePumpAmmMigrationEvent is deliberately not required because it has no
-- rows before 2026-05-21 and would truncate the frozen cohort.
--
-- Frozen outcome windows relative to graduation timestamp T:
--   max_30d: [T, T + 30d)
--   p7d:     last canonical-pool event in [T + 6d,  T + 7d)
--   p30d:    last canonical-pool event in [T + 29d, T + 30d)
--   N1:      canonical-pool volume in [T + 29d, T + 30d) >= $1,000
-- Missing p7d/p30d observations are emitted as zero, with observed flags.
--
-- Spot prices are reconstructed from post-swap pool reserves. Quote-leg volume is
-- converted with prices_external.hour; dex_solana.trades.amount_usd is never used.
-- Initial reserves and graduation price come from CreatePoolEvent, not later depth.

WITH
constants AS (
    SELECT
        TIMESTAMP '2026-05-01 00:00:00' AS cohort_start,
        TIMESTAMP '2026-07-25 00:00:00' AS cohort_end,
        'So11111111111111111111111111111111111111112' AS wsol_mint,
        'BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s' AS mayhem_agent
),
create_pool_events_ranked AS (
    SELECT
        evt_block_time AS graduated_at,
        evt_block_slot AS block_slot,
        evt_tx_index AS tx_index,
        evt_tx_id AS graduation_tx,
        pool,
        base_mint AS mint,
        quote_mint,
        base_mint_decimals AS base_decimals,
        quote_mint_decimals AS quote_decimals,
        CAST(base_amount_in AS DOUBLE) AS base_amount_in_raw,
        CAST(quote_amount_in AS DOUBLE) AS quote_amount_in_raw,
        is_mayhem_mode,
        row_number() OVER (
            PARTITION BY base_mint
            ORDER BY evt_block_time, evt_block_slot, evt_tx_index,
                     evt_inner_instruction_index, evt_tx_id
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
external_prices AS (
    SELECT
        timestamp,
        contract_address,
        max(price) AS price_usd
    FROM prices_external.hour
    WHERE blockchain = 'solana'
      AND timestamp >= TIMESTAMP '2026-05-01 00:00:00'
      AND timestamp < TIMESTAMP '2026-08-25 00:00:00'
    GROUP BY 1, 2
),
graduations AS (
    SELECT
        g.graduated_at,
        g.block_slot,
        g.graduation_tx,
        g.mint,
        g.pool,
        g.quote_mint,
        g.is_mayhem_mode,
        base_meta.name AS token_name,
        base_meta.symbol AS token_symbol,
        quote_meta.symbol AS quote_symbol,
        g.base_decimals,
        g.quote_decimals,
        g.base_amount_in_raw,
        g.quote_amount_in_raw,
        g.base_amount_in_raw / power(10, g.base_decimals) AS initial_base_reserve,
        g.quote_amount_in_raw / power(10, g.quote_decimals) AS initial_quote_reserve,
        quote_at_grad.price_usd AS quote_usd_at_graduation,
        sol_at_grad.price_usd AS sol_usd_at_graduation,
        CASE
            WHEN g.quote_mint = c.wsol_mint THEN 1.0
            ELSE quote_at_grad.price_usd / NULLIF(sol_at_grad.price_usd, 0)
        END AS quote_to_sol_at_graduation
    FROM graduations_raw g
    CROSS JOIN constants c
    LEFT JOIN tokens_solana.fungible base_meta
        ON base_meta.token_mint_address = g.mint
    LEFT JOIN tokens_solana.fungible quote_meta
        ON quote_meta.token_mint_address = g.quote_mint
    LEFT JOIN external_prices quote_at_grad
        ON quote_at_grad.timestamp = date_trunc('hour', g.graduated_at)
       AND quote_at_grad.contract_address = from_base58(g.quote_mint)
    LEFT JOIN external_prices sol_at_grad
        ON sol_at_grad.timestamp = date_trunc('hour', g.graduated_at)
       AND sol_at_grad.contract_address = from_base58(c.wsol_mint)
),
graduations_priced AS (
    SELECT
        g.*,
        initial_quote_reserve / NULLIF(initial_base_reserve, 0)
            AS graduation_price_quote,
        initial_quote_reserve / NULLIF(initial_base_reserve, 0)
            * quote_to_sol_at_graduation AS graduation_price_sol,
        initial_quote_reserve * quote_usd_at_graduation
            AS initial_quote_reserve_usd
    FROM graduations g
),
buy_trade_legs AS (
    SELECT
        g.mint,
        g.graduated_at,
        g.quote_mint,
        g.graduation_price_sol,
        b.evt_block_time AS block_time,
        b.evt_block_slot AS trade_block_slot,
        b.evt_tx_index AS trade_tx_index,
        b.evt_outer_instruction_index AS outer_instruction_index,
        b.evt_inner_instruction_index AS inner_instruction_index,
        b.evt_tx_id AS tx_id,
        b.user AS trader_id,
        CAST(b.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS post_base_reserve,
        CAST(b.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS post_quote_reserve,
        CAST(b.user_quote_amount_in AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_amount
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_buyevent b
        ON b.pool = g.pool
       AND b.evt_block_time >= g.graduated_at
       AND b.evt_block_time < g.graduated_at + INTERVAL '30' DAY
    WHERE b.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-23'
),
sell_trade_legs AS (
    SELECT
        g.mint,
        g.graduated_at,
        g.quote_mint,
        g.graduation_price_sol,
        s.evt_block_time AS block_time,
        s.evt_block_slot AS trade_block_slot,
        s.evt_tx_index AS trade_tx_index,
        s.evt_outer_instruction_index AS outer_instruction_index,
        s.evt_inner_instruction_index AS inner_instruction_index,
        s.evt_tx_id AS tx_id,
        s.user AS trader_id,
        CAST(s.pool_base_token_reserves AS DOUBLE) / power(10, g.base_decimals)
            AS post_base_reserve,
        CAST(s.pool_quote_token_reserves AS DOUBLE) / power(10, g.quote_decimals)
            AS post_quote_reserve,
        CAST(s.user_quote_amount_out AS DOUBLE) / power(10, g.quote_decimals)
            AS quote_amount
    FROM graduations_priced g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_sellevent s
        ON s.pool = g.pool
       AND s.evt_block_time >= g.graduated_at
       AND s.evt_block_time < g.graduated_at + INTERVAL '30' DAY
    WHERE s.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-23'
),
canonical_trade_legs AS (
    SELECT * FROM buy_trade_legs
    UNION ALL
    SELECT * FROM sell_trade_legs
),
canonical_trades AS (
    SELECT
        t.*,
        post_quote_reserve / NULLIF(post_base_reserve, 0) AS trade_price_quote,
        post_quote_reserve / NULLIF(post_base_reserve, 0)
            * CASE
                WHEN t.quote_mint = c.wsol_mint THEN 1.0
                ELSE quote_hour.price_usd / NULLIF(sol_hour.price_usd, 0)
              END AS trade_price_sol,
        quote_amount
            * CASE
                WHEN t.quote_mint = c.wsol_mint THEN 1.0
                ELSE quote_hour.price_usd / NULLIF(sol_hour.price_usd, 0)
              END AS trade_volume_sol,
        quote_amount * quote_hour.price_usd AS trade_volume_usd,
        t.trader_id <> c.mayhem_agent AS is_non_mayhem_agent
    FROM canonical_trade_legs t
    CROSS JOIN constants c
    LEFT JOIN external_prices quote_hour
        ON quote_hour.timestamp = date_trunc('hour', t.block_time)
       AND quote_hour.contract_address = from_base58(t.quote_mint)
    LEFT JOIN external_prices sol_hour
        ON sol_hour.timestamp = date_trunc('hour', t.block_time)
       AND sol_hour.contract_address = from_base58(c.wsol_mint)
    WHERE post_base_reserve > 0
      AND post_quote_reserve >= 0
      AND quote_amount >= 0
),
trade_rollup AS (
    SELECT
        mint,
        count(*) AS trade_rows_30d,
        count_if(trade_price_sol IS NOT NULL) AS priced_trade_rows_30d,
        count_if(trade_volume_usd IS NOT NULL) AS usd_priced_trade_rows_30d,
        count(DISTINCT trader_id) AS unique_traders_30d,
        count(DISTINCT trader_id) FILTER (WHERE is_non_mayhem_agent)
            AS unique_non_agent_traders_30d,
        max(trade_price_sol / NULLIF(graduation_price_sol, 0)) AS max_30d,
        max(trade_price_sol / NULLIF(graduation_price_sol, 0))
            FILTER (WHERE is_non_mayhem_agent) AS max_30d_non_agent,
        max(trade_price_sol / NULLIF(graduation_price_sol, 0))
            FILTER (WHERE trade_volume_sol >= 0.01) AS max_30d_min_001sol,
        max_by(
            trade_price_sol / NULLIF(graduation_price_sol, 0),
            ROW(trade_block_slot, trade_tx_index,
                COALESCE(outer_instruction_index, -1),
                COALESCE(inner_instruction_index, -1))
        ) FILTER (
            WHERE block_time >= graduated_at + INTERVAL '6' DAY
              AND block_time < graduated_at + INTERVAL '7' DAY
              AND trade_price_sol IS NOT NULL
        ) AS p7d_observation,
        max_by(
            trade_price_sol / NULLIF(graduation_price_sol, 0),
            ROW(trade_block_slot, trade_tx_index,
                COALESCE(outer_instruction_index, -1),
                COALESCE(inner_instruction_index, -1))
        ) FILTER (
            WHERE block_time >= graduated_at + INTERVAL '29' DAY
              AND block_time < graduated_at + INTERVAL '30' DAY
              AND trade_price_sol IS NOT NULL
        ) AS p30d_observation,
        count_if(block_time >= graduated_at + INTERVAL '6' DAY
            AND block_time < graduated_at + INTERVAL '7' DAY
            AND trade_price_sol IS NOT NULL) AS p7d_priced_trade_rows,
        count_if(block_time >= graduated_at + INTERVAL '29' DAY
            AND block_time < graduated_at + INTERVAL '30' DAY
            AND trade_price_sol IS NOT NULL) AS p30d_priced_trade_rows,
        count_if(block_time >= graduated_at + INTERVAL '29' DAY
            AND block_time < graduated_at + INTERVAL '30' DAY) AS day30_trade_rows,
        count_if(block_time >= graduated_at + INTERVAL '29' DAY
            AND block_time < graduated_at + INTERVAL '30' DAY
            AND trade_volume_usd IS NOT NULL) AS day30_usd_priced_trade_rows,
        sum(trade_volume_usd) FILTER (
            WHERE block_time >= graduated_at + INTERVAL '29' DAY
              AND block_time < graduated_at + INTERVAL '30' DAY
        ) AS day30_volume_usd,
        sum(trade_volume_usd) FILTER (
            WHERE block_time >= graduated_at + INTERVAL '29' DAY
              AND block_time < graduated_at + INTERVAL '30' DAY
              AND is_non_mayhem_agent
        ) AS day30_volume_usd_non_agent,
        count(DISTINCT trader_id) FILTER (
            WHERE block_time >= graduated_at + INTERVAL '29' DAY
              AND block_time < graduated_at + INTERVAL '30' DAY
        ) AS day30_unique_traders,
        count(DISTINCT trader_id) FILTER (
            WHERE block_time >= graduated_at + INTERVAL '29' DAY
              AND block_time < graduated_at + INTERVAL '30' DAY
              AND is_non_mayhem_agent
        ) AS day30_unique_non_agent_traders
    FROM canonical_trades
    GROUP BY 1
)
SELECT
    g.graduated_at,
    g.block_slot,
    g.graduation_tx,
    g.mint,
    g.pool,
    g.quote_mint,
    g.token_name,
    g.token_symbol,
    g.quote_symbol,
    g.base_decimals,
    g.quote_decimals,
    g.is_mayhem_mode,
    g.base_amount_in_raw,
    g.quote_amount_in_raw,
    g.initial_base_reserve,
    g.initial_quote_reserve,
    g.quote_usd_at_graduation,
    g.sol_usd_at_graduation,
    g.initial_quote_reserve_usd,
    g.graduation_price_quote,
    g.graduation_price_sol,
    COALESCE(r.trade_rows_30d, 0) AS trade_rows_30d,
    COALESCE(r.priced_trade_rows_30d, 0) AS priced_trade_rows_30d,
    COALESCE(r.usd_priced_trade_rows_30d, 0) AS usd_priced_trade_rows_30d,
    COALESCE(r.unique_traders_30d, 0) AS unique_traders_30d,
    COALESCE(r.unique_non_agent_traders_30d, 0) AS unique_non_agent_traders_30d,
    COALESCE(r.max_30d, 0) AS max_30d,
    COALESCE(r.max_30d_non_agent, 0) AS max_30d_non_agent,
    COALESCE(r.max_30d_min_001sol, 0) AS max_30d_min_001sol,
    COALESCE(r.p7d_observation, 0) AS p7d,
    COALESCE(r.p30d_observation, 0) AS p30d,
    COALESCE(r.p7d_priced_trade_rows, 0) > 0 AS p7d_observed,
    COALESCE(r.p30d_priced_trade_rows, 0) > 0 AS p30d_observed,
    COALESCE(r.day30_trade_rows, 0) AS day30_trade_rows,
    COALESCE(r.day30_usd_priced_trade_rows, 0) AS day30_usd_priced_trade_rows,
    COALESCE(r.day30_volume_usd, 0) AS day30_volume_usd,
    COALESCE(r.day30_volume_usd_non_agent, 0) AS day30_volume_usd_non_agent,
    COALESCE(r.day30_unique_traders, 0) AS day30_unique_traders,
    COALESCE(r.day30_unique_non_agent_traders, 0) AS day30_unique_non_agent_traders
FROM graduations_priced g
LEFT JOIN trade_rollup r ON r.mint = g.mint
ORDER BY g.graduated_at, g.mint
