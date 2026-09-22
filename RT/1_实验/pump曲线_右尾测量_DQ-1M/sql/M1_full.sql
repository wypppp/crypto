-- DQ-1M · M1（正式版）：cohort 逐 mint 测量。依据卡 v1.2（sha da772bf4…）。
-- 由 dq1m/sql/build_m1.py 从同一模板渲染；冒烟版与正式版只有日期和末尾输出不同。
-- cohort 创建日 2026-06-01 ~ 2026-06-07；行情扫描 2026-06-01 ~ 2026-08-06。
-- 所有分区过滤都写成日期字面量，保证分区裁剪。不要改成与参数表 JOIN。
--
-- 结构说明：Trino 不物化 CTE，重扫描（成交表 + 池事件）只允许沿 states → s1 → … → agg 单向引用一次，
-- 否则 67 天扫描会被重复计费。cohort / 映射等小表允许多次引用。
--
-- 实现口径（卡未写死、此处冻结）：
--  1) 状态 = 事件报告的储备原样使用。曲线用虚拟储备（lamports/1e9、代币/1e6）；
--     PumpSwap 用池储备，按建池事件的小数位逐池换算。若池事件报告的是交易前储备，
--     相当于"上一笔之后"的状态，对各口径估值只差一笔。
--  2) 买卖都按恒定乘积 x·y=k；费率取该状态事件上各费率字段之和，字段缺失按 0 并置标志位 256。
--  3) 曲线上卖出所得不超过该状态的 real_sol_reserves。
--  4) 入场时刻 = 创建 + 30 分钟；入场状态 = 该时刻及之前最后一个状态（可能已在池上，置标志位 1024）。
--  5) "日" = 自入场时刻起每 86,400 秒一段。各口径含义：ms_* 为该口径内最高价 ÷ 入场价（零规模事后代理），
--     hv_* 为持有到该口径、按口径内最后一个状态卖出固定持仓所得 ÷ 0.5 SOL。
--  6) T50：某段最后一个状态的价格倍数 ≤ 0.5 × max(1, 截至本段的各段收盘倍数最大值) 即触发；
--     在触发段之后的第一个状态卖出，之后再无状态则按最后一个状态卖出；未触发按 60 天内最后一个状态卖出。
--  7) 入场后没有任何新状态：持有价值按 (1 − 入场费率)² 计（买入后立即卖回）。
--
-- flags 位：1 非 SOL 计价（排除）｜2 无法入场｜4 已毕业｜8 池来自迁移事件｜16 池来自建池事件兜底
--          32 池小数位未知｜64 曲线虚拟 SOL 储备 >120｜128 mayhem｜256 入场费率字段缺失
--          512 已毕业但无池状态（退出不可行）｜1024 入场状态已在池上
WITH
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        date_diff('day', DATE '2026-06-01', min(evt_block_date)) + 1 AS cday,
        max(quote_mint) AS quote_mint,
        COALESCE(bool_or(CAST(is_mayhem_mode AS varchar) IN ('true', '1')), false) AS mayhem_create
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at
    FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-08-06'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
