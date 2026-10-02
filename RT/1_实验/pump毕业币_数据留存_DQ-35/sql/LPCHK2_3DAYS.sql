/* DQ-35 补充核查第二步（10-02，执行模型）：LPCHK_3DAYS 发现“本笔前＋本笔变动”与下一笔交易前储备大量不一致（多在当日无加池撤池的池），
   这里按本笔方向分解残差 res＝下一笔交易前 − 本笔后（quote 与 base 各一），看它是否等于 lp_fee、protocol_fee、coin_creator_fee 等，
   并比较排序是否需要外层指令序号（同一交易内多笔）。池与日期同 LPCHK_3DAYS。 */
WITH
pools AS (
    SELECT pool,
           CASE WHEN evt_block_date <= DATE '2025-04-08' THEN DATE '2025-04-08'
                WHEN evt_block_date <= DATE '2025-10-07' THEN DATE '2025-10-07'
                ELSE DATE '2026-05-19' END AS d
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE (evt_block_date BETWEEN DATE '2025-03-09' AND DATE '2025-04-08'
        OR evt_block_date BETWEEN DATE '2025-09-07' AND DATE '2025-10-07'
        OR evt_block_date BETWEEN DATE '2026-04-19' AND DATE '2026-05-19')
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
),
tr AS (
    SELECT evt_block_date AS d, pool, evt_block_slot AS slot, evt_tx_index AS txi, COALESCE(evt_outer_instruction_index, 0) AS oix, COALESCE(evt_inner_instruction_index, 0) AS iix, 'B' AS side,
           CAST(lp_fee AS DOUBLE) AS lpf, COALESCE(CAST(protocol_fee AS DOUBLE), 0) AS pf, COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS cf,
           CAST(pool_quote_token_reserves AS DOUBLE) AS q0, CAST(pool_base_token_reserves AS DOUBLE) AS b0,
           CAST(pool_quote_token_reserves AS DOUBLE) + CAST(quote_amount_in AS DOUBLE)
             - COALESCE(CAST(protocol_fee AS DOUBLE), 0) - COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS q1,
           CAST(pool_base_token_reserves AS DOUBLE) - CAST(base_amount_out AS DOUBLE) AS b1
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT evt_block_date, pool, evt_block_slot, evt_tx_index, COALESCE(evt_outer_instruction_index, 0), COALESCE(evt_inner_instruction_index, 0), 'S',
           CAST(lp_fee AS DOUBLE), COALESCE(CAST(protocol_fee AS DOUBLE), 0), COALESCE(CAST(coin_creator_fee AS DOUBLE), 0),
           CAST(pool_quote_token_reserves AS DOUBLE), CAST(pool_base_token_reserves AS DOUBLE),
           CAST(pool_quote_token_reserves AS DOUBLE) - (CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)),
           CAST(pool_base_token_reserves AS DOUBLE) + CAST(base_amount_in AS DOUBLE)
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
),
lp AS (
    SELECT evt_block_date AS d, pool FROM pumpdotfun_solana.pump_amm_evt_depositevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19') AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT evt_block_date, pool FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19') AND pool IN (SELECT pool FROM pools)
),
lpp AS (SELECT DISTINCT d, pool FROM lp),
pr AS (
    SELECT d, pool, side, slot, txi, q1, b1, lpf, pf, cf,
           lead(q0) OVER w1 AS q0n_i, lead(b0) OVER w1 AS b0n_i, lead(txi) OVER w1 AS txin_i, lead(slot) OVER w1 AS slotn_i,
           lead(q0) OVER w2 AS q0n_o, lead(b0) OVER w2 AS b0n_o
    FROM tr
    WINDOW w1 AS (PARTITION BY d, pool ORDER BY slot, txi, iix),
           w2 AS (PARTITION BY d, pool ORDER BY slot, txi, oix, iix)
),
c AS (
    SELECT p.*, l.pool IS NOT NULL AS has_lp,
           p.q0n_o - p.q1 AS rq, p.b0n_o - p.b1 AS rb,
           slotn_i = slot AND txin_i = txi AS same_tx
    FROM pr p
    LEFT JOIN lpp l ON l.d = p.d AND l.pool = p.pool
    WHERE p.q0n_o IS NOT NULL
)
SELECT d, side, has_lp,
       count(*) AS n_pairs,
       count_if(abs(q0n_i - q1) <= 1 AND abs(b0n_i - b1) <= 1) AS n_exact_inner_order,
       count_if(abs(rq) <= 1 AND abs(rb) <= 1) AS n_exact_outer_order,
       count_if(abs(rb) <= 1) AS n_base_exact,
       count_if(abs(rb) <= 1 AND abs(rq - lpf) <= 1) AS n_q_plus_lpfee,
       count_if(abs(rb) <= 1 AND abs(rq + lpf) <= 1) AS n_q_minus_lpfee,
       count_if(abs(rb) <= 1 AND abs(rq - pf) <= 1) AS n_q_plus_protofee,
       count_if(abs(rb) <= 1 AND abs(rq - pf - cf) <= 1) AS n_q_plus_proto_creator,
       count_if(abs(rb) <= 1 AND abs(rq - cf) <= 1 AND cf > 0) AS n_q_plus_creator,
       count_if(abs(rb) <= 1 AND abs(rq + pf) <= 1 AND pf > 0) AS n_q_minus_protofee,
       count_if(NOT (abs(rq) <= 1 AND abs(rb) <= 1) AND same_tx) AS n_mis_next_same_tx,
       approx_percentile(abs(rq) / nullif(q0n_o, 0), 0.5) FILTER (WHERE abs(rq) > 1) AS rq_rel_med,
       approx_percentile(abs(rq) / nullif(q0n_o, 0), 0.99) FILTER (WHERE abs(rq) > 1) AS rq_rel_p99,
       count_if(abs(rq) / nullif(q0n_o, 0) > 0.01 OR abs(rb) / nullif(b0n_o, 0) > 0.01) AS n_big_1pct
FROM c
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
