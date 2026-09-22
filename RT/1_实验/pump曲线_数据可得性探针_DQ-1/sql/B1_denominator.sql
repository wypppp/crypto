-- DQ-1 · B1：抽样日的发行分母——创建事件 vs 创建调用，当日及次日有无成交，创建时初始储备与单位
-- 创建只取 6 个抽样日；成交取抽样日及次日，并且只限这些日子创建的 mint。不读取价格结局。
WITH
ce AS (
    SELECT
        evt_block_date AS day,
        mint,
        min(evt_block_time) AS created_at,
        count(*) AS n_rows,
        max(CAST(virtual_sol_reserves AS DOUBLE)) AS c_vsr,
        max(CAST(virtual_token_reserves AS DOUBLE)) AS c_vtr,
        max(CAST(real_token_reserves AS DOUBLE)) AS c_rtr,
        max(CAST(token_total_supply AS DOUBLE)) AS c_supply,
        max(CAST(virtual_quote_reserves AS DOUBLE)) AS c_vqr,
        max(quote_mint) AS c_quote_mint,
        max(token_program) AS c_token_program
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date IN (DATE '2024-03-01', DATE '2024-09-01', DATE '2025-03-01',
                             DATE '2025-09-01', DATE '2026-03-01', DATE '2026-09-01')
    GROUP BY 1, 2
),
cc AS (
    SELECT call_block_date AS day, account_mint AS mint, 'create' AS via
    FROM pumpdotfun_solana.pump_call_create
    WHERE call_block_date IN (DATE '2024-03-01', DATE '2024-09-01', DATE '2025-03-01',
                              DATE '2025-09-01', DATE '2026-03-01', DATE '2026-09-01')
    UNION ALL
    SELECT call_block_date AS day, account_mint AS mint, 'create_v2' AS via
    FROM pumpdotfun_solana.pump_call_create_v2
    WHERE call_block_date IN (DATE '2024-03-01', DATE '2024-09-01', DATE '2025-03-01',
                              DATE '2025-09-01', DATE '2026-03-01', DATE '2026-09-01')
),
cc_mints AS (
    SELECT day, mint, count(*) AS n_calls, max(via) AS via_max, min(via) AS via_min
    FROM cc
    GROUP BY 1, 2
),
u AS (
    SELECT
        COALESCE(ce.day, cc_mints.day) AS day,
        COALESCE(ce.mint, cc_mints.mint) AS mint,
        ce.mint IS NOT NULL AS in_event,
        cc_mints.mint IS NOT NULL AS in_call,
        cc_mints.via_min, cc_mints.via_max,
        ce.created_at, ce.n_rows, ce.c_vsr, ce.c_vtr, ce.c_rtr, ce.c_supply, ce.c_vqr,
        ce.c_quote_mint, ce.c_token_program
    FROM ce
    FULL OUTER JOIN cc_mints
        ON ce.day = cc_mints.day AND ce.mint = cc_mints.mint
),
tr AS (
    SELECT mint, min(evt_block_time) AS first_trade_at, count(*) AS n_trades
    FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE evt_block_date IN (DATE '2024-03-01', DATE '2024-03-02', DATE '2024-09-01', DATE '2024-09-02',
                             DATE '2025-03-01', DATE '2025-03-02', DATE '2025-09-01', DATE '2025-09-02',
                             DATE '2026-03-01', DATE '2026-03-02', DATE '2026-09-01', DATE '2026-09-02')
      AND mint IN (SELECT mint FROM u)
    GROUP BY 1
)
SELECT
    u.day,
    count(*) AS mints_union,
    count_if(in_event) AS mints_createevent,
    count_if(in_call) AS mints_createcall,
    count_if(in_event AND NOT in_call) AS event_only,
    count_if(in_call AND NOT in_event) AS call_only,
    count_if(via_min = 'create' AND via_max = 'create') AS via_create_only,
    count_if(via_min = 'create_v2' AND via_max = 'create_v2') AS via_create_v2_only,
    count_if(n_rows > 1) AS mints_with_dup_createevent,
    count_if(t.mint IS NULL) AS mints_no_trade_day_or_next,
    count_if(t.mint IS NOT NULL) AS mints_with_trade,
    count_if(t.first_trade_at IS NOT NULL AND created_at IS NOT NULL
             AND t.first_trade_at <= created_at) AS first_trade_not_after_create_time,
    approx_percentile(t.n_trades, 0.5) AS trades_per_traded_mint_p50,
    count(c_vsr) AS n_create_vsr,
    count(c_vqr) AS n_create_vqr,
    count(c_quote_mint) AS n_create_quote_mint,
    min(c_vsr) / 1e9 AS create_vsr_min_div1e9,
    approx_percentile(c_vsr, 0.5) / 1e9 AS create_vsr_p50_div1e9,
    max(c_vsr) / 1e9 AS create_vsr_max_div1e9,
    approx_percentile(c_vtr, 0.5) / 1e6 AS create_vtr_p50_div1e6,
    approx_percentile(c_rtr, 0.5) / 1e6 AS create_rtr_p50_div1e6,
    approx_percentile(c_supply, 0.5) / 1e6 AS create_supply_p50_div1e6,
    approx_percentile(c_vqr, 0.5) AS create_vqr_p50_raw,
    array_join(slice(array_agg(DISTINCT c_quote_mint), 1, 5), ',') AS create_quote_mints,
    array_join(slice(array_agg(DISTINCT c_token_program), 1, 3), ',') AS token_programs
FROM u
LEFT JOIN tr t ON t.mint = u.mint
GROUP BY 1
ORDER BY 1
