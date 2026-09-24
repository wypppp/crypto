-- DQ-18 第 1 步 / S2d：PENGUIN 创建于 2026-01-16，核创建月的小时门槛穿越。
-- 只核门槛与小时笔数，不算收益。创建前不存在该币；本月如未过某档，不能据此断言之后永不穿越。
-- S2a（2024-10 月分区）执行 4.5625 credits；本月事前预估 8–30 credits，未经本月实测。
-- 建议网页单次成本上限 35 credits；用户批准的每条查询硬上限 50 credits。
-- 若未出现某档穿越，不能推断该币此后永不穿越。结果最多 4 行，不用 CSV 导出。

WITH trades AS (
    SELECT
        block_time,
        amount_usd,
        project_program_id AS pool_id,
        CASE
            WHEN token_bought_mint_address = '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
                THEN token_bought_amount
            ELSE token_sold_amount
        END AS token_amount
    FROM dex_solana.trades
    WHERE block_month = DATE '2026-01-01'
      AND block_date BETWEEN DATE '2026-01-16' AND DATE '2026-01-31'
      AND (
          token_bought_mint_address = '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
          OR token_sold_mint_address = '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
      )
), hourly AS (
    SELECT
        date_trunc('hour', block_time) AS hour_start,
        date_trunc('hour', block_time) + INTERVAL '1' HOUR AS signal_time,
        COUNT(*) AS n_all_trades,
        COUNT_IF(amount_usd > 0 AND token_amount > 0) AS n_price_trades,
        COUNT_IF(amount_usd IS NULL OR amount_usd <= 0 OR token_amount IS NULL OR token_amount <= 0) AS n_bad_price_trades,
        COUNT(DISTINCT pool_id) AS n_pools,
        SUM(IF(amount_usd > 0 AND token_amount > 0, amount_usd, 0)) AS valid_usd_volume,
        SUM(IF(amount_usd > 0 AND token_amount > 0, token_amount, 0)) AS valid_token_volume
    FROM trades
    GROUP BY 1, 2
), priced_hours AS (
    SELECT *, 1000000000.0 * valid_usd_volume / NULLIF(valid_token_volume, 0) AS platform_marketcap_usd
    FROM hourly
), thresholds(threshold_usd) AS (
    VALUES (1000000.0), (5000000.0), (20000000.0), (100000000.0)
), qualified AS (
    SELECT
        h.*,
        t.threshold_usd,
        ROW_NUMBER() OVER (PARTITION BY t.threshold_usd ORDER BY h.signal_time) AS crossing_rank
    FROM priced_hours h
    CROSS JOIN thresholds t
    WHERE h.platform_marketcap_usd >= t.threshold_usd
)
SELECT
    '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump' AS mint,
    t.threshold_usd,
    q.hour_start AS first_qualifying_hour_start,
    q.signal_time AS first_signal_time,
    q.platform_marketcap_usd,
    q.n_all_trades,
    q.n_price_trades,
    q.n_bad_price_trades,
    q.n_pools,
    q.valid_usd_volume
FROM thresholds t
LEFT JOIN qualified q
    ON q.threshold_usd = t.threshold_usd
   AND q.crossing_rank = 1
ORDER BY t.threshold_usd
