/* DQ-35 v2.2 探针（10-05，执行模型）：vq 逐笔解码的费用——方案 B，解码调用表的 inner_instructions（buy、buy_exact_quote_in、sell）。
   同一小时；只输出计数。 */
WITH c AS (
    SELECT call_inner_instructions AS ins FROM pumpdotfun_solana.pump_amm_call_buy
    WHERE call_block_date = DATE '2026-09-23'
      AND call_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND call_block_time < TIMESTAMP '2026-09-23 13:00:00'
    UNION ALL
    SELECT call_inner_instructions FROM pumpdotfun_solana.pump_amm_call_buy_exact_quote_in
    WHERE call_block_date = DATE '2026-09-23'
      AND call_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND call_block_time < TIMESTAMP '2026-09-23 13:00:00'
    UNION ALL
    SELECT call_inner_instructions FROM pumpdotfun_solana.pump_amm_call_sell
    WHERE call_block_date = DATE '2026-09-23'
      AND call_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND call_block_time < TIMESTAMP '2026-09-23 13:00:00'
),
e AS (
    SELECT from_base58(t.data) AS b
    FROM c
    CROSS JOIN UNNEST(transform(c.ins, x -> CAST(ROW(x.data, x.executing_account) AS ROW(data varchar, ea varchar)))) AS t(data, ea)
    WHERE t.ea = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
)
SELECT count(*) AS n,
       count_if(bytearray_substring(b, 9, 8) = 0x67f4521f2cf57777) AS n_buy,
       count_if(bytearray_substring(b, 9, 8) = 0x3e2f370aa503dc2a) AS n_sell
FROM e
WHERE bytearray_substring(b, 1, 8) = 0xe445a52e51cb9a1d
  AND bytearray_substring(b, 9, 8) IN (0x67f4521f2cf57777, 0x3e2f370aa503dc2a)
