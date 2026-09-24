-- DQ-18 第 2 步 A 段诊断：一次扫描 2025-12，查五个极小成交额穿越与
-- WHITEWHALE 正常成交额穿越的原始腿。只判断价格口径，绝不改冻结门槛或抽样框。
-- 样例是在 A 段结果揭示异常后选取，属事后诊断，不是独立验证。
-- 单次硬上限 50 credits；预计费用未经本查询实测。结果最多 36 行。

WITH samples(mint, hour_start) AS (
    VALUES
    ('1W9V5vdMAvx8Ma52TkzLTT35XQ9wtTLaJMYr8g5pump', TIMESTAMP '2025-12-16 04:00:00'),
    ('21GP6Ay2R7UjuhqMX4DkA2tca6YMWVtmYgUDMxkhpump', TIMESTAMP '2025-12-04 13:00:00'),
    ('2JaEtWuAnamvLkhduL4jA7gdF84DK4uucrVuN16zpump', TIMESTAMP '2025-12-04 13:00:00'),
    ('2YiGUyzh4GinEQgbPUCnb9SiPkNfHLNKPo8GVsJdpump', TIMESTAMP '2025-12-04 12:00:00'),
    ('2gsDabBhCi6nqg5TGet24Ms9VY6rx6bpHLmtL4Lppump', TIMESTAMP '2025-12-04 12:00:00'),
    ('a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump', TIMESTAMP '2025-12-26 22:00:00')
), raw_trades AS (
    SELECT block_time, block_date, tx_id, project,
           project_program_id AS pool_id, amount_usd,
           token_bought_mint_address, token_sold_mint_address,
           token_bought_amount, token_sold_amount
    FROM dex_solana.trades
    WHERE block_month = DATE '2025-12-01'
      AND block_date IN (DATE '2025-12-04', DATE '2025-12-16', DATE '2025-12-26')
      AND (
          token_bought_mint_address IN (SELECT mint FROM samples)
          OR token_sold_mint_address IN (SELECT mint FROM samples)
      )
), legs AS (
    SELECT s.mint, s.hour_start, t.*,
           IF(t.token_bought_mint_address = s.mint,
              t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = s.mint,
              t.token_bought_amount, t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = s.mint,
              t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM samples s
    JOIN raw_trades t
      ON (t.token_bought_mint_address = s.mint
          OR t.token_sold_mint_address = s.mint)
     AND t.block_time >= s.hour_start
     AND t.block_time < s.hour_start + INTERVAL '1' HOUR
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY mint, hour_start
        ORDER BY amount_usd DESC NULLS LAST, block_time, tx_id
    ) AS row_rank
    FROM legs
)
SELECT mint, hour_start, block_time, project, pool_id, tx_id,
       token_bought_mint_address, token_sold_mint_address,
       token_bought_amount, token_sold_amount,
       quote_mint, quote_amount, token_amount,
       amount_usd AS dune_amount_usd_for_diagnostic_only,
       quote_amount / NULLIF(token_amount, 0) AS raw_quote_per_token
FROM ranked
WHERE row_rank <= 6
ORDER BY mint, row_rank
