/* DQ-28 诊断（10-02，看结果后）：一个异常币在创建 slot 的事件构成；只读 2026-08-05 分区。 */
WITH m(mint) AS (VALUES ('LANkHe7bzfPE1FCBCnFZ9g8AUntuT4vHqNW7x34pump'))
SELECT 'create' AS k, evt_block_slot AS slot, evt_tx_id AS tx, CAST("user" AS varchar) AS usr, CAST(NULL AS varchar) AS pool,
       CAST(NULL AS double) AS a1, CAST(NULL AS double) AS a2, CAST(NULL AS varchar) AS note
FROM pumpdotfun_solana.pump_evt_createevent WHERE evt_block_date = DATE '2026-08-05' AND mint IN (SELECT mint FROM m)
UNION ALL
SELECT 'curve', evt_block_slot, evt_tx_id, CAST("user" AS varchar), NULL,
       CAST(COALESCE(sol_amount, solAmount) AS double) / 1e9, CAST(COALESCE(virtual_sol_reserves, virtualSolReserves) AS double) / 1e9,
       CAST(COALESCE(is_buy, isBuy) AS varchar) || '/' || CAST(mayhem_mode AS varchar)
FROM pumpdotfun_solana.pump_evt_tradeevent WHERE evt_block_date = DATE '2026-08-05' AND mint IN (SELECT mint FROM m)
UNION ALL
SELECT 'pool', evt_block_slot, evt_tx_id, CAST(creator AS varchar), pool,
       CAST(base_amount_in AS double), CAST(quote_amount_in AS double), base_mint || '|' || quote_mint
FROM pumpdotfun_solana.pump_amm_evt_createpoolevent WHERE evt_block_date = DATE '2026-08-05'
  AND (base_mint IN (SELECT mint FROM m) OR quote_mint IN (SELECT mint FROM m))
UNION ALL
SELECT 'mig', evt_block_slot, evt_tx_id, CAST("user" AS varchar), pool, NULL, NULL, NULL
FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent WHERE evt_block_date = DATE '2026-08-05' AND mint IN (SELECT mint FROM m)
ORDER BY 2, 1
LIMIT 60
