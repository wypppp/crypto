/* DQ-26 Q2 外部跟随（卡片_Q2_执行_v1.md）；由 sql/build_q2_sql.py 生成（REG_20260601）。
   币：2026-06-01～2026-06-01 创建的 SOL 计价 pump 币；成交（曲线＋PumpSwap）截至 2026-06-03 24:00 UTC；只读 2026-06-01～2026-06-03 的分区。
   触发＝每币 t3 事件，卖出信号＝t3+30 秒（回归，对照 S1）；延迟 2/5/15/30 秒；跟随退出与 5 秒 b50；估值同 S1 s9/s10（口径 A/B）。 */
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
        *,
        min(CASE WHEN is_buy AND sol_gross >= 0.1 AND usr IS NOT NULL AND usr <> dev THEN rn END)
          OVER (PARTITION BY mint, usr) AS first_q_rn
    FROM ev2
),
q2 AS (
    SELECT
        *,
        rn = first_q_rn AS q_new,
        sum(IF(rn = first_q_rn, 1, 0)) OVER (
            PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS q_count,
        max_by(venue, rn) OVER (PARTITION BY mint) AS v_end,
        max_by(x, rn) OVER (PARTITION BY mint) AS x_end,
        max_by(y, rn) OVER (PARTITION BY mint) AS y_end,
        max_by(IF(venue = 0, xr), IF(venue = 0, rn)) OVER (PARTITION BY mint) AS xr_end,
        max_by(IF(venue = 0, fee_bps), IF(venue = 0, rn)) OVER (PARTITION BY mint) AS fee_end,
        sum(IF(venue = 1, fee_all)) OVER (PARTITION BY mint)
          / sum(IF(venue = 1, sol_gross)) OVER (PARTITION BY mint) AS amm_fee_rate
    FROM q1
),
q3 AS (
    SELECT
        *,
        max(IF(q_new AND q_count = 3, dt)) OVER (PARTITION BY mint) AS t3_s
    FROM q2
),
trig AS (
    SELECT
        mint, 't3' AS entity,
        rn AS b_rn, dt AS b_dt, slot = created_slot AS b_same_slot, venue AS b_venue,
        sol_user AS b_sol, dt + 30 AS s_dt, t3_s, created_at,
        1 AS ent_n_buy, 0 AS ent_n_sell, sol_user AS ent_buy_sol
    FROM q3
    WHERE q_new AND q_count = 3
),
path AS (
    SELECT
        t.mint, t.entity, t.b_rn, t.b_dt, t.s_dt,
        t.created_at, t.t3_s, t.b_same_slot, t.b_venue, t.b_sol,
        t.ent_n_buy, t.ent_n_sell, t.ent_buy_sol,
        q.rn, q.dt, q.venue, q.x, q.y, q.xr,
        CASE WHEN q.venue = 0 THEN q.fee_bps
             WHEN q.fee_all > 0 AND q.sol_gross > 0 THEN q.fee_all / q.sol_gross * 1e4
             ELSE 125 END AS fee_bps,
        q.x / q.y AS price
    FROM trig t
    JOIN q3 q ON q.mint = t.mint AND q.rn >= t.b_rn AND q.dt <= t.b_dt + 604800
    WHERE q.x > 0 AND q.y > 0
),
p1 AS (
    SELECT
        *,
        max(IF(dt <= b_dt + 2, rn)) OVER (PARTITION BY mint, entity) AS e2,
        max(IF(dt <= LEAST(COALESCE(s_dt + 2, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x2,
        max(IF(dt <= b_dt + 5, rn)) OVER (PARTITION BY mint, entity) AS e5,
        max(IF(dt <= LEAST(COALESCE(s_dt + 5, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x5,
        max(IF(dt <= b_dt + 15, rn)) OVER (PARTITION BY mint, entity) AS e15,
        max(IF(dt <= LEAST(COALESCE(s_dt + 15, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x15,
        max(IF(dt <= b_dt + 30, rn)) OVER (PARTITION BY mint, entity) AS e30,
        max(IF(dt <= LEAST(COALESCE(s_dt + 30, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x30
    FROM path
),
p2 AS (
    SELECT
        *,
        max(IF(rn = e2, x)) OVER (PARTITION BY mint, entity) AS ex2, max(IF(rn = e2, y)) OVER (PARTITION BY mint, entity) AS ey2, max(IF(rn = e2, fee_bps)) OVER (PARTITION BY mint, entity) AS ef2, max(IF(rn = e2, dt)) OVER (PARTITION BY mint, entity) AS edt2,
        max(IF(rn = e5, x)) OVER (PARTITION BY mint, entity) AS ex5, max(IF(rn = e5, y)) OVER (PARTITION BY mint, entity) AS ey5, max(IF(rn = e5, fee_bps)) OVER (PARTITION BY mint, entity) AS ef5, max(IF(rn = e5, dt)) OVER (PARTITION BY mint, entity) AS edt5,
        max(IF(rn = e15, x)) OVER (PARTITION BY mint, entity) AS ex15, max(IF(rn = e15, y)) OVER (PARTITION BY mint, entity) AS ey15, max(IF(rn = e15, fee_bps)) OVER (PARTITION BY mint, entity) AS ef15, max(IF(rn = e15, dt)) OVER (PARTITION BY mint, entity) AS edt15,
        max(IF(rn = e30, x)) OVER (PARTITION BY mint, entity) AS ex30, max(IF(rn = e30, y)) OVER (PARTITION BY mint, entity) AS ey30, max(IF(rn = e30, fee_bps)) OVER (PARTITION BY mint, entity) AS ef30, max(IF(rn = e30, dt)) OVER (PARTITION BY mint, entity) AS edt30,
        max(IF(rn = e5, venue)) OVER (PARTITION BY mint, entity) AS evenue_b,
        max(IF(rn = e5, x / y)) OVER (PARTITION BY mint, entity) AS eprice_b
    FROM p1
),
p3 AS (
    SELECT
        *,
        ey2 - ex2 * ey2 / (ex2 + 0.5 * (1 - ef2 / 1e4)) AS tok2,
        ey5 - ex5 * ey5 / (ex5 + 0.5 * (1 - ef5 / 1e4)) AS tok5,
        ey15 - ex15 * ey15 / (ex15 + 0.5 * (1 - ef15 / 1e4)) AS tok15,
        ey30 - ex30 * ey30 / (ex30 + 0.5 * (1 - ef30 / 1e4)) AS tok30,
        price / NULLIF(eprice_b, 0) AS pm_b
    FROM p2
),
p4 AS (
    SELECT
        *,
        LEAST(
            CASE WHEN venue = 0 THEN (x * tok5 / (y + tok5)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok5)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef5 / 1e4), 1e18)) AS m_ab,
        LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok5 THEN (x * y / (y - tok5) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok5)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef5 / 1e4), 1e18)) AS m_bb,
        max(IF(rn >= e5, pm_b)) OVER (
            PARTITION BY mint, entity ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS runmax_b
    FROM p3
),
res AS (
    SELECT
        mint, entity,
    max(created_at) AS created_at, max(t3_s) AS t3_s, max(b_dt) AS b_dt, max(s_dt) AS s_dt,
    bool_or(b_same_slot) AS b_same_slot, max(b_venue) AS b_venue, max(b_sol) AS b_sol,
    max(ent_n_buy) AS ent_n_buy, max(ent_n_sell) AS ent_n_sell, max(ent_buy_sol) AS ent_buy_sol,
    max(IF(rn = x2, LEAST(
            CASE WHEN venue = 0 THEN (x * tok2 / (y + tok2)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok2)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef2 / 1e4), 1e18)))) AS sell_a_d2,
    max(IF(rn = x2, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok2 THEN (x * y / (y - tok2) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok2)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef2 / 1e4), 1e18)))) AS sell_b_d2,
    max(edt2) AS edt2, max(IF(rn = x2, dt)) AS xdt2,
    max(IF(rn = x2, venue)) AS xvenue2,
    max(IF(rn = x5, LEAST(
            CASE WHEN venue = 0 THEN (x * tok5 / (y + tok5)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok5)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef5 / 1e4), 1e18)))) AS sell_a_d5,
    max(IF(rn = x5, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok5 THEN (x * y / (y - tok5) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok5)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef5 / 1e4), 1e18)))) AS sell_b_d5,
    max(edt5) AS edt5, max(IF(rn = x5, dt)) AS xdt5,
    max(IF(rn = x5, venue)) AS xvenue5,
    max(IF(rn = x15, LEAST(
            CASE WHEN venue = 0 THEN (x * tok15 / (y + tok15)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok15)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef15 / 1e4), 1e18)))) AS sell_a_d15,
    max(IF(rn = x15, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok15 THEN (x * y / (y - tok15) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok15)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef15 / 1e4), 1e18)))) AS sell_b_d15,
    max(edt15) AS edt15, max(IF(rn = x15, dt)) AS xdt15,
    max(IF(rn = x15, venue)) AS xvenue15,
    max(IF(rn = x30, LEAST(
            CASE WHEN venue = 0 THEN (x * tok30 / (y + tok30)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok30)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef30 / 1e4), 1e18)))) AS sell_a_d30,
    max(IF(rn = x30, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok30 THEN (x * y / (y - tok30) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok30)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef30 / 1e4), 1e18)))) AS sell_b_d30,
    max(edt30) AS edt30, max(IF(rn = x30, dt)) AS xdt30,
    max(IF(rn = x30, venue)) AS xvenue30,
    NULLIF(min_by(COALESCE(m_ab, -1.0), rn) FILTER (WHERE rn >= e5 AND pm_b <= 0.5 * greatest(1.0, runmax_b)), -1.0) AS b50_stop_a,
    NULLIF(min_by(COALESCE(m_bb, -1.0), rn) FILTER (WHERE rn >= e5 AND pm_b <= 0.5 * greatest(1.0, runmax_b)), -1.0) AS b50_stop_b,
    min(dt) FILTER (WHERE rn >= e5 AND pm_b <= 0.5 * greatest(1.0, runmax_b)) AS b50_stop_dt,
    NULLIF(max_by(COALESCE(m_ab, -1.0), rn), -1.0) AS hor_a,
    NULLIF(max_by(COALESCE(m_bb, -1.0), rn), -1.0) AS hor_b,
    5 AS b50_delay,
    max(dt) AS last_dt,
    max(evenue_b) AS e_venue_b,
    max(tok5) AS tok_b,
    count(*) AS n_path
    FROM p4
    GROUP BY 1, 2
)
SELECT *
FROM res
