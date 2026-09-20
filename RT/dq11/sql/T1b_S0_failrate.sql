-- DQ-11 T1b · S0：最小探针（E2 前置）
-- 唯一目的：确认 solana.instruction_calls 是否真的收录失败交易。
-- 文档只说 tx_success 是"父交易是否成功"，没说失败交易入不入表。若 false 计数为 0，则该表只有成功交易，E2 必须换源。
-- 扫描限定：单个 block_date 的 1 小时 + 单个 executing_account。先跑这条，确认 credits 后再跑 S1/S2。
SELECT
    tx_success,
    count(*)                    AS n_instructions,
    count(DISTINCT tx_id)       AS n_tx
FROM solana.instruction_calls
WHERE block_date = DATE '2026-06-01'
  AND block_time >= TIMESTAMP '2026-06-01 12:00:00'
  AND block_time <  TIMESTAMP '2026-06-01 13:00:00'
  AND executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
GROUP BY 1
