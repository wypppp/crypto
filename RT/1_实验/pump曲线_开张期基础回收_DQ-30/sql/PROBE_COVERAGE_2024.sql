/* DQ-30 覆盖探针（10-02）：pump 曲线成交与创建事件在 2024-01～06 的逐周行数；只读 2024-01-01～06-30 分区。 */
SELECT 'trade' AS t, date_trunc('week', evt_block_date) AS wk, count(*) AS n, min(evt_block_time) AS t_min, count(DISTINCT mint) AS n_mint
FROM pumpdotfun_solana.pump_evt_tradeevent
WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '2024-06-30'
GROUP BY 1, 2
UNION ALL
SELECT 'create', date_trunc('week', evt_block_date), count(*), min(evt_block_time), count(DISTINCT mint)
FROM pumpdotfun_solana.pump_evt_createevent
WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '2024-06-30'
GROUP BY 1, 2
ORDER BY 1, 2
