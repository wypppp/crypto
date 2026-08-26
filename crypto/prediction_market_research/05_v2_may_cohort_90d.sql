-- Complete one-week entry cohort under the CLOB v2 regime.
-- Cohort: first-ever observed maker fill from 2026-05-01 through 2026-05-07 UTC.
-- Horizon: exactly 90 days after each wallet's first fill.
--
-- Capital is a conservative trade-ledger estimate. It treats net token sales as
-- fully collateralized shorts and does not yet credit user-initiated merge cash,
-- maker rebates, or rewards. Wallets touching v3 are flagged because v3 market
-- metadata is not yet available in polymarket_polygon.market_details.

WITH
v2_first AS (
    SELECT maker AS wallet, min(evt_block_time) AS first_trade_time
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date BETWEEN DATE '2026-04-01' AND DATE '2026-05-07'
    GROUP BY 1
),
candidate AS (
    SELECT wallet, first_trade_time
    FROM v2_first
    WHERE first_trade_time >= TIMESTAMP '2026-05-01 00:00:00'
      AND first_trade_time < TIMESTAMP '2026-05-08 00:00:00'
),
old_seen AS (
    SELECT DISTINCT maker AS wallet
    FROM polymarket_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date < DATE '2026-05-01'
      AND maker IN (SELECT wallet FROM candidate)

    UNION

    SELECT DISTINCT maker AS wallet
    FROM polymarket_polygon.negriskctfexchange_evt_orderfilled
    WHERE evt_block_date < DATE '2026-05-01'
      AND maker IN (SELECT wallet FROM candidate)
),
cohort AS (
    SELECT
        c.wallet,
        c.first_trade_time,
        c.first_trade_time + INTERVAL '90' DAY AS horizon_time
    FROM candidate c
    LEFT JOIN old_seen o ON o.wallet = c.wallet
    WHERE o.wallet IS NULL
),
v3_users AS (
    SELECT DISTINCT v.maker AS wallet
    FROM polymarket_v3_polygon.exchange_evt_orderfilled v
    JOIN cohort c ON c.wallet = v.maker
    WHERE v.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
      AND v.evt_block_time <= c.horizon_time
),
raw_trades AS (
    SELECT
        c.wallet,
        c.first_trade_time,
        c.horizon_time,
        v.contract_address,
        v.evt_block_time,
        v.evt_tx_hash,
        v.evt_index,
        v.side,
        v.tokenId AS token_id,
        CASE
            WHEN v.side = 0 THEN CAST(v.takerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(v.makerAmountFilled AS DOUBLE) / 1e6
        END AS qty,
        CASE
            WHEN v.side = 0 THEN CAST(v.makerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(v.takerAmountFilled AS DOUBLE) / 1e6
        END AS collateral,
        CAST(v.fee AS DOUBLE) / 1e6 AS fee
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled v
    JOIN cohort c ON c.wallet = v.maker
    WHERE v.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
      AND v.evt_block_time >= c.first_trade_time
      AND v.evt_block_time <= c.horizon_time
),
trade_deltas AS (
    SELECT
        *,
        CASE WHEN side = 0 THEN qty ELSE -qty END AS position_delta,
        CASE
            WHEN side = 0 THEN -collateral - fee
            ELSE collateral - fee
        END AS base_cash_delta,
        CASE
            WHEN side = 0 THEN collateral + fee
            ELSE greatest(qty - collateral + fee, 0)
        END AS entry_risk
    FROM raw_trades
    WHERE qty > 0
      AND collateral >= 0
),
position_running AS (
    SELECT
        *,
        sum(position_delta) OVER (
            PARTITION BY wallet, token_id
            ORDER BY evt_block_time, evt_tx_hash, evt_index
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_position
    FROM trade_deltas
),
short_running AS (
    SELECT
        *,
        greatest(-cumulative_position, 0) AS short_collateral,
        lag(greatest(-cumulative_position, 0), 1, 0e0) OVER (
            PARTITION BY wallet, token_id
            ORDER BY evt_block_time, evt_tx_hash, evt_index
        ) AS previous_short_collateral
    FROM position_running
),
trade_ledger AS (
    SELECT
        *,
        base_cash_delta - (short_collateral - previous_short_collateral)
            AS economic_cash_delta,
        row_number() OVER (
            PARTITION BY wallet, token_id
            ORDER BY evt_block_time DESC, evt_tx_hash DESC, evt_index DESC
        ) AS reverse_trade_n
    FROM short_running
),
token_ends AS (
    SELECT
        wallet,
        first_trade_time,
        horizon_time,
        token_id,
        cumulative_position AS ending_position,
        evt_block_time AS last_trade_time
    FROM trade_ledger
    WHERE reverse_trade_n = 1
),
condition_resolutions AS (
    SELECT
        lower(to_hex(conditionId)) AS condition_key,
        max(evt_block_time) AS onchain_resolution_time
    FROM polymarket_polygon.ctf_evt_conditionresolution
    WHERE evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
    GROUP BY 1
),
market_metadata_raw AS (
    SELECT
        token_id,
        max_by(condition_id, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS condition_id,
        max_by(outcome_index, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS outcome_index,
        max_by(settlement_value, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS settlement_value,
        max_by(tags, coalesce(last_changed_at, TIMESTAMP '1970-01-01')) AS tags
    FROM polymarket_polygon.market_details
    GROUP BY 1
),
market_metadata AS (
    SELECT
        m.*,
        r.onchain_resolution_time AS resolved_on_timestamp
    FROM market_metadata_raw m
    LEFT JOIN condition_resolutions r
        ON r.condition_key = replace(lower(m.condition_id), '0x', '')
),
token_states AS (
    SELECT
        t.*,
        m.condition_id,
        m.outcome_index,
        m.settlement_value,
        m.resolved_on_timestamp,
        m.tags,
        m.resolved_on_timestamp IS NOT NULL
            AND m.resolved_on_timestamp <= t.horizon_time AS resolved_by_horizon
    FROM token_ends t
    LEFT JOIN market_metadata m ON m.token_id = t.token_id
),
resolution_events AS (
    SELECT
        wallet,
        greatest(resolved_on_timestamp, last_trade_time)
            + INTERVAL '0.001' SECOND AS event_time,
        CASE
            WHEN ending_position >= 0
                THEN settlement_value * ending_position
            ELSE (1 - settlement_value) * (-ending_position)
        END AS cash_delta
    FROM token_states
    WHERE resolved_by_horizon
      AND settlement_value IS NOT NULL
      AND abs(ending_position) > 1e-9
),
unresolved_by_condition AS (
    SELECT
        wallet,
        condition_id,
        sum(
            CASE
                WHEN outcome_index = 0 AND ending_position >= 0 THEN ending_position
                WHEN outcome_index <> 0 AND ending_position < 0 THEN -ending_position
                ELSE 0
            END
        ) AS value_if_outcome_0,
        sum(
            CASE
                WHEN outcome_index = 1 AND ending_position >= 0 THEN ending_position
                WHEN outcome_index <> 1 AND ending_position < 0 THEN -ending_position
                ELSE 0
            END
        ) AS value_if_outcome_1
    FROM token_states
    WHERE NOT resolved_by_horizon
      AND condition_id IS NOT NULL
      AND outcome_index IN (0, 1)
      AND abs(ending_position) > 1e-9
    GROUP BY 1, 2
),
unresolved_values AS (
    SELECT
        wallet,
        sum(least(value_if_outcome_0, value_if_outcome_1)) AS unresolved_value_lower,
        sum(greatest(value_if_outcome_0, value_if_outcome_1)) AS unresolved_value_upper
    FROM unresolved_by_condition
    GROUP BY 1
),
capital_events AS (
    SELECT
        wallet,
        evt_block_time AS event_time,
        economic_cash_delta AS cash_delta,
        0 AS event_order
    FROM trade_ledger

    UNION ALL

    SELECT wallet, event_time, cash_delta, 1 AS event_order
    FROM resolution_events
),
cash_running AS (
    SELECT
        wallet,
        event_time,
        event_order,
        sum(cash_delta) OVER (
            PARTITION BY wallet
            ORDER BY event_time, event_order
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_cash
    FROM capital_events
),
capital_summary AS (
    SELECT
        wallet,
        greatest(-min(cumulative_cash), 0) AS capital_upper_bound,
        max(cumulative_cash) AS max_cumulative_cash,
        max_by(cumulative_cash, ROW(event_time, event_order)) AS ending_cash
    FROM cash_running
    GROUP BY 1
),
trade_summary AS (
    SELECT
        wallet,
        min(first_trade_time) AS first_trade_time,
        min(horizon_time) AS horizon_time,
        count(*) AS trade_events_n,
        count_if(side = 0) AS buy_events_n,
        count_if(side = 1) AS sell_events_n,
        count(DISTINCT token_id) AS token_ids_n,
        sum(collateral) AS collateral_turnover,
        sum(fee) AS fees_paid,
        sum(entry_risk) AS gross_entry_risk,
        max(entry_risk) AS max_single_entry_risk
    FROM trade_ledger
    GROUP BY 1
),
state_summary AS (
    SELECT
        wallet,
        count(*) AS ending_token_positions_n,
        count_if(resolved_by_horizon) AS resolved_token_positions_n,
        count_if(NOT resolved_by_horizon) AS unresolved_token_positions_n,
        count_if(condition_id IS NULL) AS metadata_missing_token_positions_n
    FROM token_states
    WHERE abs(ending_position) > 1e-9
    GROUP BY 1
),
resolution_cash AS (
    SELECT wallet, sum(cash_delta) AS resolution_cash
    FROM resolution_events
    GROUP BY 1
)
SELECT
    to_hex(t.wallet) AS wallet,
    t.first_trade_time,
    t.horizon_time,
    t.trade_events_n,
    t.buy_events_n,
    t.sell_events_n,
    t.token_ids_n,
    t.collateral_turnover,
    t.fees_paid,
    t.gross_entry_risk,
    t.max_single_entry_risk,
    c.capital_upper_bound,
    c.ending_cash,
    coalesce(r.resolution_cash, 0) AS resolution_cash,
    coalesce(u.unresolved_value_lower, 0) AS unresolved_value_lower,
    coalesce(u.unresolved_value_upper, 0) AS unresolved_value_upper,
    c.ending_cash + coalesce(u.unresolved_value_lower, 0) AS net_profit_lower,
    c.ending_cash + coalesce(u.unresolved_value_upper, 0) AS net_profit_upper,
    CASE
        WHEN c.capital_upper_bound > 0 THEN
            (c.capital_upper_bound + c.ending_cash
                + coalesce(u.unresolved_value_lower, 0)) / c.capital_upper_bound
    END AS return_multiple_lower,
    CASE
        WHEN c.capital_upper_bound > 0 THEN
            (c.capital_upper_bound + c.ending_cash
                + coalesce(u.unresolved_value_upper, 0)) / c.capital_upper_bound
    END AS return_multiple_upper,
    coalesce(s.ending_token_positions_n, 0) AS ending_token_positions_n,
    coalesce(s.resolved_token_positions_n, 0) AS resolved_token_positions_n,
    coalesce(s.unresolved_token_positions_n, 0) AS unresolved_token_positions_n,
    coalesce(s.metadata_missing_token_positions_n, 0)
        AS metadata_missing_token_positions_n,
    v.wallet IS NOT NULL AS touched_v3
FROM trade_summary t
JOIN capital_summary c ON c.wallet = t.wallet
LEFT JOIN unresolved_values u ON u.wallet = t.wallet
LEFT JOIN resolution_cash r ON r.wallet = t.wallet
LEFT JOIN state_summary s ON s.wallet = t.wallet
LEFT JOIN v3_users v ON v.wallet = t.wallet
