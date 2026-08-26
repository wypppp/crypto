-- Audit simple and high-turnover wallets from the first 90-day cohort result.

WITH target(wallet) AS (
    VALUES
        (0x482284A310C716C4723517614E9E76665F0EE801),
        (0xF92EF6A0EF0E71095AF5B07CFEF7D60D34B70131),
        (0xBEB4CE12A45775B2219DE309CBB9A79034C5DE5D),
        (0x7D72C16DE1BDDA6865C23F0C3B4D93AAE698D034),
        (0x81F58B61C1DF6DABF5B4141BBA2168F4240FC44E),
        (0x0CB85BE1B9BFC5291E3DF24B7969F6FB292D4484),
        (0xD18AA9F4B13FF514F168314FF61E0CA7F9424B74)
),
condition_resolutions AS (
    SELECT
        lower(to_hex(conditionId)) AS condition_key,
        max(evt_block_time) AS onchain_resolution_time
    FROM polymarket_polygon.ctf_evt_conditionresolution
    WHERE evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
    GROUP BY 1
),
md_raw AS (
    SELECT
        token_id,
        max_by(condition_id, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS condition_id,
        max_by(question, coalesce(last_changed_at, TIMESTAMP '1970-01-01')) AS question,
        max_by(token_outcome_name, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS outcome_name,
        max_by(outcome_index, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS outcome_index,
        max_by(settlement_value, coalesce(last_changed_at, TIMESTAMP '1970-01-01'))
            AS settlement_value,
        max_by(tags, coalesce(last_changed_at, TIMESTAMP '1970-01-01')) AS tags
    FROM polymarket_polygon.market_details
    GROUP BY 1
),
md AS (
    SELECT
        m.*,
        r.onchain_resolution_time AS resolved_on_timestamp
    FROM md_raw m
    LEFT JOIN condition_resolutions r
        ON r.condition_key = replace(lower(m.condition_id), '0x', '')
),
trades AS (
    SELECT
        v.*,
        CASE
            WHEN side = 0 THEN CAST(takerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(makerAmountFilled AS DOUBLE) / 1e6
        END AS qty,
        CASE
            WHEN side = 0 THEN CAST(makerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(takerAmountFilled AS DOUBLE) / 1e6
        END AS collateral
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled v
    JOIN target t ON t.wallet = v.maker
    WHERE v.evt_block_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-06'
)
SELECT
    to_hex(t.maker) AS wallet,
    min(t.evt_block_time) AS first_fill_time,
    max(t.evt_block_time) AS last_fill_time,
    CASE WHEN t.side = 0 THEN 'BUY' ELSE 'SELL' END AS side,
    CAST(t.tokenId AS VARCHAR) AS token_id,
    count(*) AS fill_events_n,
    sum(t.qty) AS qty,
    sum(t.collateral) AS collateral,
    sum(t.collateral) / nullif(sum(t.qty), 0) AS weighted_price,
    sum(CAST(t.fee AS DOUBLE)) / 1e6 AS fee,
    sum(
        CASE
            WHEN t.side = 0
                THEN m.settlement_value * t.qty - t.collateral
                    - CAST(t.fee AS DOUBLE) / 1e6
            ELSE t.collateral - m.settlement_value * t.qty
                    - CAST(t.fee AS DOUBLE) / 1e6
        END
    ) AS resolved_trade_pnl,
    to_hex(t.builder) AS builder,
    m.question,
    m.outcome_name,
    m.outcome_index,
    m.settlement_value,
    m.resolved_on_timestamp,
    m.tags
FROM trades t
LEFT JOIN md m ON m.token_id = t.tokenId
GROUP BY
    t.maker,
    t.side,
    t.tokenId,
    t.builder,
    m.question,
    m.outcome_name,
    m.outcome_index,
    m.settlement_value,
    m.resolved_on_timestamp,
    m.tags
ORDER BY wallet, first_fill_time, token_id, side
