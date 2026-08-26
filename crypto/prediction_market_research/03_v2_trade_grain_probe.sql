-- Sample v2/v3 events to identify aggregate taker rows and amount semantics.

WITH fills AS (
    SELECT
        'v2' AS version,
        contract_address,
        evt_block_time,
        evt_tx_hash,
        evt_index,
        maker,
        taker,
        orderHash,
        side,
        tokenId,
        makerAmountFilled,
        takerAmountFilled,
        fee,
        builder,
        metadata
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2026-08-20'

    UNION ALL

    SELECT
        'v3' AS version,
        contract_address,
        evt_block_time,
        evt_tx_hash,
        evt_index,
        maker,
        taker,
        orderHash,
        side,
        tokenId,
        makerAmountFilled,
        takerAmountFilled,
        fee,
        builder,
        metadata
    FROM polymarket_v3_polygon.exchange_evt_orderfilled
    WHERE evt_block_date >= DATE '2026-08-20'
)
SELECT
    version,
    to_hex(contract_address) AS contract_address,
    evt_block_time,
    to_hex(evt_tx_hash) AS tx_hash,
    evt_index,
    to_hex(orderHash) AS order_hash,
    side,
    CAST(tokenId AS VARCHAR) AS token_id,
    CAST(makerAmountFilled AS DOUBLE) / 1e6 AS maker_amount,
    CAST(takerAmountFilled AS DOUBLE) / 1e6 AS taker_amount,
    CASE
        WHEN side = 0
            THEN CAST(makerAmountFilled AS DOUBLE) / nullif(CAST(takerAmountFilled AS DOUBLE), 0)
        ELSE CAST(takerAmountFilled AS DOUBLE) / nullif(CAST(makerAmountFilled AS DOUBLE), 0)
    END AS price,
    to_hex(maker) AS maker,
    to_hex(taker) AS taker,
    taker = contract_address AS exchange_is_taker,
    CAST(fee AS DOUBLE) / 1e6 AS fee_scaled,
    to_hex(builder) AS builder,
    to_hex(metadata) AS metadata
FROM fills
ORDER BY evt_block_time DESC, tx_hash, evt_index
LIMIT 500

