/* DQ-35 v2.2 探针（10-05，执行模型；总控第十九轮第二节第 4 条）：vq 逐笔解码的费用——方案 A，solana.instruction_calls。
   2026-09-23（开发周）06:00～12:00（6 小时，测费用是否随时长线性）全部 PumpSwap 买卖事件的自调用指令；只输出计数，不下载明细。 */
SELECT count(*) AS n,
       count_if(bytearray_substring(data, 9, 8) = 0x67f4521f2cf57777) AS n_buy,
       count_if(bytearray_substring(data, 9, 8) = 0x3e2f370aa503dc2a) AS n_sell,
       count(DISTINCT tx_id) AS n_tx,
       min(length(data)) AS min_len, max(length(data)) AS max_len
FROM solana.instruction_calls
WHERE block_date = DATE '2026-09-23'
  AND block_time >= TIMESTAMP '2026-09-23 06:00:00' AND block_time < TIMESTAMP '2026-09-23 12:00:00'
  AND executing_account = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
  AND is_inner = true AND tx_success = true
  AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
  AND bytearray_substring(data, 9, 8) IN (0x67f4521f2cf57777, 0x3e2f370aa503dc2a)
