/* DQ-28 同槽买家拆分 A 格与现金（卡片_v1.md）；由 sql/build_ss_sql.py 生成。
   币：2026-08-04～2026-08-05 创建的 SOL 计价 pump 币；格＝创建 slot 内有买入的非创建者钱包。成交（曲线＋PumpSwap）截至 2026-08-12 24:00 UTC；只读 2026-08-04～2026-08-12 的分区。 */
WITH
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        max(CAST("user" AS varchar)) AS dev,
        max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-05'
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
    WHERE evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
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
    WHERE evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
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
    WHERE a.evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
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
    WHERE a.evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
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
        CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr,
        (COALESCE(CAST(t.fee AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee AS DOUBLE), 0) + COALESCE(CAST(t.buyback_fee AS DOUBLE), 0)) / 1e9 AS fee_evt,
        COALESCE(CAST(t.cashback AS DOUBLE), 0) / 1e9 AS cashback,
        t.evt_tx_id AS tx_id
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-12'
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
        CAST(NULL AS DOUBLE),
        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE), CAST(NULL AS varchar)
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
      AND e.ts < DATE '2026-08-12' + INTERVAL '1' DAY
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
ctx AS (
    SELECT mint, min_by(evt_tx_id, evt_block_slot) AS create_tx
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-08-04' AND DATE '2026-08-05'
    GROUP BY 1
)
SELECT
    q.mint, q.usr, max(q.dev) AS dev, max(q.created_at) AS created_at, max(q.t3_s) AS t3_s,
    bool_or(q.is_buy AND q.slot = q.created_slot AND q.tx_id = c.create_tx) AS same_tx,
    sum(IF(q.is_buy AND q.slot = q.created_slot, q.sol_gross, 0)) AS ss_buy_sol,
    sum(IF(q.is_buy, IF(q.venue = 0, q.sol_gross + q.fee_evt, q.sol_user), 0)) AS pay,
    sum(IF(q.is_buy, 0, IF(q.venue = 0, q.sol_gross - q.fee_evt, q.sol_user))) AS recv,
    sum(IF(q.is_buy, q.sol_user, 0)) AS pay_rate,
    sum(IF(q.is_buy, 0, q.sol_user)) AS recv_rate,
    sum(IF(q.is_buy, q.tok, 0)) AS tok_b,
    sum(IF(q.is_buy, 0, q.tok)) AS tok_s,
    count_if(q.is_buy) AS n_buy, count_if(NOT q.is_buy) AS n_sell,
    count_if(q.venue = 1) AS n_amm,
    min(IF(NOT q.is_buy, q.dt)) AS first_sell_dt,
    CASE
            WHEN sum(IF(is_buy, tok, 0)) - sum(IF(is_buy, 0, tok)) <= 0 OR max(y_end) IS NULL OR max(y_end) <= 0 THEN 0.0
            WHEN max(v_end) = 0 THEN least(
                max(x_end) * (sum(IF(is_buy, tok, 0)) - sum(IF(is_buy, 0, tok))) / (max(y_end) + sum(IF(is_buy, tok, 0)) - sum(IF(is_buy, 0, tok))), COALESCE(max(xr_end), 0)
            ) * (1 - COALESCE(max(fee_end), 0) / 1e4)
            ELSE max(x_end) * (sum(IF(is_buy, tok, 0)) - sum(IF(is_buy, 0, tok))) / (max(y_end) + sum(IF(is_buy, tok, 0)) - sum(IF(is_buy, 0, tok))) * (1 - COALESCE(max(amm_fee_rate), 0.0125))
        END AS liq_sol
FROM q3 q
LEFT JOIN ctx c ON c.mint = q.mint
WHERE q.usr IS NOT NULL AND q.usr <> q.dev
GROUP BY 1, 2
HAVING bool_or(q.is_buy AND q.slot = q.created_slot)
