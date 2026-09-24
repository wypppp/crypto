-- DQ-18 第 1 步 / S4a：GOAT 与 FARTCOIN 在 $20m 小时信号后，四种首笔成交核对。
-- 信号来自 S2a；只返回真实逐笔记录，不计算收益或倍数。
-- 仅扫 2024-10 月分区的 10-13、10-19 两日；事前预估 5–20 credits，
-- 建议网页单次执行上限 25 credits，用户批准的每条查询硬上限为 50。
-- 输出 8 行，不用网页 CSV 导出。成交价仍只是小单打印价，不等于买入报价。

WITH signals(mint, signal_time) AS (
    VALUES
        ('CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump', from_iso8601_timestamp('2024-10-13T02:00:00Z')),
        ('9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump', from_iso8601_timestamp('2024-10-19T18:00:00Z'))
), variants(variant, delay_seconds, min_trade_usd) AS (
    VALUES
        ('first', 0, 0.0),
        ('delay_5m', 300, 0.0),
        ('delay_60m', 3600, 0.0),
        ('first_at_least_50_usd', 0, 50.0)
), trades AS (
    SELECT
        CASE
            WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump'
            ) THEN token_bought_mint_address
            ELSE token_sold_mint_address
        END AS mint,
        block_time,
        block_slot,
        tx_index,
        outer_instruction_index,
        inner_instruction_index,
        tx_id,
        project,
        project_program_id AS pool_id,
        token_bought_mint_address,
        token_sold_mint_address,
        amount_usd,
        CASE
            WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump'
            ) THEN token_bought_amount
            ELSE token_sold_amount
        END AS token_amount
    FROM dex_solana.trades
    WHERE block_month = DATE '2024-10-01'
      AND block_date IN (DATE '2024-10-13', DATE '2024-10-19')
      AND (
          token_bought_mint_address IN (
              'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
              '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump'
          )
          OR token_sold_mint_address IN (
              'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
              '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump'
          )
      )
), ranked AS (
    SELECT
        s.mint,
        s.signal_time,
        v.variant,
        t.block_time,
        t.block_slot,
        t.tx_index,
        t.outer_instruction_index,
        t.inner_instruction_index,
        t.tx_id,
        t.project,
        t.pool_id,
        t.amount_usd,
        t.token_amount,
        t.amount_usd / NULLIF(t.token_amount, 0) AS printed_price_usd,
        IF(t.token_bought_mint_address = s.mint, 'token_bought', 'token_sold') AS trade_direction,
        ROW_NUMBER() OVER (
            PARTITION BY s.mint, v.variant
            ORDER BY t.block_time, t.block_slot, t.tx_index,
                     t.outer_instruction_index, t.inner_instruction_index, t.tx_id
        ) AS rn
    FROM signals s
    CROSS JOIN variants v
    JOIN trades t
      ON t.mint = s.mint
     AND t.block_time >= date_add('second', v.delay_seconds, s.signal_time)
     AND t.block_time < s.signal_time + INTERVAL '24' HOUR
     AND (v.min_trade_usd = 0 OR t.amount_usd >= v.min_trade_usd)
)
SELECT
    s.mint,
    s.signal_time,
    v.variant,
    r.block_time AS first_trade_time,
    date_diff('second', s.signal_time, r.block_time) AS seconds_after_signal,
    r.block_slot,
    r.tx_index,
    r.outer_instruction_index,
    r.inner_instruction_index,
    r.tx_id,
    r.project,
    r.pool_id,
    r.trade_direction,
    r.amount_usd,
    r.token_amount,
    r.printed_price_usd
FROM signals s
CROSS JOIN variants v
LEFT JOIN ranked r
  ON r.mint = s.mint AND r.variant = v.variant AND r.rn = 1
ORDER BY s.mint, v.variant
