-- Audit the CLOB v2/v3 tables introduced after the 2026-04-28 cutover.

WITH fills AS (
    SELECT
        'v2' AS version,
        contract_address,
        evt_block_time,
        evt_block_date,
        maker,
        taker,
        orderHash,
        side,
        tokenId,
        makerAmountFilled,
        takerAmountFilled,
        fee,
        builder
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2026-04-01'

    UNION ALL

    SELECT
        'v3' AS version,
        contract_address,
        evt_block_time,
        evt_block_date,
        maker,
        taker,
        orderHash,
        side,
        tokenId,
        makerAmountFilled,
        takerAmountFilled,
        fee,
        builder
    FROM polymarket_v3_polygon.exchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2026-04-01'
)
SELECT
    version,
    to_hex(contract_address) AS contract_address,
    min(evt_block_time) AS min_executed_at,
    max(evt_block_time) AS max_executed_at,
    count(*) AS fill_events_n,
    approx_distinct(orderHash) AS orders_approx_n,
    approx_distinct(maker) AS makers_approx_n,
    approx_distinct(taker) AS takers_approx_n,
    approx_distinct(tokenId) AS outcome_tokens_approx_n,
    approx_distinct(builder) AS builders_approx_n,
    count_if(side = 0) AS maker_buy_events_n,
    count_if(side = 1) AS maker_sell_events_n,
    count_if(taker = contract_address) AS exchange_as_taker_n,
    count_if(maker = contract_address) AS exchange_as_maker_n,
    sum(
        CASE
            WHEN side = 0 THEN CAST(makerAmountFilled AS DOUBLE)
            ELSE CAST(takerAmountFilled AS DOUBLE)
        END
    ) / 1e6 AS collateral_volume_usd_raw,
    sum(CAST(fee AS DOUBLE)) / 1e6 AS fee_usd_raw
FROM fills
GROUP BY 1, 2
ORDER BY min_executed_at

