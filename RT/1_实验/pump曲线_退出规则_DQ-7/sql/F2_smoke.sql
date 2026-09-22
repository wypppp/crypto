-- DQ-7 · F2（冒烟版）：回撤时区分洗盘与砸盘 + 分批止盈。依据 dq7/DQ7_卡.md。
-- cohort 创建日 2026-06-07 ~ 2026-06-07；行情扫描至 2026-06-10（入场后 30 天封顶）。
-- 相对 F1 的改动：持有期 60→30 天；PumpSwap 事件补入 user/方向/数量（毕业后也能追踪卖方）；
-- 新增 内部人集合（创建者 + 创建区块内买入者）持仓与入场后累计净卖出比例、30 分钟窗口新买家数与买卖额、半仓卖出价值；
-- 12 条退出规则（6 条全额 + 6 条分批止盈）与首次 50% 回撤时刻的解剖列（v1.1 增加：从未买过的钱包卖出额、30 分钟成交数及其前一个 30 分钟的成交数）。
-- 注意：已毕业后入场的币，入场前特征现在包含 PumpSwap 成交（F1 中不含），与 F1 的该部分特征不完全可比。
-- 冒烟：只看汇总与自检。
-- [模板来源 DQ-1F · F1，经 dq7/sql/build_f2.py 定点修改]（冒烟版）：活跃池逐 mint 的入场特征 + 8 条动态退出规则 + DQ-1M 标签。依据 DQ1F_卡.md。
-- 由 dq1f/sql/build_f1.py 从同一模板渲染；冒烟版、开发版、验证版只有日期与末尾输出不同。
-- cohort 创建日 2026-06-07 ~ 2026-06-07；行情扫描 2026-06-07 ~ 2026-06-10；创建者历史回看自 2026-05-08。

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
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-10'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
mig AS (
    SELECT mint, arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-10'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-10'
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
    WHERE t.evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-10'
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
            WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-10'
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
            WHERE evt_block_date BETWEEN DATE '2026-06-07' AND DATE '2026-06-10'
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
        LEAST(c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY, TIMESTAMP '2026-06-10 23:59:59 UTC') AS t_end,
        date_diff('second', c.created_at + INTERVAL '30' MINUTE, s.ts) AS dt,
        row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.iix) AS rn
    FROM states s
    JOIN sol_cohort c ON c.mint = s.mint
    WHERE s.ts <= c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY
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
        row_number() OVER (PARTITION BY mint, usr ORDER BY rn) AS u_rn1,
        min(CASE WHEN is_buy THEN rn END) OVER (PARTITION BY mint, usr) AS u_first_buy_rn
    FROM s2
),
s4 AS (
    SELECT
        *,
        ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4)) AS tok,
        (x / y) / (ex / ey) AS pm,
        usr IS NOT NULL AND u_rn1 = 1 AS u_first,
        rank() OVER (PARTITION BY mint ORDER BY CASE WHEN usr IS NOT NULL AND u_rn1 = 1 AND u_net_pre > 0 THEN u_net_pre END DESC NULLS LAST) AS u_rank,
        usr IS NOT NULL AND (usr = dev OR u_first_buy_slot = created_slot) AS ins,
        usr IS NOT NULL AND COALESCE(is_buy, false) AND rn = u_first_buy_rn AS is_newb,
        usr IS NOT NULL AND NOT COALESCE(is_buy, true) AND (u_first_buy_rn IS NULL OR u_first_buy_rn > rn) AS is_nb_sell
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
        p AND rn = max(CASE WHEN p THEN rn END) OVER (PARTITION BY mint, d) AS is_close,
        LEAST(
            CASE WHEN venue = 0 AND y > tok / 2 THEN (x * y / (y - tok / 2) - x) * (1 - fee_bps / 1e4)
                 WHEN venue = 0 THEN NULL
                 ELSE (x - x * y / (y + tok / 2)) * (1 - fee_bps / 1e4) END,
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - efee / 1e4)), 1e18)) / 0.5 AS smh,
        sum(CASE WHEN u_first AND ins AND u_net_pre > 0 THEN u_net_pre END) OVER (PARTITION BY mint) AS ins_hold,
        sum(CASE WHEN u_first AND u_net_pre > 0 THEN u_net_pre END) OVER (PARTITION BY mint) AS pos_hold,
        sum(CASE WHEN p AND ins AND tok_amt IS NOT NULL THEN IF(is_buy, -tok_amt, tok_amt) END)
            OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ins_cum_sold
    FROM s4
),
s6 AS (
    SELECT
        *,
        max(CASE WHEN is_close THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_close,
        max(CASE WHEN rn >= entry_rn THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_post,
        lead(sm) OVER (PARTITION BY mint ORDER BY rn) AS lead_sm,
        lead(ts) OVER (PARTITION BY mint ORDER BY rn) AS lead_ts,
        lead(smh) OVER (PARTITION BY mint ORDER BY rn) AS lead_smh,
        COALESCE(ins_cum_sold / nullif(ins_hold, 0), 0) AS ins_exit,
        sum(IF(is_newb, 1, 0)) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS newb30,
        sum(CASE WHEN NOT is_buy THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS sell30,
        sum(CASE WHEN is_buy THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS buy30,
        sum(CASE WHEN ins AND NOT is_buy THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS ins_sell30,
        sum(CASE WHEN is_nb_sell THEN sol_amt END) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS nb_sell30,
        count(*) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW) AS trades30,
        count(*) OVER (PARTITION BY mint ORDER BY dt RANGE BETWEEN 3600 PRECEDING AND 1801 PRECEDING) AS trades30_prev
    FROM s5
),
s7 AS (
    SELECT
        *,
        min(CASE WHEN is_close AND pm <= 0.5 * greatest(1.0, runmax_close) THEN d END) OVER (PARTITION BY mint) AS d_trig,
        min(CASE WHEN p AND pm >= 2 THEN rn END) OVER (PARTITION BY mint) AS tp2_rn,
        min(CASE WHEN p AND pm >= 3 THEN rn END) OVER (PARTITION BY mint) AS tp3_rn,
        min(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN rn END) OVER (PARTITION BY mint) AS dd_rn
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
        max(tp2_rn) AS tp2_rn,
        max(tp3_rn) AS tp3_rn,
        max_by(smh, rn) FILTER (WHERE p) AS smh_last,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS b50_v,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS b50_t,
        min_by(CASE WHEN ((p AND ins_hold > 0 AND ins_exit >= 0.5) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND ins_hold > 0 AND ins_exit >= 0.5) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS ins50_h70_v,
        min_by(CASE WHEN ((p AND ins_hold > 0 AND ins_exit >= 0.5) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE ((p AND ins_hold > 0 AND ins_exit >= 0.5) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS ins50_h70_t,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c30_i02_v,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c30_i02_t,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c30_i05_v,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c30_i05_t,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c100_i02_v,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c100_i02_t,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c100_i05_v,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS c100_i05_t,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_r70_pv,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_r70_pt,
        min_by(smh, rn) FILTER (WHERE rn = tp2_rn) AS tp2_r70_hv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_smh ELSE smh END) ELSE smh END, rn) FILTER (WHERE rn > tp2_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_r70_qv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE rn > tp2_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_r70_qt,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_rNA_pv,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_rNA_pt,
        min_by(smh, rn) FILTER (WHERE rn = tp2_rn) AS tp2_rNA_hv,
        min_by(CASE WHEN false THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_smh ELSE smh END) ELSE smh END, rn) FILTER (WHERE rn > tp2_rn AND (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_rNA_qv,
        min_by(CASE WHEN false THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE rn > tp2_rn AND (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_rNA_qt,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp3_rn IS NULL OR rn < tp3_rn)) AS tp3_r70_pv,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp3_rn IS NULL OR rn < tp3_rn)) AS tp3_r70_pt,
        min_by(smh, rn) FILTER (WHERE rn = tp3_rn) AS tp3_r70_hv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_smh ELSE smh END) ELSE smh END, rn) FILTER (WHERE rn > tp3_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp3_r70_qv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE rn > tp3_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp3_r70_qt,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp3_rn IS NULL OR rn < tp3_rn)) AS tp3_rNA_pv,
        min_by(CASE WHEN ((p AND pm <= 0.50 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE (((p AND pm <= 0.50 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp3_rn IS NULL OR rn < tp3_rn)) AS tp3_rNA_pt,
        min_by(smh, rn) FILTER (WHERE rn = tp3_rn) AS tp3_rNA_hv,
        min_by(CASE WHEN false THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_smh ELSE smh END) ELSE smh END, rn) FILTER (WHERE rn > tp3_rn AND (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp3_rNA_qv,
        min_by(CASE WHEN false THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE rn > tp3_rn AND (false OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp3_rNA_qt,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_c30_i02_r70_pv,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE ((((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.2 OR newb30 < 30)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_c30_i02_r70_pt,
        min_by(smh, rn) FILTER (WHERE rn = tp2_rn) AS tp2_c30_i02_r70_hv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_smh ELSE smh END) ELSE smh END, rn) FILTER (WHERE rn > tp2_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_c30_i02_r70_qv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE rn > tp2_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_c30_i02_r70_qt,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_c100_i05_r70_pv,
        min_by(CASE WHEN (((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE ((((p AND pm <= 0.50 * greatest(1.0, runmax_post)) AND (ins_exit >= 0.5 OR newb30 < 100)) OR (p AND pm <= 0.30 * greatest(1.0, runmax_post)) OR (p AND ins_hold > 0 AND ins_exit >= 0.5)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AND (tp2_rn IS NULL OR rn < tp2_rn)) AS tp2_c100_i05_r70_pt,
        min_by(smh, rn) FILTER (WHERE rn = tp2_rn) AS tp2_c100_i05_r70_hv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN (CASE WHEN lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5 THEN lead_smh ELSE smh END) ELSE smh END, rn) FILTER (WHERE rn > tp2_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_c100_i05_r70_qv,
        min_by(CASE WHEN ((p AND pm <= 0.30 * greatest(1.0, runmax_post))) THEN dt ELSE greatest(dt, 0) + 86400 END, rn) FILTER (WHERE rn > tp2_rn AND (((p AND pm <= 0.30 * greatest(1.0, runmax_post))) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS tp2_c100_i05_r70_qt,
        min_by(dt, rn) FILTER (WHERE rn = dd_rn) AS dd_dt,
        min_by(runmax_post, rn) FILTER (WHERE rn = dd_rn) AS dd_runmax,
        min_by(pm, rn) FILTER (WHERE rn = dd_rn) AS dd_pm,
        min_by(venue, rn) FILTER (WHERE rn = dd_rn) AS dd_venue,
        min_by(ins_exit, rn) FILTER (WHERE rn = dd_rn) AS dd_ins_exit,
        min_by(newb30, rn) FILTER (WHERE rn = dd_rn) AS dd_newb30,
        min_by(sell30, rn) FILTER (WHERE rn = dd_rn) AS dd_sell30,
        min_by(buy30, rn) FILTER (WHERE rn = dd_rn) AS dd_buy30,
        min_by(ins_sell30, rn) FILTER (WHERE rn = dd_rn) AS dd_ins_sell30,
        min_by(sm, rn) FILTER (WHERE rn = dd_rn) AS dd_sm,
        min_by(nb_sell30, rn) FILTER (WHERE rn = dd_rn) AS dd_nb_sell30,
        min_by(trades30, rn) FILTER (WHERE rn = dd_rn) AS dd_trades30,
        min_by(trades30_prev, rn) FILTER (WHERE rn = dd_rn) AS dd_trades30_prev,
        max(pm) FILTER (WHERE rn > dd_rn) AS dd_post_max_pm,
        max(ins_hold) AS ins_hold,
        max(pos_hold) AS pos_hold,
        count_if(p AND is_newb) AS n_newb_post,
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
        round(COALESCE(a.ms_60d, 1.0), 6) AS ms_30d,
        round(COALESCE(a.hv_2h, power(1 - a.efee / 1e4, 2)), 6) AS hv_2h,
        round(COALESCE(a.hv_24h, power(1 - a.efee / 1e4, 2)), 6) AS hv_24h,
        round(COALESCE(a.hv_7d, power(1 - a.efee / 1e4, 2)), 6) AS hv_7d,
        round(COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS hv_30d,
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
        round(COALESCE(a.b50_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS b50,
        COALESCE(a.b50_t, a.last_dt, 0) AS b50_dt,
        round(COALESCE(a.ins50_h70_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS ins50_h70,
        COALESCE(a.ins50_h70_t, a.last_dt, 0) AS ins50_h70_dt,
        round(COALESCE(a.c30_i02_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS c30_i02,
        COALESCE(a.c30_i02_t, a.last_dt, 0) AS c30_i02_dt,
        round(COALESCE(a.c30_i05_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS c30_i05,
        COALESCE(a.c30_i05_t, a.last_dt, 0) AS c30_i05_dt,
        round(COALESCE(a.c100_i02_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS c100_i02,
        COALESCE(a.c100_i02_t, a.last_dt, 0) AS c100_i02_dt,
        round(COALESCE(a.c100_i05_v, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS c100_i05,
        COALESCE(a.c100_i05_t, a.last_dt, 0) AS c100_i05_dt,
        round(CASE WHEN a.tp2_r70_pv IS NOT NULL THEN a.tp2_r70_pv WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_r70_hv, 0) + COALESCE(a.tp2_r70_qv, a.smh_last, 0) ELSE COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)) END, 6) AS tp2_r70,
        CASE WHEN a.tp2_r70_pv IS NOT NULL THEN a.tp2_r70_pt WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_r70_qt, a.last_dt, 0) ELSE COALESCE(a.last_dt, 0) END AS tp2_r70_dt,
        round(CASE WHEN a.tp2_rNA_pv IS NOT NULL THEN a.tp2_rNA_pv WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_rNA_hv, 0) + COALESCE(a.tp2_rNA_qv, a.smh_last, 0) ELSE COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)) END, 6) AS tp2_rNA,
        CASE WHEN a.tp2_rNA_pv IS NOT NULL THEN a.tp2_rNA_pt WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_rNA_qt, a.last_dt, 0) ELSE COALESCE(a.last_dt, 0) END AS tp2_rNA_dt,
        round(CASE WHEN a.tp3_r70_pv IS NOT NULL THEN a.tp3_r70_pv WHEN a.tp3_rn IS NOT NULL THEN COALESCE(a.tp3_r70_hv, 0) + COALESCE(a.tp3_r70_qv, a.smh_last, 0) ELSE COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)) END, 6) AS tp3_r70,
        CASE WHEN a.tp3_r70_pv IS NOT NULL THEN a.tp3_r70_pt WHEN a.tp3_rn IS NOT NULL THEN COALESCE(a.tp3_r70_qt, a.last_dt, 0) ELSE COALESCE(a.last_dt, 0) END AS tp3_r70_dt,
        round(CASE WHEN a.tp3_rNA_pv IS NOT NULL THEN a.tp3_rNA_pv WHEN a.tp3_rn IS NOT NULL THEN COALESCE(a.tp3_rNA_hv, 0) + COALESCE(a.tp3_rNA_qv, a.smh_last, 0) ELSE COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)) END, 6) AS tp3_rNA,
        CASE WHEN a.tp3_rNA_pv IS NOT NULL THEN a.tp3_rNA_pt WHEN a.tp3_rn IS NOT NULL THEN COALESCE(a.tp3_rNA_qt, a.last_dt, 0) ELSE COALESCE(a.last_dt, 0) END AS tp3_rNA_dt,
        round(CASE WHEN a.tp2_c30_i02_r70_pv IS NOT NULL THEN a.tp2_c30_i02_r70_pv WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_c30_i02_r70_hv, 0) + COALESCE(a.tp2_c30_i02_r70_qv, a.smh_last, 0) ELSE COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)) END, 6) AS tp2_c30_i02_r70,
        CASE WHEN a.tp2_c30_i02_r70_pv IS NOT NULL THEN a.tp2_c30_i02_r70_pt WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_c30_i02_r70_qt, a.last_dt, 0) ELSE COALESCE(a.last_dt, 0) END AS tp2_c30_i02_r70_dt,
        round(CASE WHEN a.tp2_c100_i05_r70_pv IS NOT NULL THEN a.tp2_c100_i05_r70_pv WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_c100_i05_r70_hv, 0) + COALESCE(a.tp2_c100_i05_r70_qv, a.smh_last, 0) ELSE COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2)) END, 6) AS tp2_c100_i05_r70,
        CASE WHEN a.tp2_c100_i05_r70_pv IS NOT NULL THEN a.tp2_c100_i05_r70_pt WHEN a.tp2_rn IS NOT NULL THEN COALESCE(a.tp2_c100_i05_r70_qt, a.last_dt, 0) ELSE COALESCE(a.last_dt, 0) END AS tp2_c100_i05_r70_dt,
        round(COALESCE(a.ins_hold, 0) / nullif(a.pos_hold, 0), 4) AS ins_hold_share,
        a.dd_dt, round(a.dd_runmax, 4) AS dd_runmax, a.dd_venue,
        round(a.dd_ins_exit, 4) AS dd_ins_exit, a.dd_newb30,
        round(a.dd_sell30, 4) AS dd_sell30, round(a.dd_buy30, 4) AS dd_buy30, round(a.dd_ins_sell30, 4) AS dd_ins_sell30,
        round(a.dd_sm, 6) AS dd_sm, round(a.dd_post_max_pm / nullif(a.dd_pm, 0), 4) AS dd_rebound,
        round(a.dd_nb_sell30, 4) AS dd_nb_sell30, a.dd_trades30, a.dd_trades30_prev,
        a.n_newb_post,
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
-- 冒烟输出：一行汇总。bad_* 为回收超过事后最高价 1.5 倍的币数（应为 0）。
SELECT
    count(*) AS n_active,
    count_if(dd_dt IS NOT NULL) AS n_dd,
    approx_percentile(dd_newb30, 0.5) AS dd_newb30_p50,
    approx_percentile(dd_ins_exit, 0.5) AS dd_ins_exit_p50,
    count_if(dd_ins_exit > 1.5 OR dd_ins_exit < -1.5) AS bad_ins_exit,
    approx_percentile(ins_hold_share, 0.5) AS ins_hold_share_p50,
    count_if(ins_hold_share > 1.0001) AS bad_ins_share,
    round(avg(b50), 4) AS avg_b50,
    count_if(b50 > 1.5 * ms_30d + 0.1) AS bad_b50,
    round(avg(ins50_h70), 4) AS avg_ins50_h70,
    count_if(ins50_h70 > 1.5 * ms_30d + 0.1) AS bad_ins50_h70,
    round(avg(c30_i02), 4) AS avg_c30_i02,
    count_if(c30_i02 > 1.5 * ms_30d + 0.1) AS bad_c30_i02,
    round(avg(c30_i05), 4) AS avg_c30_i05,
    count_if(c30_i05 > 1.5 * ms_30d + 0.1) AS bad_c30_i05,
    round(avg(c100_i02), 4) AS avg_c100_i02,
    count_if(c100_i02 > 1.5 * ms_30d + 0.1) AS bad_c100_i02,
    round(avg(c100_i05), 4) AS avg_c100_i05,
    count_if(c100_i05 > 1.5 * ms_30d + 0.1) AS bad_c100_i05,
    round(avg(tp2_r70), 4) AS avg_tp2_r70,
    count_if(tp2_r70 > 1.5 * ms_30d + 0.1) AS bad_tp2_r70,
    round(avg(tp2_rNA), 4) AS avg_tp2_rNA,
    count_if(tp2_rNA > 1.5 * ms_30d + 0.1) AS bad_tp2_rNA,
    round(avg(tp3_r70), 4) AS avg_tp3_r70,
    count_if(tp3_r70 > 1.5 * ms_30d + 0.1) AS bad_tp3_r70,
    round(avg(tp3_rNA), 4) AS avg_tp3_rNA,
    count_if(tp3_rNA > 1.5 * ms_30d + 0.1) AS bad_tp3_rNA,
    round(avg(tp2_c30_i02_r70), 4) AS avg_tp2_c30_i02_r70,
    count_if(tp2_c30_i02_r70 > 1.5 * ms_30d + 0.1) AS bad_tp2_c30_i02_r70,
    round(avg(tp2_c100_i05_r70), 4) AS avg_tp2_c100_i05_r70,
    count_if(tp2_c100_i05_r70 > 1.5 * ms_30d + 0.1) AS bad_tp2_c100_i05_r70
FROM final
