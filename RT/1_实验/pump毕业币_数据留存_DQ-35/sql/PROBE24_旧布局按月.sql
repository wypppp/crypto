/* DQ-35 旧布局按月核对（10-06，执行模型；总控第二十一轮第三节“早期按月核对”、GPT 批 1a-i 增量复核①）。
   每月一个 DQ-37 开发周日（2025-03～2026-06，另加 2026-07-14 与 07-15 升级前的部分），PumpSwap 全部池子的买卖自调用事件，
   按（日期、事件、字节长度、池龄）计数：池龄＝事件日减建池日（当日、30 天内、30 天以上、查不到建池）。
   池地址在事件第 129～160 字节（IDL e0687ae9 与 2c22246b 相同）。只输出计数与字节长度，不含价格。
   用途：升级前出现过的（事件, 长度）组合构成“已核对旧布局”白名单；重取时不在白名单里的升级前事件记“未知”并阻断验收。 */
WITH ic AS (
    SELECT block_date AS d, block_time AS ts, bytearray_substring(data, 9, 8) AS disc, length(data) AS blen,
           to_base58(bytearray_substring(data, 129, 32)) AS pool,
           CASE WHEN bytearray_substring(data, 9, 8) = 0x3e2f370aa503dc2a THEN length(data) >= 416
                WHEN length(data) >= 413
                THEN length(data) >= 461 + CAST(bytearray_to_bigint(reverse(bytearray_substring(data, 410, 4))) AS BIGINT)
                ELSE false END AS has_vq_field
    FROM solana.instruction_calls
    WHERE block_date IN (DATE '2025-03-24', DATE '2025-04-07', DATE '2025-05-03', DATE '2025-06-03', DATE '2025-07-07', DATE '2025-08-03', DATE '2025-09-03', DATE '2025-10-03', DATE '2025-11-03', DATE '2025-12-03', DATE '2026-01-03', DATE '2026-02-09', DATE '2026-03-09', DATE '2026-04-06', DATE '2026-05-25', DATE '2026-06-03', DATE '2026-07-14', DATE '2026-07-15')
      AND executing_account = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
      AND is_inner = true AND tx_success = true
      AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
      AND bytearray_substring(data, 9, 8) IN (0x67f4521f2cf57777, 0x3e2f370aa503dc2a)
      AND (block_date <> DATE '2026-07-15' OR block_time < TIMESTAMP '2026-07-15 18:07:19')
),
cp AS (
    SELECT pool, min(evt_block_date) AS cd
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2025-03-01' AND DATE '2026-07-15'
      AND pool IN (SELECT DISTINCT pool FROM ic)
    GROUP BY 1
)
SELECT CAST(ic.d AS varchar) AS d, CASE WHEN ic.disc = 0x3e2f370aa503dc2a THEN 'S' ELSE 'B' END AS side, ic.blen,
       CASE WHEN cp.cd IS NULL THEN 'no_create' WHEN cp.cd = ic.d THEN 'same_day'
            WHEN date_diff('day', cp.cd, ic.d) < 30 THEN 'lt30' ELSE 'ge30' END AS age,
       count(*) AS n, count(DISTINCT ic.pool) AS n_pools, count_if(ic.has_vq_field) AS n_has_vq_field
FROM ic LEFT JOIN cp ON cp.pool = ic.pool
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4
