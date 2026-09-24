-- DQ-18 第 1 步 / S2a：2024-10 创建的三个已确认 pump 币，核对四档小时 VWAP 首次穿越。
-- 仅扫描 2024-10 一个 dex_solana.trades 月分区，不能替代其他月份的完整历史。
-- 只输出逐币逐门槛时刻及数据质量；不计算任何入场、退出或收益倍数。
-- S0 单币单日执行 12.2702 credits。本查询按一个月分区、三币、小时分组，
-- 事前预估 15–35 credits，未经该月实测；建议网页单次上限 35 credits，
-- 用户批准的每条查询硬上限 50 credits。若超上限或失败，回报成本和错误，不立即重跑。
-- 查询 ID 可复用，但必须记录新的 execution ID；结果最多 12 行，不用网页导出。

WITH trades AS (
    SELECT
        CASE
            WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) THEN token_bought_mint_address
            ELSE token_sold_mint_address
        END AS mint,
        block_time,
        amount_usd,
        project_program_id AS pool_id,
        CASE
            WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) THEN token_bought_amount
            ELSE token_sold_amount
        END AS token_amount
    FROM dex_solana.trades
    WHERE block_month = DATE '2024-10-01'
      AND block_date BETWEEN DATE '2024-10-10' AND DATE '2024-10-31'
      AND (
          token_bought_mint_address IN (
              'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
              '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
              '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
          )
          OR token_sold_mint_address IN (
              'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
              '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
              '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
          )
      )
), hourly AS (
    SELECT
        mint,
        date_trunc('hour', block_time) AS hour_start,
        date_trunc('hour', block_time) + INTERVAL '1' HOUR AS signal_time,
        COUNT(*) AS n_all_trades,
        COUNT_IF(amount_usd > 0 AND token_amount > 0) AS n_price_trades,
        COUNT_IF(amount_usd IS NULL OR amount_usd <= 0 OR token_amount IS NULL OR token_amount <= 0) AS n_bad_price_trades,
        COUNT(DISTINCT pool_id) AS n_pools,
        SUM(IF(amount_usd > 0 AND token_amount > 0, amount_usd, 0)) AS valid_usd_volume,
        SUM(IF(amount_usd > 0 AND token_amount > 0, token_amount, 0)) AS valid_token_volume
    FROM trades
    GROUP BY 1, 2, 3
), priced_hours AS (
    SELECT *, 1000000000.0 * valid_usd_volume / NULLIF(valid_token_volume, 0) AS platform_marketcap_usd
    FROM hourly
), thresholds(threshold_usd) AS (
    VALUES (1000000.0), (5000000.0), (20000000.0), (100000000.0)
), qualified AS (
    SELECT
        h.*,
        t.threshold_usd,
        ROW_NUMBER() OVER (PARTITION BY h.mint, t.threshold_usd ORDER BY h.signal_time) AS crossing_rank
    FROM priced_hours h
    CROSS JOIN thresholds t
    WHERE h.platform_marketcap_usd >= t.threshold_usd
), mints(mint) AS (
    VALUES
        ('CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump'),
        ('9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump'),
        ('2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump')
)
SELECT
    m.mint,
    t.threshold_usd,
    q.hour_start AS first_qualifying_hour_start,
    q.signal_time AS first_signal_time,
    q.platform_marketcap_usd,
    q.n_all_trades,
    q.n_price_trades,
    q.n_bad_price_trades,
    q.n_pools,
    q.valid_usd_volume
FROM mints m
CROSS JOIN thresholds t
LEFT JOIN qualified q
    ON q.mint = m.mint
   AND q.threshold_usd = t.threshold_usd
   AND q.crossing_rank = 1
ORDER BY m.mint, t.threshold_usd
