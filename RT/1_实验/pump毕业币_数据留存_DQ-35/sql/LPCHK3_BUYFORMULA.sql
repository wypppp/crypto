/* DQ-35 补充核查第三步（10-02，执行模型）：PumpSwap 买入后池的 quote 储备用哪个公式。LPCHK2 显示卖出按 F59 公式逐位吻合，买入在 2025 年不吻合。
   候选：A 交易前＋quote_amount_in−protocol_fee−coin_creator_fee（F59）；B ＋quote_amount_in_with_lp_fee；C ＋quote_amount_in；
   D ＋user_quote_amount_in−protocol_fee−coin_creator_fee；E ＋quote_amount_in＋lp_fee；F ＋quote_amount_in_with_lp_fee−protocol_fee−coin_creator_fee。
   对照：下一笔成交的交易前 quote 储备（按 slot、tx、外层、内层指令排序；只用当日无加池撤池的池；同 LPCHK 的池与日期）。 */
WITH
pools AS (
    SELECT pool
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE (evt_block_date BETWEEN DATE '2025-03-09' AND DATE '2025-04-08'
        OR evt_block_date BETWEEN DATE '2025-09-07' AND DATE '2025-10-07'
        OR evt_block_date BETWEEN DATE '2026-04-19' AND DATE '2026-05-19')
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
),
lpp AS (
    SELECT DISTINCT evt_block_date AS d, pool FROM pumpdotfun_solana.pump_amm_evt_depositevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
    UNION
    SELECT DISTINCT evt_block_date, pool FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
),
tr AS (
    SELECT evt_block_date AS d, pool, evt_block_slot AS slot, evt_tx_index AS txi,
           COALESCE(evt_outer_instruction_index, 0) AS oix, COALESCE(evt_inner_instruction_index, 0) AS iix, 'B' AS side,
           CAST(pool_quote_token_reserves AS DOUBLE) AS q0,
           CAST(quote_amount_in AS DOUBLE) AS qin,
           CAST(quote_amount_in_with_lp_fee AS DOUBLE) AS qinl,
           CAST(user_quote_amount_in AS DOUBLE) AS qu,
           CAST(lp_fee AS DOUBLE) AS lpf,
           COALESCE(CAST(protocol_fee AS DOUBLE), 0) AS pf,
           COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS cf
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT evt_block_date, pool, evt_block_slot, evt_tx_index,
           COALESCE(evt_outer_instruction_index, 0), COALESCE(evt_inner_instruction_index, 0), 'S',
           CAST(pool_quote_token_reserves AS DOUBLE), NULL, NULL, NULL, NULL, NULL, NULL
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
),
pr AS (
    SELECT t.*, lead(q0) OVER (PARTITION BY d, pool ORDER BY slot, txi, oix, iix) AS q0n
    FROM tr t
),
c AS (
    SELECT p.*
    FROM pr p
    LEFT JOIN lpp l ON l.d = p.d AND l.pool = p.pool
    WHERE p.side = 'B' AND p.q0n IS NOT NULL AND l.pool IS NULL
)
SELECT d,
       count(*) AS n_buy_pairs,
       count_if(abs(q0 + qin - pf - cf - q0n) <= 1) AS a_f59,
       count_if(abs(q0 + qinl - q0n) <= 1) AS b_with_lp,
       count_if(abs(q0 + qin - q0n) <= 1) AS c_qin,
       count_if(abs(q0 + qu - pf - cf - q0n) <= 1) AS d_user_minus_fees,
       count_if(abs(q0 + qin + lpf - q0n) <= 1) AS e_qin_plus_lp,
       count_if(abs(q0 + qinl - pf - cf - q0n) <= 1) AS f_with_lp_minus_fees,
       count_if(abs(qinl - qin - lpf) <= 1) AS chk_qinl_eq_qin_lp,
       count_if(abs(qu - qinl - pf - cf) <= 1) AS chk_qu_eq_qinl_pf_cf,
       approx_percentile(q0n - (q0 + qin - pf - cf), 0.5) AS res_a_med,
       approx_percentile((q0n - (q0 + qin - pf - cf)) / nullif(lpf, 0), 0.5) AS res_a_over_lpf_med,
       approx_percentile((q0n - (q0 + qin - pf - cf)) / nullif(qin, 0), 0.5) AS res_a_over_qin_med
FROM c
GROUP BY 1
ORDER BY 1
