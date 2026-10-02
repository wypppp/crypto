/* DQ-30 字段探针（10-02）：pump 曲线成交事件在 2024 年各日期的字段空值与规模；只读所列 8 个日期分区。 */
SELECT
    evt_block_date AS d,
    count(*) AS n_ev,
    count(DISTINCT mint) AS n_mint,
    count(real_sol_reserves) AS n_xr,
    count(fee_basis_points) AS n_fee_bps,
    count(fee) AS n_fee,
    count(COALESCE(virtual_sol_reserves, virtualSolReserves)) AS n_vx,
    count(virtualSolReserves) AS n_vx_camel,
    count(COALESCE(sol_amount, solAmount)) AS n_sol,
    min(evt_block_time) AS t_min
FROM pumpdotfun_solana.pump_evt_tradeevent
WHERE evt_block_date IN (
    DATE '2024-01-19', DATE '2024-01-25', DATE '2024-02-15', DATE '2024-03-15',
    DATE '2024-04-15', DATE '2024-06-15', DATE '2024-09-16', DATE '2025-01-15'
)
GROUP BY 1
ORDER BY 1
