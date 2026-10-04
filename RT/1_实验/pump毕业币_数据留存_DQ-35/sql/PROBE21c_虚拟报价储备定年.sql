/* DQ-35 v2.1 探针（10-04，执行模型）：PumpSwap 事件里的 virtual_quote_reserves 从哪天起非零。
   背景：PROBE21b 发现 2026-09-23 当日新池的买卖已按“真实报价储备＋virtual_quote_reserves”成交（Dune 解码表没有此列）。
   范围：39 个 DQ-37 开发周日期（避开封存期），每日只取当日由 pump 迁移创建的池在 12:00～12:05 的 buy／sell 调用；
   只读事件字节长度与 virtual_quote_reserves（协议参数），不读价格或收益。
   偏移（官方 IDL main，PROBE21b 已逐字段核对）：卖出事件 data 第 401～416 字节（1 起算）；买入事件在 ix_name 之后再隔 32 字节。 */
WITH
pl AS (
    SELECT DISTINCT evt_block_date AS d, pool
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date IN (DATE '2025-04-07', DATE '2025-04-21', DATE '2025-05-03', DATE '2025-05-18', DATE '2025-06-03', DATE '2025-06-18', DATE '2025-07-07', DATE '2025-07-18', DATE '2025-08-03', DATE '2025-09-03', DATE '2025-09-22', DATE '2025-10-03', DATE '2025-10-18', DATE '2025-11-03', DATE '2025-11-18', DATE '2025-12-03', DATE '2025-12-18', DATE '2026-01-03', DATE '2026-01-19', DATE '2026-02-09', DATE '2026-02-18', DATE '2026-03-09', DATE '2026-03-18', DATE '2026-04-06', DATE '2026-04-18', DATE '2026-06-03', DATE '2026-07-18', DATE '2026-08-03', DATE '2026-08-18', DATE '2026-09-03', DATE '2026-09-08', DATE '2026-09-10', DATE '2026-09-21', DATE '2026-09-24', DATE '2026-09-26', DATE '2026-09-28', DATE '2026-09-30', DATE '2026-10-02', DATE '2026-10-03')
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
),
calls AS (
    SELECT 'B' AS side, call_block_date AS d, account_pool AS pool, call_inner_instructions AS ins
    FROM pumpdotfun_solana.pump_amm_call_buy
    WHERE call_block_date IN (DATE '2025-04-07', DATE '2025-04-21', DATE '2025-05-03', DATE '2025-05-18', DATE '2025-06-03', DATE '2025-06-18', DATE '2025-07-07', DATE '2025-07-18', DATE '2025-08-03', DATE '2025-09-03', DATE '2025-09-22', DATE '2025-10-03', DATE '2025-10-18', DATE '2025-11-03', DATE '2025-11-18', DATE '2025-12-03', DATE '2025-12-18', DATE '2026-01-03', DATE '2026-01-19', DATE '2026-02-09', DATE '2026-02-18', DATE '2026-03-09', DATE '2026-03-18', DATE '2026-04-06', DATE '2026-04-18', DATE '2026-06-03', DATE '2026-07-18', DATE '2026-08-03', DATE '2026-08-18', DATE '2026-09-03', DATE '2026-09-08', DATE '2026-09-10', DATE '2026-09-21', DATE '2026-09-24', DATE '2026-09-26', DATE '2026-09-28', DATE '2026-09-30', DATE '2026-10-02', DATE '2026-10-03')
      AND ((call_block_time >= TIMESTAMP '2025-04-07 12:00:00' AND call_block_time < TIMESTAMP '2025-04-07 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-04-21 12:00:00' AND call_block_time < TIMESTAMP '2025-04-21 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-05-03 12:00:00' AND call_block_time < TIMESTAMP '2025-05-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-05-18 12:00:00' AND call_block_time < TIMESTAMP '2025-05-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-06-03 12:00:00' AND call_block_time < TIMESTAMP '2025-06-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-06-18 12:00:00' AND call_block_time < TIMESTAMP '2025-06-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-07-07 12:00:00' AND call_block_time < TIMESTAMP '2025-07-07 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-07-18 12:00:00' AND call_block_time < TIMESTAMP '2025-07-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-08-03 12:00:00' AND call_block_time < TIMESTAMP '2025-08-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-09-03 12:00:00' AND call_block_time < TIMESTAMP '2025-09-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-09-22 12:00:00' AND call_block_time < TIMESTAMP '2025-09-22 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-10-03 12:00:00' AND call_block_time < TIMESTAMP '2025-10-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-10-18 12:00:00' AND call_block_time < TIMESTAMP '2025-10-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-11-03 12:00:00' AND call_block_time < TIMESTAMP '2025-11-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-11-18 12:00:00' AND call_block_time < TIMESTAMP '2025-11-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-12-03 12:00:00' AND call_block_time < TIMESTAMP '2025-12-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-12-18 12:00:00' AND call_block_time < TIMESTAMP '2025-12-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-01-03 12:00:00' AND call_block_time < TIMESTAMP '2026-01-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-01-19 12:00:00' AND call_block_time < TIMESTAMP '2026-01-19 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-02-09 12:00:00' AND call_block_time < TIMESTAMP '2026-02-09 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-02-18 12:00:00' AND call_block_time < TIMESTAMP '2026-02-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-03-09 12:00:00' AND call_block_time < TIMESTAMP '2026-03-09 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-03-18 12:00:00' AND call_block_time < TIMESTAMP '2026-03-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-04-06 12:00:00' AND call_block_time < TIMESTAMP '2026-04-06 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-04-18 12:00:00' AND call_block_time < TIMESTAMP '2026-04-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-06-03 12:00:00' AND call_block_time < TIMESTAMP '2026-06-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-07-18 12:00:00' AND call_block_time < TIMESTAMP '2026-07-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-08-03 12:00:00' AND call_block_time < TIMESTAMP '2026-08-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-08-18 12:00:00' AND call_block_time < TIMESTAMP '2026-08-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-03 12:00:00' AND call_block_time < TIMESTAMP '2026-09-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-08 12:00:00' AND call_block_time < TIMESTAMP '2026-09-08 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-10 12:00:00' AND call_block_time < TIMESTAMP '2026-09-10 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-21 12:00:00' AND call_block_time < TIMESTAMP '2026-09-21 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-24 12:00:00' AND call_block_time < TIMESTAMP '2026-09-24 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-26 12:00:00' AND call_block_time < TIMESTAMP '2026-09-26 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-28 12:00:00' AND call_block_time < TIMESTAMP '2026-09-28 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-30 12:00:00' AND call_block_time < TIMESTAMP '2026-09-30 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-10-02 12:00:00' AND call_block_time < TIMESTAMP '2026-10-02 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-10-03 12:00:00' AND call_block_time < TIMESTAMP '2026-10-03 12:05:00'))
    UNION ALL
    SELECT 'S', call_block_date, account_pool, call_inner_instructions
    FROM pumpdotfun_solana.pump_amm_call_sell
    WHERE call_block_date IN (DATE '2025-04-07', DATE '2025-04-21', DATE '2025-05-03', DATE '2025-05-18', DATE '2025-06-03', DATE '2025-06-18', DATE '2025-07-07', DATE '2025-07-18', DATE '2025-08-03', DATE '2025-09-03', DATE '2025-09-22', DATE '2025-10-03', DATE '2025-10-18', DATE '2025-11-03', DATE '2025-11-18', DATE '2025-12-03', DATE '2025-12-18', DATE '2026-01-03', DATE '2026-01-19', DATE '2026-02-09', DATE '2026-02-18', DATE '2026-03-09', DATE '2026-03-18', DATE '2026-04-06', DATE '2026-04-18', DATE '2026-06-03', DATE '2026-07-18', DATE '2026-08-03', DATE '2026-08-18', DATE '2026-09-03', DATE '2026-09-08', DATE '2026-09-10', DATE '2026-09-21', DATE '2026-09-24', DATE '2026-09-26', DATE '2026-09-28', DATE '2026-09-30', DATE '2026-10-02', DATE '2026-10-03')
      AND ((call_block_time >= TIMESTAMP '2025-04-07 12:00:00' AND call_block_time < TIMESTAMP '2025-04-07 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-04-21 12:00:00' AND call_block_time < TIMESTAMP '2025-04-21 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-05-03 12:00:00' AND call_block_time < TIMESTAMP '2025-05-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-05-18 12:00:00' AND call_block_time < TIMESTAMP '2025-05-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-06-03 12:00:00' AND call_block_time < TIMESTAMP '2025-06-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-06-18 12:00:00' AND call_block_time < TIMESTAMP '2025-06-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-07-07 12:00:00' AND call_block_time < TIMESTAMP '2025-07-07 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-07-18 12:00:00' AND call_block_time < TIMESTAMP '2025-07-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-08-03 12:00:00' AND call_block_time < TIMESTAMP '2025-08-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-09-03 12:00:00' AND call_block_time < TIMESTAMP '2025-09-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-09-22 12:00:00' AND call_block_time < TIMESTAMP '2025-09-22 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-10-03 12:00:00' AND call_block_time < TIMESTAMP '2025-10-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-10-18 12:00:00' AND call_block_time < TIMESTAMP '2025-10-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-11-03 12:00:00' AND call_block_time < TIMESTAMP '2025-11-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-11-18 12:00:00' AND call_block_time < TIMESTAMP '2025-11-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-12-03 12:00:00' AND call_block_time < TIMESTAMP '2025-12-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2025-12-18 12:00:00' AND call_block_time < TIMESTAMP '2025-12-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-01-03 12:00:00' AND call_block_time < TIMESTAMP '2026-01-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-01-19 12:00:00' AND call_block_time < TIMESTAMP '2026-01-19 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-02-09 12:00:00' AND call_block_time < TIMESTAMP '2026-02-09 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-02-18 12:00:00' AND call_block_time < TIMESTAMP '2026-02-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-03-09 12:00:00' AND call_block_time < TIMESTAMP '2026-03-09 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-03-18 12:00:00' AND call_block_time < TIMESTAMP '2026-03-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-04-06 12:00:00' AND call_block_time < TIMESTAMP '2026-04-06 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-04-18 12:00:00' AND call_block_time < TIMESTAMP '2026-04-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-06-03 12:00:00' AND call_block_time < TIMESTAMP '2026-06-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-07-18 12:00:00' AND call_block_time < TIMESTAMP '2026-07-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-08-03 12:00:00' AND call_block_time < TIMESTAMP '2026-08-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-08-18 12:00:00' AND call_block_time < TIMESTAMP '2026-08-18 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-03 12:00:00' AND call_block_time < TIMESTAMP '2026-09-03 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-08 12:00:00' AND call_block_time < TIMESTAMP '2026-09-08 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-10 12:00:00' AND call_block_time < TIMESTAMP '2026-09-10 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-21 12:00:00' AND call_block_time < TIMESTAMP '2026-09-21 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-24 12:00:00' AND call_block_time < TIMESTAMP '2026-09-24 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-26 12:00:00' AND call_block_time < TIMESTAMP '2026-09-26 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-28 12:00:00' AND call_block_time < TIMESTAMP '2026-09-28 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-09-30 12:00:00' AND call_block_time < TIMESTAMP '2026-09-30 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-10-02 12:00:00' AND call_block_time < TIMESTAMP '2026-10-02 12:05:00')
         OR (call_block_time >= TIMESTAMP '2026-10-03 12:00:00' AND call_block_time < TIMESTAMP '2026-10-03 12:05:00'))
),
ev AS (
    SELECT c.side, c.d, c.pool, from_base58(t.data) AS b
    FROM calls c
    JOIN pl ON pl.d = c.d AND pl.pool = c.pool
    CROSS JOIN UNNEST(transform(c.ins, x -> CAST(ROW(x.data, x.executing_account) AS ROW(data varchar, ea varchar))))
         AS t(data, ea)
    WHERE t.ea = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
      AND bytearray_substring(from_base58(t.data), 1, 8) = 0xe445a52e51cb9a1d
      AND bytearray_substring(from_base58(t.data), 9, 8) IN (0x67f4521f2cf57777, 0x3e2f370aa503dc2a)
),
vq AS (
    SELECT side, d, pool, length(b) AS nbytes,
           CASE WHEN side = 'S' AND length(b) >= 416 THEN 401
                WHEN side = 'B' AND length(b) >= 489
                THEN 414 + CAST(bytearray_to_bigint(reverse(bytearray_substring(b, 410, 4))) AS INTEGER) + 32 END AS pos,
           b
    FROM ev
),
v AS (
    SELECT side, d, pool, nbytes,
           CASE WHEN pos IS NOT NULL THEN bytearray_to_bigint(reverse(bytearray_substring(b, pos, 8))) END AS vq_lo,
           CASE WHEN pos IS NOT NULL THEN bytearray_substring(b, pos + 8, 8) <> 0x0000000000000000 END AS vq_hi_nz
    FROM vq
)
SELECT d, side, count(*) AS n, count(DISTINCT pool) AS n_pools,
       array_join(array_sort(array_distinct(array_agg(CAST(nbytes AS varchar)))), ',') AS nbytes_set,
       count_if(vq_lo IS NOT NULL) AS n_has_vq, count_if(vq_lo <> 0 OR vq_hi_nz) AS n_vq_nonzero,
       count(DISTINCT CASE WHEN vq_lo <> 0 THEN pool END) AS n_pools_vq_nonzero,
       min(vq_lo) AS vq_min, max(vq_lo) AS vq_max, approx_percentile(vq_lo, 0.5) AS vq_med, count_if(vq_hi_nz) AS n_hi_nz
FROM v
GROUP BY 1, 2
ORDER BY 1, 2
