-- DQ-11 T1b · S1：优先费实测分布（E1）
-- 把 pump 成交事件连到 solana.transactions，取实际支付的交易费。
-- fee 为总交易费（lamports，含优先费）。Solana 基础费 = 5000 lamports/签名。
-- 单签名交易的优先费 = fee - 5000；同时输出 fee 是否为 5000 的整数倍，用于识别多签名与零优先费两种情形。
-- 扫描限定：单日 + 1 小时窗口，两侧都走分区列。
WITH ev AS (
    SELECT DISTINCT evt_tx_id AS tx_id
    FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE evt_block_date = DATE '2026-06-01'
      AND evt_block_time >= TIMESTAMP '2026-06-01 12:00:00'
      AND evt_block_time <  TIMESTAMP '2026-06-01 13:00:00'
),
tx AS (
    SELECT id, fee, success, compute_units_consumed
    FROM solana.transactions
    WHERE block_date = DATE '2026-06-01'
      AND block_time >= TIMESTAMP '2026-06-01 12:00:00'
      AND block_time <  TIMESTAMP '2026-06-01 13:00:00'
)
SELECT
    count(*)                                              AS n_matched,
    sum(CASE WHEN NOT t.success THEN 1 ELSE 0 END)        AS n_failed_with_event,
    approx_percentile(t.fee, 0.10)                        AS fee_p10,
    approx_percentile(t.fee, 0.50)                        AS fee_p50,
    approx_percentile(t.fee, 0.90)                        AS fee_p90,
    approx_percentile(t.fee, 0.99)                        AS fee_p99,
    sum(CASE WHEN t.fee <= 5000 THEN 1 ELSE 0 END)        AS n_fee_le_base,
    sum(CASE WHEN t.fee % 5000 = 0 THEN 1 ELSE 0 END)     AS n_fee_multiple_of_base,
    approx_percentile(t.compute_units_consumed, 0.50)     AS cu_p50
FROM ev
JOIN tx t ON t.id = ev.tx_id
