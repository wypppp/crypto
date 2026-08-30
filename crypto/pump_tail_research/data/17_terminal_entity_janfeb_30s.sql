-- Frozen point-in-time E1-core entity features. Contains no outcome or label.
WITH
constants AS (
    SELECT
        TIMESTAMP '2026-01-01 00:00:00' AS cohort_start,
        TIMESTAMP '2026-03-01 00:00:00' AS cohort_end
),
create_ranked AS (
    SELECT
        evt_block_time AS graduated_at,
        evt_block_date AS graduated_date,
        evt_tx_id AS graduation_tx,
        pool,
        base_mint AS mint,
        coin_creator,
        base_mint_decimals AS base_decimals,
        CAST(base_amount_in AS DOUBLE) AS base_amount_raw,
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
graduations AS (
    SELECT
        graduated_at, graduated_date, graduation_tx, pool, mint, coin_creator,
        base_decimals,
        base_amount_raw / power(10, base_decimals) AS initial_pool_base_tokens
    FROM create_ranked
    WHERE mint_creation_number = 1
),
curve_trades AS (
    SELECT
        g.mint,
        g.graduated_at,
        g.coin_creator,
        t.evt_block_time,
        t.evt_block_slot,
        t.evt_tx_index,
        t.evt_tx_id,
        t.user,
        t.evt_tx_signer,
        t.is_buy,
        CAST(t.token_amount AS DOUBLE) / power(10, g.base_decimals) AS token_amount
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_evt_tradeevent t
        ON t.mint = g.mint
       AND t.evt_block_time <= g.graduated_at
    WHERE t.evt_block_date BETWEEN DATE '2025-12-01' AND DATE '2026-02-28'
      AND t.user IS NOT NULL
      AND t.token_amount IS NOT NULL
      AND t.token_amount >= 0
),
curve_tx_users AS (
    SELECT
        mint, evt_tx_id,
        min(evt_block_time) AS tx_time,
        count(DISTINCT user) AS distinct_users
    FROM curve_trades
    GROUP BY 1, 2
    HAVING count(DISTINCT user) BETWEEN 2 AND 8
),
candidate_atomic_users AS (
    SELECT DISTINCT
        t.mint, t.user, t.evt_tx_id, x.tx_time
    FROM curve_trades t
    INNER JOIN curve_tx_users x
        ON x.mint = t.mint AND x.evt_tx_id = t.evt_tx_id
    INNER JOIN solana.transactions s
        ON s.block_date = CAST(t.evt_block_time AS DATE)
       AND s.id = t.evt_tx_id
       AND s.success
    WHERE contains(s.signers, t.user)
),
verified_atomic_groups AS (
    SELECT
        c.mint, c.evt_tx_id, min(c.tx_time) AS tx_time,
        count(DISTINCT c.user) AS verified_users,
        max(x.distinct_users) AS event_users
    FROM candidate_atomic_users c
    INNER JOIN curve_tx_users x
        ON x.mint = c.mint AND x.evt_tx_id = c.evt_tx_id
    GROUP BY 1, 2
    HAVING count(DISTINCT c.user) = max(x.distinct_users)
),
wallet_first_atomic AS (
    SELECT c.mint, c.user,
        min_by(c.evt_tx_id, ROW(c.tx_time, c.evt_tx_id)) AS atomic_tx_id
    FROM candidate_atomic_users c
    INNER JOIN verified_atomic_groups v
        ON v.mint = c.mint AND v.evt_tx_id = c.evt_tx_id
    GROUP BY 1, 2
),
wallet_positions_raw AS (
    SELECT
        mint,
        max(graduated_at) AS graduated_at,
        max(coin_creator) AS coin_creator,
        user,
        sum(CASE WHEN is_buy THEN token_amount ELSE -token_amount END) AS net_tokens,
        sum(CASE WHEN is_buy THEN token_amount ELSE 0 END) AS bought_tokens
    FROM curve_trades
    GROUP BY 1, 4
),
wallet_positions AS (
    SELECT
        w.*,
        greatest(w.net_tokens, 0.0) AS positive_tokens,
        a.atomic_tx_id,
        CASE WHEN a.atomic_tx_id IS NOT NULL
             THEN concat('atomic:', a.atomic_tx_id)
             ELSE concat('wallet:', w.user)
        END AS entity_key
    FROM wallet_positions_raw w
    LEFT JOIN wallet_first_atomic a
        ON a.mint = w.mint AND a.user = w.user
),
wallet_totals AS (
    SELECT
        mint,
        count(*) AS pretrade_wallet_count,
        count_if(positive_tokens > 0) AS positive_holder_wallet_count,
        sum(positive_tokens) AS positive_token_total,
        max(positive_tokens) AS top_wallet_tokens,
        sum(power(positive_tokens, 2)) AS wallet_token_squared_sum,
        sum(positive_tokens) FILTER (WHERE user = coin_creator) AS creator_positive_tokens
    FROM wallet_positions
    GROUP BY 1
),
entity_positions AS (
    SELECT
        mint, entity_key,
        sum(positive_tokens) AS entity_tokens,
        max(CASE WHEN user = coin_creator THEN 1 ELSE 0 END) AS creator_connected,
        max(CASE WHEN atomic_tx_id IS NOT NULL THEN 1 ELSE 0 END) AS atomic_linked,
        count(*) AS component_wallets
    FROM wallet_positions
    GROUP BY 1, 2
),
entity_totals AS (
    SELECT
        mint,
        count_if(entity_tokens > 0) AS entity_count,
        max(component_wallets) AS max_component_wallets,
        max(entity_tokens) AS top_entity_tokens,
        sum(power(entity_tokens, 2)) AS entity_token_squared_sum,
        sum(entity_tokens) FILTER (WHERE creator_connected = 1) AS creator_entity_tokens,
        sum(component_wallets) FILTER (WHERE atomic_linked = 1) AS atomic_linked_wallets,
        sum(entity_tokens) FILTER (WHERE atomic_linked = 1) AS atomic_linked_tokens
    FROM entity_positions
    GROUP BY 1
),
post_buys AS (
    SELECT
        g.mint,
        b.user,
        CAST(b.user_quote_amount_in AS DOUBLE) AS quote_amount_raw
    FROM graduations g
    INNER JOIN pumpdotfun_solana.pump_amm_evt_buyevent b
        ON b.pool = g.pool
       AND b.evt_block_time >= g.graduated_at
       AND b.evt_block_time <= g.graduated_at + INTERVAL '30' SECOND
    WHERE b.evt_block_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-01'
),
post_buy_entities AS (
    SELECT
        b.mint,
        COALESCE(w.entity_key, concat('wallet:', b.user)) AS entity_key,
        sum(b.quote_amount_raw) AS buy_quote_raw
    FROM post_buys b
    LEFT JOIN wallet_positions w
        ON w.mint = b.mint AND w.user = b.user
    GROUP BY 1, 2
),
post_buy_totals AS (
    SELECT
        mint,
        sum(buy_quote_raw) AS buy_quote_total,
        max(buy_quote_raw) AS max_entity_buy_quote,
        sum(power(buy_quote_raw, 2)) AS entity_buy_quote_squared_sum
    FROM post_buy_entities
    GROUP BY 1
)
SELECT
    g.graduated_at,
    g.mint,
    COALESCE(w.pretrade_wallet_count, 0) AS pretrade_wallet_count,
    COALESCE(w.positive_holder_wallet_count, 0) AS positive_holder_wallet_count,
    COALESCE(w.top_wallet_tokens / NULLIF(w.positive_token_total, 0), 0.0)
        AS pre_top_wallet_holding_share,
    COALESCE(w.wallet_token_squared_sum / NULLIF(power(w.positive_token_total, 2), 0), 0.0)
        AS pre_wallet_holding_hhi,
    COALESCE(w.creator_positive_tokens / NULLIF(w.positive_token_total, 0), 0.0)
        AS pre_creator_holding_share,
    COALESCE(e.entity_count, 0) AS entity_count,
    COALESCE(w.positive_holder_wallet_count / NULLIF(CAST(e.entity_count AS DOUBLE), 0), 1.0)
        AS wallet_to_entity_ratio,
    COALESCE(e.top_entity_tokens / NULLIF(w.positive_token_total, 0), 0.0)
        AS top_entity_holding_share,
    COALESCE(e.entity_token_squared_sum / NULLIF(power(w.positive_token_total, 2), 0), 0.0)
        AS entity_holding_hhi,
    COALESCE(e.creator_entity_tokens / NULLIF(w.positive_token_total, 0), 0.0)
        AS creator_connected_entity_holding_share,
    COALESCE(e.atomic_linked_wallets / NULLIF(CAST(w.pretrade_wallet_count AS DOUBLE), 0), 0.0)
        AS atomic_linked_wallet_share,
    COALESCE(e.atomic_linked_tokens / NULLIF(w.positive_token_total, 0), 0.0)
        AS atomic_linked_holding_share,
    COALESCE(e.max_component_wallets, 1) AS max_component_wallets,
    COALESCE(e.top_entity_tokens / NULLIF(g.initial_pool_base_tokens, 0), 0.0)
        AS top_entity_sellable_to_pool_base_ratio,
    COALESCE(p.max_entity_buy_quote / NULLIF(p.buy_quote_total, 0), 0.0)
        AS entity_max_buy_volume_share_5m,
    COALESCE(p.entity_buy_quote_squared_sum / NULLIF(power(p.buy_quote_total, 2), 0), 0.0)
        AS entity_buy_volume_hhi_5m,
    COALESCE(
        (e.top_entity_tokens - w.top_wallet_tokens) / NULLIF(w.positive_token_total, 0),
        0.0
    ) AS entity_merge_delta_top_holding_share,
    COALESCE(
        (e.entity_token_squared_sum - w.wallet_token_squared_sum)
            / NULLIF(power(w.positive_token_total, 2), 0),
        0.0
    ) AS entity_merge_delta_holding_hhi,
    CASE WHEN e.atomic_linked_wallets > 0 THEN 1.0 ELSE 0.0 END
        AS entity_atomic_coverage_flag,
    CAST(NULL AS DOUBLE) AS direct_funder_linked_holding_share,
    CAST(NULL AS DOUBLE) AS creator_funded_holding_share,
    CAST(NULL AS DOUBLE) AS jito_bundle_linked_holding_share
FROM graduations g
LEFT JOIN wallet_totals w ON w.mint = g.mint
LEFT JOIN entity_totals e ON e.mint = g.mint
LEFT JOIN post_buy_totals p ON p.mint = g.mint
ORDER BY g.graduated_at, g.mint
