-- DQ-18 第 1 步 / S2e：WHITEWHALE 创建月（2025-10）四档均未穿越；
-- 接着核 2025-11 至 2025-12 的首次小时门槛，不计算收益。
-- 事前估计 6–20 credits，仅按 S2c 单月实耗 3.501 粗推；
-- 建议网页单次上限 25 credits，用户授权的每条查询最高 50。
-- 若某档仍为空，不能断言 2026 年后也未穿越。最多 4 行，不需 CSV。

WITH trades AS (
    SELECT
        block_time,
        amount_usd,
        project_program_id AS pool_id,
        CASE
            WHEN token_bought_mint_address = 'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump'
                THEN token_bought_amount
            ELSE token_sold_amount
        END AS token_amount
    FROM dex_solana.trades
    WHERE block_month IN (DATE '2025-11-01', DATE '2025-12-01')
      AND block_date BETWEEN DATE '2025-11-01' AND DATE '2025-12-31'
      AND (
          token_bought_mint_address = 'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump'
          OR token_sold_mint_address = 'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump'
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
    'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump' AS mint,
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
