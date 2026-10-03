/* DQ-37 探针 2（10-03，执行模型）：2025-10-07（开发周）创建的 pump 币，创建后 3 天内的曲线成交笔数分布（只数笔数，用于定“每币前几百笔”的 N 与体量；不看价格或收益） */
WITH c AS (
    SELECT mint, min(evt_block_time) AS created_at
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date = DATE '2025-10-07'
    GROUP BY 1
),
t AS (
    SELECT t.mint, count(*) AS n
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN c ON c.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '2025-10-07' AND DATE '2025-10-10'
      AND t.evt_block_time < c.created_at + INTERVAL '3' DAY
    GROUP BY 1
)
SELECT (SELECT count(*) FROM c) AS n_coins,
       count(*) AS n_coins_traded,
       sum(n) AS trades,
       sum(least(n, 100)) AS trades_cap100,
       sum(least(n, 300)) AS trades_cap300,
       sum(least(n, 500)) AS trades_cap500,
       approx_percentile(n, ARRAY[0.5, 0.9, 0.99]) AS n_q50_90_99,
       count_if(n > 300) AS n_coins_over300
FROM t
