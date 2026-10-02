/* DQ-34 访问探针（10-02，执行模型）：hyperliquid.perp_trades 能否读、HIP-3 是否在内、每笔是否双边；只读 2026-09-27 一天、xyz:SP500 一个币；不读价格与盈亏 */
SELECT block_date, perp_dex, coin, is_taker,
       count(*) AS n_legs, count(DISTINCT trader) AS n_traders, count(DISTINCT tid) AS n_tid,
       sum(notional_usd) AS usd, min(block_time) AS t_min, max(block_time) AS t_max
FROM hyperliquid.perp_trades
WHERE block_date = DATE '2026-09-27' AND coin = 'xyz:SP500'
GROUP BY 1, 2, 3, 4
