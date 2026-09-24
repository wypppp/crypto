-- DQ-18 第 1 步 / S3b：WHITEWHALE、PENGUIN 首次 $20m 小时的全部池与报价币。
-- 核 Dune 美元价格是否与原始换币比相容，不计算收益。
-- 两个月分区、各取一天一小时；参照 S3a 双月实耗 9.658，事前粗估 8–20 credits。
-- 建议网页单次上限 25 credits，用户每条查询硬上限 50；不要导出 CSV。

WITH signals(mint, hour_start) AS (
    VALUES
        ('a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump', TIMESTAMP '2025-12-26 22:00:00'),
        ('8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump', TIMESTAMP '2026-01-23 22:00:00')
), trades AS (
    SELECT
        block_time, project, project_program_id AS pool_id, amount_usd,
        token_bought_mint_address, token_sold_mint_address,
        token_bought_amount, token_sold_amount
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
        s.mint, s.hour_start, t.project, t.pool_id, t.amount_usd,
        IF(t.token_bought_mint_address = s.mint,
            t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
        IF(t.token_bought_mint_address = s.mint,
            t.token_bought_amount, t.token_sold_amount) AS token_amount,
        IF(t.token_bought_mint_address = s.mint,
            t.token_sold_amount, t.token_bought_amount) AS quote_amount,
        IF(t.token_bought_mint_address IN (
                'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
                '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
            ) AND t.token_sold_mint_address IN (
                'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
                '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
            ), 1, 0) AS both_target
    FROM signals s
    JOIN trades t
      ON (t.token_bought_mint_address = s.mint OR t.token_sold_mint_address = s.mint)
     AND t.block_time >= s.hour_start
     AND t.block_time < s.hour_start + INTERVAL '1' HOUR
), grouped AS (
    SELECT
        mint, hour_start, project, pool_id, quote_mint,
        COUNT(*) AS n_trades,
        SUM(both_target) AS n_both_target,
        COUNT_IF(amount_usd IS NULL OR amount_usd <= 0 OR token_amount IS NULL OR token_amount <= 0) AS n_bad_price,
        SUM(IF(amount_usd > 0 AND token_amount > 0, amount_usd, 0)) AS usd_volume,
        SUM(IF(amount_usd > 0 AND token_amount > 0, token_amount, 0)) AS token_volume,
        SUM(IF(token_amount > 0 AND quote_amount > 0, token_amount, 0)) AS raw_token_volume,
        SUM(IF(token_amount > 0 AND quote_amount > 0, quote_amount, 0)) AS quote_volume
    FROM coin_legs
    GROUP BY 1, 2, 3, 4, 5
)
SELECT
    mint, hour_start, project, pool_id, quote_mint,
    n_trades, n_both_target, n_bad_price,
    usd_volume, token_volume,
    usd_volume / NULLIF(token_volume, 0) AS usd_per_token,
    quote_volume / NULLIF(raw_token_volume, 0) AS quote_per_token,
    usd_volume / NULLIF(SUM(usd_volume) OVER (PARTITION BY mint), 0) AS share_of_valid_usd_volume
FROM grouped
ORDER BY mint, usd_volume DESC, pool_id
