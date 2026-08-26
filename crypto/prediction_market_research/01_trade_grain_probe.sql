-- Inspect raw OrderFilled row grain, price construction, and token registration.

WITH fills AS (
    SELECT
        'ctf' AS exchange_type,
        evt_block_time,
        evt_tx_hash,
        evt_index,
        maker,
        taker,
        orderHash,
        makerAssetId,
        takerAssetId,
        makerAmountFilled,
        takerAmountFilled,
        fee
    FROM polymarket_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2026-08-01'

    UNION ALL

    SELECT
        'neg_risk' AS exchange_type,
        evt_block_time,
        evt_tx_hash,
        evt_index,
        maker,
        taker,
        orderHash,
        makerAssetId,
        takerAssetId,
        makerAmountFilled,
        takerAmountFilled,
        fee
    FROM polymarket_polygon.negriskctfexchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2026-08-01'
), normalized AS (
    SELECT
        *,
        CASE WHEN makerAssetId = UINT256 '0' THEN takerAssetId ELSE makerAssetId END
            AS outcome_token_id,
        CASE
            WHEN makerAssetId = UINT256 '0'
                THEN CAST(takerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(makerAmountFilled AS DOUBLE) / 1e6
        END AS outcome_tokens,
        CASE
            WHEN makerAssetId = UINT256 '0'
                THEN CAST(makerAmountFilled AS DOUBLE) / 1e6
            ELSE CAST(takerAmountFilled AS DOUBLE) / 1e6
        END AS collateral_usd,
        CASE WHEN makerAssetId = UINT256 '0' THEN maker ELSE taker END AS buyer,
        CASE WHEN makerAssetId = UINT256 '0' THEN taker ELSE maker END AS seller
    FROM fills
    WHERE makerAssetId = UINT256 '0' OR takerAssetId = UINT256 '0'
)
SELECT
    exchange_type,
    evt_block_time,
    to_hex(evt_tx_hash) AS tx_hash,
    evt_index,
    to_hex(orderHash) AS order_hash,
    CAST(outcome_token_id AS VARCHAR) AS outcome_token_id,
    outcome_tokens,
    collateral_usd,
    collateral_usd / nullif(outcome_tokens, 0) AS price,
    to_hex(buyer) AS buyer,
    to_hex(seller) AS seller,
    CAST(fee AS VARCHAR) AS raw_fee
FROM normalized
ORDER BY evt_block_time DESC, evt_index DESC
LIMIT 200

