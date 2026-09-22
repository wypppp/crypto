-- DQ-1F · F1（冒烟版）：活跃池逐 mint 的入场特征 + 8 条动态退出规则 + DQ-1M 标签。依据 DQ1F_卡.md。
-- 由 dq1f/sql/build_f1.py 从同一模板渲染；冒烟版、开发版、验证版只有日期与末尾输出不同。
-- cohort 创建日 2026-06-07 ~ 2026-06-07；行情扫描 2026-06-07 ~ 2026-06-09；创建者历史回看自 2026-05-08。
-- 冒烟：只核对语法、量级与成本。
-- 结构：Trino 不物化 CTE。重扫描（成交表 + 池事件）只沿 states → s1 → … → s7 → agg 单向引用一次；
-- 钱包层特征（持仓、创建者、首块买家）用 (mint, 钱包) 分区的窗口函数在同一条链内完成，不另开分支。
-- 口径沿用 DQ-1M M2（链上核验 F59）：曲线事件为交易后储备；池事件为交易前储备，取同池下一笔的交易前储备作为交易后状态；
-- 卖出按持仓计入曲线状态计算，上限为 real_sol_reserves 加我方买入净额；回购费不计入。
-- 活跃池：入场时仍在曲线上且虚拟 SOL ≥30.5，或入场时已毕业；非 SOL、无法入场、虚拟 SOL >120 的异常币不输出。
-- 退出规则（卡第四节）：回撤止损 s ∈ {30%,50%,70%,不设} × 沉寂离场 D ∈ {1h,24h}；回撤触发后若 5 秒内有下一笔，按下一笔之后状态卖出。
-- 正式版输出最后附一行 mint='__SUMMARY__'，含义见末尾注释。
WITH
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        date_diff('day', DATE '2026-06-07', min(evt_block_date)) + 1 AS cday,
        max(quote_mint) AS quote_mint,
        max("user") AS dev,
        COALESCE(bool_or(CAST(is_mayhem_mode AS varchar) IN ('true', '1')), false) AS mayhem_create
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-07'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
dev_hist AS (
    -- 创建者历史：发币与毕业放进同一条按时间排序的事件流做累计计数，避免"创建者 × 创建者"连接爆炸。
    SELECT mint, prior_launches AS dev_prior_launches, prior_grads AS dev_prior_grads
    FROM (
        SELECT
            mint, is_launch,
            COALESCE(sum(is_launch) OVER (PARTITION BY dev ORDER BY t, is_launch ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prior_launches,
            COALESCE(sum(is_grad) OVER (PARTITION BY dev ORDER BY t, is_launch ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prior_grads
        FROM (
            SELECT l.dev, l.mint, l.t, 1 AS is_launch, 0 AS is_grad
            FROM (
                SELECT mint, max("user") AS dev, min(evt_block_time) AS t
                FROM pumpdotfun_solana.pump_evt_createevent
                WHERE evt_block_date BETWEEN DATE '2026-05-08' AND DATE '2026-06-07'
                GROUP BY 1
            ) l
            UNION ALL
            SELECT l.dev, l.mint, g.t, 0 AS is_launch, 1 AS is_grad
            FROM (
                SELECT mint, max("user") AS dev
                FROM pumpdotfun_solana.pump_evt_createevent
                WHERE evt_block_date BETWEEN DATE '2026-05-08' AND DATE '2026-06-07'
                GROUP BY 1
            ) l
            JOIN (
                SELECT mint, min(evt_block_time) AS t
                FROM pumpdotfun_solana.pump_evt_completeevent
                WHERE evt_block_date BETWEEN DATE '2026-05-08' AND DATE '2026-06-07'
                GROUP BY 1
            ) g ON g.mint = l.mint
        ) ev
    ) cum
    WHERE is_launch = 1
      AND mint IN (SELECT mint FROM sol_cohort)
),
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
mig AS (
    SELECT mint, arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
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
        COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
        t.fee_basis_points IS NULL AS fee_missing,
        COALESCE(CAST(t.mayhem_mode AS varchar) IN ('true', '1'), false) AS mayhem,
        t."user" AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt,
        CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok_amt,
        t.evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AS outer_pump
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mp.mint, p.ts, 1 AS venue, p.slot, p.txi, p.iix,
        p.qraw / power(10, mp.qd) AS x,
        p.braw / power(10, mp.bd) AS y,
        CAST(NULL AS DOUBLE) AS xr,
        p.fee_bps, p.fee_missing, false AS mayhem,
        CAST(NULL AS varchar) AS usr, CAST(NULL AS boolean) AS is_buy,
        CAST(NULL AS DOUBLE) AS sol_amt, CAST(NULL AS DOUBLE) AS tok_amt, CAST(NULL AS boolean) AS outer_pump
    FROM (
        SELECT pool, ts, slot, txi, iix, fee_bps, fee_missing,
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
                   lp_fee_basis_points IS NULL AS fee_missing
            FROM pumpdotfun_solana.pump_amm_evt_buyevent
            WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
              AND pool IN (SELECT pool FROM mapping WHERE pool IS NOT NULL)
            UNION ALL
            SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix,
                   CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
                   CAST(pool_base_token_reserves AS DOUBLE) AS braw,
                   -(CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)) AS dq,
                   CAST(base_amount_in AS DOUBLE) AS db,
                   COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                     + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
                   lp_fee_basis_points IS NULL AS fee_missing
            FROM pumpdotfun_solana.pump_amm_evt_sellevent
            WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-09'
              AND pool IN (SELECT pool FROM mapping WHERE pool IS NOT NULL)
        ) e
    ) p
    JOIN mapping mp ON mp.pool = p.pool
),
s1 AS (
    SELECT
        s.*,
        c.created_slot,
        c.dev,
        c.created_at + INTERVAL '30' MINUTE AS t_entry,
        LEAST(c.created_at + INTERVAL '30' MINUTE + INTERVAL '60' DAY, TIMESTAMP '2026-06-09 23:59:59 UTC') AS t_end,
        date_diff('second', c.created_at + INTERVAL '30' MINUTE, s.ts) AS dt,
        row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.iix) AS rn
    FROM states s
    JOIN sol_cohort c ON c.mint = s.mint
    WHERE s.ts <= c.created_at + INTERVAL '30' MINUTE + INTERVAL '60' DAY
      AND s.x > 0 AND s.y > 0
),
s2 AS (
    SELECT
        *,
        CAST(floor(dt / 86400.0) AS integer) AS d,
        max(CASE WHEN dt <= 0 THEN rn END) OVER (PARTITION BY mint) AS entry_rn
    FROM s1
),
s3 AS (
    SELECT
        *,
        rn <= entry_rn AS pre,
        rn > entry_rn AS p,
        max(CASE WHEN rn = entry_rn THEN x END) OVER (PARTITION BY mint) AS ex,
        max(CASE WHEN rn = entry_rn THEN y END) OVER (PARTITION BY mint) AS ey,
        max(CASE WHEN rn = entry_rn THEN fee_bps END) OVER (PARTITION BY mint) AS efee,
        COALESCE(bool_or(CASE WHEN rn = entry_rn THEN fee_missing END) OVER (PARTITION BY mint), false) AS efee_missing,
        max(CASE WHEN rn = entry_rn THEN venue END) OVER (PARTITION BY mint) AS evenue,
        sum(CASE WHEN rn <= entry_rn AND usr IS NOT NULL THEN IF(is_buy, tok_amt, -tok_amt) END) OVER (PARTITION BY mint, usr) AS u_net_pre,
        min(CASE WHEN rn <= entry_rn AND is_buy THEN slot END) OVER (PARTITION BY mint, usr) AS u_first_buy_slot,
        row_number() OVER (PARTITION BY mint, usr ORDER BY rn) AS u_rn1
    FROM s2
),
s4 AS (
    SELECT
        *,
        ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4)) AS tok,
        (x / y) / (ex / ey) AS pm,
        usr IS NOT NULL AND u_rn1 = 1 AS u_first,
        rank() OVER (PARTITION BY mint ORDER BY CASE WHEN usr IS NOT NULL AND u_rn1 = 1 AND u_net_pre > 0 THEN u_net_pre END DESC NULLS LAST) AS u_rank
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
        p AND rn = max(CASE WHEN p THEN rn END) OVER (PARTITION BY mint, d) AS is_close
    FROM s4
),
s6 AS (
    SELECT
        *,
        max(CASE WHEN is_close THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_close,
        max(CASE WHEN rn >= entry_rn THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_post,
        lead(sm) OVER (PARTITION BY mint ORDER BY rn) AS lead_sm,
        lead(ts) OVER (PARTITION BY mint ORDER BY rn) AS lead_ts
    FROM s5
),
s7 AS (
    SELECT
        *,
        min(CASE WHEN is_close AND pm <= 0.5 * greatest(1.0, runmax_close) THEN d END) OVER (PARTITION BY mint) AS d_trig
    FROM s6
),
agg AS (
    SELECT
        mint,
        max(entry_rn) AS entry_rn,
        max(ex) AS ex,
        max(efee) AS efee,
        max(evenue) AS evenue,
        max(t_entry) AS t_entry,
        max(created_slot) AS created_slot,
        bool_or(venue = 0 AND x > 120) AS anomaly,
        bool_or(mayhem) AS mayhem_trade,
        -- DQ-1M 标签
        max(pm) FILTER (WHERE p) AS ms_60d,
        max_by(sm, rn) FILTER (WHERE p AND dt <= 7200) AS hv_2h,
        max_by(sm, rn) FILTER (WHERE p AND dt <= 86400) AS hv_24h,
        max_by(sm, rn) FILTER (WHERE p AND dt <= 604800) AS hv_7d,
        max_by(sm, rn) FILTER (WHERE p) AS sm_last,
        max(dt) FILTER (WHERE p) AS last_dt,
        max_by(dt, pm) FILTER (WHERE p) AS peak_dt,
        max(d_trig) AS d_trig,
        min_by(sm, rn) FILTER (WHERE p AND d > d_trig) AS sm_after,
        -- 入场特征（只用 pre 行）
        count_if(pre) AS n_trades_pre,
        count_if(u_first AND u_first_buy_slot IS NOT NULL) AS n_buyers_pre,
        CAST(count_if(pre AND venue = 0 AND NOT outer_pump) AS DOUBLE) / nullif(count_if(pre AND venue = 0), 0) AS bot_share_pre,
        sum(CASE WHEN pre AND venue = 0 THEN IF(is_buy, sol_amt, -sol_amt) END) AS net_sol_pre,
        CAST(count_if(pre AND venue = 0 AND NOT is_buy) AS DOUBLE) / nullif(count_if(pre AND venue = 0), 0) AS sell_share_pre,
        max(ts) FILTER (WHERE pre) AS last_pre_ts,
        max(pm) FILTER (WHERE pre) AS pre_peak_pm,
        sum(CASE WHEN u_first AND u_net_pre > 0 THEN u_net_pre END) AS pos_net_total,
        max(CASE WHEN u_first AND u_rank = 1 AND u_net_pre > 0 THEN u_net_pre END) AS top1_net,
        sum(CASE WHEN u_first AND u_rank <= 5 AND u_net_pre > 0 THEN u_net_pre END) AS top5_net,
        max(CASE WHEN u_first AND usr = dev THEN u_net_pre END) AS dev_net,
        sum(CASE WHEN pre AND venue = 0 AND usr = dev AND NOT is_buy THEN sol_amt END) AS dev_sold_sol,
        count_if(u_first AND usr <> dev AND u_first_buy_slot = created_slot) AS slot0_buyers,
        sum(CASE WHEN u_first AND usr <> dev AND u_first_buy_slot = created_slot AND u_net_pre > 0 THEN u_net_pre END) AS slot0_net,
        count_if(u_first AND usr <> dev AND u_first_buy_slot <= created_slot + 10) AS early10_buyers,
        -- 退出规则
        min_by(CASE WHEN (p AND pm <= 0.70 * greatest(1.0, runmax_post)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.70 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS x30_1h_v,
        min_by(CASE WHEN (p AND pm <= 0.70 * greatest(1.0, runmax_post)) THEN dt ELSE greatest(dt, 0) + 3600 END, rn) FILTER (WHERE ((p AND pm <= 0.70 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS x30_1h_t,
        min_by(CASE WHEN (p AND pm <= 0.70 * greatest(1.0, runmax_post)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.70 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS x30_24h_v,
        min_by(CASE WHEN (p AND pm <= 0.70 * greatest(1.0, runmax_post)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE ((p AND pm <= 0.70 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS x30_24h_t,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS x50_1h_v,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN dt ELSE greatest(dt, 0) + 3600 END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS x50_1h_t,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS x50_24h_v,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS x50_24h_t,
        min_by(CASE WHEN (p AND pm <= 0.30 * greatest(1.0, runmax_post)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS x70_1h_v,
        min_by(CASE WHEN (p AND pm <= 0.30 * greatest(1.0, runmax_post)) THEN dt ELSE greatest(dt, 0) + 3600 END, rn) FILTER (WHERE ((p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS x70_1h_t,
        min_by(CASE WHEN (p AND pm <= 0.30 * greatest(1.0, runmax_post)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS x70_24h_v,
        min_by(CASE WHEN (p AND pm <= 0.30 * greatest(1.0, runmax_post)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE ((p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS x70_24h_t,
        min_by(CASE WHEN false THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS xNA_1h_v,
        min_by(CASE WHEN false THEN dt ELSE greatest(dt, 0) + 3600 END, rn) FILTER (WHERE (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600))) AS xNA_1h_t,
        min_by(CASE WHEN false THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS xNA_24h_v,
        min_by(CASE WHEN false THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS xNA_24h_t,
        count(*) AS n_rows
    FROM s7
    GROUP BY 1
),
final AS (
    SELECT
        c.mint,
        c.cday,
        (CASE WHEN co.mint IS NOT NULL THEN 4 ELSE 0 END)
          + (CASE WHEN c.mayhem_create OR a.mayhem_trade THEN 128 ELSE 0 END)
          + (CASE WHEN a.evenue = 1 THEN 1024 ELSE 0 END) AS flags,
        round(a.ex, 3) AS entry_x_sol,
        round(COALESCE(a.ms_60d, 1.0), 6) AS ms_60d,
        round(COALESCE(a.hv_2h, power(1 - a.efee / 1e4, 2)), 6) AS hv_2h,
        round(COALESCE(a.hv_24h, power(1 - a.efee / 1e4, 2)), 6) AS hv_24h,
        round(COALESCE(a.hv_7d, power(1 - a.efee / 1e4, 2)), 6) AS hv_7d,
        round(COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS hv_60d,
        round(CASE WHEN a.d_trig IS NULL THEN COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2))
                   ELSE COALESCE(a.sm_after, a.sm_last) END, 6) AS mpi_t50,
        a.peak_dt,
        date_diff('second', a.t_entry, co.completed_at) AS grad_dt,
        a.n_trades_pre,
        a.n_buyers_pre,
        round(a.n_trades_pre / greatest(a.ex - 30, 0.5), 3) AS trades_per_sol,
        round(a.bot_share_pre, 4) AS bot_share_pre,
        round(a.net_sol_pre, 4) AS net_sol_pre,
        round(a.sell_share_pre, 4) AS sell_share_pre,
        date_diff('second', a.last_pre_ts, a.t_entry) AS secs_since_last,
        round(a.pre_peak_pm, 4) AS pre_peak_pm,
        COALESCE(h.dev_prior_launches, 0) AS dev_prior_launches,
        COALESCE(h.dev_prior_grads, 0) AS dev_prior_grads,
        round(COALESCE(a.dev_net, 0) / nullif(a.pos_net_total, 0), 4) AS dev_net_share,
        round(COALESCE(a.dev_sold_sol, 0), 4) AS dev_sold_sol,
        round(a.top1_net / nullif(a.pos_net_total, 0), 4) AS top1_share,
        round(a.top5_net / nullif(a.pos_net_total, 0), 4) AS top5_share,
        a.slot0_buyers,
        round(COALESCE(a.slot0_net, 0) / nullif(a.pos_net_total, 0), 4) AS slot0_share,
        a.early10_buyers,
        round(COALESCE(a.x30_1h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x30_1h,
        COALESCE(a.x30_1h_t, a.last_dt, 0) AS x30_1h_dt,
        round(COALESCE(a.x30_24h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x30_24h,
        COALESCE(a.x30_24h_t, a.last_dt, 0) AS x30_24h_dt,
        round(COALESCE(a.x50_1h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x50_1h,
        COALESCE(a.x50_1h_t, a.last_dt, 0) AS x50_1h_dt,
        round(COALESCE(a.x50_24h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x50_24h,
        COALESCE(a.x50_24h_t, a.last_dt, 0) AS x50_24h_dt,
        round(COALESCE(a.x70_1h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x70_1h,
        COALESCE(a.x70_1h_t, a.last_dt, 0) AS x70_1h_dt,
        round(COALESCE(a.x70_24h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x70_24h,
        COALESCE(a.x70_24h_t, a.last_dt, 0) AS x70_24h_dt,
        round(COALESCE(a.xNA_1h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS xNA_1h,
        COALESCE(a.xNA_1h_t, a.last_dt, 0) AS xNA_1h_dt,
        round(COALESCE(a.xNA_24h_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS xNA_24h,
        COALESCE(a.xNA_24h_t, a.last_dt, 0) AS xNA_24h_dt,
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
-- 冒烟版输出：汇总一行，核对语法、各特征量级、退出规则是否自洽
SELECT
    count(*) AS n_active,
    count_if(bitwise_and(flags, 4) > 0) AS n_grad,
    count_if(bitwise_and(flags, 128) > 0) AS n_mayhem,
    count_if(bitwise_and(flags, 1024) > 0) AS n_entry_on_pool,
    count_if(mpi_t50 >= 10) AS n_winner_t50,
    approx_percentile(entry_x_sol, 0.5) AS entry_x_p50,
    approx_percentile(n_trades_pre, 0.5) AS n_trades_pre_p50,
    approx_percentile(n_buyers_pre, 0.5) AS n_buyers_pre_p50,
    approx_percentile(trades_per_sol, 0.5) AS trades_per_sol_p50,
    approx_percentile(bot_share_pre, 0.5) AS bot_share_p50,
    approx_percentile(top1_share, 0.5) AS top1_share_p50,
    approx_percentile(top5_share, 0.5) AS top5_share_p50,
    approx_percentile(dev_net_share, 0.5) AS dev_net_share_p50,
    approx_percentile(slot0_buyers, 0.9) AS slot0_buyers_p90,
    approx_percentile(dev_prior_launches, 0.9) AS dev_prior_launches_p90,
    approx_percentile(secs_since_last, 0.5) AS secs_since_last_p50,
    avg(mpi_t50) AS mean_mpi_t50,
    avg(x30_1h) AS mean_x30_1h,
    avg(x50_24h) AS mean_x50_24h,
    avg(xNA_24h) AS mean_xNA_24h,
    approx_percentile(x50_1h_dt, 0.5) AS x50_1h_dt_p50,
    count_if(top1_share > 1.0001 OR top5_share > 1.0001 OR top1_share > top5_share + 1e-6) AS bad_share_sanity,
    count_if(x30_1h > ms_60d * 1.5 AND ms_60d > 1) AS bad_exit_sanity,
    count_if(pre_peak_pm < 0.9999) AS bad_pre_peak_sanity
FROM final
