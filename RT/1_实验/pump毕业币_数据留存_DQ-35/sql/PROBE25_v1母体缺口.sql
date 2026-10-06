/* DQ-35 v1 可用性评估（10-06，执行模型；总控第二十一轮第二节第 3 条 1）：GPT 10-03 提取 SQL 审计第 1、2 条的影响范围。
   只用创建与建池时刻，不读价格。母体同 v1：pump 迁移、池序号 0 的 PumpSwap 池，建于 2025-03-16～2026-09-30。
   1. 代号窗口：v1 毕业后层的代号只回查到“池检索起日前 90 天”（片起日 −180−90），所以建池晚于曲线创建 90 天以上的币，
      后面的分片会缺；晚于 270 天以上整币缺。按（建池 − 曲线创建）天数分组计数。
   2. 封存口径：v1 按建池日排除 2026-06-15～07-12；DQ-37 按币的曲线创建日。两种口径交叉计数（漏挡／误挡）。 */
WITH cp AS (
    SELECT pool, min(evt_block_time) AS pool_at, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2025-03-16' AND DATE '2026-09-30'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1
),
cc AS (
    SELECT mint, min(evt_block_time) AS curve_at
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '2026-09-30'
      AND mint IN (SELECT mint FROM cp)
    GROUP BY 1
),
j AS (
    SELECT cp.pool, cp.pool_at, cc.curve_at,
           date_diff('day', cc.curve_at, cp.pool_at) AS lag_d,
           cp.pool_at >= TIMESTAMP '2026-06-15 00:00:00' AND cp.pool_at < TIMESTAMP '2026-07-13 00:00:00' AS sealed_by_pool,
           cc.curve_at >= TIMESTAMP '2026-06-15 00:00:00' AND cc.curve_at < TIMESTAMP '2026-07-13 00:00:00' AS sealed_by_curve
    FROM cp LEFT JOIN cc ON cc.mint = cp.mint
)
SELECT CASE WHEN curve_at IS NULL THEN 'no_curve'
            WHEN lag_d <= 90 THEN 'lag_le90' WHEN lag_d <= 270 THEN 'lag_91_270' ELSE 'lag_gt270' END AS lag_class,
       sealed_by_pool, sealed_by_curve,
       count(*) AS n_pools, min(pool_at) AS first_pool, max(pool_at) AS last_pool
FROM j
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
