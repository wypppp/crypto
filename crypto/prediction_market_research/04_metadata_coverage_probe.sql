-- Verify that market_details maps raw token IDs to outcomes and settlements.

WITH md AS (
    SELECT
        token_id,
        max_by(condition_id, last_changed_at) AS condition_id,
        max_by(question, last_changed_at) AS question,
        max_by(tags, last_changed_at) AS tags,
        max_by(settlement_value, last_changed_at) AS settlement_value,
        max_by(resolved_on_timestamp, last_changed_at) AS resolved_on_timestamp
    FROM polymarket_polygon.market_details
    GROUP BY 1
), source_tokens AS (
    SELECT
        'v1_ctf_2025_01' AS source,
        CASE WHEN makerAssetId = UINT256 '0' THEN takerAssetId ELSE makerAssetId END AS token_id,
        evt_block_time
    FROM polymarket_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date BETWEEN DATE '2025-01-01' AND DATE '2025-01-07'

    UNION ALL

    SELECT
        'v1_neg_2025_01' AS source,
        CASE WHEN makerAssetId = UINT256 '0' THEN takerAssetId ELSE makerAssetId END AS token_id,
        evt_block_time
    FROM polymarket_polygon.negriskctfexchange_evt_orderfilled
    WHERE evt_block_date BETWEEN DATE '2025-01-01' AND DATE '2025-01-07'

    UNION ALL

    SELECT
        CASE
            WHEN contract_address = 0xE111180000D2663C0091E4F400237545B87B996B
                THEN 'v2_ctf_2026_08'
            ELSE 'v2_neg_2026_08'
        END AS source,
        tokenId AS token_id,
        evt_block_time
    FROM polymarket_v2_polygon.ctfexchange_evt_orderfilled
    WHERE evt_block_date BETWEEN DATE '2026-08-20' AND DATE '2026-08-24'

    UNION ALL

    SELECT
        'v3_2026_08' AS source,
        tokenId AS token_id,
        evt_block_time
    FROM polymarket_v3_polygon.exchange_evt_orderfilled
    WHERE evt_block_date BETWEEN DATE '2026-08-20' AND DATE '2026-08-24'
)
SELECT
    source,
    count(*) AS fill_events_n,
    approx_distinct(s.token_id) AS token_ids_approx_n,
    count_if(md.token_id IS NOT NULL) AS metadata_matched_rows_n,
    count_if(md.settlement_value IS NOT NULL) AS resolved_rows_n,
    approx_distinct(CASE WHEN md.token_id IS NOT NULL THEN s.token_id END)
        AS metadata_matched_tokens_approx_n,
    approx_distinct(CASE WHEN md.settlement_value IS NOT NULL THEN s.token_id END)
        AS resolved_tokens_approx_n
FROM source_tokens s
LEFT JOIN md ON md.token_id = s.token_id
GROUP BY 1
ORDER BY 1

