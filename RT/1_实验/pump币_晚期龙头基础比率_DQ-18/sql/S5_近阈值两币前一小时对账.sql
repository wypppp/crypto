-- DQ-18 第 1 步 / S5：仅核 WHITEWHALE、PENGUIN 的 $20m 信号前一小时。
-- S3b 已核穿越小时；此查询检查前一小时是否确实低于门槛。
-- 不计算入场回报、止损或收益分布。
-- 两个月分区、各一天、各只取两小时；参照 S3b 的 12.1225 credits，
-- 事前粗估 8–20 credits，建议网页单次执行上限 25，硬上限 50。
-- 结果应为少量 mint×小时×报价币行，不需要 CSV 导出。

WITH signals(mint, crossing_hour) AS (
    VALUES
        ('a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump', TIMESTAMP '2025-12-26 22:00:00'),
        ('8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump', TIMESTAMP '2026-01-23 22:00:00')
), trades AS (
    SELECT
        block_time,
        amount_usd,
        token_bought_mint_address,
        token_sold_mint_address,
        token_bought_amount,
        token_sold_amount
    FROM dex_solana.trades
    WHERE block_month IN (DATE '2025-12-01', DATE '2026-01-01')
      AND block_date IN (DATE '2025-12-26', DATE '2026-01-23')
      AND (
          token_bought_mint_address IN (
              'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
              '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
          ) OR token_sold_mint_address IN (
              'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
              '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
          )
      )
), coin_legs AS (
    SELECT
        s.mint,
        date_trunc('hour', t.block_time) AS hour_start,
        t.amount_usd,
        IF(t.token_bought_mint_address = s.mint,
            t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
        IF(t.token_bought_mint_address = s.mint,
            t.token_bought_amount, t.token_sold_amount) AS token_amount,
        IF(t.token_bought_mint_address = s.mint,
            t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM signals s
    JOIN trades t
      ON (t.token_bought_mint_address = s.mint OR t.token_sold_mint_address = s.mint)
     AND t.block_time >= s.crossing_hour - INTERVAL '1' HOUR
     AND t.block_time < s.crossing_hour + INTERVAL '1' HOUR
)
SELECT
    mint,
    hour_start,
    quote_mint,
    COUNT(*) AS n_trades,
    COUNT_IF(amount_usd IS NULL OR amount_usd <= 0 OR token_amount IS NULL OR token_amount <= 0) AS n_bad_price,
    SUM(IF(amount_usd > 0 AND token_amount > 0, amount_usd, 0)) AS usd_volume,
    SUM(IF(amount_usd > 0 AND token_amount > 0, token_amount, 0)) AS priced_token_volume,
    SUM(IF(token_amount > 0 AND quote_amount > 0, quote_amount, 0)) AS raw_quote_volume,
    SUM(IF(token_amount > 0 AND quote_amount > 0, token_amount, 0)) AS raw_token_volume
FROM coin_legs
GROUP BY 1, 2, 3
ORDER BY mint, hour_start, quote_mint
