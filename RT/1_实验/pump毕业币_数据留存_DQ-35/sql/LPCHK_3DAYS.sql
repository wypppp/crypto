/* DQ-35 补充核查（10-02，执行模型；总控第十轮第 9 条，兼为代码审计第 2 处量化）：
   pump 迁移池（建池事件由 pump 程序发起、序号 0）在两笔成交之间的加池、撤池是否常见。
   抽样 3 天：2025-04-08、2025-10-07、2026-05-19（均在 C1 的评估周内，不在封存周）；池＝该日之前 30 天内（含当日）建的池。
   每个池当日的成交按 (slot, tx, 内指令) 排序，比较“本笔交易前储备＋本笔变动”（F59 公式）与下一笔成交的交易前储备；
   另数当日这些池的 DepositEvent、WithdrawEvent。只输出按日汇总，不输出逐币结果。 */
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
    SELECT evt_block_date AS d, pool, evt_block_slot AS slot, evt_tx_index AS txi, COALESCE(evt_inner_instruction_index, 0) AS iix,
           CAST(pool_quote_token_reserves AS DOUBLE) AS q0, CAST(pool_base_token_reserves AS DOUBLE) AS b0,
           CAST(pool_quote_token_reserves AS DOUBLE) + CAST(quote_amount_in AS DOUBLE)
             - COALESCE(CAST(protocol_fee AS DOUBLE), 0) - COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS q1,
           CAST(pool_base_token_reserves AS DOUBLE) - CAST(base_amount_out AS DOUBLE) AS b1
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT evt_block_date, pool, evt_block_slot, evt_tx_index, COALESCE(evt_inner_instruction_index, 0),
           CAST(pool_quote_token_reserves AS DOUBLE), CAST(pool_base_token_reserves AS DOUBLE),
           CAST(pool_quote_token_reserves AS DOUBLE) - (CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)),
           CAST(pool_base_token_reserves AS DOUBLE) + CAST(base_amount_in AS DOUBLE)
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
),
lp AS (
    SELECT evt_block_date AS d, pool, 'D' AS kind
    FROM pumpdotfun_solana.pump_amm_evt_depositevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT evt_block_date, pool, 'W'
    FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
    WHERE evt_block_date IN (DATE '2025-04-08', DATE '2025-10-07', DATE '2026-05-19')
      AND pool IN (SELECT pool FROM pools)
),
lpp AS (
    SELECT d, pool, count_if(kind = 'D') AS n_dep, count_if(kind = 'W') AS n_wd
    FROM lp
    GROUP BY 1, 2
),
pr AS (
    SELECT d, pool, q1, b1,
           lead(q0) OVER (PARTITION BY d, pool ORDER BY slot, txi, iix) AS q0n,
           lead(b0) OVER (PARTITION BY d, pool ORDER BY slot, txi, iix) AS b0n
    FROM tr
),
pm AS (
    SELECT p.d, p.pool, p.q1, p.b1, p.q0n, p.b0n,
           p.q0n IS NOT NULL AND (abs(p.q1 - p.q0n) > 1 OR abs(p.b1 - p.b0n) > 1) AS mis,
           greatest(abs(p.q1 - p.q0n) / nullif(p.q0n, 0), abs(p.b1 - p.b0n) / nullif(p.b0n, 0)) AS rel,
           COALESCE(l.n_dep, 0) + COALESCE(l.n_wd, 0) > 0 AS has_lp
    FROM pr p
    LEFT JOIN lpp l ON l.d = p.d AND l.pool = p.pool
),
agg AS (
    SELECT d,
           count(DISTINCT pool) AS n_pools_traded,
           count(*) AS n_trades,
           count_if(q0n IS NOT NULL) AS n_pairs,
           count_if(mis) AS n_pairs_mismatch,
           count_if(mis AND rel > 1e-6) AS n_pairs_mismatch_rel_1e6,
           count_if(mis AND has_lp) AS n_mismatch_in_lp_pools,
           count_if(mis AND NOT has_lp) AS n_mismatch_in_nolp_pools,
           approx_percentile(rel, 0.5) FILTER (WHERE mis) AS rel_median_mismatch,
           max(rel) FILTER (WHERE mis) AS rel_max_mismatch,
           count(DISTINCT IF(has_lp, pool)) AS n_traded_pools_with_lp
    FROM pm
    GROUP BY d
),
pc AS (SELECT d, count(*) AS n_pools_created_30d FROM pools GROUP BY d),
lc AS (SELECT d, sum(n_dep) AS n_deposit_events, sum(n_wd) AS n_withdraw_events, count(*) AS n_pools_with_lp FROM lpp GROUP BY d)
SELECT a.*, pc.n_pools_created_30d, lc.n_deposit_events, lc.n_withdraw_events, lc.n_pools_with_lp
FROM agg a
LEFT JOIN pc ON pc.d = a.d
LEFT JOIN lc ON lc.d = a.d
ORDER BY a.d
