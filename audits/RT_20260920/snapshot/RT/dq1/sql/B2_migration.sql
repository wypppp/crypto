-- DQ-1 · B2：抽样日完成（CompleteEvent）→ 迁移调用 → PumpSwap canonical 建池 → 迁移事件 的映射可得性
-- 完成只取 6 个抽样日；迁移证据取抽样日及次日。不读取价格结局。
WITH
co AS (
    SELECT evt_block_date AS day, mint, min(evt_block_time) AS completed_at, count(*) AS n_rows,
           max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date IN (DATE '2024-03-01', DATE '2024-09-01', DATE '2025-03-01',
                             DATE '2025-09-01', DATE '2026-03-01', DATE '2026-09-01')
    GROUP BY 1, 2
),
mc_raw AS (
    SELECT account_mint AS mint, call_block_time AS t, account_pool AS pool, 'migrate' AS via
    FROM pumpdotfun_solana.pump_call_migrate
    WHERE call_block_date IN (DATE '2024-03-01', DATE '2024-03-02', DATE '2024-09-01', DATE '2024-09-02',
                              DATE '2025-03-01', DATE '2025-03-02', DATE '2025-09-01', DATE '2025-09-02',
                              DATE '2026-03-01', DATE '2026-03-02', DATE '2026-09-01', DATE '2026-09-02')
    UNION ALL
    SELECT account_base_mint AS mint, call_block_time AS t, account_pool AS pool, 'migrate_v2' AS via
    FROM pumpdotfun_solana.pump_call_migrate_v2
    WHERE call_block_date IN (DATE '2024-03-01', DATE '2024-03-02', DATE '2024-09-01', DATE '2024-09-02',
                              DATE '2025-03-01', DATE '2025-03-02', DATE '2025-09-01', DATE '2025-09-02',
                              DATE '2026-03-01', DATE '2026-03-02', DATE '2026-09-01', DATE '2026-09-02')
),
mc AS (
    SELECT mint, min(t) AS migrate_call_at, count(*) AS n_calls,
           count(DISTINCT pool) AS n_pools, arbitrary(pool) AS pool, max(via) AS via
    FROM mc_raw
    GROUP BY 1
),
cp AS (
    SELECT base_mint AS mint, min(evt_block_time) AS createpool_at, count(*) AS n_rows,
           count(DISTINCT pool) AS n_pools, arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date IN (DATE '2024-03-01', DATE '2024-03-02', DATE '2024-09-01', DATE '2024-09-02',
                             DATE '2025-03-01', DATE '2025-03-02', DATE '2025-09-01', DATE '2025-09-02',
                             DATE '2026-03-01', DATE '2026-03-02', DATE '2026-09-01', DATE '2026-09-02')
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1
),
me AS (
    SELECT mint, min(evt_block_time) AS migration_event_at, count(DISTINCT pool) AS n_pools,
           arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date IN (DATE '2024-03-01', DATE '2024-03-02', DATE '2024-09-01', DATE '2024-09-02',
                             DATE '2025-03-01', DATE '2025-03-02', DATE '2025-09-01', DATE '2025-09-02',
                             DATE '2026-03-01', DATE '2026-03-02', DATE '2026-09-01', DATE '2026-09-02')
    GROUP BY 1
)
SELECT
    co.day,
    count(*) AS completed_mints,
    count_if(co.n_rows > 1) AS completed_dup_rows,
    count_if(mc.mint IS NOT NULL) AS with_migrate_call,
    count_if(cp.mint IS NOT NULL) AS with_canonical_createpool,
    count_if(me.mint IS NOT NULL) AS with_migration_event,
    count_if(mc.mint IS NULL AND cp.mint IS NULL AND me.mint IS NULL) AS with_no_pumpswap_evidence,
    count_if(cp.mint IS NOT NULL AND mc.mint IS NOT NULL AND cp.pool = mc.pool) AS createpool_pool_eq_call_pool,
    count_if(cp.mint IS NOT NULL AND me.mint IS NOT NULL AND cp.pool = me.pool) AS createpool_pool_eq_event_pool,
    count_if(cp.n_pools > 1 OR mc.n_pools > 1 OR me.n_pools > 1) AS multi_pool_mints,
    count_if(cp.createpool_at < co.completed_at) AS createpool_before_complete,
    approx_percentile(date_diff('second', co.completed_at, cp.createpool_at), 0.5) AS lag_complete_to_pool_s_p50,
    approx_percentile(date_diff('second', co.completed_at, cp.createpool_at), 0.9) AS lag_complete_to_pool_s_p90,
    max(date_diff('second', co.completed_at, cp.createpool_at)) AS lag_complete_to_pool_s_max,
    array_join(slice(array_agg(DISTINCT mc.via), 1, 3), ',') AS migrate_via_values,
    array_join(slice(array_agg(DISTINCT co.quote_mint), 1, 4), ',') AS complete_quote_mints
FROM co
LEFT JOIN mc ON mc.mint = co.mint
LEFT JOIN cp ON cp.mint = co.mint
LEFT JOIN me ON me.mint = co.mint
GROUP BY 1
ORDER BY 1
