-- DQ-8A · F3 诊断（冒烟 Gate 0 的 bad_b50_mismatch=3）：检查点面板。依据 dq8/DQ-8A 卡 · 决策价值地图（最终冻结版）.md。
-- cohort 创建日 2026-06-07 ~ 2026-06-07；行情扫描至 2026-06-10（入场后 30 天封顶）。重扫描链与口径沿用 DQ-7 F2（build_f2.render 截至 s7）。
-- 行 = (mint, 区间 iv)。iv=0：入场及之前；iv=k (1..10)：(τ_{k-1}, τ_k]；iv=11：(7d, 30d]。τ = [0, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400, 259200, 604800] 秒。无成交区间不输出。
-- l_*：区间最后一笔后的状态（检查点决策信息）；e_*：区间开头 5 秒内最后一笔后的状态（上一检查点决策的成交状态）；*_sm：原始仓位卖出回收。
-- f_*：区间最后一笔处的特征（30 分钟窗口按该笔时间计）；f_maxpm：区间内最高价倍数。
-- t50/t70：原始仓位区间内首次触发 50%/70% 移动止损的时点与成交回收（5 秒抢跑规则）。dead_*：其后 24 小时无成交的行（dead_rows 打包全部：dt,x,y,xr,venue,fee）。
-- trig_new：检查点 k=1..10 新买入 0.5 SOL 的持仓（买入状态 = 截至 τ_k+5 秒最后一笔后；running peak 自买入起逐笔累积、跨区间延续）
--   在本区间首次触发 50%/70% 移动止损的 "k,s,dt,回收" 列表，以 ';' 分隔；回收 -1 表示无法估值。
-- bad_k0：通用新仓位逻辑取 k=0 时与原始仓位 t50/t70 不一致（应恒为 false）；bad_early：新仓位触发早于买入（应恒为 false）。
-- 冒烟：只看汇总与自检（含 b50 两路径对照、k=0 通用逻辑对照），会重复扫描一次，成本约为单路径的 2 倍。
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
        lead(x) OVER (PARTITION BY mint ORDER BY rn) AS lead_x,
        lead(y) OVER (PARTITION BY mint ORDER BY rn) AS lead_y,
        lead(xr) OVER (PARTITION BY mint ORDER BY rn) AS lead_xr,
        lead(venue) OVER (PARTITION BY mint ORDER BY rn) AS lead_venue,
        lead(fee_bps) OVER (PARTITION BY mint ORDER BY rn) AS lead_fee_bps,
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
b1 AS (
    SELECT *, CASE iv WHEN 1 THEN 0 WHEN 2 THEN 300 WHEN 3 THEN 900 WHEN 4 THEN 1800 WHEN 5 THEN 3600 WHEN 6 THEN 7200 WHEN 7 THEN 14400 WHEN 8 THEN 28800 WHEN 9 THEN 86400 WHEN 10 THEN 259200 WHEN 11 THEN 604800 END AS lo
    FROM (
        SELECT *,
        entry_rn AS rnk_0,
        max(CASE WHEN dt <= 300 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_1,
        max(CASE WHEN dt <= 900 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_2,
        max(CASE WHEN dt <= 1800 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_3,
        max(CASE WHEN dt <= 3600 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_4,
        max(CASE WHEN dt <= 7200 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_5,
        max(CASE WHEN dt <= 14400 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_6,
        max(CASE WHEN dt <= 28800 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_7,
        max(CASE WHEN dt <= 86400 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_8,
        max(CASE WHEN dt <= 259200 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_9,
        max(CASE WHEN dt <= 604800 + 5 THEN rn END) OVER (PARTITION BY mint) AS rnk_10,
        CASE WHEN dt <= 0 THEN 0 WHEN dt <= 300 THEN 1 WHEN dt <= 900 THEN 2 WHEN dt <= 1800 THEN 3 WHEN dt <= 3600 THEN 4 WHEN dt <= 7200 THEN 5 WHEN dt <= 14400 THEN 6 WHEN dt <= 28800 THEN 7 WHEN dt <= 86400 THEN 8 WHEN dt <= 259200 THEN 9 WHEN dt <= 604800 THEN 10 ELSE 11 END AS iv
        FROM s7
    ) z
),
b2 AS (
    SELECT *,
        max(CASE WHEN rn = rnk_0 THEN pm END) OVER (PARTITION BY mint) AS pmb_0,
        max(CASE WHEN rn = rnk_0 THEN x END) OVER (PARTITION BY mint) AS xb_0,
        max(CASE WHEN rn = rnk_0 THEN y END) OVER (PARTITION BY mint) AS yb_0,
        max(CASE WHEN rn = rnk_0 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_0,
        max(CASE WHEN rn > rnk_0 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_0,
        max(CASE WHEN rn = rnk_1 THEN pm END) OVER (PARTITION BY mint) AS pmb_1,
        max(CASE WHEN rn = rnk_1 THEN x END) OVER (PARTITION BY mint) AS xb_1,
        max(CASE WHEN rn = rnk_1 THEN y END) OVER (PARTITION BY mint) AS yb_1,
        max(CASE WHEN rn = rnk_1 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_1,
        max(CASE WHEN rn > rnk_1 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_1,
        max(CASE WHEN rn = rnk_2 THEN pm END) OVER (PARTITION BY mint) AS pmb_2,
        max(CASE WHEN rn = rnk_2 THEN x END) OVER (PARTITION BY mint) AS xb_2,
        max(CASE WHEN rn = rnk_2 THEN y END) OVER (PARTITION BY mint) AS yb_2,
        max(CASE WHEN rn = rnk_2 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_2,
        max(CASE WHEN rn > rnk_2 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_2,
        max(CASE WHEN rn = rnk_3 THEN pm END) OVER (PARTITION BY mint) AS pmb_3,
        max(CASE WHEN rn = rnk_3 THEN x END) OVER (PARTITION BY mint) AS xb_3,
        max(CASE WHEN rn = rnk_3 THEN y END) OVER (PARTITION BY mint) AS yb_3,
        max(CASE WHEN rn = rnk_3 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_3,
        max(CASE WHEN rn > rnk_3 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_3,
        max(CASE WHEN rn = rnk_4 THEN pm END) OVER (PARTITION BY mint) AS pmb_4,
        max(CASE WHEN rn = rnk_4 THEN x END) OVER (PARTITION BY mint) AS xb_4,
        max(CASE WHEN rn = rnk_4 THEN y END) OVER (PARTITION BY mint) AS yb_4,
        max(CASE WHEN rn = rnk_4 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_4,
        max(CASE WHEN rn > rnk_4 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_4,
        max(CASE WHEN rn = rnk_5 THEN pm END) OVER (PARTITION BY mint) AS pmb_5,
        max(CASE WHEN rn = rnk_5 THEN x END) OVER (PARTITION BY mint) AS xb_5,
        max(CASE WHEN rn = rnk_5 THEN y END) OVER (PARTITION BY mint) AS yb_5,
        max(CASE WHEN rn = rnk_5 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_5,
        max(CASE WHEN rn > rnk_5 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_5,
        max(CASE WHEN rn = rnk_6 THEN pm END) OVER (PARTITION BY mint) AS pmb_6,
        max(CASE WHEN rn = rnk_6 THEN x END) OVER (PARTITION BY mint) AS xb_6,
        max(CASE WHEN rn = rnk_6 THEN y END) OVER (PARTITION BY mint) AS yb_6,
        max(CASE WHEN rn = rnk_6 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_6,
        max(CASE WHEN rn > rnk_6 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_6,
        max(CASE WHEN rn = rnk_7 THEN pm END) OVER (PARTITION BY mint) AS pmb_7,
        max(CASE WHEN rn = rnk_7 THEN x END) OVER (PARTITION BY mint) AS xb_7,
        max(CASE WHEN rn = rnk_7 THEN y END) OVER (PARTITION BY mint) AS yb_7,
        max(CASE WHEN rn = rnk_7 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_7,
        max(CASE WHEN rn > rnk_7 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_7,
        max(CASE WHEN rn = rnk_8 THEN pm END) OVER (PARTITION BY mint) AS pmb_8,
        max(CASE WHEN rn = rnk_8 THEN x END) OVER (PARTITION BY mint) AS xb_8,
        max(CASE WHEN rn = rnk_8 THEN y END) OVER (PARTITION BY mint) AS yb_8,
        max(CASE WHEN rn = rnk_8 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_8,
        max(CASE WHEN rn > rnk_8 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_8,
        max(CASE WHEN rn = rnk_9 THEN pm END) OVER (PARTITION BY mint) AS pmb_9,
        max(CASE WHEN rn = rnk_9 THEN x END) OVER (PARTITION BY mint) AS xb_9,
        max(CASE WHEN rn = rnk_9 THEN y END) OVER (PARTITION BY mint) AS yb_9,
        max(CASE WHEN rn = rnk_9 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_9,
        max(CASE WHEN rn > rnk_9 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_9,
        max(CASE WHEN rn = rnk_10 THEN pm END) OVER (PARTITION BY mint) AS pmb_10,
        max(CASE WHEN rn = rnk_10 THEN x END) OVER (PARTITION BY mint) AS xb_10,
        max(CASE WHEN rn = rnk_10 THEN y END) OVER (PARTITION BY mint) AS yb_10,
        max(CASE WHEN rn = rnk_10 THEN fee_bps END) OVER (PARTITION BY mint) AS feeb_10,
        max(CASE WHEN rn > rnk_10 THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pkr_10
    FROM b1
),
b3 AS (
    SELECT *,
        yb_0 - xb_0 * yb_0 / (xb_0 + 0.5 * (1 - feeb_0 / 1e4)) AS tok_0,
        yb_1 - xb_1 * yb_1 / (xb_1 + 0.5 * (1 - feeb_1 / 1e4)) AS tok_1,
        yb_2 - xb_2 * yb_2 / (xb_2 + 0.5 * (1 - feeb_2 / 1e4)) AS tok_2,
        yb_3 - xb_3 * yb_3 / (xb_3 + 0.5 * (1 - feeb_3 / 1e4)) AS tok_3,
        yb_4 - xb_4 * yb_4 / (xb_4 + 0.5 * (1 - feeb_4 / 1e4)) AS tok_4,
        yb_5 - xb_5 * yb_5 / (xb_5 + 0.5 * (1 - feeb_5 / 1e4)) AS tok_5,
        yb_6 - xb_6 * yb_6 / (xb_6 + 0.5 * (1 - feeb_6 / 1e4)) AS tok_6,
        yb_7 - xb_7 * yb_7 / (xb_7 + 0.5 * (1 - feeb_7 / 1e4)) AS tok_7,
        yb_8 - xb_8 * yb_8 / (xb_8 + 0.5 * (1 - feeb_8 / 1e4)) AS tok_8,
        yb_9 - xb_9 * yb_9 / (xb_9 + 0.5 * (1 - feeb_9 / 1e4)) AS tok_9,
        yb_10 - xb_10 * yb_10 / (xb_10 + 0.5 * (1 - feeb_10 / 1e4)) AS tok_10
    FROM b2
),
grp AS (
    SELECT
        mint,
        iv,
        count(*) AS n,
        min(dt) AS first_dt,
        min(dt) FILTER (WHERE dt > lo + 5) AS first_after5_dt,
        max(dt) AS last_dt,
        bool_or(venue = 0 AND x > 120) AS anom,
        round(max_by(x, rn), 6) AS l_x,
        round(max_by(y, rn), 0) AS l_y,
        round(max_by(xr, rn), 6) AS l_xr,
        max_by(venue, rn) AS l_venue,
        max_by(fee_bps, rn) AS l_fee_bps,
        round(max_by(sm, rn) FILTER (WHERE rn >= entry_rn), 6) AS l_sm,
        round(max_by(x, rn) FILTER (WHERE dt <= lo + 5), 6) AS e_x,
        round(max_by(y, rn) FILTER (WHERE dt <= lo + 5), 0) AS e_y,
        round(max_by(xr, rn) FILTER (WHERE dt <= lo + 5), 6) AS e_xr,
        max_by(venue, rn) FILTER (WHERE dt <= lo + 5) AS e_venue,
        max_by(fee_bps, rn) FILTER (WHERE dt <= lo + 5) AS e_fee_bps,
        round(max_by(sm, rn) FILTER (WHERE dt <= lo + 5 AND rn >= entry_rn), 6) AS e_sm,
        round(max_by(pm, rn), 6) AS f_pm,
        round(max_by(runmax_post, rn), 6) AS f_runmax,
        round(max(pm) FILTER (WHERE rn >= entry_rn), 6) AS f_maxpm,
        max_by(newb30, rn) AS f_newb30,
        max_by(trades30, rn) AS f_trades30,
        max_by(trades30_prev, rn) AS f_trades30_prev,
        round(max_by(buy30, rn), 4) AS f_buy30,
        round(max_by(sell30, rn), 4) AS f_sell30,
        round(max_by(nb_sell30, rn), 4) AS f_nb_sell30,
        round(max_by(ins_exit, rn), 4) AS f_ins_exit,
        min(dt) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post))) AS t50_dt,
        round(min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), lead_sm, sm), rn) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post))), 6) AS t50_v,
        min(dt) FILTER (WHERE (p AND pm <= 0.30 * greatest(1.0, runmax_post))) AS t70_dt,
        round(min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), lead_sm, sm), rn) FILTER (WHERE (p AND pm <= 0.30 * greatest(1.0, runmax_post))), 6) AS t70_v,
        min(dt) FILTER (WHERE (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)) AS dead_dt,
        round(min_by(sm, rn) FILTER (WHERE (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)), 6) AS dead_sm,
        array_join(array_agg(format('%d,%.6f,%.0f,%.6f,%d,%.2f', dt, x, y, COALESCE(xr, -1), venue, fee_bps)) FILTER (WHERE (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)), ';') AS dead_rows,
        min(dt) FILTER (WHERE (rn > rnk_0 AND pm <= 0.50 * greatest(pmb_0, COALESCE(pkr_0, pmb_0)))) AS k0_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_0 THEN (lead_x * lead_y / (lead_y - tok_0) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_0)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_0 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_0 THEN (x * y / (y - tok_0) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_0)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_0 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_0 AND pm <= 0.50 * greatest(pmb_0, COALESCE(pkr_0, pmb_0)))) AS k0_50_v,
        min(dt) FILTER (WHERE (rn > rnk_0 AND pm <= 0.30 * greatest(pmb_0, COALESCE(pkr_0, pmb_0)))) AS k0_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_0 THEN (lead_x * lead_y / (lead_y - tok_0) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_0)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_0 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_0 THEN (x * y / (y - tok_0) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_0)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_0 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_0 AND pm <= 0.30 * greatest(pmb_0, COALESCE(pkr_0, pmb_0)))) AS k0_70_v,
        min(dt) FILTER (WHERE (rn > rnk_1 AND pm <= 0.50 * greatest(pmb_1, COALESCE(pkr_1, pmb_1)))) AS k1_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_1 THEN (lead_x * lead_y / (lead_y - tok_1) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_1)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_1 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_1 THEN (x * y / (y - tok_1) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_1)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_1 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_1 AND pm <= 0.50 * greatest(pmb_1, COALESCE(pkr_1, pmb_1)))) AS k1_50_v,
        min(dt) FILTER (WHERE (rn > rnk_1 AND pm <= 0.30 * greatest(pmb_1, COALESCE(pkr_1, pmb_1)))) AS k1_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_1 THEN (lead_x * lead_y / (lead_y - tok_1) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_1)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_1 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_1 THEN (x * y / (y - tok_1) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_1)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_1 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_1 AND pm <= 0.30 * greatest(pmb_1, COALESCE(pkr_1, pmb_1)))) AS k1_70_v,
        min(dt) FILTER (WHERE (rn > rnk_2 AND pm <= 0.50 * greatest(pmb_2, COALESCE(pkr_2, pmb_2)))) AS k2_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_2 THEN (lead_x * lead_y / (lead_y - tok_2) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_2)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_2 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_2 THEN (x * y / (y - tok_2) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_2)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_2 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_2 AND pm <= 0.50 * greatest(pmb_2, COALESCE(pkr_2, pmb_2)))) AS k2_50_v,
        min(dt) FILTER (WHERE (rn > rnk_2 AND pm <= 0.30 * greatest(pmb_2, COALESCE(pkr_2, pmb_2)))) AS k2_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_2 THEN (lead_x * lead_y / (lead_y - tok_2) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_2)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_2 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_2 THEN (x * y / (y - tok_2) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_2)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_2 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_2 AND pm <= 0.30 * greatest(pmb_2, COALESCE(pkr_2, pmb_2)))) AS k2_70_v,
        min(dt) FILTER (WHERE (rn > rnk_3 AND pm <= 0.50 * greatest(pmb_3, COALESCE(pkr_3, pmb_3)))) AS k3_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_3 THEN (lead_x * lead_y / (lead_y - tok_3) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_3)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_3 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_3 THEN (x * y / (y - tok_3) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_3)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_3 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_3 AND pm <= 0.50 * greatest(pmb_3, COALESCE(pkr_3, pmb_3)))) AS k3_50_v,
        min(dt) FILTER (WHERE (rn > rnk_3 AND pm <= 0.30 * greatest(pmb_3, COALESCE(pkr_3, pmb_3)))) AS k3_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_3 THEN (lead_x * lead_y / (lead_y - tok_3) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_3)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_3 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_3 THEN (x * y / (y - tok_3) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_3)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_3 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_3 AND pm <= 0.30 * greatest(pmb_3, COALESCE(pkr_3, pmb_3)))) AS k3_70_v,
        min(dt) FILTER (WHERE (rn > rnk_4 AND pm <= 0.50 * greatest(pmb_4, COALESCE(pkr_4, pmb_4)))) AS k4_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_4 THEN (lead_x * lead_y / (lead_y - tok_4) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_4)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_4 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_4 THEN (x * y / (y - tok_4) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_4)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_4 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_4 AND pm <= 0.50 * greatest(pmb_4, COALESCE(pkr_4, pmb_4)))) AS k4_50_v,
        min(dt) FILTER (WHERE (rn > rnk_4 AND pm <= 0.30 * greatest(pmb_4, COALESCE(pkr_4, pmb_4)))) AS k4_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_4 THEN (lead_x * lead_y / (lead_y - tok_4) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_4)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_4 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_4 THEN (x * y / (y - tok_4) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_4)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_4 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_4 AND pm <= 0.30 * greatest(pmb_4, COALESCE(pkr_4, pmb_4)))) AS k4_70_v,
        min(dt) FILTER (WHERE (rn > rnk_5 AND pm <= 0.50 * greatest(pmb_5, COALESCE(pkr_5, pmb_5)))) AS k5_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_5 THEN (lead_x * lead_y / (lead_y - tok_5) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_5)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_5 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_5 THEN (x * y / (y - tok_5) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_5)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_5 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_5 AND pm <= 0.50 * greatest(pmb_5, COALESCE(pkr_5, pmb_5)))) AS k5_50_v,
        min(dt) FILTER (WHERE (rn > rnk_5 AND pm <= 0.30 * greatest(pmb_5, COALESCE(pkr_5, pmb_5)))) AS k5_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_5 THEN (lead_x * lead_y / (lead_y - tok_5) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_5)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_5 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_5 THEN (x * y / (y - tok_5) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_5)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_5 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_5 AND pm <= 0.30 * greatest(pmb_5, COALESCE(pkr_5, pmb_5)))) AS k5_70_v,
        min(dt) FILTER (WHERE (rn > rnk_6 AND pm <= 0.50 * greatest(pmb_6, COALESCE(pkr_6, pmb_6)))) AS k6_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_6 THEN (lead_x * lead_y / (lead_y - tok_6) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_6)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_6 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_6 THEN (x * y / (y - tok_6) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_6)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_6 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_6 AND pm <= 0.50 * greatest(pmb_6, COALESCE(pkr_6, pmb_6)))) AS k6_50_v,
        min(dt) FILTER (WHERE (rn > rnk_6 AND pm <= 0.30 * greatest(pmb_6, COALESCE(pkr_6, pmb_6)))) AS k6_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_6 THEN (lead_x * lead_y / (lead_y - tok_6) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_6)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_6 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_6 THEN (x * y / (y - tok_6) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_6)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_6 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_6 AND pm <= 0.30 * greatest(pmb_6, COALESCE(pkr_6, pmb_6)))) AS k6_70_v,
        min(dt) FILTER (WHERE (rn > rnk_7 AND pm <= 0.50 * greatest(pmb_7, COALESCE(pkr_7, pmb_7)))) AS k7_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_7 THEN (lead_x * lead_y / (lead_y - tok_7) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_7)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_7 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_7 THEN (x * y / (y - tok_7) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_7)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_7 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_7 AND pm <= 0.50 * greatest(pmb_7, COALESCE(pkr_7, pmb_7)))) AS k7_50_v,
        min(dt) FILTER (WHERE (rn > rnk_7 AND pm <= 0.30 * greatest(pmb_7, COALESCE(pkr_7, pmb_7)))) AS k7_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_7 THEN (lead_x * lead_y / (lead_y - tok_7) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_7)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_7 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_7 THEN (x * y / (y - tok_7) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_7)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_7 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_7 AND pm <= 0.30 * greatest(pmb_7, COALESCE(pkr_7, pmb_7)))) AS k7_70_v,
        min(dt) FILTER (WHERE (rn > rnk_8 AND pm <= 0.50 * greatest(pmb_8, COALESCE(pkr_8, pmb_8)))) AS k8_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_8 THEN (lead_x * lead_y / (lead_y - tok_8) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_8)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_8 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_8 THEN (x * y / (y - tok_8) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_8)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_8 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_8 AND pm <= 0.50 * greatest(pmb_8, COALESCE(pkr_8, pmb_8)))) AS k8_50_v,
        min(dt) FILTER (WHERE (rn > rnk_8 AND pm <= 0.30 * greatest(pmb_8, COALESCE(pkr_8, pmb_8)))) AS k8_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_8 THEN (lead_x * lead_y / (lead_y - tok_8) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_8)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_8 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_8 THEN (x * y / (y - tok_8) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_8)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_8 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_8 AND pm <= 0.30 * greatest(pmb_8, COALESCE(pkr_8, pmb_8)))) AS k8_70_v,
        min(dt) FILTER (WHERE (rn > rnk_9 AND pm <= 0.50 * greatest(pmb_9, COALESCE(pkr_9, pmb_9)))) AS k9_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_9 THEN (lead_x * lead_y / (lead_y - tok_9) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_9)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_9 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_9 THEN (x * y / (y - tok_9) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_9)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_9 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_9 AND pm <= 0.50 * greatest(pmb_9, COALESCE(pkr_9, pmb_9)))) AS k9_50_v,
        min(dt) FILTER (WHERE (rn > rnk_9 AND pm <= 0.30 * greatest(pmb_9, COALESCE(pkr_9, pmb_9)))) AS k9_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_9 THEN (lead_x * lead_y / (lead_y - tok_9) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_9)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_9 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_9 THEN (x * y / (y - tok_9) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_9)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_9 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_9 AND pm <= 0.30 * greatest(pmb_9, COALESCE(pkr_9, pmb_9)))) AS k9_70_v,
        min(dt) FILTER (WHERE (rn > rnk_10 AND pm <= 0.50 * greatest(pmb_10, COALESCE(pkr_10, pmb_10)))) AS k10_50_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_10 THEN (lead_x * lead_y / (lead_y - tok_10) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_10)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_10 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_10 THEN (x * y / (y - tok_10) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_10)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_10 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_10 AND pm <= 0.50 * greatest(pmb_10, COALESCE(pkr_10, pmb_10)))) AS k10_50_v,
        min(dt) FILTER (WHERE (rn > rnk_10 AND pm <= 0.30 * greatest(pmb_10, COALESCE(pkr_10, pmb_10)))) AS k10_70_dt,
        min_by(IF((lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5), LEAST(CASE WHEN lead_venue = 0 AND lead_y > tok_10 THEN (lead_x * lead_y / (lead_y - tok_10) - lead_x) * (1 - lead_fee_bps / 1e4) WHEN lead_venue = 0 THEN NULL ELSE (lead_x - lead_x * lead_y / (lead_y + tok_10)) * (1 - lead_fee_bps / 1e4) END, COALESCE(IF(lead_venue = 0, lead_xr + 0.5 * (1 - feeb_10 / 1e4)), 1e18)) / 0.5, LEAST(CASE WHEN venue = 0 AND y > tok_10 THEN (x * y / (y - tok_10) - x) * (1 - fee_bps / 1e4) WHEN venue = 0 THEN NULL ELSE (x - x * y / (y + tok_10)) * (1 - fee_bps / 1e4) END, COALESCE(IF(venue = 0, xr + 0.5 * (1 - feeb_10 / 1e4)), 1e18)) / 0.5), rn) FILTER (WHERE (rn > rnk_10 AND pm <= 0.30 * greatest(pmb_10, COALESCE(pkr_10, pmb_10)))) AS k10_70_v
    FROM b3
    GROUP BY 1, 2
),
fin AS (
    SELECT
        mint,
        iv,
        n,
        first_dt,
        first_after5_dt,
        last_dt,
        l_x,
        l_y,
        l_xr,
        l_venue,
        l_fee_bps,
        l_sm,
        e_x,
        e_y,
        e_xr,
        e_venue,
        e_fee_bps,
        e_sm,
        f_pm,
        f_runmax,
        f_maxpm,
        f_newb30,
        f_trades30,
        f_trades30_prev,
        f_buy30,
        f_sell30,
        f_nb_sell30,
        f_ins_exit,
        t50_dt,
        t50_v,
        t70_dt,
        t70_v,
        dead_dt,
        dead_sm,
        dead_rows,
        array_join(filter(ARRAY[
            IF(k1_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 1, 50, k1_50_dt, COALESCE(k1_50_v, -1))),
            IF(k1_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 1, 70, k1_70_dt, COALESCE(k1_70_v, -1))),
            IF(k2_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 2, 50, k2_50_dt, COALESCE(k2_50_v, -1))),
            IF(k2_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 2, 70, k2_70_dt, COALESCE(k2_70_v, -1))),
            IF(k3_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 3, 50, k3_50_dt, COALESCE(k3_50_v, -1))),
            IF(k3_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 3, 70, k3_70_dt, COALESCE(k3_70_v, -1))),
            IF(k4_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 4, 50, k4_50_dt, COALESCE(k4_50_v, -1))),
            IF(k4_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 4, 70, k4_70_dt, COALESCE(k4_70_v, -1))),
            IF(k5_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 5, 50, k5_50_dt, COALESCE(k5_50_v, -1))),
            IF(k5_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 5, 70, k5_70_dt, COALESCE(k5_70_v, -1))),
            IF(k6_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 6, 50, k6_50_dt, COALESCE(k6_50_v, -1))),
            IF(k6_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 6, 70, k6_70_dt, COALESCE(k6_70_v, -1))),
            IF(k7_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 7, 50, k7_50_dt, COALESCE(k7_50_v, -1))),
            IF(k7_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 7, 70, k7_70_dt, COALESCE(k7_70_v, -1))),
            IF(k8_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 8, 50, k8_50_dt, COALESCE(k8_50_v, -1))),
            IF(k8_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 8, 70, k8_70_dt, COALESCE(k8_70_v, -1))),
            IF(k9_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 9, 50, k9_50_dt, COALESCE(k9_50_v, -1))),
            IF(k9_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 9, 70, k9_70_dt, COALESCE(k9_70_v, -1))),
            IF(k10_50_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 10, 50, k10_50_dt, COALESCE(k10_50_v, -1))),
            IF(k10_70_dt IS NULL, NULL, format('%d,%d,%d,%.6f', 10, 70, k10_70_dt, COALESCE(k10_70_v, -1)))
        ], z -> z IS NOT NULL), ';') AS trig_new,
        (k0_50_dt IS DISTINCT FROM t50_dt OR k0_70_dt IS DISTINCT FROM t70_dt OR abs(COALESCE(k0_50_v, -9) - COALESCE(t50_v, -9)) > 1e-5 OR abs(COALESCE(k0_70_v, -9) - COALESCE(t70_v, -9)) > 1e-5) AS bad_k0,
        (k1_50_dt <= 300 OR k1_70_dt <= 300 OR k2_50_dt <= 900 OR k2_70_dt <= 900 OR k3_50_dt <= 1800 OR k3_70_dt <= 1800 OR k4_50_dt <= 3600 OR k4_70_dt <= 3600 OR k5_50_dt <= 7200 OR k5_70_dt <= 7200 OR k6_50_dt <= 14400 OR k6_70_dt <= 14400 OR k7_50_dt <= 28800 OR k7_70_dt <= 28800 OR k8_50_dt <= 86400 OR k8_70_dt <= 86400 OR k9_50_dt <= 259200 OR k9_70_dt <= 259200 OR k10_50_dt <= 604800 OR k10_70_dt <= 604800) AS bad_early,
        anom_any, x0, v0
    FROM (
        SELECT *,
            max(CASE WHEN iv = 0 THEN l_x END) OVER (PARTITION BY mint) AS x0,
            max(CASE WHEN iv = 0 THEN l_venue END) OVER (PARTITION BY mint) AS v0,
            bool_or(anom) OVER (PARTITION BY mint) AS anom_any
        FROM grp
    ) q
),
final AS (
    SELECT * FROM fin WHERE x0 IS NOT NULL AND NOT anom_any AND (x0 >= 30.5 OR v0 = 1)
),
direct AS (
    SELECT mint,
        COALESCE(min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN (CASE WHEN (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))),
                 max_by(sm, rn) FILTER (WHERE p), power(1 - max(efee) / 1e4, 2)) AS b50_direct,
        min_by(dt, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS d_ev_dt,
        min_by(rn, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS d_ev_rn,
        min_by(IF((p AND pm <= 0.50 * greatest(1.0, runmax_post)), 1, 0), rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS d_ev_is_trig,
        min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN (CASE WHEN (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE ((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS d_ev_v,
        count_if(((p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400))) AS d_n_ev,
        count_if(p) AS d_n_p,
        max(entry_rn) AS d_entry_rn,
        max_by(sm, rn) FILTER (WHERE p) AS d_last_sm
    FROM s7
    GROUP BY 1
),
pb AS (
    SELECT mint,
        COALESCE(min_by(CASE WHEN t50_dt IS NOT NULL AND (dead_dt IS NULL OR t50_dt <= dead_dt) THEN t50_v ELSE dead_sm END, iv)
                 FILTER (WHERE t50_dt IS NOT NULL OR dead_dt IS NOT NULL),
                 max_by(l_sm, iv) FILTER (WHERE l_sm IS NOT NULL)) AS b50_panel,
        array_join(array_agg(array_join(ARRAY[CAST(iv AS varchar), CAST(n AS varchar), COALESCE(CAST(first_dt AS varchar), 'NA'),
            COALESCE(CAST(last_dt AS varchar), 'NA'), COALESCE(CAST(t50_dt AS varchar), 'NA'), COALESCE(CAST(t50_v AS varchar), 'NA'),
            COALESCE(CAST(dead_dt AS varchar), 'NA'), COALESCE(CAST(dead_sm AS varchar), 'NA'), COALESCE(CAST(l_sm AS varchar), 'NA')], ':') ORDER BY iv), ' | ') AS buckets
    FROM final
    GROUP BY 1
)
-- 诊断输出：只列出面板 b50 与直接 b50 不一致的币。buckets 每段为 iv:n:first_dt:last_dt:t50_dt:t50_v:dead_dt:dead_sm:l_sm。
SELECT mint, b50_panel, b50_direct, d_ev_dt, d_ev_rn, d_ev_is_trig, d_ev_v, d_n_ev, d_n_p, d_entry_rn, d_last_sm, buckets
FROM pb JOIN direct USING (mint)
WHERE abs(b50_panel - b50_direct) > 1e-5 OR b50_panel IS NULL OR b50_direct IS NULL
ORDER BY mint
