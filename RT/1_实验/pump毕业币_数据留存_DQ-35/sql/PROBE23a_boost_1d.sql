/* DQ-35 v2.2 探针（10-06，执行模型；总控第二十轮第二节）：InitBoost 全量扫描的费用。
   2026-08-20 一天，PumpSwap 全部自调用事件按事件判别符计数（顺带列出升级后有哪些事件类型），
   以及 InitBoost／BoostBuyAndBurn 涉及的池数。只输出计数，不含价格。 */
SELECT bytearray_substring(data, 9, 8) AS disc,
       count(*) AS n,
       count(DISTINCT CASE WHEN bytearray_substring(data, 9, 8) IN (0xae7c4af90451f611, 0x3f451c16305cc2b9)
                           THEN bytearray_substring(data, 89, 32) END) AS n_boost_pools,
       min(length(data)) AS min_len, max(length(data)) AS max_len
FROM solana.instruction_calls
WHERE block_date = DATE '2026-08-20'
  AND executing_account = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
  AND is_inner = true AND tx_success = true
  AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
GROUP BY 1
ORDER BY 2 DESC
