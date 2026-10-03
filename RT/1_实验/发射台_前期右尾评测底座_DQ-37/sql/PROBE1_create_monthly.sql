/* DQ-37 探针 1（10-03，执行模型）：pump 曲线创建事件全历史扫描的费用，以及每月新币数（只数个数，用于估算曲线阶段留存的体量；不看任何价格或收益） */
SELECT date_trunc('month', evt_block_time) AS m,
       count(*) AS n_create,
       count(DISTINCT mint) AS n_mint,
       count_if(quote_mint IS NOT NULL AND quote_mint <> 'So11111111111111111111111111111111111111112') AS n_custom_quote,
       count_if(is_mayhem_mode) AS n_mayhem,
       count_if(symbol IS NULL) AS n_sym_null
FROM pumpdotfun_solana.pump_evt_createevent
WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '2026-09-29'
GROUP BY 1
ORDER BY 1
