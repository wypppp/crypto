/* DQ-29 C4 冒烟（10-02，≤10 credits）：four.meme 两代合约的覆盖、中文名占比、逐笔字段空值与计价币。
   只读：两张创建表全量（小表）；2026-09-15 一天的第二代买卖事件；2026-09 的加池事件。不读任何价格结果。 */
WITH
cr AS (
    SELECT 'gen1' AS gen, evt_block_date AS d, name, symbol FROM four_meme_bnb.tokenmanager_evt_tokencreate
    UNION ALL
    SELECT 'gen2', evt_block_date, name, symbol FROM four_meme_bnb.tokenmanager2_evt_tokencreate
),
cov AS (
    SELECT
        'create_by_month' AS sec, gen AS k1, CAST(date_trunc('month', d) AS varchar) AS k2,
        count(*) AS n,
        count_if(regexp_like(name, '\p{Han}') OR regexp_like(symbol, '\p{Han}')) AS n2,
        CAST(NULL AS bigint) AS n3, CAST(NULL AS bigint) AS n4, CAST(NULL AS bigint) AS n5
    FROM cr
    GROUP BY 1, 2, 3
),
tr AS (
    SELECT 'buy' AS side, token, fee, price, funds, offers, cost FROM four_meme_bnb.tokenmanager2_evt_tokenpurchase
    WHERE evt_block_date = DATE '2026-09-15'
    UNION ALL
    SELECT 'sell', token, fee, price, funds, offers, cost FROM four_meme_bnb.tokenmanager2_evt_tokensale
    WHERE evt_block_date = DATE '2026-09-15'
),
day AS (
    SELECT
        'trades_20260915' AS sec, side AS k1, CAST(NULL AS varchar) AS k2,
        count(*) AS n, count(DISTINCT token) AS n2,
        count_if(fee = 0) AS n3, count_if(price = 0) AS n4, count_if(funds = 0 OR offers = 0) AS n5
    FROM tr
    GROUP BY 1, 2, 3
),
lq AS (
    SELECT
        'liquidity_quote_202609' AS sec, CAST(quote AS varchar) AS k1, CAST(NULL AS varchar) AS k2,
        count(*) AS n, CAST(NULL AS bigint) AS n2, CAST(NULL AS bigint) AS n3, CAST(NULL AS bigint) AS n4, CAST(NULL AS bigint) AS n5
    FROM four_meme_bnb.tokenmanager2_evt_liquidityadded
    WHERE evt_block_date BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'
    GROUP BY 1, 2, 3
)
SELECT * FROM cov
UNION ALL SELECT * FROM day
UNION ALL SELECT * FROM lq
ORDER BY 1, 2, 3
