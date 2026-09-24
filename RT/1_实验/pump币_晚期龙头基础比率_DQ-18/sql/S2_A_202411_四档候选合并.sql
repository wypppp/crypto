-- DQ-18 第 2 步 A 段：2024-11 全部 pump 创建币，四档门槛一次枚举。
-- 同一次 dex_solana.trades 月分区扫描完成：原始换币量计价、创建人群、Mayhem、
-- 每个候选信号小时的报价覆盖。输出是“11 月内首个达标小时”，不是历史首次。
-- B 段查完整前史后才准标记“首次”、冻结抽样框。
-- CreateEvent 的 is_mayhem_mode 在第 1 步五个已知币上全为 NULL；NULL=未知，
-- 不得当成 false。Mayhem 的正例与总数须另行核 BondingCurve/CreateV2 语义。
-- 不计算信号后的收益、倍数，也不读取封存 cohort。
-- 单次执行硬上限 50 credits；此前只有少数已知币的月扫描费用，
-- 全月人群及 SOL 分钟价格联结的费用未知。请记录 query/execution ID、实耗、扫描量。
-- 结果行数未知，先不要网页导出 CSV；执行方经 API 先读 metadata/行数。
-- 若这条达到上限，不原样重跑；按日期分段，但保持同一套 SQL 口径。

WITH created AS (
    SELECT
        mint,
        MIN(evt_block_time) AS created_at,
        MIN_BY(is_mayhem_mode, evt_block_time) AS is_mayhem_mode,
        MIN_BY(token_program, evt_block_time) AS token_program
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date < DATE '2024-12-01'
    GROUP BY mint
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd, COUNT(*) AS n_price_rows
    FROM prices.usd
    WHERE blockchain = 'solana'
      AND symbol = 'SOL'
      AND minute >= TIMESTAMP '2024-11-01 00:00:00'
      AND minute < TIMESTAMP '2024-12-01 00:00:00'
    GROUP BY minute
), month_trades AS (
    SELECT
        block_time,
        amount_usd,
        token_bought_mint_address,
        token_sold_mint_address,
        token_bought_amount,
        token_sold_amount
    FROM dex_solana.trades
    WHERE block_month = DATE '2024-11-01'
      AND block_time >= TIMESTAMP '2024-11-01 00:00:00'
      AND block_time < TIMESTAMP '2024-12-01 00:00:00'
      AND token_bought_mint_address <> token_sold_mint_address
), pump_legs AS (
    SELECT
        c.mint,
        c.created_at,
        c.is_mayhem_mode,
        c.token_program,
        t.block_time,
        t.amount_usd AS dune_amount_usd_for_coverage_only,
        IF(t.token_bought_mint_address = c.mint,
           t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
        IF(t.token_bought_mint_address = c.mint,
           t.token_bought_amount, t.token_sold_amount) AS token_amount,
        IF(t.token_bought_mint_address = c.mint,
           t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM month_trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address,
                            t.token_sold_mint_address]) AS leg(mint)
    JOIN created c ON c.mint = leg.mint
    WHERE t.block_time >= c.created_at
), valued AS (
    SELECT
        l.*,
        CASE
            WHEN l.quote_mint = 'So11111111111111111111111111111111111111112'
                THEN l.quote_amount * s.sol_usd
            WHEN l.quote_mint IN (
                'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
                'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
            ) THEN l.quote_amount
            ELSE NULL
        END AS quote_usd,
        CASE
            WHEN l.quote_mint IN (
                'So11111111111111111111111111111111111111112',
                'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
                'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
            ) THEN TRUE ELSE FALSE
        END AS supported_quote,
        s.n_price_rows
    FROM pump_legs l
    LEFT JOIN sol_minute s
      ON l.quote_mint = 'So11111111111111111111111111111111111111112'
     AND s.minute = date_trunc('minute', l.block_time)
), hourly AS (
    SELECT
        mint,
        MIN(created_at) AS created_at,
        MAX_BY(is_mayhem_mode, created_at) AS is_mayhem_mode,
        MAX_BY(token_program, created_at) AS token_program,
        date_trunc('hour', block_time) AS hour_start,
        COUNT(*) AS n_all_trades,
        COUNT_IF(token_amount > 0 AND quote_usd > 0) AS n_price_trades,
        COUNT_IF(NOT supported_quote) AS n_excluded_quote_trades,
        COUNT_IF(supported_quote AND
            (token_amount IS NULL OR token_amount <= 0 OR quote_usd IS NULL OR quote_usd <= 0))
            AS n_bad_supported_quote_trades,
        COUNT_IF(quote_mint = 'So11111111111111111111111111111111111111112'
                 AND n_price_rows IS NULL) AS n_missing_sol_minute_price,
        COUNT_IF(quote_mint = 'So11111111111111111111111111111111111111112'
                 AND n_price_rows > 1) AS n_multi_sol_minute_price,
        COUNT_IF(NOT supported_quote AND
            (dune_amount_usd_for_coverage_only IS NULL OR dune_amount_usd_for_coverage_only <= 0))
            AS n_excluded_unknown_usd,
        SUM(IF(NOT supported_quote AND dune_amount_usd_for_coverage_only > 0,
               dune_amount_usd_for_coverage_only, 0)) AS excluded_dune_usd_proxy,
        SUM(IF(dune_amount_usd_for_coverage_only > 0,
               dune_amount_usd_for_coverage_only, 0)) AS all_dune_usd_proxy,
        SUM(IF(token_amount > 0 AND quote_usd > 0, token_amount, 0)) AS valid_token_volume,
        SUM(IF(token_amount > 0 AND quote_usd > 0, quote_usd, 0)) AS valid_usd_volume
    FROM valued
    GROUP BY mint, date_trunc('hour', block_time)
), priced_hours AS (
    SELECT *,
        1000000000.0 * valid_usd_volume / NULLIF(valid_token_volume, 0)
            AS platform_marketcap_usd
    FROM hourly
), thresholds(threshold_usd) AS (
    VALUES (1000000.0), (5000000.0), (20000000.0), (100000000.0)
), ranked AS (
    SELECT
        h.*,
        t.threshold_usd,
        ROW_NUMBER() OVER (
            PARTITION BY h.mint, t.threshold_usd ORDER BY h.hour_start
        ) AS rank_in_month
    FROM priced_hours h
    CROSS JOIN thresholds t
    WHERE h.platform_marketcap_usd >= t.threshold_usd
)
SELECT
    mint,
    threshold_usd,
    created_at,
    is_mayhem_mode,
    token_program,
    hour_start,
    hour_start + INTERVAL '1' HOUR AS signal_time,
    platform_marketcap_usd,
    n_all_trades,
    n_price_trades,
    n_excluded_quote_trades,
    n_bad_supported_quote_trades,
    n_missing_sol_minute_price,
    n_multi_sol_minute_price,
    n_excluded_unknown_usd,
    excluded_dune_usd_proxy,
    all_dune_usd_proxy,
    excluded_dune_usd_proxy / NULLIF(all_dune_usd_proxy, 0)
        AS excluded_share_of_dune_priced_volume_proxy,
    valid_usd_volume
FROM ranked
WHERE rank_in_month = 1
ORDER BY threshold_usd, mint
