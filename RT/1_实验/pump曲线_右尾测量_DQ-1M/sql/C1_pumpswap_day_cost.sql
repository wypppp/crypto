-- DQ-1M · C1：PumpSwap 买卖事件单日分区的扫描成本与可用字段校准
-- 只扫 1 天。目的：测这一天的 bytes_read 与 CPU 秒，并确认池储备字段可用。
-- 不读取任何代币在决策时点之后的价格结局。
WITH b AS (
    SELECT evt_block_time AS ts, pool,
           CAST(quote_amount_in AS DOUBLE) AS quote_delta,
           CAST(base_amount_out AS DOUBLE) AS base_delta,
           CAST(pool_quote_token_reserves AS DOUBLE) AS qr,
           CAST(pool_base_token_reserves AS DOUBLE) AS br
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date = DATE '2026-06-15'
),
s AS (
    SELECT evt_block_time AS ts, pool,
           CAST(quote_amount_out AS DOUBLE) AS quote_delta,
           CAST(base_amount_in AS DOUBLE) AS base_delta,
           CAST(pool_quote_token_reserves AS DOUBLE) AS qr,
           CAST(pool_base_token_reserves AS DOUBLE) AS br
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date = DATE '2026-06-15'
),
u AS (
    SELECT 'buy' AS side, * FROM b
    UNION ALL
    SELECT 'sell' AS side, * FROM s
)
SELECT
    side,
    count(*) AS rows_total,
    count(DISTINCT pool) AS pools,
    count_if(qr IS NULL OR br IS NULL) AS n_reserve_null,
    count_if(qr = 0 OR br = 0) AS n_reserve_zero,
    approx_percentile(qr / 1e9, 0.5) AS pool_quote_sol_p50,
    approx_percentile(br / 1e6, 0.5) AS pool_base_tokens_p50,
    min(ts) AS first_time,
    max(ts) AS last_time
FROM u
GROUP BY 1
ORDER BY 1
