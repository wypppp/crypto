-- DQ-18 A 段普查诊断：2025-02 可疑的 1 亿美元首次穿越（6 个 mint×小时）
-- 按 project、池（project_program_id）、报价币分解该小时的 P1 有效成交；只扫 2025-02 一个月分区。
-- 运行时单条上限 100 credits。不含信号后数据。
WITH target(mint, hour_start) AS (
    VALUES
        ('AxriehR6Xw3adzHopnvMn7GcpRFcD41ddpiTWMg6pump', TIMESTAMP '2025-02-09 04:00:00'),
        ('7oBYdEhV4GkXC19ZfgAvXpJWp2Rn9pm1Bx2cVNxFpump', TIMESTAMP '2025-02-09 23:00:00'),
        ('6tNbg1WWk12GC2bYAmxcMQRLMW4632pieNFFxRyvpump', TIMESTAMP '2025-02-12 02:00:00'),
        ('3kK1CKrjUFs5fcmucnBCSHv8X7ggMXfmWghqLz5Tpump', TIMESTAMP '2025-02-15 03:00:00'),
        ('EsvEXjYfrHkf7UzNmMwe8ykcUQTRCvc9d93TP5Jmpump', TIMESTAMP '2025-02-15 22:00:00'),
        ('2oUmyeXZ9bpUyCxTqyhoiq79TvCQ5famLQTBa3FEpump', TIMESTAMP '2025-02-17 16:00:00')
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '2025-02-01' AND minute < TIMESTAMP '2025-03-01'
    GROUP BY minute
), t AS (
    SELECT tr.block_time, tr.project, tr.version, tr.project_program_id, tr.tx_id,
           tg.mint,
           IF(tr.token_bought_mint_address = tg.mint, tr.token_sold_mint_address, tr.token_bought_mint_address) AS quote_mint,
           IF(tr.token_bought_mint_address = tg.mint, tr.token_bought_amount, tr.token_sold_amount) AS token_amount,
           IF(tr.token_bought_mint_address = tg.mint, tr.token_sold_amount, tr.token_bought_amount) AS quote_amount,
           tr.amount_usd
    FROM dex_solana.trades tr
    JOIN target tg
      ON (tr.token_bought_mint_address = tg.mint OR tr.token_sold_mint_address = tg.mint)
     AND tr.block_time >= tg.hour_start AND tr.block_time < tg.hour_start + INTERVAL '1' HOUR
    WHERE tr.block_month = DATE '2025-02-01'
      AND tr.project <> 'pumpdotfun'
)
SELECT t.mint, t.project, t.version, t.project_program_id, t.quote_mint,
       COUNT(*) AS n,
       COUNT(DISTINCT t.tx_id) AS n_tx,
       SUM(t.quote_amount) AS quote_sum,
       SUM(t.quote_amount * s.sol_usd) AS usd_sol_based,
       SUM(t.amount_usd) AS dune_amount_usd,
       SUM(t.token_amount) AS token_sum,
       1e9 * SUM(t.quote_amount * s.sol_usd) / NULLIF(SUM(t.token_amount), 0) AS vwap_cap_usd,
       approx_percentile(t.quote_amount, 0.5) AS median_quote,
       MAX(t.quote_amount) AS max_quote
FROM t LEFT JOIN sol_minute s ON s.minute = date_trunc('minute', t.block_time)
GROUP BY 1, 2, 3, 4, 5
ORDER BY t.mint, usd_sol_based DESC
