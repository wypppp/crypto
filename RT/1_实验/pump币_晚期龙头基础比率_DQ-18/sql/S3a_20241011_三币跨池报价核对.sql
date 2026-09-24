-- DQ-18 第 1 步 / S3a：三枚 2024 知名币首次 $20m 的整点小时，按池拆价格与对手币。
-- 目的：核 v2 的跨池 VWAP 是否被异价池或非 SOL/稳定币报价污染；不算收益。
-- 已有 S2a 2024-10 执行 4.5625、S2b 2024-11 执行 4.8856 credits；
-- 本查询两月但只取三个小时，事前粗估 8–20 credits，建议单次上限 25；用户硬上限 50。
-- 每池×报价币一行；不做 LIMIT，因需看到所有池。预期几十行，勿在网页导出 CSV。

WITH signals(mint, hour_start) AS (
    VALUES
        ('CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump', TIMESTAMP '2024-10-13 01:00:00'),
        ('9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump', TIMESTAMP '2024-10-19 17:00:00'),
        ('2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump', TIMESTAMP '2024-11-02 16:00:00')
), trades AS (
    SELECT
        CASE
            WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) THEN token_bought_mint_address ELSE token_sold_mint_address END AS mint,
        block_time,
        project,
        project_program_id AS pool_id,
        amount_usd,
        CASE WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) AND token_sold_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) THEN 1 ELSE 0 END AS both_target,
        CASE WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) THEN token_bought_amount ELSE token_sold_amount END AS token_amount,
        CASE WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) THEN token_sold_mint_address ELSE token_bought_mint_address END AS quote_mint,
        CASE WHEN token_bought_mint_address IN (
                'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
                '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
                '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
            ) THEN token_sold_amount ELSE token_bought_amount END AS quote_amount
    FROM dex_solana.trades
    WHERE block_month IN (DATE '2024-10-01', DATE '2024-11-01')
      AND block_date IN (DATE '2024-10-13', DATE '2024-10-19', DATE '2024-11-02')
      AND (
          token_bought_mint_address IN (
              'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
              '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
              '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
          ) OR token_sold_mint_address IN (
              'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
              '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump',
              '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump'
          )
      )
), grouped AS (
    SELECT
        s.mint,
        s.hour_start,
        t.project,
        t.pool_id,
        t.quote_mint,
        COUNT(*) AS n_trades,
        SUM(t.both_target) AS n_both_target,
        COUNT_IF(t.amount_usd IS NULL OR t.amount_usd <= 0 OR t.token_amount IS NULL OR t.token_amount <= 0) AS n_bad_price,
        SUM(IF(t.amount_usd > 0 AND t.token_amount > 0, t.amount_usd, 0)) AS usd_volume,
        SUM(IF(t.amount_usd > 0 AND t.token_amount > 0, t.token_amount, 0)) AS token_volume,
        SUM(IF(t.token_amount > 0 AND t.quote_amount > 0, t.token_amount, 0)) AS raw_token_volume,
        SUM(IF(t.token_amount > 0 AND t.quote_amount > 0, t.quote_amount, 0)) AS quote_volume
    FROM signals s
    JOIN trades t ON t.mint = s.mint
       AND t.block_time >= s.hour_start
       AND t.block_time < s.hour_start + INTERVAL '1' HOUR
    GROUP BY 1, 2, 3, 4, 5
)
SELECT
    mint,
    hour_start,
    project,
    pool_id,
    quote_mint,
    n_trades,
    n_both_target,
    n_bad_price,
    usd_volume,
    token_volume,
    usd_volume / NULLIF(token_volume, 0) AS usd_per_token,
    quote_volume / NULLIF(raw_token_volume, 0) AS quote_per_token,
    usd_volume / NULLIF(SUM(usd_volume) OVER (PARTITION BY mint), 0) AS share_of_valid_usd_volume
FROM grouped
ORDER BY mint, usd_volume DESC, pool_id
