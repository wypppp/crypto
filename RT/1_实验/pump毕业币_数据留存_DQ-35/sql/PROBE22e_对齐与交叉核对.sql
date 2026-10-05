/* DQ-35 v2.2 探针（10-05，执行模型；总控第十九轮第二节）：原始事件逐笔解码 vq 的对齐与交叉核对。只输出计数。
   2026-09-23（开发周）12:00～12:10 全部 PumpSwap 事件自调用（solana.instruction_calls，只取成功交易），
   与解码事件表按（交易、外层、内层指令号、方向）对齐：两边多出、重复；对齐后核原始字节与解码列（代币量、池报价储备）；
   解出 vq（i128 小端有符号，高 8 字节超范围记溢出），对卖出用整数成交式反解区间做交叉核对；统计 boost 两类事件。
   偏移（官方 IDL main，PROBE21b 逐字段核对，1 起算）：卖出 vq 401～416；买入 ix_name 长度在 410～413，cashback_bps 在 414＋n，vq 在 446＋n。 */
WITH
ic AS (
    SELECT tx_id, outer_instruction_index AS oix, inner_instruction_index AS iix, data AS b,
           bytearray_substring(data, 9, 8) AS disc
    FROM solana.instruction_calls
    WHERE block_date = DATE '2026-09-23'
      AND block_time >= TIMESTAMP '2026-09-23 12:00:00' AND block_time < TIMESTAMP '2026-09-23 12:10:00'
      AND executing_account = 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
      AND is_inner = true AND tx_success = true
      AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
),
rv AS (
    SELECT tx_id, oix, iix, disc,
           CASE WHEN disc = 0x67f4521f2cf57777 THEN 'B' WHEN disc = 0x3e2f370aa503dc2a THEN 'S' END AS side,
           CASE WHEN disc = 0x67f4521f2cf57777
                THEN 446 + CAST(bytearray_to_bigint(reverse(bytearray_substring(b, 410, 4))) AS INTEGER)
                WHEN disc = 0x3e2f370aa503dc2a THEN 401 END AS pv,
           bytearray_to_bigint(reverse(bytearray_substring(b, 25, 8))) AS amt1,
           bytearray_to_bigint(reverse(bytearray_substring(b, 65, 8))) AS q_res,
           b
    FROM ic
    WHERE disc IN (0x67f4521f2cf57777, 0x3e2f370aa503dc2a)
),
rvq AS (
    SELECT rv.*,
           CASE WHEN length(b) >= pv + 15 THEN bytearray_to_bigint(reverse(bytearray_substring(b, pv, 8))) END AS lo_s,
           CASE WHEN length(b) >= pv + 15 THEN bytearray_to_bigint(reverse(bytearray_substring(b, pv + 8, 8))) END AS hi_s
    FROM rv
),
v AS (
    SELECT rvq.*,
           CASE WHEN hi_s IS NOT NULL AND abs(hi_s) < 4000000000000000000
                THEN CAST(hi_s AS DECIMAL(38,0)) * DECIMAL '18446744073709551616'
                     + CAST(lo_s AS DECIMAL(38,0)) + CASE WHEN lo_s < 0 THEN DECIMAL '18446744073709551616' ELSE DECIMAL '0' END
           END AS vq,
           CASE WHEN hi_s IS NOT NULL AND abs(hi_s) >= 4000000000000000000 THEN 1 ELSE 0 END AS vq_ovf
    FROM rvq
),
ev AS (
    SELECT 'B' AS side, evt_tx_id AS tx_id, evt_outer_instruction_index AS oix, evt_inner_instruction_index AS iix,
           CAST(base_amount_out AS DECIMAL(38,0)) AS amt1, CAST(pool_quote_token_reserves AS DECIMAL(38,0)) AS q0,
           CAST(pool_base_token_reserves AS DECIMAL(38,0)) AS b0, CAST(NULL AS DECIMAL(38,0)) AS q_out
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date = DATE '2026-09-23'
      AND evt_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND evt_block_time < TIMESTAMP '2026-09-23 12:10:00'
    UNION ALL
    SELECT 'S', evt_tx_id, evt_outer_instruction_index, evt_inner_instruction_index,
           CAST(base_amount_in AS DECIMAL(38,0)), CAST(pool_quote_token_reserves AS DECIMAL(38,0)),
           CAST(pool_base_token_reserves AS DECIMAL(38,0)), CAST(quote_amount_out AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date = DATE '2026-09-23'
      AND evt_block_time >= TIMESTAMP '2026-09-23 12:00:00' AND evt_block_time < TIMESTAMP '2026-09-23 12:10:00'
),
j AS (
    SELECT e.side AS e_side, v.side AS v_side, e.amt1 AS e_amt1, v.amt1 AS v_amt1, e.q0, e.b0, e.q_out, v.q_res, v.vq, v.vq_ovf
    FROM ev e
    FULL OUTER JOIN v ON v.tx_id = e.tx_id AND v.oix = e.oix AND v.iix = e.iix AND v.side = e.side
),
x AS (
    SELECT j.*,
           CASE WHEN e_side = 'S' AND v_side = 'S' AND e_amt1 > 0 AND b0 < DECIMAL '1000000000000000000' AND q_out < DECIMAL '1000000000000000000'
                THEN (q_out * (b0 + e_amt1) + e_amt1 - 1 - mod(q_out * (b0 + e_amt1) + e_amt1 - 1, e_amt1)) / e_amt1 - q0 END AS vlo,
           CASE WHEN e_side = 'S' AND v_side = 'S' AND e_amt1 > 0 AND b0 < DECIMAL '1000000000000000000' AND q_out < DECIMAL '1000000000000000000'
                THEN ((q_out + 1) * (b0 + e_amt1) + e_amt1 - 1 - mod((q_out + 1) * (b0 + e_amt1) + e_amt1 - 1, e_amt1)) / e_amt1 - 1 - q0 END AS vhi
    FROM j
)
SELECT count_if(e_side IS NOT NULL AND v_side IS NOT NULL) AS n_matched,
       count_if(e_side IS NOT NULL AND v_side IS NULL) AS n_decoded_only,
       count_if(e_side IS NULL AND v_side IS NOT NULL) AS n_raw_only,
       count_if(e_side IS NOT NULL AND v_side IS NOT NULL AND (CAST(v_amt1 AS DECIMAL(38,0)) <> e_amt1 OR CAST(q_res AS DECIMAL(38,0)) <> q0)) AS n_field_mismatch,
       count_if(v_side IS NOT NULL AND vq IS NULL) AS n_vq_null, sum(vq_ovf) AS n_vq_ovf,
       count_if(vq < 0) AS n_vq_neg, count_if(vq > 0) AS n_vq_pos, count_if(vq = 0) AS n_vq_zero,
       count_if(vlo IS NOT NULL) AS n_xchk, count_if(vlo IS NOT NULL AND (vq < vlo OR vq > vhi)) AS n_xchk_fail,
       (SELECT count(*) FROM (SELECT tx_id, oix, iix, side FROM v GROUP BY 1, 2, 3, 4 HAVING count(*) > 1)) AS n_raw_dup_keys,
       (SELECT count_if(disc = 0xae7c4af90451f611) FROM ic) AS n_init_boost,
       (SELECT count_if(disc = 0x3f451c16305cc2b9) FROM ic) AS n_boost_buy_burn,
       (SELECT count(*) FROM ic) AS n_ic_events
FROM x
