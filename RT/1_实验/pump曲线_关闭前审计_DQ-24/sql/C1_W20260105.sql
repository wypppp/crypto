-- DQ-24（C1）周 2026-01-05：pump +30 分钟做多关闭前审计。依据 卡片_v1.md。
-- cohort 创建日 2026-01-05 ~ 2026-01-11；行情扫描至 2026-02-11（入场后 30 天封顶）；创建者历史回看自 2025-12-05（滚动 30 天，严格在前）。
-- 池状态与成交链（comp … states）原样取自 DQ-7 冻结的 F2_dev.sql（sha256 9313de98…），只换日期；
-- 曲线成交缺费率字段时按 100 bps 补（flags 2048 标出入场时缺失）。
-- 卖出两种口径：B＝旧式（我方仓位留在曲线里，偏乐观，sm）；A＝卖进不含我方仓位的状态（偏保守，sma）。池上两者相同。
-- 退出：b50（50% 回撤＋24 小时沉寂）；x50_1h（50% 回撤＋1 小时沉寂，DQ-1F 主候选的退出）；
-- rb50（主退出）：b50 因价格触发出场后，若价格收复出场前高点 H＝max(1, 入场后最高)，按收复时状态（5 秒内有下一笔则按下一笔后）
--   用第一段全部所得买回，再按 b50（相对买回后最高）出场；只买回一次；30 天封顶按最后状态估值。
-- 只输出活跃池（入场时曲线虚拟 SOL ≥30.5 或已在池上；非 SOL、无法入场、虚拟 SOL >120 不输出），另加一行 __SUMMARY__。
WITH
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        date_diff('day', DATE '2026-01-05', min(evt_block_date)) + 1 AS cday,
        max(quote_mint) AS quote_mint,
        max("user") AS dev,
        COALESCE(bool_or(CAST(is_mayhem_mode AS varchar) IN ('true', '1')), false) AS mayhem_create
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-01-05' AND DATE '2026-01-11'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
cr AS (
    SELECT mint, max("user") AS dev, min(evt_block_time) AS t,
           min(evt_block_slot) AS slot, min_by(evt_tx_index, evt_block_slot) AS txi
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2025-12-05' AND DATE '2026-01-11'
    GROUP BY 1
),
dev_hist AS (
    -- 修正 §5.1 缺陷：严格在前、滚动 30 天的发币数＝同一创建者按 (slot, txi) 排在前面的发币数 − 其中早于 30 天的
    SELECT mint, (rn_dev - 1) - n_old AS dev_prior_launches
    FROM (
        SELECT
            mint,
            row_number() OVER (PARTITION BY dev ORDER BY slot, txi, mint) AS rn_dev,
            count(*) OVER (PARTITION BY dev ORDER BY to_unixtime(t) RANGE BETWEEN UNBOUNDED PRECEDING AND 2592000 PRECEDING) AS n_old
        FROM cr
    ) z
    WHERE mint IN (SELECT mint FROM sol_cohort)
),
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '2026-01-05' AND DATE '2026-02-11'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
mig AS (
    SELECT mint, arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-01-05' AND DATE '2026-02-11'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
cp AS (
    SELECT
        pool,
        max(base_mint) AS base_mint,
        max(base_mint_decimals) AS bd,
        max(quote_mint_decimals) AS qd,
        COALESCE(bool_or(evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0), false) AS by_pump
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-01-05' AND DATE '2026-02-11'
      AND base_mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
fb AS (
    SELECT base_mint AS mint, min(pool) AS pool FROM cp WHERE by_pump GROUP BY 1
),
mapping AS (
    SELECT
        s.mint,
        COALESCE(m.pool, f.pool) AS pool,
        c.bd,
        c.qd
    FROM sol_cohort s
    LEFT JOIN mig m ON m.mint = s.mint
    LEFT JOIN fb f ON f.mint = s.mint
    LEFT JOIN cp c ON c.pool = COALESCE(m.pool, f.pool)
),
-- ===== 重扫描链：以下每一层只被下一层引用一次 =====
states AS (
    SELECT
        t.mint,
        t.evt_block_time AS ts,
        0 AS venue,
        t.evt_block_slot AS slot,
        t.evt_tx_index AS txi,
        t.evt_inner_instruction_index AS iix,
        CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
        CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
        CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr,
        COALESCE(CAST(t.fee_basis_points AS DOUBLE) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0), 100) AS fee_bps,
        t.fee_basis_points IS NULL AS fee_missing,
        COALESCE(CAST(t.mayhem_mode AS varchar) IN ('true', '1'), false) AS mayhem,
        t."user" AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt,
        CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok_amt,
        t.evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AS outer_pump
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-01-05' AND DATE '2026-02-11'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mp.mint, p.ts, 1 AS venue, p.slot, p.txi, p.iix,
        p.qraw / power(10, mp.qd) AS x,
        p.braw / power(10, mp.bd) AS y,
        CAST(NULL AS DOUBLE) AS xr,
        p.fee_bps, p.fee_missing, false AS mayhem,
        p.usr, p.is_buy,
        p.sraw / power(10, mp.qd) AS sol_amt, p.traw / power(10, mp.bd) AS tok_amt, CAST(NULL AS boolean) AS outer_pump
    FROM (
        SELECT pool, ts, slot, txi, iix, fee_bps, fee_missing, usr, is_buy, sraw, traw,
               COALESCE(lead(qraw) OVER (PARTITION BY pool ORDER BY slot, txi, iix), qraw + dq) AS qraw,
               COALESCE(lead(braw) OVER (PARTITION BY pool ORDER BY slot, txi, iix), braw + db) AS braw
        FROM (
            SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix,
                   CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
                   CAST(pool_base_token_reserves AS DOUBLE) AS braw,
                   CAST(quote_amount_in AS DOUBLE) - COALESCE(CAST(protocol_fee AS DOUBLE), 0) - COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS dq,
                   -CAST(base_amount_out AS DOUBLE) AS db,
                   COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                     + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
                   lp_fee_basis_points IS NULL AS fee_missing,
                   "user" AS usr, true AS is_buy, CAST(quote_amount_in AS DOUBLE) AS sraw, CAST(base_amount_out AS DOUBLE) AS traw
            FROM pumpdotfun_solana.pump_amm_evt_buyevent
            WHERE evt_block_date BETWEEN DATE '2026-01-05' AND DATE '2026-02-11'
              AND pool IN (SELECT pool FROM mapping WHERE pool IS NOT NULL)
            UNION ALL
            SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix,
                   CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
                   CAST(pool_base_token_reserves AS DOUBLE) AS braw,
                   -(CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)) AS dq,
                   CAST(base_amount_in AS DOUBLE) AS db,
                   COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                     + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
                   lp_fee_basis_points IS NULL AS fee_missing,
                   "user" AS usr, false AS is_buy, CAST(quote_amount_out AS DOUBLE) AS sraw, CAST(base_amount_in AS DOUBLE) AS traw
            FROM pumpdotfun_solana.pump_amm_evt_sellevent
            WHERE evt_block_date BETWEEN DATE '2026-01-05' AND DATE '2026-02-11'
              AND pool IN (SELECT pool FROM mapping WHERE pool IS NOT NULL)
        ) e
    ) p
    JOIN mapping mp ON mp.pool = p.pool
),
s1 AS (
    SELECT
        s.*,
        c.created_at + INTERVAL '30' MINUTE AS t_entry,
        LEAST(c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY, TIMESTAMP '2026-02-11 23:59:59 UTC') AS t_end,
        date_diff('second', c.created_at + INTERVAL '30' MINUTE, s.ts) AS dt,
        row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.iix) AS rn
    FROM states s
    JOIN sol_cohort c ON c.mint = s.mint
    WHERE s.ts <= c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY
      AND s.x > 0 AND s.y > 0
),
s2 AS (
    SELECT *, max(CASE WHEN dt <= 0 THEN rn END) OVER (PARTITION BY mint) AS entry_rn
    FROM s1
),
s3 AS (
    SELECT
        *,
        rn > entry_rn AS p,
        max(CASE WHEN rn = entry_rn THEN x END) OVER (PARTITION BY mint) AS ex,
        max(CASE WHEN rn = entry_rn THEN y END) OVER (PARTITION BY mint) AS ey,
        max(CASE WHEN rn = entry_rn THEN fee_bps END) OVER (PARTITION BY mint) AS efee,
        COALESCE(bool_or(CASE WHEN rn = entry_rn THEN fee_missing END) OVER (PARTITION BY mint), false) AS efee_missing,
        max(CASE WHEN rn = entry_rn THEN venue END) OVER (PARTITION BY mint) AS evenue
    FROM s2
),
s4 AS (
    SELECT *, ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4)) AS tok, (x / y) / (ex / ey) AS pm
    FROM s3
),
s5 AS (
    SELECT
        *,
        LEAST(
            CASE WHEN venue = 0 AND y > tok THEN (x * y / (y - tok) - x) * (1 - fee_bps / 1e4)
                 WHEN venue = 0 THEN NULL
                 ELSE (x - x * y / (y + tok)) * (1 - fee_bps / 1e4) END,
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - efee / 1e4)), 1e18)) / 0.5 AS sm,
        LEAST(
            (x - x * y / (y + tok)) * (1 - fee_bps / 1e4),
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - efee / 1e4)), 1e18)) / 0.5 AS sma
    FROM s4
),
s6 AS (
    SELECT
        *,
        max(CASE WHEN rn >= entry_rn THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_post,
        lead(sm) OVER (PARTITION BY mint ORDER BY rn) AS lead_sm, lead(sma) OVER (PARTITION BY mint ORDER BY rn) AS lead_sma, lead(ts) OVER (PARTITION BY mint ORDER BY rn) AS lead_ts
    FROM s5
),
s7 AS (
    SELECT *, min(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400) THEN rn END) OVER (PARTITION BY mint) AS ex1_rn
    FROM s6
),
s8 AS (
    SELECT
        *,
        COALESCE(bool_or(CASE WHEN rn = ex1_rn THEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) END) OVER (PARTITION BY mint), false) AS ex1_price,
        max(CASE WHEN rn = ex1_rn THEN greatest(1.0, runmax_post) END) OVER (PARTITION BY mint) AS hh,
        max(CASE WHEN rn = ex1_rn THEN (CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm ELSE sm END) END) OVER (PARTITION BY mint) AS v1b,
        max(CASE WHEN rn = ex1_rn THEN (CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sma ELSE sma END) END) OVER (PARTITION BY mint) AS v1a
    FROM s7
),
s9 AS (
    SELECT *, min(CASE WHEN ex1_price AND rn > ex1_rn AND pm >= hh THEN rn END) OVER (PARTITION BY mint) AS r2
    FROM s8
),
s10 AS (
    SELECT *, r2 + IF(COALESCE(bool_or(CASE WHEN rn = r2 THEN (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) END) OVER (PARTITION BY mint), false), 1, 0) AS r2b
    FROM s9
),
s11 AS (
    SELECT
        *,
        max(CASE WHEN rn = r2b THEN x END) OVER (PARTITION BY mint) AS xb,
        max(CASE WHEN rn = r2b THEN y END) OVER (PARTITION BY mint) AS yb,
        max(CASE WHEN rn = r2b THEN fee_bps END) OVER (PARTITION BY mint) AS feeb,
        max(CASE WHEN rn = r2b THEN pm END) OVER (PARTITION BY mint) AS pmb,
        max(CASE WHEN rn = r2b THEN dt END) OVER (PARTITION BY mint) AS dtb,
        max(CASE WHEN rn >= r2b THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS m2
    FROM s10
),
s12 AS (
    SELECT
        *,
        yb - xb * yb / (xb + 0.5 * v1b * (1 - feeb / 1e4)) AS tok2b,
        yb - xb * yb / (xb + 0.5 * v1a * (1 - feeb / 1e4)) AS tok2a
    FROM s11
),
s13 AS (
    SELECT
        *,
        LEAST(
            CASE WHEN venue = 0 AND y > tok2b THEN (x * y / (y - tok2b) - x) * (1 - fee_bps / 1e4)
                 WHEN venue = 0 THEN NULL
                 ELSE (x - x * y / (y + tok2b)) * (1 - fee_bps / 1e4) END,
            COALESCE(IF(venue = 0, xr + 0.5 * v1b * (1 - feeb / 1e4)), 1e18)) / 0.5 AS sm2,
        LEAST(
            (x - x * y / (y + tok2a)) * (1 - fee_bps / 1e4),
            COALESCE(IF(venue = 0, xr + 0.5 * v1a * (1 - feeb / 1e4)), 1e18)) / 0.5 AS sm2a
    FROM s12
),
s14 AS (
    SELECT
        *,
        lead(sm2) OVER (PARTITION BY mint ORDER BY rn) AS lead_sm2,
        lead(sm2a) OVER (PARTITION BY mint ORDER BY rn) AS lead_sm2a
    FROM s13
),
agg AS (
    SELECT
        mint,
        max(entry_rn) AS entry_rn,
        max(ex) AS ex,
        max(efee) AS efee,
        bool_or(efee_missing) AS efee_missing,
        max(evenue) AS evenue,
        bool_or(venue = 0 AND x > 120) AS anomaly,
        bool_or(mayhem) AS mayhem_trade,
        max(pm) FILTER (WHERE p) AS ms_30d,
        max_by(sm, rn) FILTER (WHERE p) AS sm_last,
        max_by(sma, rn) FILTER (WHERE p) AS sma_last,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm ELSE sm END, rn) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS b50_b,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sma ELSE sma END, rn) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS b50_a,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm ELSE sm END, rn) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600)) AS x50_1h_b,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sma ELSE sma END, rn) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600)) AS x50_1h_a,
        max(r2b) AS r2b,
        bool_or(ex1_price) AS ex1_price,
        max(hh) AS hh,
        max(dtb) AS rebuy_dt,
        min_by(CASE WHEN (r2b IS NOT NULL AND rn > r2b AND pm <= 0.50 * greatest(pmb, m2)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm2 ELSE sm2 END, rn) FILTER (WHERE (r2b IS NOT NULL AND rn > r2b AND pm <= 0.50 * greatest(pmb, m2)) OR (r2b IS NOT NULL AND rn >= r2b AND date_diff('second', ts, COALESCE(lead_ts, t_end)) > 86400)) AS rb2_b,
        min_by(CASE WHEN (r2b IS NOT NULL AND rn > r2b AND pm <= 0.50 * greatest(pmb, m2)) AND (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm2a ELSE sm2a END, rn) FILTER (WHERE (r2b IS NOT NULL AND rn > r2b AND pm <= 0.50 * greatest(pmb, m2)) OR (r2b IS NOT NULL AND rn >= r2b AND date_diff('second', ts, COALESCE(lead_ts, t_end)) > 86400)) AS rb2_a,
        max_by(sm2, rn) FILTER (WHERE rn >= r2b) AS sm2_last,
        max_by(sm2a, rn) FILTER (WHERE rn >= r2b) AS sm2a_last,
        count(*) AS n_rows
    FROM s14
    GROUP BY 1
),
final AS (
    SELECT
        c.mint,
        c.cday,
        (CASE WHEN co.mint IS NOT NULL THEN 4 ELSE 0 END)
          + (CASE WHEN c.mayhem_create OR a.mayhem_trade THEN 128 ELSE 0 END)
          + (CASE WHEN a.evenue = 1 THEN 1024 ELSE 0 END)
          + (CASE WHEN a.efee_missing THEN 2048 ELSE 0 END) AS flags,
        round(a.ex, 3) AS entry_x_sol,
        COALESCE(h.dev_prior_launches, 0) AS dev_prior_launches,
        round(COALESCE(a.ms_30d, 1.0), 6) AS ms_30d,
        round(COALESCE(a.b50_b, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS b50_b,
        round(COALESCE(a.b50_a, a.sma_last, power(1 - a.efee / 1e4, 2)), 6) AS b50_a,
        round(COALESCE(a.x50_1h_b, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x50_1h_b,
        round(COALESCE(a.x50_1h_a, a.sma_last, power(1 - a.efee / 1e4, 2)), 6) AS x50_1h_a,
        round(CASE WHEN a.r2b IS NULL THEN COALESCE(a.b50_b, a.sm_last, power(1 - a.efee / 1e4, 2))
                   ELSE COALESCE(a.rb2_b, a.sm2_last) END, 6) AS rb50_b,
        round(CASE WHEN a.r2b IS NULL THEN COALESCE(a.b50_a, a.sma_last, power(1 - a.efee / 1e4, 2))
                   ELSE COALESCE(a.rb2_a, a.sm2a_last) END, 6) AS rb50_a,
        CASE WHEN a.r2b IS NOT NULL THEN 2 WHEN a.ex1_price THEN 1 ELSE 0 END AS rb_state,
        a.rebuy_dt,
        round(a.hh, 4) AS hh,
        a.n_rows
    FROM cohort c
    JOIN sol_cohort s ON s.mint = c.mint
    JOIN agg a ON a.mint = c.mint
    LEFT JOIN comp co ON co.mint = c.mint
    LEFT JOIN dev_hist h ON h.mint = c.mint
    WHERE a.entry_rn IS NOT NULL
      AND NOT COALESCE(a.anomaly, false)
      AND (a.ex >= 30.5 OR a.evenue = 1)
)
SELECT * FROM final
UNION ALL
SELECT
    '__SUMMARY__' AS mint,
    (SELECT count(*) FROM sol_cohort) AS cday,
    (SELECT count(*) FROM cohort) - (SELECT count(*) FROM sol_cohort) AS flags,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
ORDER BY cday, mint
