-- DQ-18 第 1 步 / S4b：PNUT、WHITEWHALE、PENGUIN 在 $20m 信号后四种首笔成交。
-- 包括信号后第一笔、+5 分钟后第一笔、+60 分钟后第一笔、首笔 >=$50。
-- 只核时间、池、成交金额与打印价，不计算收益；打印价不是我方买单报价。
-- 扫 2024-11 / 2025-12 / 2026-01 三个月分区和必要次日。
-- 参照 S4a 单月两币实耗 11.1902，事前粗估 12–30 credits；建议单次上限 35，硬上限 50。

WITH signals(mint, signal_time) AS (
    VALUES
        ('2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump', TIMESTAMP '2024-11-02 17:00:00'),
        ('a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump', TIMESTAMP '2025-12-26 23:00:00'),
        ('8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump', TIMESTAMP '2026-01-23 23:00:00')
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
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump',
                'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
                '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
            ) THEN token_bought_mint_address ELSE token_sold_mint_address END AS mint,
        block_time, block_slot, tx_index, outer_instruction_index,
        inner_instruction_index, tx_id, project, project_program_id AS pool_id,
        token_bought_mint_address, amount_usd,
        CASE WHEN token_bought_mint_address IN (
            '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump',
            'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
            '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
        ) THEN token_bought_amount ELSE token_sold_amount END AS token_amount
    FROM dex_solana.trades
    WHERE block_month IN (DATE '2024-11-01', DATE '2025-12-01', DATE '2026-01-01')
      AND block_date IN (
          DATE '2024-11-02', DATE '2024-11-03',
          DATE '2025-12-26', DATE '2025-12-27',
          DATE '2026-01-23', DATE '2026-01-24'
      )
      AND (
          token_bought_mint_address IN (
              '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump',
              'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
              '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
          ) OR token_sold_mint_address IN (
              '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump',
              'a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',
              '8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump'
          )
      )
), ranked AS (
    SELECT
        s.mint, v.variant,
        t.block_time, t.block_slot, t.tx_index, t.outer_instruction_index,
        t.inner_instruction_index, t.tx_id, t.project, t.pool_id,
        t.amount_usd, t.token_amount,
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
    s.mint, s.signal_time, v.variant,
    r.block_time AS first_trade_time,
    date_diff('second', s.signal_time, r.block_time) AS seconds_after_signal,
    r.block_slot, r.tx_index, r.outer_instruction_index, r.inner_instruction_index,
    r.tx_id, r.project, r.pool_id, r.trade_direction,
    r.amount_usd, r.token_amount, r.printed_price_usd
FROM signals s
CROSS JOIN variants v
LEFT JOIN ranked r ON r.mint = s.mint AND r.variant = v.variant AND r.rn = 1
ORDER BY s.mint, v.variant
