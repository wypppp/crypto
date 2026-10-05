/* DQ-35 InitBoost 全量扫描 a（10-06，执行模型；总控第二十轮第二节）：2026-07-15～2026-08-04 的 PumpSwap 自调用事件。
   生成：过程/build_boostscan_sql.py。rec='P' 每个有 boost 的池一行（次数、时刻、vq 极值、建池信息）；
   rec='D' 全部事件按判别符计数。没有成交价或收益。 */
WITH ic AS (
    SELECT block_time AS ts, data AS b, bytearray_substring(data, 9, 8) AS disc
    FROM solana.instruction_calls
    WHERE block_date BETWEEN DATE '2026-07-15' AND DATE '2026-08-04'
      AND executing_account = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
      AND is_inner = true AND tx_success = true
      AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
),
bo AS (
    SELECT ts, disc, to_base58(bytearray_substring(b, 89, 32)) AS pool,
           bytearray_to_bigint(reverse(bytearray_substring(b, pv, 8))) AS lo_s,
           bytearray_to_bigint(reverse(bytearray_substring(b, pv + 8, 8))) AS hi_s
    FROM (SELECT ic.*, CASE WHEN disc = 0xae7c4af90451f611 THEN 121 ELSE 177 END AS pv
          FROM ic WHERE disc IN (0xae7c4af90451f611, 0x3f451c16305cc2b9) AND length(b) >= 192 - 56 * CAST(disc = 0xae7c4af90451f611 AS INTEGER))
),
bv AS (
    SELECT ts, disc, pool, CASE WHEN abs(hi_s) < 4000000000000000000
                THEN CAST(hi_s AS DECIMAL(38,0)) * DECIMAL '18446744073709551616' + CAST(lo_s AS DECIMAL(38,0))
                     + CASE WHEN lo_s < 0 THEN DECIMAL '18446744073709551616' ELSE DECIMAL '0' END END AS vq,
           CASE WHEN abs(hi_s) >= 4000000000000000000 THEN 1 ELSE 0 END AS ovf
    FROM bo
),
pp AS (
    SELECT pool,
           count_if(disc = 0xae7c4af90451f611) AS n_init, count_if(disc = 0x3f451c16305cc2b9) AS n_burn,
           to_unixtime(min(CASE WHEN disc = 0xae7c4af90451f611 THEN ts END)) AS first_init_t,
           to_unixtime(max(CASE WHEN disc = 0xae7c4af90451f611 THEN ts END)) AS last_init_t,
           to_unixtime(min(CASE WHEN disc = 0x3f451c16305cc2b9 THEN ts END)) AS first_burn_t,
           min(CASE WHEN disc = 0xae7c4af90451f611 THEN vq END) AS vq_init_min, max(CASE WHEN disc = 0xae7c4af90451f611 THEN vq END) AS vq_init_max,
           min(CASE WHEN disc = 0x3f451c16305cc2b9 THEN vq END) AS vq_burn_min, max(CASE WHEN disc = 0x3f451c16305cc2b9 THEN vq END) AS vq_burn_max,
           sum(ovf) AS n_ovf
    FROM bv GROUP BY 1
),
cp AS (
    SELECT pool, to_unixtime(min(evt_block_time)) AS pool_created_t, min_by(base_mint, evt_block_time) AS base_mint,
           min_by(quote_mint, evt_block_time) AS quote_mint,
           min_by(evt_outer_executing_account, evt_block_time) AS creator_prog,
           min_by("index", evt_block_time) AS pool_index, count(*) AS n_create
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2025-03-01' AND DATE '2026-08-04'
      AND pool IN (SELECT pool FROM pp)
    GROUP BY 1
)
SELECT 'P' AS rec, pp.pool, CAST(NULL AS VARCHAR) AS disc, pp.n_init, pp.n_burn, pp.first_init_t, pp.last_init_t, pp.first_burn_t,
       pp.vq_init_min, pp.vq_init_max, pp.vq_burn_min, pp.vq_burn_max, pp.n_ovf,
       cp.pool_created_t, cp.base_mint, cp.quote_mint, cp.creator_prog, cp.pool_index, cp.n_create
FROM pp LEFT JOIN cp ON cp.pool = pp.pool
UNION ALL
SELECT 'D', NULL, to_hex(disc), count(*), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM ic GROUP BY disc
