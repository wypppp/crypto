/* DQ-37 探针 3（10-03，执行模型）：曲线阶段留存的体量。2025-10-07（开发周）创建的 pump 币，按三层估行数：
   ①分桶（创建后 [0,300 秒) 5 秒、[300 秒,1 小时) 1 分钟、[1,24 小时) 1 小时，只数有成交的桶）；②每币前 N 笔逐笔（N＝50/100/200/300，创建后 7 天内）；
   ③按币哈希抽 1/8 时的行数。只数行数，不看价格或收益 */
WITH c AS (
    SELECT mint, min(evt_block_time) AS created_at
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date = DATE '2025-10-07'
    GROUP BY 1
),
t AS (
    SELECT t.mint, c.created_at, t.evt_block_time AS ts,
           row_number() OVER (PARTITION BY t.mint ORDER BY t.evt_block_slot, t.evt_tx_index, t.evt_outer_instruction_index, t.evt_inner_instruction_index) AS rn,
           date_diff('second', c.created_at, t.evt_block_time) AS age
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN c ON c.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '2025-10-07' AND DATE '2025-10-14'
      AND t.evt_block_time < c.created_at + INTERVAL '7' DAY
),
b AS (
    SELECT mint,
           CASE WHEN age < 300 THEN 'A' WHEN age < 3600 THEN 'B' WHEN age < 86400 THEN 'C' END AS kind,
           CASE WHEN age < 300 THEN floor(age / 5e0) WHEN age < 3600 THEN floor(age / 60e0) WHEN age < 86400 THEN floor(age / 3600e0) END AS bkey
    FROM t
    WHERE age < 86400
    GROUP BY 1, 2, 3
)
SELECT (SELECT count(*) FROM c) AS n_coins,
       (SELECT count(*) FROM b WHERE kind = 'A') AS bucket_rows_a,
       (SELECT count(*) FROM b WHERE kind = 'B') AS bucket_rows_b,
       (SELECT count(*) FROM b WHERE kind = 'C') AS bucket_rows_c,
       count(*) AS trades_7d,
       count_if(rn <= 50) AS first50, count_if(rn <= 100) AS first100,
       count_if(rn <= 200) AS first200, count_if(rn <= 300) AS first300,
       count_if(rn <= 100 AND mod(from_big_endian_32(substr(sha256(to_utf8(mint)), 1, 4)), 8) = 0) AS first100_hash8
FROM t
