-- Coverage audit for Polymarket's two Polygon CLOB contracts.
-- makerAssetId or takerAssetId = 0 denotes USDC collateral.

WITH fills AS (
    SELECT
        'ctf' AS exchange_type,
        evt_block_time,
        evt_block_date,
        maker,
        taker,
        orderHash,
        makerAssetId,
        takerAssetId,
        makerAmountFilled,
        takerAmountFilled,
        fee
    FROM polymarket_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2024-01-01'

    UNION ALL

    SELECT
        'neg_risk' AS exchange_type,
        evt_block_time,
        evt_block_date,
        maker,
        taker,
        orderHash,
        makerAssetId,
        takerAssetId,
        makerAmountFilled,
        takerAmountFilled,
        fee
    FROM polymarket_polygon.negriskctfexchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2024-01-01'
)
SELECT
    exchange_type,
    min(evt_block_time) AS min_executed_at,
    max(evt_block_time) AS max_executed_at,
    count(*) AS fill_events_n,
    approx_distinct(orderHash) AS orders_approx_n,
    approx_distinct(maker) AS makers_approx_n,
    approx_distinct(taker) AS takers_approx_n,
    sum(
        CASE
            WHEN makerAssetId = UINT256 '0'
                THEN CAST(makerAmountFilled AS DOUBLE) / 1e6
            WHEN takerAssetId = UINT256 '0'
                THEN CAST(takerAmountFilled AS DOUBLE) / 1e6
            ELSE 0
        END
    ) AS collateral_volume_usd,
    count_if(makerAssetId = UINT256 '0') AS maker_buys_n,
    count_if(takerAssetId = UINT256 '0') AS taker_buys_n,
    count_if(makerAssetId <> UINT256 '0' AND takerAssetId <> UINT256 '0')
        AS non_collateral_pair_n,
    sum(CAST(fee AS DOUBLE)) / 1e6 AS raw_fee_scaled_1e6
FROM fills
GROUP BY 1
ORDER BY fill_events_n DESC

