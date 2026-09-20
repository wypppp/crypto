-- DQ-8A Gate 1 诊断：F2_dev 与 F3 面板 b50 不一致的 29 个币 + 仅在 F2 中的 5 个币。
-- 两条链：oix 升序（= F3 冻结口径）与 oix 降序（另一种并列次序）；tie_rows_oldkey = 旧排序键 (ts,venue,slot,txi,iix) 下的并列行数。
WITH
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        date_diff('day', DATE '2026-06-01', min(evt_block_date)) + 1 AS cday,
        max(quote_mint) AS quote_mint,
        max("user") AS dev,
        COALESCE(bool_or(CAST(is_mayhem_mode AS varchar) IN ('true', '1')), false) AS mayhem_create
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
      AND mint IN ('9WLBMMg94MiKw2CWgovDbgLE6fwgvx9dHJbnu3Bdpump','2ydoyUm8X69SYccAN8PwBr7BxZ7686AcWw75jZg9pdkk','GaoHm7AkGjSKKze8d27r7gqVqkJz2JpmdwDyUWnjpump','CpTVgtkuhFjVMbajQLFnPdXcnKoVPFip9TLfA9Sppump','d3h4TPUPSyDazpghK8NxLvnfgrQmHpGa4Baavg1pump','5wiDmEGwbYm2EzHgEPWY4ic1moiAoWumUsKP4uvEpump','HreiQ5rJW4RNEpoEcPEaZu1X9P7vGvFUGnMZZC42pump','ZELjsewnfCQukqtmbi8FiDVYQxpYnSrDThvDRa9pump','FtDnE82cajMe39XCiWgBFG66miTExy1cCbFr3gHupump','4RUygDZkg2K3EKSL9D6BEqvMS7wQn6vjK9YqfHeGpump','8rHCDi4Hib62NrHTiFN4LRvL5FesDH69ViXzJvkupump','7QCAkgQS3q8czp45az391i3o5Lp9AheDJph6EpjUpump','8Y3zV1ArfZxVm31vrKLYzG2fBPtb1WT8FvQrt6u9pump','HQCFyRNtCtb5yacgWp96EUjChQxG2GmdQCTufi2Hpump','A3TYWaJhGA6NEaNVrGdDPwyojmN4wSu7vzfxn1ezpump','e2uhKRLTEt1NZZ9pNGc84rV8f7uA6Uy6v67J4Yppump','4w1PenhAivvf4E4MGSqJQY3vey8tyM1kMDxuCzp1pump','FaxwVzsNZw7S2jfvYjPP5gXrh7hPbEZbDoLwLYWEpump','GTuyRqA8B8NcMZiezDnpaEsx1dr8xoLLLAJN7NPxpump','7W5vcEZFPR1sknTm5z2VhzVzJNnstbKQtUcwUX3dpump','9picvPsPa1wjRKWzAhssoHwuZKuyv9gUbbc7C9q8pump','EYz8Ha7wXUio3RjvhZjmYrWPqKCTCRYetkQTtN3zpump','D3qJKtNN44L5r3eFGDMATk1ut4L8mJMMbe9nxXxtpump','GZWCFUYLgAszKriDCwPtqyvtGjpdnLVKTbqRqUqxpump','HUJUzc79EZhuAhF79aH78DRbnP8y55gDSwebkPKMpump','5S4VFSNeW5CDBP9djPURAupDSBiM46Thu1bbn94pump','GnPnJvkeyEPpTK5dkSi3UwkmJHNmrK1BAGitoGhhpump','7xGcLFjPcrGvvf8Cxb4DXmGYh73fg6FDEMQv5ms4pump','3NSiYpEinqFNJv9Ccktm6zYYsRtTYwjQroKCm6nSpump','CsnC4hDZG8qVSH1tWVqjS28QMtZp7nJqGTGxPgaapump','7VSNppqnpC35TFj1Ci93QaWLqPer5NhcXpBcapb4ycki','n2ffG2QeKA9bvP5VCFGJ1szmYnd6SXowHF2ALCcJnCv','485PiQdzYZQi7kqGqNvX4suBXKooQQBUKdmFrWJFpump','FedJJBRC5UZny3zoLsz8myQVeXdWoorFzttvW7JBpump')
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
                WHERE evt_block_date BETWEEN DATE '2026-05-02' AND DATE '2026-06-07'
                GROUP BY 1
            ) l
            UNION ALL
            SELECT l.dev, l.mint, g.t, 0 AS is_launch, 1 AS is_grad
            FROM (
                SELECT mint, max("user") AS dev
                FROM pumpdotfun_solana.pump_evt_createevent
                WHERE evt_block_date BETWEEN DATE '2026-05-02' AND DATE '2026-06-07'
                GROUP BY 1
            ) l
            JOIN (
                SELECT mint, min(evt_block_time) AS t
                FROM pumpdotfun_solana.pump_evt_completeevent
                WHERE evt_block_date BETWEEN DATE '2026-05-02' AND DATE '2026-06-07'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
mig AS (
    SELECT mint, arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
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
        t.evt_outer_instruction_index AS oix,
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
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mp.mint, p.ts, 1 AS venue, p.slot, p.txi, p.iix, p.oix,
        p.qraw / power(10, mp.qd) AS x,
        p.braw / power(10, mp.bd) AS y,
        CAST(NULL AS DOUBLE) AS xr,
        p.fee_bps, p.fee_missing, false AS mayhem,
        p.usr, p.is_buy,
        p.sraw / power(10, mp.qd) AS sol_amt, p.traw / power(10, mp.bd) AS tok_amt, CAST(NULL AS boolean) AS outer_pump
    FROM (
        SELECT pool, ts, slot, txi, iix, oix, fee_bps, fee_missing, usr, is_buy, sraw, traw,
               COALESCE(lead(qraw) OVER (PARTITION BY pool ORDER BY slot, txi, oix, iix), qraw + dq) AS qraw,
               COALESCE(lead(braw) OVER (PARTITION BY pool ORDER BY slot, txi, oix, iix), braw + db) AS braw
        FROM (
            SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix, evt_outer_instruction_index AS oix,
                   CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
                   CAST(pool_base_token_reserves AS DOUBLE) AS braw,
                   CAST(quote_amount_in AS DOUBLE) - COALESCE(CAST(protocol_fee AS DOUBLE), 0) - COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS dq,
                   -CAST(base_amount_out AS DOUBLE) AS db,
                   COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                     + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
                   lp_fee_basis_points IS NULL AS fee_missing,
                   "user" AS usr, true AS is_buy, CAST(quote_amount_in AS DOUBLE) AS sraw, CAST(base_amount_out AS DOUBLE) AS traw
            FROM pumpdotfun_solana.pump_amm_evt_buyevent
            WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
              AND pool IN (SELECT pool FROM mapping WHERE pool IS NOT NULL)
            UNION ALL
            SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix, evt_outer_instruction_index AS oix,
                   CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
                   CAST(pool_base_token_reserves AS DOUBLE) AS braw,
                   -(CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)) AS dq,
                   CAST(base_amount_in AS DOUBLE) AS db,
                   COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                     + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
                   lp_fee_basis_points IS NULL AS fee_missing,
                   "user" AS usr, false AS is_buy, CAST(quote_amount_out AS DOUBLE) AS sraw, CAST(base_amount_in AS DOUBLE) AS traw
            FROM pumpdotfun_solana.pump_amm_evt_sellevent
            WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
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
        LEAST(c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY, TIMESTAMP '2026-07-08 23:59:59 UTC') AS t_end,
        date_diff('second', c.created_at + INTERVAL '30' MINUTE, s.ts) AS dt,
        row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.oix, s.iix) AS rn
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
cohort_d AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        date_diff('day', DATE '2026-06-01', min(evt_block_date)) + 1 AS cday,
        max(quote_mint) AS quote_mint,
        max("user") AS dev,
        COALESCE(bool_or(CAST(is_mayhem_mode AS varchar) IN ('true', '1')), false) AS mayhem_create
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
    GROUP BY 1
),
sol_cohort_d AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort_d
    WHERE (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
      AND mint IN ('9WLBMMg94MiKw2CWgovDbgLE6fwgvx9dHJbnu3Bdpump','2ydoyUm8X69SYccAN8PwBr7BxZ7686AcWw75jZg9pdkk','GaoHm7AkGjSKKze8d27r7gqVqkJz2JpmdwDyUWnjpump','CpTVgtkuhFjVMbajQLFnPdXcnKoVPFip9TLfA9Sppump','d3h4TPUPSyDazpghK8NxLvnfgrQmHpGa4Baavg1pump','5wiDmEGwbYm2EzHgEPWY4ic1moiAoWumUsKP4uvEpump','HreiQ5rJW4RNEpoEcPEaZu1X9P7vGvFUGnMZZC42pump','ZELjsewnfCQukqtmbi8FiDVYQxpYnSrDThvDRa9pump','FtDnE82cajMe39XCiWgBFG66miTExy1cCbFr3gHupump','4RUygDZkg2K3EKSL9D6BEqvMS7wQn6vjK9YqfHeGpump','8rHCDi4Hib62NrHTiFN4LRvL5FesDH69ViXzJvkupump','7QCAkgQS3q8czp45az391i3o5Lp9AheDJph6EpjUpump','8Y3zV1ArfZxVm31vrKLYzG2fBPtb1WT8FvQrt6u9pump','HQCFyRNtCtb5yacgWp96EUjChQxG2GmdQCTufi2Hpump','A3TYWaJhGA6NEaNVrGdDPwyojmN4wSu7vzfxn1ezpump','e2uhKRLTEt1NZZ9pNGc84rV8f7uA6Uy6v67J4Yppump','4w1PenhAivvf4E4MGSqJQY3vey8tyM1kMDxuCzp1pump','FaxwVzsNZw7S2jfvYjPP5gXrh7hPbEZbDoLwLYWEpump','GTuyRqA8B8NcMZiezDnpaEsx1dr8xoLLLAJN7NPxpump','7W5vcEZFPR1sknTm5z2VhzVzJNnstbKQtUcwUX3dpump','9picvPsPa1wjRKWzAhssoHwuZKuyv9gUbbc7C9q8pump','EYz8Ha7wXUio3RjvhZjmYrWPqKCTCRYetkQTtN3zpump','D3qJKtNN44L5r3eFGDMATk1ut4L8mJMMbe9nxXxtpump','GZWCFUYLgAszKriDCwPtqyvtGjpdnLVKTbqRqUqxpump','HUJUzc79EZhuAhF79aH78DRbnP8y55gDSwebkPKMpump','5S4VFSNeW5CDBP9djPURAupDSBiM46Thu1bbn94pump','GnPnJvkeyEPpTK5dkSi3UwkmJHNmrK1BAGitoGhhpump','7xGcLFjPcrGvvf8Cxb4DXmGYh73fg6FDEMQv5ms4pump','3NSiYpEinqFNJv9Ccktm6zYYsRtTYwjQroKCm6nSpump','CsnC4hDZG8qVSH1tWVqjS28QMtZp7nJqGTGxPgaapump','7VSNppqnpC35TFj1Ci93QaWLqPer5NhcXpBcapb4ycki','n2ffG2QeKA9bvP5VCFGJ1szmYnd6SXowHF2ALCcJnCv','485PiQdzYZQi7kqGqNvX4suBXKooQQBUKdmFrWJFpump','FedJJBRC5UZny3zoLsz8myQVeXdWoorFzttvW7JBpump')
),
dev_hist_d AS (
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
                WHERE evt_block_date BETWEEN DATE '2026-05-02' AND DATE '2026-06-07'
                GROUP BY 1
            ) l
            UNION ALL
            SELECT l.dev, l.mint, g.t, 0 AS is_launch, 1 AS is_grad
            FROM (
                SELECT mint, max("user") AS dev
                FROM pumpdotfun_solana.pump_evt_createevent
                WHERE evt_block_date BETWEEN DATE '2026-05-02' AND DATE '2026-06-07'
                GROUP BY 1
            ) l
            JOIN (
                SELECT mint, min(evt_block_time) AS t
                FROM pumpdotfun_solana.pump_evt_completeevent
                WHERE evt_block_date BETWEEN DATE '2026-05-02' AND DATE '2026-06-07'
                GROUP BY 1
            ) g ON g.mint = l.mint
        ) ev
    ) cum
    WHERE is_launch = 1
      AND mint IN (SELECT mint FROM sol_cohort_d)
),
comp_d AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
      AND mint IN (SELECT mint FROM sol_cohort_d)
    GROUP BY 1
),
mig_d AS (
    SELECT mint, arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
      AND mint IN (SELECT mint FROM sol_cohort_d)
    GROUP BY 1
),
cp_d AS (
    SELECT
        pool,
        max(base_mint) AS base_mint,
        max(base_mint_decimals) AS bd,
        max(quote_mint_decimals) AS qd,
        COALESCE(bool_or(evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0), false) AS by_pump
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
      AND base_mint IN (SELECT mint FROM sol_cohort_d)
    GROUP BY 1
),
fb_d AS (
    SELECT base_mint AS mint, min(pool) AS pool FROM cp_d WHERE by_pump GROUP BY 1
),
mapping_d AS (
    SELECT
        s.mint,
        COALESCE(m.pool, f.pool) AS pool,
        c.bd,
        c.qd
    FROM sol_cohort_d s
    LEFT JOIN mig_d m ON m.mint = s.mint
    LEFT JOIN fb_d f ON f.mint = s.mint
    LEFT JOIN cp_d c ON c.pool = COALESCE(m.pool, f.pool)
),
-- ===== 重扫描链：以下每一层只被下一层引用一次 =====
states_d AS (
    SELECT
        t.mint,
        t.evt_block_time AS ts,
        0 AS venue,
        t.evt_block_slot AS slot,
        t.evt_tx_index AS txi,
        t.evt_inner_instruction_index AS iix,
        t.evt_outer_instruction_index AS oix,
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
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
      AND t.mint IN (SELECT mint FROM sol_cohort_d)
    UNION ALL
    SELECT
        mp.mint, p.ts, 1 AS venue, p.slot, p.txi, p.iix, p.oix,
        p.qraw / power(10, mp.qd) AS x,
        p.braw / power(10, mp.bd) AS y,
        CAST(NULL AS DOUBLE) AS xr,
        p.fee_bps, p.fee_missing, false AS mayhem,
        p.usr, p.is_buy,
        p.sraw / power(10, mp.qd) AS sol_amt, p.traw / power(10, mp.bd) AS tok_amt, CAST(NULL AS boolean) AS outer_pump
    FROM (
        SELECT pool, ts, slot, txi, iix, oix, fee_bps, fee_missing, usr, is_buy, sraw, traw,
               COALESCE(lead(qraw) OVER (PARTITION BY pool ORDER BY slot, txi, oix DESC, iix), qraw + dq) AS qraw,
               COALESCE(lead(braw) OVER (PARTITION BY pool ORDER BY slot, txi, oix DESC, iix), braw + db) AS braw
        FROM (
            SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix, evt_outer_instruction_index AS oix,
                   CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
                   CAST(pool_base_token_reserves AS DOUBLE) AS braw,
                   CAST(quote_amount_in AS DOUBLE) - COALESCE(CAST(protocol_fee AS DOUBLE), 0) - COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS dq,
                   -CAST(base_amount_out AS DOUBLE) AS db,
                   COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                     + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
                   lp_fee_basis_points IS NULL AS fee_missing,
                   "user" AS usr, true AS is_buy, CAST(quote_amount_in AS DOUBLE) AS sraw, CAST(base_amount_out AS DOUBLE) AS traw
            FROM pumpdotfun_solana.pump_amm_evt_buyevent
            WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
              AND pool IN (SELECT pool FROM mapping_d WHERE pool IS NOT NULL)
            UNION ALL
            SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_inner_instruction_index AS iix, evt_outer_instruction_index AS oix,
                   CAST(pool_quote_token_reserves AS DOUBLE) AS qraw,
                   CAST(pool_base_token_reserves AS DOUBLE) AS braw,
                   -(CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)) AS dq,
                   CAST(base_amount_in AS DOUBLE) AS db,
                   COALESCE(CAST(lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(protocol_fee_basis_points AS DOUBLE), 0)
                     + COALESCE(CAST(coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
                   lp_fee_basis_points IS NULL AS fee_missing,
                   "user" AS usr, false AS is_buy, CAST(quote_amount_out AS DOUBLE) AS sraw, CAST(base_amount_in AS DOUBLE) AS traw
            FROM pumpdotfun_solana.pump_amm_evt_sellevent
            WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-08'
              AND pool IN (SELECT pool FROM mapping_d WHERE pool IS NOT NULL)
        ) e
    ) p
    JOIN mapping_d mp ON mp.pool = p.pool
),
s1_d AS (
    SELECT
        s.*,
        c.created_slot,
        c.dev,
        c.created_at + INTERVAL '30' MINUTE AS t_entry,
        LEAST(c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY, TIMESTAMP '2026-07-08 23:59:59 UTC') AS t_end,
        date_diff('second', c.created_at + INTERVAL '30' MINUTE, s.ts) AS dt,
        row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.oix DESC, s.iix) AS rn
    FROM states_d s
    JOIN sol_cohort_d c ON c.mint = s.mint
    WHERE s.ts <= c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY
      AND s.x > 0 AND s.y > 0
),
s2_d AS (
    SELECT
        *,
        CAST(floor(dt / 86400.0) AS integer) AS d,
        max(CASE WHEN dt <= 0 THEN rn END) OVER (PARTITION BY mint) AS entry_rn
    FROM s1_d
),
s3_d AS (
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
    FROM s2_d
),
s4_d AS (
    SELECT
        *,
        ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4)) AS tok,
        (x / y) / (ex / ey) AS pm,
        usr IS NOT NULL AND u_rn1 = 1 AS u_first,
        rank() OVER (PARTITION BY mint ORDER BY CASE WHEN usr IS NOT NULL AND u_rn1 = 1 AND u_net_pre > 0 THEN u_net_pre END DESC NULLS LAST) AS u_rank,
        usr IS NOT NULL AND (usr = dev OR u_first_buy_slot = created_slot) AS ins,
        usr IS NOT NULL AND COALESCE(is_buy, false) AND rn = u_first_buy_rn AS is_newb,
        usr IS NOT NULL AND NOT COALESCE(is_buy, true) AND (u_first_buy_rn IS NULL OR u_first_buy_rn > rn) AS is_nb_sell
    FROM s3_d
),
s5_d AS (
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
    FROM s4_d
),
s6_d AS (
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
    FROM s5_d
),
s7_d AS (
    SELECT
        *,
        min(CASE WHEN is_close AND pm <= 0.5 * greatest(1.0, runmax_close) THEN d END) OVER (PARTITION BY mint) AS d_trig,
        min(CASE WHEN p AND pm >= 2 THEN rn END) OVER (PARTITION BY mint) AS tp2_rn,
        min(CASE WHEN p AND pm >= 3 THEN rn END) OVER (PARTITION BY mint) AS tp3_rn,
        min(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN rn END) OVER (PARTITION BY mint) AS dd_rn
    FROM s6_d
),
asc_s AS (
    SELECT mint,
        COALESCE(min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN (CASE WHEN (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)),
                 max_by(sm, rn) FILTER (WHERE p), power(1 - max(efee) / 1e4, 2)) AS b50,
        max(CASE WHEN rn = entry_rn THEN x END) AS x0, max(CASE WHEN rn = entry_rn THEN venue END) AS v0,
        bool_or(venue = 0 AND x > 120) AS anom, count_if(p) AS n_p, count(*) AS n_rows,
        count_if(tie_n > 1) AS tie_rows_oldkey, count_if(tie_n > 1 AND p) AS tie_rows_post
    FROM (SELECT *, count(*) OVER (PARTITION BY mint, ts, venue, slot, txi, iix) AS tie_n FROM s7) z
    GROUP BY 1
),
desc_s AS (
    SELECT mint,
        COALESCE(min_by(CASE WHEN (p AND pm <= 0.50 * greatest(1.0, runmax_post)) THEN (CASE WHEN (lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5) THEN lead_sm ELSE sm END) ELSE sm END, rn) FILTER (WHERE (p AND pm <= 0.50 * greatest(1.0, runmax_post)) OR (rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)),
                 max_by(sm, rn) FILTER (WHERE p), power(1 - max(efee) / 1e4, 2)) AS b50,
        max(CASE WHEN rn = entry_rn THEN x END) AS x0, max(CASE WHEN rn = entry_rn THEN venue END) AS v0,
        bool_or(venue = 0 AND x > 120) AS anom, count_if(p) AS n_p, count(*) AS n_rows,
        count_if(tie_n > 1) AS tie_rows_oldkey, count_if(tie_n > 1 AND p) AS tie_rows_post
    FROM (SELECT *, count(*) OVER (PARTITION BY mint, ts, venue, slot, txi, iix) AS tie_n FROM s7_d) z
    GROUP BY 1
)
SELECT a.mint, round(a.b50, 6) AS b50_asc, round(d.b50, 6) AS b50_desc, round(a.x0, 4) AS x0_asc, round(d.x0, 4) AS x0_desc,
       a.v0 AS v0_asc, d.v0 AS v0_desc, a.anom AS anom_asc, d.anom AS anom_desc, a.n_p, a.n_rows, a.tie_rows_oldkey, a.tie_rows_post
FROM asc_s a FULL JOIN desc_s d ON a.mint = d.mint
ORDER BY a.mint