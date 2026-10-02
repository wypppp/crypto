/* DQ-34 数据保全：xStocks（官方 Xs* 铸币地址）在 Solana DEX 的 15 分钟价格与成交；只读 2026-04-01 月分区；由 xs_dune.py 生成 */
WITH xs AS (
    SELECT token_mint_address AS mint, symbol
    FROM tokens_solana.fungible
    WHERE token_mint_address LIKE 'Xs%' AND name LIKE '%xStock'
),
legs AS (
    SELECT t.block_time, xs.symbol, t.project, t.amount_usd,
           t.token_bought_amount AS qty, 1 AS buy
    FROM dex_solana.trades t JOIN xs ON t.token_bought_mint_address = xs.mint
    WHERE t.block_month = DATE '2026-04-01'
    UNION ALL
    SELECT t.block_time, xs.symbol, t.project, t.amount_usd,
           t.token_sold_amount AS qty, 0 AS buy
    FROM dex_solana.trades t JOIN xs ON t.token_sold_mint_address = xs.mint
    WHERE t.block_month = DATE '2026-04-01'
)
SELECT from_unixtime(floor(to_unixtime(block_time) / 900) * 900) AS t15, symbol,
       count(*) AS n, sum(buy) AS n_buy, sum(amount_usd) AS usd, sum(qty) AS qty,
       min_by(amount_usd / qty, block_time) AS px_open, max_by(amount_usd / qty, block_time) AS px_close,
       max(amount_usd / qty) AS px_high, min(amount_usd / qty) AS px_low, count(DISTINCT project) AS n_venues
FROM legs
WHERE qty > 0 AND amount_usd > 0
GROUP BY 1, 2
ORDER BY 1, 2