mig AS (
    SELECT mint, arbitrary(pool) AS pool, count(DISTINCT pool) AS n_pools
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-08-06'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-08-06'
      AND base_mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
fb AS (
    SELECT base_mint AS mint, min(pool) AS pool
    FROM cp
    WHERE by_pump
    GROUP BY 1
),
mapping AS (
    SELECT
        s.mint,
        COALESCE(m.pool, f.pool) AS pool,
        CASE WHEN m.pool IS NOT NULL THEN 'migration_event'
             WHEN f.pool IS NOT NULL THEN 'createpool_fallback' END AS pool_source,
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
        COALESCE(CAST(t.mayhem_mode AS varchar) IN ('true', '1'), false) AS mayhem
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-08-06'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mp.mint, p.ts, 1 AS venue, p.slot, p.txi, p.iix,
        p.qraw / power(10, mp.qd) AS x,
        p.braw / power(10, mp.bd) AS y,
        CAST(NULL AS DOUBLE) AS xr,
        p.fee_bps, p.fee_missing, false AS mayhem
    FROM (
        SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix,
               CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
               CAST(pool_base_token_reserves AS DOUBLE) AS braw,
               COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                 + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
               lp_fee_basis_points IS NULL AS fee_missing
        FROM pumpdotfun_solana.pump_amm_evt_buyevent
        WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-08-06'
          AND pool IN (SELECT pool FROM mapping WHERE pool IS NOT NULL)
        UNION ALL
        SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix,
               CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
               CAST(pool_base_token_reserves AS DOUBLE) AS braw,
               COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                 + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
               lp_fee_basis_points IS NULL AS fee_missing
        FROM pumpdotfun_solana.pump_amm_evt_sellevent
        WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-08-06'
          AND pool IN (SELECT pool FROM mapping WHERE pool IS NOT NULL)
    ) p
    JOIN mapping mp ON mp.pool = p.pool
),
s1 AS (
    SELECT
        s.*,
        c.created_at + INTERVAL '30' MINUTE AS t_entry,
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
        rn > entry_rn AS p,
        max(CASE WHEN rn = entry_rn THEN x END) OVER (PARTITION BY mint) AS ex,
        max(CASE WHEN rn = entry_rn THEN y END) OVER (PARTITION BY mint) AS ey,
        max(CASE WHEN rn = entry_rn THEN fee_bps END) OVER (PARTITION BY mint) AS efee,
        COALESCE(bool_or(CASE WHEN rn = entry_rn THEN fee_missing END) OVER (PARTITION BY mint), false) AS efee_missing,
        max(CASE WHEN rn = entry_rn THEN venue END) OVER (PARTITION BY mint) AS evenue
    FROM s2
),
s4 AS (
    SELECT
        *,
        ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4)) AS tok,
        (x / y) / (ex / ey) AS pm
    FROM s3
),
s5 AS (
    SELECT
        *,
        LEAST((x - x * y / (y + tok)) * (1 - fee_bps / 1e4), COALESCE(IF(venue = 0, xr), 1e18)) / 0.5 AS sm,
        p AND rn = max(CASE WHEN p THEN rn END) OVER (PARTITION BY mint, d) AS is_close
    FROM s4
),
s6 AS (
    SELECT
        *,
        max(CASE WHEN is_close THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_close
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
        bool_or(efee_missing) AS efee_missing,
        max(evenue) AS evenue,
        bool_or(venue = 0 AND x > 120) AS anomaly,
        bool_or(mayhem) AS mayhem_trade,
        bool_or(venue = 1) AS has_pool_state,
        max(pm) FILTER (WHERE p AND dt <= 7200) AS ms_2h,
        max(pm) FILTER (WHERE p AND dt <= 86400) AS ms_24h,
        max(pm) FILTER (WHERE p AND dt <= 604800) AS ms_7d,
        max(pm) FILTER (WHERE p AND dt <= 2592000) AS ms_30d,
        max(pm) FILTER (WHERE p) AS ms_60d,
        max_by(sm, rn) FILTER (WHERE p AND dt <= 7200) AS hv_2h,
        max_by(sm, rn) FILTER (WHERE p AND dt <= 86400) AS hv_24h,
        max_by(sm, rn) FILTER (WHERE p AND dt <= 604800) AS hv_7d,
        max_by(sm, rn) FILTER (WHERE p AND dt <= 2592000) AS hv_30d,
        max_by(sm, rn) FILTER (WHERE p) AS hv_60d,
        max(dt) FILTER (WHERE p) AS last_dt,
        max(d_trig) AS d_trig,
        min_by(sm, rn) FILTER (WHERE p AND d > d_trig) AS sm_after,
        min_by(x, rn) FILTER (WHERE p AND d > d_trig) AS x_after,
        max_by(sm, rn) FILTER (WHERE p) AS sm_last,
        max_by(x, rn) FILTER (WHERE p) AS x_last
    FROM s7
    GROUP BY 1
),
final AS (
    SELECT
        c.mint,
        c.cday,
          (CASE WHEN s.mint IS NULL THEN 1 ELSE 0 END)
        + (CASE WHEN s.mint IS NOT NULL AND a.entry_rn IS NULL THEN 2 ELSE 0 END)
        + (CASE WHEN co.mint IS NOT NULL THEN 4 ELSE 0 END)
        + (CASE WHEN mp.pool_source = 'migration_event' THEN 8 ELSE 0 END)
        + (CASE WHEN mp.pool_source = 'createpool_fallback' THEN 16 ELSE 0 END)
        + (CASE WHEN mp.pool IS NOT NULL AND (mp.bd IS NULL OR mp.qd IS NULL) THEN 32 ELSE 0 END)
        + (CASE WHEN a.anomaly THEN 64 ELSE 0 END)
        + (CASE WHEN c.mayhem_create OR a.mayhem_trade THEN 128 ELSE 0 END)
        + (CASE WHEN a.efee_missing THEN 256 ELSE 0 END)
        + (CASE WHEN co.mint IS NOT NULL AND NOT COALESCE(a.has_pool_state, false) THEN 512 ELSE 0 END)
        + (CASE WHEN a.evenue = 1 THEN 1024 ELSE 0 END) AS flags,
        round(a.ex, 3) AS entry_x_sol,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.ms_2h, 1.0)), 6) AS ms_2h,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.ms_24h, 1.0)), 6) AS ms_24h,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.ms_7d, 1.0)), 6) AS ms_7d,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.ms_30d, 1.0)), 6) AS ms_30d,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.ms_60d, 1.0)), 6) AS ms_60d,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.hv_2h, power(1 - a.efee / 1e4, 2))), 6) AS hv_2h,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.hv_24h, power(1 - a.efee / 1e4, 2))), 6) AS hv_24h,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.hv_7d, power(1 - a.efee / 1e4, 2))), 6) AS hv_7d,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.hv_30d, power(1 - a.efee / 1e4, 2))), 6) AS hv_30d,
        round(IF(a.entry_rn IS NOT NULL, COALESCE(a.hv_60d, power(1 - a.efee / 1e4, 2))), 6) AS hv_60d,
        round(IF(a.entry_rn IS NOT NULL,
                 CASE WHEN a.d_trig IS NULL THEN COALESCE(a.sm_last, power(1 - a.efee / 1e4, 2))
                      ELSE COALESCE(a.sm_after, a.sm_last) END), 6) AS mpi_t50,
        a.d_trig AS t50_day,
        round(CASE WHEN a.d_trig IS NULL THEN a.x_last ELSE COALESCE(a.x_after, a.x_last) END, 3) AS exit_x_sol,
        a.last_dt
    FROM cohort c
    LEFT JOIN sol_cohort s ON s.mint = c.mint
    LEFT JOIN agg a ON a.mint = c.mint
    LEFT JOIN comp co ON co.mint = c.mint
    LEFT JOIN mapping mp ON mp.mint = c.mint
)
-- 正式版输出：每个 cohort mint 一行（含非 SOL 计价与无法入场的币，用于分母分解）
-- 结果行数约 20 万。请在网页下载 CSV；不要用 API 读取（API 按数据点计费，远高于 CSV 下载）。
SELECT *
FROM final
ORDER BY cday, mint
