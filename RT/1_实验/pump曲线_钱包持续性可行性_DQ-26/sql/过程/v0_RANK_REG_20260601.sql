/* DQ-26 第一步·排名查询（卡片_v1.md §1～§3）；由 sql/build_rank_sql.py 生成（REG_20260601）。
   币：2026-06-01～2026-06-01 创建的 SOL 计价 pump 币；成交（曲线＋PumpSwap）截至 2026-06-03 24:00 UTC。
   mig … amm_raw 逐字取自 DQ-21 sql/WM_A.sql（只换日期）；t3 同 S0 v1.3；期末持仓按池状态清算。
   只读 2026-06-01～2026-06-03 的分区。输出 kind：S 汇总、W 合格钱包、D 初排前 1000 个钱包的（钱包, 币）明细、C 币级状态。 */
WITH
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        max(CAST("user" AS varchar)) AS dev,
        max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-01'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
mig AS (
    SELECT mint, min_by(pool, evt_block_slot) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-03'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
cp AS (
    SELECT
        pool,
        max(base_mint) AS base_mint,
        max(quote_mint) AS quote_mint,
        max(base_mint_decimals) AS bd,
        max(quote_mint_decimals) AS qd,
        min(evt_block_slot) AS pool_created_slot,
        COALESCE(bool_or(evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0), false) AS by_pump
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-03'
      AND (
          base_mint IN (SELECT mint FROM sol_cohort)
          OR quote_mint IN (SELECT mint FROM sol_cohort)
      )
    GROUP BY 1
),
cp_norm AS (
    SELECT
        pool,
        CASE
            WHEN quote_mint = 'So11111111111111111111111111111111111111112' THEN base_mint
            WHEN base_mint = 'So11111111111111111111111111111111111111112' THEN quote_mint
        END AS mint,
        base_mint = 'So11111111111111111111111111111111111111112' AS pool_reversed,
        CASE WHEN base_mint = 'So11111111111111111111111111111111111111112' THEN qd ELSE bd END AS td,
        CASE WHEN base_mint = 'So11111111111111111111111111111111111111112' THEN bd ELSE qd END AS sd,
        pool_created_slot,
        by_pump
    FROM cp
    WHERE (
        quote_mint = 'So11111111111111111111111111111111111111112'
        AND base_mint IN (SELECT mint FROM sol_cohort)
    ) OR (
        base_mint = 'So11111111111111111111111111111111111111112'
        AND quote_mint IN (SELECT mint FROM sol_cohort)
    )
),
fallback_pool AS (
    SELECT mint, min_by(pool, pool_created_slot) AS pool
    FROM cp_norm
    WHERE by_pump
    GROUP BY 1
),
mapping0 AS (
    SELECT c.mint, COALESCE(m.pool, f.pool) AS pool
    FROM sol_cohort c
    LEFT JOIN mig m ON m.mint = c.mint
    LEFT JOIN fallback_pool f ON f.mint = c.mint
),
mapping AS (
    SELECT m.mint, m.pool, p.pool_reversed, p.td, p.sd
    FROM mapping0 m
    JOIN cp_norm p ON p.pool = m.pool AND p.mint = m.mint
),
amm_raw AS (
    SELECT
        m.mint, m.pool_reversed, m.td, m.sd,
        a.evt_block_time AS ts, a.evt_block_slot AS slot, a.evt_tx_index AS txi,
        COALESCE(a.evt_outer_instruction_index, 0) AS oix,
        COALESCE(a.evt_inner_instruction_index, -1) AS iix,
        CAST(a."user" AS varchar) AS usr,
        NOT m.pool_reversed AS is_buy,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_out AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.user_quote_amount_in AS DOUBLE) / power(10, m.sd) END AS sol_user,
        CASE WHEN m.pool_reversed THEN CAST(a.user_quote_amount_in AS DOUBLE) / power(10, m.td)
             ELSE CAST(a.base_amount_out AS DOUBLE) / power(10, m.td) END AS tok,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.protocol_fee AS DOUBLE) / power(10, m.sd)) AS fee_proto,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.coin_creator_fee AS DOUBLE) / power(10, m.sd)) AS fee_creator,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.lp_fee AS DOUBLE) / power(10, m.sd)) AS fee_lp,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END AS sol_pre_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END AS target_pre_raw,
        CASE WHEN m.pool_reversed THEN -CAST(a.base_amount_out AS DOUBLE)
             ELSE CAST(a.quote_amount_in_with_lp_fee AS DOUBLE) END AS dsol_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.quote_amount_in_with_lp_fee AS DOUBLE)
             ELSE -CAST(a.base_amount_out AS DOUBLE) END AS dtarget_raw
    FROM pumpdotfun_solana.pump_amm_evt_buyevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-03'
    UNION ALL
    SELECT
        m.mint, m.pool_reversed, m.td, m.sd,
        a.evt_block_time, a.evt_block_slot, a.evt_tx_index,
        COALESCE(a.evt_outer_instruction_index, 0), COALESCE(a.evt_inner_instruction_index, -1),
        CAST(a."user" AS varchar),
        m.pool_reversed,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.user_quote_amount_out AS DOUBLE) / power(10, m.sd) END,
        CASE WHEN m.pool_reversed THEN CAST(a.user_quote_amount_out AS DOUBLE) / power(10, m.td)
             ELSE CAST(a.base_amount_in AS DOUBLE) / power(10, m.td) END,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.protocol_fee AS DOUBLE) / power(10, m.sd)),
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.coin_creator_fee AS DOUBLE) / power(10, m.sd)),
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.lp_fee AS DOUBLE) / power(10, m.sd)),
        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE)
             ELSE -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0)) END,
        CASE WHEN m.pool_reversed THEN -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0))
             ELSE CAST(a.base_amount_in AS DOUBLE) END
    FROM pumpdotfun_solana.pump_amm_evt_sellevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-03'
),
ev AS (
    SELECT
        t.mint, 0 AS venue, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
        COALESCE(t.evt_outer_instruction_index, 0) AS oix,
        COALESCE(t.evt_inner_instruction_index, -1) AS iix,
        CAST(t."user" AS varchar) AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CASE WHEN COALESCE(t.is_buy, t.isBuy)
             THEN CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) + ceiling(CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) * (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) / 1e4)
             ELSE CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) - ceiling(CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) * (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) / 1e4) END / 1e9 AS sol_user,
        CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_gross,
        CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok,
        ceiling(CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) * (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) / 1e4) / 1e9 AS fee_all,
        (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) AS fee_bps,
        CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
        CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
        CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-03'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mint, 1, ts, slot, txi, oix, iix, usr, is_buy, sol_user,
        IF(is_buy, sol_user - COALESCE(fee_proto, 0) - COALESCE(fee_creator, 0) - COALESCE(fee_lp, 0),
                   sol_user + COALESCE(fee_proto, 0) + COALESCE(fee_creator, 0) + COALESCE(fee_lp, 0)),
        tok,
        COALESCE(fee_proto, 0) + COALESCE(fee_creator, 0) + COALESCE(fee_lp, 0),
        CAST(NULL AS DOUBLE),
        (sol_pre_raw + dsol_raw) / power(10, sd), (target_pre_raw + dtarget_raw) / power(10, td),
        CAST(NULL AS DOUBLE)
    FROM amm_raw
),
ev2 AS (
    SELECT
        e.*, c.created_at, c.created_slot, c.dev,
        row_number() OVER (PARTITION BY e.mint ORDER BY e.slot, e.txi, e.oix, e.iix, e.venue) AS rn,
        date_diff('second', c.created_at, max(e.ts) OVER (
            PARTITION BY e.mint ORDER BY e.slot, e.txi, e.oix, e.iix, e.venue
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) AS dt
    FROM ev e
    JOIN sol_cohort c ON c.mint = e.mint
    WHERE e.ts >= c.created_at
      AND e.ts < DATE '2026-06-03' + INTERVAL '1' DAY
),
q1 AS (
    SELECT
        mint, rn, dt,
        min(CASE WHEN is_buy AND sol_gross >= 0.1 AND usr IS NOT NULL AND usr <> dev THEN rn END)
          OVER (PARTITION BY mint, usr) AS first_q_rn
    FROM ev2
),
q2 AS (
    SELECT
        mint, rn, dt, rn = first_q_rn AS q_new,
        sum(IF(rn = first_q_rn, 1, 0)) OVER (
            PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS q_count
    FROM q1
),
t3 AS (
    SELECT mint, min_by(dt, rn) AS t3_s
    FROM q2
    WHERE q_new AND q_count = 3
    GROUP BY 1
),
coin AS (
    SELECT
        e.mint,
        max(e.created_at) AS created_at,
        max(e.created_slot) AS created_slot,
        max(e.dev) AS dev,
        max(t.t3_s) AS t3_s,
        count(*) AS n_ev,
        count_if(e.venue = 1) AS n_amm,
        max_by(e.venue, e.rn) AS v_end,
        max_by(e.x, e.rn) AS x_end,
        max_by(e.y, e.rn) AS y_end,
        max_by(e.xr, e.rn) FILTER (WHERE e.venue = 0) AS xr_end,
        max_by(e.fee_bps, e.rn) FILTER (WHERE e.venue = 0) AS fee_end,
        sum(e.fee_all) FILTER (WHERE e.venue = 1) / sum(e.sol_gross) FILTER (WHERE e.venue = 1) AS amm_fee_rate,
        sum(IF(e.venue = 0 AND e.is_buy, e.sol_gross, 0)) AS curve_in,
        sum(IF(e.venue = 0 AND NOT e.is_buy, e.sol_gross, 0)) AS curve_out
    FROM ev2 e
    LEFT JOIN t3 t ON t.mint = e.mint
    GROUP BY 1
),
w AS (
    SELECT
        e.mint, e.usr,
        count_if(e.is_buy) AS n_buy,
        count_if(NOT e.is_buy) AS n_sell,
        sum(IF(e.is_buy, e.sol_user, 0)) AS in_sol,
        sum(IF(e.is_buy, 0, e.sol_user)) AS out_sol,
        sum(IF(e.is_buy, e.tok, 0)) AS tok_b,
        sum(IF(e.is_buy, 0, e.tok)) AS tok_s,
        min(IF(e.is_buy, e.dt)) AS fb_dt,
        min(IF(NOT e.is_buy, e.dt)) AS fs_dt,
        bool_or(e.is_buy AND e.slot = c.created_slot) AS same_slot,
        sum(IF(e.is_buy AND c.t3_s <= 300 AND e.dt < c.t3_s + 5, e.sol_user, 0)) AS in_pre_t35,
        sum(IF(e.is_buy AND c.t3_s <= 300, e.sol_user, 0)) AS in_t3coin
    FROM ev2 e
    JOIN coin c ON c.mint = e.mint
    WHERE e.usr IS NOT NULL
    GROUP BY 1, 2
),
wl AS (
    SELECT
        w.*,
        CASE
            WHEN w.tok_b - w.tok_s <= 0 OR c.y_end IS NULL OR c.y_end <= 0 THEN 0.0
            WHEN c.v_end = 0 THEN least(
                c.x_end * (w.tok_b - w.tok_s) / (c.y_end + w.tok_b - w.tok_s), COALESCE(c.xr_end, 0)
            ) * (1 - COALESCE(c.fee_end, 0) / 1e4)
            ELSE c.x_end * (w.tok_b - w.tok_s) / (c.y_end + w.tok_b - w.tok_s)
                 * (1 - COALESCE(c.amm_fee_rate, 0.0125))
        END AS liq_sol
    FROM w
    JOIN coin c ON c.mint = w.mint
),
bs AS (
    SELECT usr, approx_percentile(sol_user, 0.5) AS med_buy
    FROM ev2
    WHERE is_buy AND usr IS NOT NULL
    GROUP BY 1
),
ws AS (
    SELECT
        wl.usr,
        count_if(wl.n_buy > 0) AS n_coins,
        sum(wl.n_buy) AS n_buy,
        sum(wl.n_sell) AS n_sell,
        sum(wl.in_sol) AS in_sol,
        sum(wl.out_sol) AS out_sol,
        sum(wl.liq_sol) AS liq_sol,
        sum(wl.out_sol + wl.liq_sol - wl.in_sol) AS pnl0,
        sum(wl.in_pre_t35) AS in_pre_t35,
        sum(wl.in_t3coin) AS in_t3coin,
        count_if(wl.same_slot) AS n_same_slot,
        count_if(wl.n_buy = 0 AND wl.n_sell > 0) AS n_sellonly,
        approx_percentile(IF(wl.fs_dt >= wl.fb_dt, wl.fs_dt - wl.fb_dt), 0.5) AS hold_med
    FROM wl
    GROUP BY 1
    HAVING count_if(wl.n_buy > 0) >= 5 AND sum(wl.in_sol) >= 2
),
wr AS (
    SELECT ws.*, b.med_buy, row_number() OVER (ORDER BY ws.pnl0 DESC, ws.usr) AS rk
    FROM ws
    LEFT JOIN bs b ON b.usr = ws.usr
),
d AS (
    SELECT wl.*, wr.rk
    FROM wl
    JOIN wr ON wr.usr = wl.usr
    WHERE wr.rk <= 1000
)
SELECT
    'S' AS kind, CAST(NULL AS varchar) AS usr, CAST(NULL AS varchar) AS mint, CAST(NULL AS bigint) AS rk,
    (SELECT count(*) FROM sol_cohort) AS n_coins, (SELECT count(*) FROM coin) AS n_buy,
    (SELECT count_if(t3_s <= 300) FROM coin) AS n_sell,
    CAST((SELECT count(*) FROM ws) AS DOUBLE) AS in_sol, CAST((SELECT count(*) FROM w) AS DOUBLE) AS out_sol,
    CAST((SELECT sum(n_amm) FROM coin) AS DOUBLE) AS liq_sol, CAST((SELECT sum(n_ev) FROM coin) AS DOUBLE) AS pnl0,
    CAST(NULL AS DOUBLE) AS tok_b, CAST(NULL AS DOUBLE) AS tok_s, CAST(NULL AS bigint) AS fb_dt, CAST(NULL AS bigint) AS fs_dt,
    CAST(NULL AS boolean) AS same_slot, CAST(NULL AS DOUBLE) AS in_pre_t35, CAST(NULL AS DOUBLE) AS in_t3coin,
    CAST(NULL AS bigint) AS n_same_slot, CAST(NULL AS bigint) AS n_sellonly, CAST(NULL AS DOUBLE) AS hold_med, CAST(NULL AS DOUBLE) AS med_buy,
    CAST(NULL AS timestamp) AS created_at, CAST(NULL AS bigint) AS created_slot, CAST(NULL AS varchar) AS dev, CAST(NULL AS bigint) AS t3_s,
    CAST(NULL AS bigint) AS n_ev, CAST(NULL AS bigint) AS n_amm, CAST(NULL AS integer) AS v_end,
    CAST(NULL AS DOUBLE) AS x_end, CAST(NULL AS DOUBLE) AS y_end, CAST(NULL AS DOUBLE) AS xr_end,
    CAST(NULL AS DOUBLE) AS fee_end, CAST(NULL AS DOUBLE) AS amm_fee_rate, CAST(NULL AS DOUBLE) AS curve_in, CAST(NULL AS DOUBLE) AS curve_out
UNION ALL
SELECT
    'W', usr, NULL, rk, n_coins, n_buy, n_sell, in_sol, out_sol, liq_sol, pnl0,
    NULL, NULL, NULL, NULL, NULL, in_pre_t35, in_t3coin, n_same_slot, n_sellonly, hold_med, med_buy,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM wr
UNION ALL
SELECT
    'D', usr, mint, rk, NULL, n_buy, n_sell, in_sol, out_sol, liq_sol, out_sol + liq_sol - in_sol,
    tok_b, tok_s, fb_dt, fs_dt, same_slot, in_pre_t35, in_t3coin, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM d
UNION ALL
SELECT
    'C', NULL, mint, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    created_at, created_slot, dev, t3_s, n_ev, n_amm, v_end, x_end, y_end, xr_end, fee_end, amm_fee_rate, curve_in, curve_out
FROM coin

