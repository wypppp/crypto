-- DQ-1M · C2：curve 成交表单日分区 + 按 mint 做窗口函数的 CPU 增量校准
-- 只扫 1 天。与 DQ-1 的 A 查询（同表、单日、仅聚合）对比，差额即窗口函数的代价。
-- 逐笔顺序按 slot、交易序号、内层指令序号，测量卡沿用同一顺序。
WITH t AS (
    SELECT
        mint,
        evt_block_time AS ts,
        evt_block_slot AS slot,
        evt_tx_index AS tx_index,
        evt_inner_instruction_index AS inner_ix,
        CAST(COALESCE(virtual_sol_reserves, virtualSolReserves) AS DOUBLE) / 1e9 AS vsr,
        CAST(COALESCE(virtual_token_reserves, virtualTokenReserves) AS DOUBLE) / 1e6 AS vtr,
        quote_mint
    FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE evt_block_date = DATE '2026-06-15'
),
p AS (
    SELECT
        mint, ts, vsr, vtr,
        vsr / NULLIF(vtr, 0) AS price,
        max(vsr / NULLIF(vtr, 0)) OVER (
            PARTITION BY mint ORDER BY slot, tx_index, inner_ix
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS run_max
    FROM t
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
)
SELECT
    count(*) AS rows_total,
    count(DISTINCT mint) AS mints,
    count_if(price IS NULL) AS n_price_null,
    count_if(vsr > 120) AS n_vsr_gt_120,
    count_if(vsr = 0) AS n_vsr_zero,
    count_if(price <= 0.5 * run_max) AS n_below_half_runmax,
    approx_percentile(run_max / NULLIF(price, 0), 0.5) AS runmax_over_price_p50,
    max(vsr) AS vsr_max
FROM p
