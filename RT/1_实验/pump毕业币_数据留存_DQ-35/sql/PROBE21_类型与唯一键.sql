/* DQ-35 v2.1 结构探针（10-04，执行模型）：只看字段类型、事件键是否唯一、计价资产分布；不看价格或收益。2026-09-23 一天 */
WITH b AS (
    SELECT pool, evt_block_slot AS slot, evt_tx_index AS txi, evt_outer_instruction_index AS oix,
           COALESCE(evt_inner_instruction_index, -1) AS iix, pool_quote_token_reserves AS q0
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date = DATE '2026-09-23'
),
s AS (
    SELECT pool, evt_block_slot AS slot, evt_tx_index AS txi, evt_outer_instruction_index AS oix,
           COALESCE(evt_inner_instruction_index, -1) AS iix
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date = DATE '2026-09-23'
),
cp AS (
    SELECT quote_mint, count(*) AS n
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-09-01' AND DATE '2026-09-29'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0
    GROUP BY 1
)
SELECT 'type_q0' AS k, max(typeof(q0)) AS v FROM b
UNION ALL SELECT 'buy_rows', CAST(count(*) AS varchar) FROM b
UNION ALL SELECT 'buy_distinct_key', CAST(count(DISTINCT (pool, slot, txi, oix, iix)) AS varchar) FROM b
UNION ALL SELECT 'buy_inner_null', CAST(count_if(iix = -1) AS varchar) FROM b
UNION ALL SELECT 'sell_rows', CAST(count(*) AS varchar) FROM s
UNION ALL SELECT 'sell_distinct_key', CAST(count(DISTINCT (pool, slot, txi, oix, iix)) AS varchar) FROM s
UNION ALL SELECT 'quote:' || quote_mint, CAST(n AS varchar) FROM cp
