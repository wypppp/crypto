/* DQ-21 S0 v1.1 — A/B 开发期事件时点机会普查。
   v1.1 在任何 Dune 执行前取代 v1：补全 PumpSwap base=wSOL 的反向池，
   按 slot/tx/instruction 排序同秒事件，并使用已经链上对账的 AMM 金额/交易后储备口径；
   研究问题、总体、抽样与结果权限不变。
   仅 2026-06-01～06-14 创建的 SOL 计价 pump 币；不读取 06-15 起创建的封存 cohort。
   一次扫描成交路径，输出：全部可执行 10x 右尾 + 固定哈希 2% 子队列 + R0 已看过币。
   本查询不包含资金关系，不是收益检验。执行与取回成本上限见 v1.1 执行更正。 */
WITH
r0_seen(mint) AS (
    SELECT mint FROM (VALUES
        /* 由 sample.csv 在冻结时生成；空值占位会在运行前生成脚本中替换。 */
        ('12JPYuF5tvXbCPy7KLmEoqB53Mbpxre2L6yCteXEpump'),
        ('28ZB8XufMp87CAwBVRvo1dHGicVB6CyMysryqY6qpump'),
        ('2XQXAnHFoh92B95hribj4reS1o4LwpyaKgFXmgWQpump'),
        ('2cgAW8un1eE2xN99PTs4NJyFYXA4pzqUEQTJbiuowgcn'),
        ('2dJniDEAGCG7zWKseCkyrML3W23WLjDf1CGxpNv3pump'),
        ('2qhwsQpTspqfdtTa2Yrox98kwam7vkbZNUabsLZ5pump'),
        ('2r9x15QN6obFdUPGKmv98x99N4PAYKsL7xg8Ug2Spump'),
        ('2sUsARJsNq6tM3Z4nas9Todu6auLL47e4utynsdwpump'),
        ('35Ki5P8TWL6VwhCXJ3RZMQb1HKV3xfSfiqjtYBBapump'),
        ('3757xRe9ejGDXNFbwNyM64KLX1fkf2jgyHAunZfspump'),
        ('37pTLREQQonabNbVYvsrwrmBj5wT9LqxKA6nUzEYpump'),
        ('3EuefWfzbkXoE6YSxKJLzn8M7gWrKLW65LDTTEjUpump'),
        ('3FDvp4d7RVqU1Ng6DQXBpVnyG844CeJYx8WW5PBHpump'),
        ('3KviqQykdwZBb6LQkksjYbr9pQP9WQBBdSvf3tb5pump'),
        ('3RabpBEybbRi7xk4Z8rwiPLTkQMnTwm8PD39Ngt1wep1'),
        ('3izvF4HcyYY4RXLyEBDHUNjjb4n2jZFfys7Dtw6Upump'),
        ('3nTmaNvUd12oEd52rsjc8hZLqSjRm1yoEtCnZBDRpump'),
        ('3uRnHKeooz6NyiCrD1Dq5JEpM5XPKe3abxAsJvNGpump'),
        ('4SQ2qZrKeCUtMQacmTCLxttjX1y4r3zHidnFwsHvpump'),
        ('4sEPTyzdj2At9X2gSPg5HKfEAnD9hSqv5DqiY6E7pump'),
        ('57L67vSKy6fkDNjwncNx6UX1BQnWCsc1a4hcWYyhpump'),
        ('5JbJX1QXzRBeX6d6KkMKbtuTfmgxpc4ASDtfz7uopump'),
        ('5K2mmc16PDufaVZY7Cr4sqM8vacdbq21rSxpqwyYVGoE'),
        ('5Sgx4R6W2e7ZH2toZ2J5x9zYmEAsrZg4ay4Bk7Jtpump'),
        ('5cMcYeG4PSebuurzSpW1C36igxTyV3WaGhzUEFmppump'),
        ('5eyrv3Wuc8GLMnLM3RGLAgahaAEv3bvUzWFczp8gpump'),
        ('5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump'),
        ('5msxC5d3SYnLs5pgGaWsi9aeBihJmddY3uVguV8Fpump'),
        ('62JPRFp7wvf2VXPQc9zgtjynZis9yGofdh2cgtwqpump'),
        ('67CDB8uKAukpTXWV7YPwAAK4dJUjVtyFJEMwLFeBpump'),
        ('6LTZzr1u8TUMixEn1Lw9H2X1dQGWCzFD8UwiESgdpump'),
        ('6g8uqRDkGc62s4n3M7yDAPrZqkGPbqaeuqPrE97Fpump'),
        ('6rbwj1wzJMH1gQMqSWEiwcuUsQGYGDpfSVXfyKXSpump'),
        ('6tbd2au2Dtm9vaJPSuhfAe4bi52UFk9HeKDqfwwJae2U'),
        ('6vpjdKC8EAHdqXgX3gry3voXnQYGuRR6RJkH7hMxpump'),
        ('7Fgs3tqGT2sBGx6B55kdzEZFcCbgtPsD5k4hsoX4pump'),
        ('7HzXuJB4yJKFvGz5meJey8EhE6xuW2w2t4a8Jjd8pump'),
        ('7JnXhMSaX5uoiHxvrApZcmri3a6u4rS5AGXUhpH6pump'),
        ('7LUfsEbQZXxPq6cWA6x2s2pvswUKuu4qWH6BMLYopump'),
        ('7YE6BUanMhvoJYwVC8sLBEMrJjAzr9cnpvkRXmCzpump'),
        ('7xhT4Fs7KXhb7kHHJ73pZoLvqa7GVWgJLnuUBi5Ypump'),
        ('81TnF7k8V8NPBLbP54MRDAftmAphWDKhi49fYfDbs99C'),
        ('81uq5m7ZJF1p5n3jrjBE1TvSnh2GFHFbAFMCQ81wpump'),
        ('8CYQP7cnc4xDefoBp2K5nYTCht2zwUQtsQ1T1iAopump'),
        ('8NJQWbjtkbUbYhkcgp9jSJJo4pwkfwdKD8JfhHxrpump'),
        ('8iyxKLAc8c3fZt6udcVJ9DA9uGcYYZgdfDHms7VZpump'),
        ('8jyUQyUuHMua72KebwnyJ5hybycjTPSkB3b8zqjHpump'),
        ('8kJcRLna8k6qvTrTwTZxPWMvXxdtHF2bwinsxXJ1pump'),
        ('932aB51UWX51yzT9mTneNuUy9fh5p4B8FdmMnqBhvNcm'),
        ('93DB6Wsm1QjxXLXm9eEtTkUCpkYD69XbfgHoZBSpump'),
        ('97bMMJD7ev3eZzyBgHLpacpNSDWH9Vrke6gBE6p6pump'),
        ('9PoGmWKbQNLWYynwNVGNXireSs7KcCPHikDwJRd4pump'),
        ('9RWbXv3hCdmEpkqwb659JCvnVes6XLhvpXB7oYxjpump'),
        ('9Y6f6KaguaxF4yRo9Mv4WrGAncjqR3AexnHK6bCspump'),
        ('9ekZJnccBGbrZ7wj13qgcLH5dCBru579dPDdSUGopump'),
        ('9iqwUDuHMNXvSzh1N5yaubUitanLuPtx4ec9CJiqpump'),
        ('9qpDk7hGSHqyfMGDT7p4zFQ35aGff248Qes48CgLpump'),
        ('AKQsb5XKL7RohnLGWjRui5ArUYVSZWJ5VwDSa2EEpump'),
        ('ARYoDE9aaS4u7N3xfRysHwSAbY3bVFGHq5eGi3NuyYM6'),
        ('ASTcDNieMSvrSEtg1HUogScEgSSeEForG4ZKohuPpump'),
        ('AomvUWpEPZYw4FNNVJH3gfzJvVtJx37LFWcdGYEpump'),
        ('AzVXNsPqr9kZyfqUzpJfSN6rCH7PcVEnsGDpFGzjpump'),
        ('B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump'),
        ('B66MkcNKFbXwFa7XbX1CbHMBPdgLyQtp6X75eAHspump'),
        ('BJkAwqXE3w3iAwuwSHacsz9T3RTVKyFjpttMEfbvpump'),
        ('BThQvp71A4krugaqoaGXzX4yQSSRKQEMrvNar8pypump'),
        ('BUvuChjfCJxfUyCRMNWtm2W5ygTc7vV7mK4N22tGpump'),
        ('BecDT17N8aMugk1jjBspereXzBu1FzWnwQP7cMS2pump'),
        ('BvVumYuqfiMty43uJNU8keYmnVaXJzEhy9t1kRe8pump'),
        ('C3b3ZdKQZ5BQYo8PQyQuv7bGT2fXd8RTpErbuz9npump'),
        ('CMzcCtnwPC3hcJfUwc2hrQojHubgHr4o7nUPPHiJpump'),
        ('D826xNm4gC9L97UjnFjpbsZoUXAKdEWXukyfdA4Apump'),
        ('DAW7qFqQ4jnWeVPgzeNZzEKgxWr9nNXo7dKSZPQ1pump'),
        ('DEAVE9fyfQDk3fDLspnEv7y7dTGErezq2FFrp6B2pump'),
        ('DKvB8MKLTyDeBhy6LsdQUsws9epWbC8A8HAW5Lb9pump'),
        ('DLt86ttMxRKvJWg7H6Tcr8V2nGGrnLWisKtuYJ7epump'),
        ('Dbi7ZS53u8KjCUMCx9XDj9mJcSJ4uxyGuEuzQ7Hzpump'),
        ('DioWcz9RdEHNPQZiiRDLyHvqJB3j88CduS3LepNGpump'),
        ('E2sHHwpzeVjhV3DjAMP8kYBeG27qT66xS3V9EBYVpump'),
        ('EGcyghBEZ3A1t32FkcPzbKnMjE9UpBgK7789rq1W4JcR'),
        ('EVY4xJ3ytMHa77sjgs2uVj7fgXj1ha98QSQxPadApump'),
        ('EYEyyarU2mpWCTjEU5j2ezk2QEvCcr6SFMukc7Vjpump'),
        ('EqG6cBksZ6qBG5dRdYqja1R8gCeXWsCpdmiK2RUdpump'),
        ('FTRk6qHeoNvPHKpsPGbiVbpuRytVWfAd6jYsQFGypump'),
        ('FbZbeMQGonXiUKK5QGDWXTGvraY2A3fRvwBZTbYRpump'),
        ('G55tdZ564fkV46Hw6EhTa2W6xkAgFH8ugvLjvv2Epump'),
        ('GB2t2Hs2Awo4YAafTL7PzYafQJ75CkPCLCEnWoD8pump'),
        ('GCnoV95mgWUsz8M5mayYv5XJEdfASupdt6pm3ztnpump'),
        ('GCoJ8URGCr2dvY5pHVv3NbQ1hEQ3FzQEmyeGLbVgpump'),
        ('GPuJcLQ4u3r1pzh9qAiJaXXf9ak6ui6DxwDAAHsppump'),
        ('GUsV1iB83HJTcdFnqRtRSKoXcrWZfcDBSnnsb4Dxpump'),
        ('Geha2uBuvCUeAQSuwjkzKdvExUtMAXenJB8qEnDnpump'),
        ('GigDaD7zbfEYUpNzpZuYfKmGSHRRDMysnRvtEJ25pump'),
        ('GqVb7LcyFX4Xwr2UT9NTxagBUAgZkzwGrQEwCm4Kpump'),
        ('Gw7YRUTc4uc4uBv1WLgciu2sZNeaBdcuYkkyGejzpump'),
        ('HENbwYB9roXganed9MFXm9kQ9YnhMb1cTHxeg44gpump'),
        ('Hx2PQy6jWEnemnjuV6owU9VSHca2DkhCqhCQxzqJpump'),
        ('J4x1EMmQjF6WEzXq2tUtzY89x5aMhYz5CzfevcJEpump'),
        ('MBVyDu7GddjEZ9zNBHWBTqJkhU6Fv4g4VUNGZUnpump'),
        ('YxUstMyYDyqPNz78auhYfhdUKrBQgg7uctnKNDEpump'),
        ('ZhN8j2bJfs5BswAU1Axbnhpvea74dR2H6Bs9C4tpump'),
        ('fgLjT6mAQJosXq6oz8Zk96zcnEpbV6wV5SUSK3Dpump'),
        ('kGCE3FqVUwg2Rp7fgGLi2x6v1dvJnbttJhCyvpxpump'),
        ('oFm29ScgdzqckDVYCN7PxnZKnQL7p9btkUBqQvNpump'),
        ('wrxBhFHqdgYiYBjUrnHqU4Si5j59cWuocG32HNspump')
    ) AS v(mint)
),
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        max(CAST("user" AS varchar)) AS dev,
        max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'
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
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'
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
        m.mint, a.pool, m.pool_reversed, m.td, m.sd,
        a.evt_block_time AS ts, a.evt_block_slot AS slot, a.evt_tx_index AS txi,
        COALESCE(a.evt_outer_instruction_index, 0) AS oix,
        COALESCE(a.evt_inner_instruction_index, -1) AS iix,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END AS sol_pre_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END AS target_pre_raw,
        CASE WHEN m.pool_reversed THEN -CAST(a.base_amount_out AS DOUBLE)
             ELSE CAST(a.quote_amount_in_with_lp_fee AS DOUBLE) END AS dsol_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.quote_amount_in_with_lp_fee AS DOUBLE)
             ELSE -CAST(a.base_amount_out AS DOUBLE) END AS dtarget_raw,
        COALESCE(CAST(a.lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(a.protocol_fee_basis_points AS DOUBLE), 0)
          + COALESCE(CAST(a.coin_creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
        CAST(a."user" AS varchar) AS usr,
        NOT m.pool_reversed AS is_buy,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_out AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.quote_amount_in_with_lp_fee AS DOUBLE) / power(10, m.sd) END AS sol_amt
    FROM pumpdotfun_solana.pump_amm_evt_buyevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'
    UNION ALL
    SELECT
        m.mint, a.pool, m.pool_reversed, m.td, m.sd,
        a.evt_block_time, a.evt_block_slot, a.evt_tx_index,
        COALESCE(a.evt_outer_instruction_index, 0), COALESCE(a.evt_inner_instruction_index, -1),
        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE)
             ELSE -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0)) END,
        CASE WHEN m.pool_reversed THEN -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0))
             ELSE CAST(a.base_amount_in AS DOUBLE) END,
        COALESCE(CAST(a.lp_fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(a.protocol_fee_basis_points AS DOUBLE), 0)
          + COALESCE(CAST(a.coin_creator_fee_basis_points AS DOUBLE), 0),
        CAST(a."user" AS varchar),
        m.pool_reversed,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.quote_amount_out AS DOUBLE) / power(10, m.sd) END
    FROM pumpdotfun_solana.pump_amm_evt_sellevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'
),
amm_states AS (
    SELECT
        mint, ts, 1 AS venue, slot, txi, oix, iix,
        (sol_pre_raw + dsol_raw) / power(10, sd) AS x,
        (target_pre_raw + dtarget_raw) / power(10, td) AS y,
        CAST(NULL AS DOUBLE) AS xr, fee_bps, usr, is_buy, sol_amt, pool_reversed
    FROM amm_raw
),
states AS (
    SELECT
        t.mint, t.evt_block_time AS ts, 0 AS venue, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
        COALESCE(t.evt_outer_instruction_index, 0) AS oix,
        COALESCE(t.evt_inner_instruction_index, -1) AS iix,
        CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
        CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
        CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr,
        COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,
        CAST(t."user" AS varchar) AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt,
        false AS pool_reversed
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT mint, ts, venue, slot, txi, oix, iix, x, y, xr, fee_bps, usr, is_buy, sol_amt, pool_reversed
    FROM amm_states
),
s1_raw AS (
    SELECT
        s.*, c.created_at, c.created_slot, c.dev,
        row_number() OVER (PARTITION BY s.mint ORDER BY s.slot, s.txi, s.oix, s.iix, s.venue) AS rn,
        max(s.ts) OVER (
            PARTITION BY s.mint ORDER BY s.slot, s.txi, s.oix, s.iix, s.venue
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS clock_ts
    FROM states s
    JOIN sol_cohort c ON c.mint = s.mint
    WHERE s.ts >= c.created_at
      AND s.ts <= c.created_at + INTERVAL '30' DAY
      AND s.x > 0 AND s.y > 0
),
s1 AS (
    SELECT *, date_diff('second', created_at, clock_ts) AS dt
    FROM s1_raw
),
s2 AS (
    SELECT
        *,
        min(CASE WHEN is_buy AND sol_amt >= 0.1 AND usr IS NOT NULL AND usr <> dev THEN rn END)
          OVER (PARTITION BY mint, usr) AS first_q_rn
    FROM s1
),
s3 AS (
    SELECT
        *,
        (rn = first_q_rn) AS q_new,
        x / y AS price,
        count(*) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS n_trades_cum,
        sum(CASE WHEN is_buy THEN sol_amt ELSE 0 END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS buy_sol_cum,
        sum(CASE WHEN NOT is_buy THEN sol_amt ELSE 0 END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS sell_sol_cum,
        sum(CASE WHEN is_buy AND usr = dev THEN sol_amt ELSE 0 END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS dev_buy_sol_cum
    FROM s2
),
s4 AS (
    SELECT
        *,
        sum(CASE WHEN q_new THEN 1 ELSE 0 END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS q_count
    FROM s3
),
s5 AS (
    SELECT
        *,
        min(CASE WHEN q_new AND q_count = 3 THEN rn END) OVER (PARTITION BY mint) AS t3_rn
    FROM s4
),
s6 AS (
    SELECT
        *,
        max(CASE WHEN rn = t3_rn THEN clock_ts END) OVER (PARTITION BY mint) AS t3_ts
    FROM s5
),
s7 AS (
    SELECT
        *,
        max(CASE WHEN clock_ts <= t3_ts + INTERVAL '5' SECOND THEN rn END) OVER (PARTITION BY mint) AS e5_rn,
        max(CASE WHEN clock_ts <= t3_ts + INTERVAL '30' SECOND THEN rn END) OVER (PARTITION BY mint) AS e30_rn,
        max(CASE WHEN clock_ts <= t3_ts + INTERVAL '120' SECOND THEN rn END) OVER (PARTITION BY mint) AS e120_rn
    FROM s6
),
s8 AS (
    SELECT
        *,
        max(CASE WHEN rn = e5_rn THEN x END) OVER (PARTITION BY mint) AS e5_x,
        max(CASE WHEN rn = e5_rn THEN y END) OVER (PARTITION BY mint) AS e5_y,
        max(CASE WHEN rn = e5_rn THEN xr END) OVER (PARTITION BY mint) AS e5_xr,
        max(CASE WHEN rn = e5_rn THEN fee_bps END) OVER (PARTITION BY mint) AS e5_fee_bps,
        max(CASE WHEN rn = e5_rn THEN venue END) OVER (PARTITION BY mint) AS e5_venue,
        max(CASE WHEN rn = e5_rn THEN IF(pool_reversed, 1, 0) END) OVER (PARTITION BY mint) AS e5_pool_reversed,
        max(CASE WHEN rn = e5_rn THEN clock_ts END) OVER (PARTITION BY mint) AS e5_ts,
        max(CASE WHEN rn = e30_rn THEN x END) OVER (PARTITION BY mint) AS e30_x,
        max(CASE WHEN rn = e30_rn THEN y END) OVER (PARTITION BY mint) AS e30_y,
        max(CASE WHEN rn = e30_rn THEN fee_bps END) OVER (PARTITION BY mint) AS e30_fee_bps,
        max(CASE WHEN rn = e30_rn THEN clock_ts END) OVER (PARTITION BY mint) AS e30_ts,
        max(CASE WHEN rn = e120_rn THEN x END) OVER (PARTITION BY mint) AS e120_x,
        max(CASE WHEN rn = e120_rn THEN y END) OVER (PARTITION BY mint) AS e120_y,
        max(CASE WHEN rn = e120_rn THEN fee_bps END) OVER (PARTITION BY mint) AS e120_fee_bps,
        max(CASE WHEN rn = e120_rn THEN clock_ts END) OVER (PARTITION BY mint) AS e120_ts,
        max(CASE WHEN rn = e30_rn THEN x / y END) OVER (PARTITION BY mint) AS e30_price,
        max(CASE WHEN rn = e120_rn THEN x / y END) OVER (PARTITION BY mint) AS e120_price
    FROM s7
),
s9 AS (
    SELECT
        *,
        e5_y - e5_x * e5_y / (e5_x + 0.5 * (1 - e5_fee_bps / 1e4)) AS entry_tokens,
        e30_y - e30_x * e30_y / (e30_x + 0.5 * (1 - e30_fee_bps / 1e4)) AS entry_tokens_e30,
        e120_y - e120_x * e120_y / (e120_x + 0.5 * (1 - e120_fee_bps / 1e4)) AS entry_tokens_e120,
        price / NULLIF(e5_x / e5_y, 0) AS pm
    FROM s8
),
s10 AS (
    SELECT
        *,
        LEAST(
            CASE
                WHEN venue = 0 AND y > entry_tokens THEN (x * y / (y - entry_tokens) - x) * (1 - fee_bps / 1e4)
                WHEN venue = 0 THEN NULL
                ELSE (x - x * y / (y + entry_tokens)) * (1 - fee_bps / 1e4)
            END,
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - e5_fee_bps / 1e4), 1e18))
        ) / 0.5 AS sell_multiple,
        CASE WHEN rn >= e30_rn THEN LEAST(
            CASE
                WHEN venue = 0 AND y > entry_tokens_e30 THEN (x * y / (y - entry_tokens_e30) - x) * (1 - fee_bps / 1e4)
                WHEN venue = 0 THEN NULL
                ELSE (x - x * y / (y + entry_tokens_e30)) * (1 - fee_bps / 1e4)
            END,
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - e30_fee_bps / 1e4), 1e18))
        ) / 0.5 END AS sell_multiple_e30,
        CASE WHEN rn >= e120_rn THEN LEAST(
            CASE
                WHEN venue = 0 AND y > entry_tokens_e120 THEN (x * y / (y - entry_tokens_e120) - x) * (1 - fee_bps / 1e4)
                WHEN venue = 0 THEN NULL
                ELSE (x - x * y / (y + entry_tokens_e120)) * (1 - fee_bps / 1e4)
            END,
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - e120_fee_bps / 1e4), 1e18))
        ) / 0.5 END AS sell_multiple_e120,
        max(CASE WHEN rn >= e5_rn THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_pm
    FROM s9
),
coin_path AS (
    SELECT
        mint,
        min(created_at) AS created_at,
        max(dev) AS dev,
        max(t3_ts) AS t3_ts,
        date_diff('second', max(created_at), max(t3_ts)) AS t3_s,
        max(e5_x) AS e5_x, max(e5_y) AS e5_y, max(e5_xr) AS e5_xr,
        max(e5_fee_bps) AS e5_fee_bps, max(e5_venue) AS e5_venue,
        max(e5_pool_reversed) AS e5_pool_reversed,
        max(e5_ts) AS e5_ts, max(e30_ts) AS e30_ts, max(e120_ts) AS e120_ts,
        max(e30_price) / NULLIF(max(e5_x / e5_y), 0) AS price_pm_30s,
        max(e120_price) / NULLIF(max(e5_x / e5_y), 0) AS price_pm_120s,
        max_by(price, rn) FILTER (WHERE dt <= 5) / NULLIF(min_by(price, rn), 0) AS price_pm_5s_from_open,
        max_by(price, rn) FILTER (WHERE dt <= 15) / NULLIF(min_by(price, rn), 0) AS price_pm_15s_from_open,
        max_by(price, rn) FILTER (WHERE dt <= 30) / NULLIF(min_by(price, rn), 0) AS price_pm_30s_from_open,
        max_by(price, rn) FILTER (WHERE dt <= 60) / NULLIF(min_by(price, rn), 0) AS price_pm_60s_from_open,
        max_by(price, rn) FILTER (WHERE dt <= 120) / NULLIF(min_by(price, rn), 0) AS price_pm_120s_from_open,
        max_by(price, rn) FILTER (WHERE dt <= 300) / NULLIF(min_by(price, rn), 0) AS price_pm_300s_from_open,
        max(q_count) FILTER (WHERE dt <= 5) AS qbuyers_5s,
        max(q_count) FILTER (WHERE dt <= 15) AS qbuyers_15s,
        max(q_count) FILTER (WHERE dt <= 30) AS qbuyers_30s,
        max(q_count) FILTER (WHERE dt <= 60) AS qbuyers_60s,
        max(q_count) FILTER (WHERE dt <= 120) AS qbuyers_120s,
        max(q_count) FILTER (WHERE dt <= 300) AS qbuyers_300s,
        max_by(n_trades_cum, rn) FILTER (WHERE rn = t3_rn) AS trades_t3,
        max_by(buy_sol_cum, rn) FILTER (WHERE rn = t3_rn) AS buy_sol_t3,
        max_by(sell_sol_cum, rn) FILTER (WHERE rn = t3_rn) AS sell_sol_t3,
        max_by(dev_buy_sol_cum, rn) FILTER (WHERE rn = t3_rn) AS dev_buy_sol_t3,
        max(sell_multiple) FILTER (WHERE rn >= e5_rn AND clock_ts <= t3_ts + INTERVAL '10' MINUTE) AS max_sell_10m,
        max(sell_multiple) FILTER (WHERE rn >= e5_rn AND clock_ts <= t3_ts + INTERVAL '30' MINUTE) AS max_sell_30m,
        max(sell_multiple) FILTER (WHERE rn >= e5_rn AND clock_ts <= t3_ts + INTERVAL '2' HOUR) AS max_sell_2h,
        max(sell_multiple) FILTER (WHERE rn >= e5_rn AND clock_ts <= t3_ts + INTERVAL '24' HOUR) AS max_sell_24h,
        max(sell_multiple) FILTER (WHERE rn >= e5_rn) AS max_sell_30d,
        max(sell_multiple_e30) FILTER (WHERE rn >= e30_rn) AS max_sell_30d_e30,
        max(sell_multiple_e120) FILTER (WHERE rn >= e120_rn) AS max_sell_30d_e120,
        max(pm) FILTER (WHERE rn >= e5_rn) AS max_price_pm_30d,
        min(date_diff('second', e5_ts, clock_ts)) FILTER (
            WHERE rn >= e5_rn AND pm <= 0.5 * greatest(1.0, runmax_pm)
        ) AS first_dd50_s,
        max(date_diff('second', created_at, clock_ts)) AS last_trade_s,
        count(*) FILTER (WHERE rn > e5_rn) AS n_post_entry_trades
    FROM s10
    WHERE t3_ts IS NOT NULL
    GROUP BY mint
),
all_coins AS (
    SELECT
        c.mint, c.created_at, c.dev,
        p.t3_ts, p.t3_s,
        p.e5_x, p.e5_y, p.e5_xr, p.e5_fee_bps, p.e5_venue, p.e5_pool_reversed,
        p.e5_ts, p.e30_ts, p.e120_ts,
        p.price_pm_30s, p.price_pm_120s,
        p.price_pm_5s_from_open, p.price_pm_15s_from_open, p.price_pm_30s_from_open,
        p.price_pm_60s_from_open, p.price_pm_120s_from_open, p.price_pm_300s_from_open,
        p.qbuyers_5s, p.qbuyers_15s, p.qbuyers_30s, p.qbuyers_60s, p.qbuyers_120s, p.qbuyers_300s,
        p.trades_t3, p.buy_sol_t3, p.sell_sol_t3, p.dev_buy_sol_t3,
        p.max_sell_10m, p.max_sell_30m, p.max_sell_2h, p.max_sell_24h, p.max_sell_30d,
        p.max_sell_30d_e30, p.max_sell_30d_e120,
        p.max_price_pm_30d, p.first_dd50_s, p.last_trade_s, p.n_post_entry_trades,
        COALESCE(mp.pool_reversed, false) AS mapped_pool_reversed,
        p.t3_s BETWEEN 0 AND 300 AS eligible,
        COALESCE(p.max_sell_30d >= 10, false) AS tail10_exec,
        COALESCE(p.first_dd50_s BETWEEN 0 AND 1800 AND p.max_sell_24h < 2, false) AS early_crash,
        r.mint IS NOT NULL AS r0_seen,
        IF(CAST(c.created_at AS date) <= DATE '2026-06-07', 'A', 'B') AS cohort_week,
        CASE
            WHEN p.t3_s <= 5 THEN '000_005'
            WHEN p.t3_s <= 15 THEN '006_015'
            WHEN p.t3_s <= 30 THEN '016_030'
            WHEN p.t3_s <= 60 THEN '031_060'
            WHEN p.t3_s <= 120 THEN '061_120'
            WHEN p.t3_s <= 300 THEN '121_300'
            ELSE 'not_eligible'
        END AS t3_bucket,
        bitwise_and(from_big_endian_64(xxhash64(to_utf8(c.mint))), 9223372036854775807) AS mint_hash
    FROM sol_cohort c
    LEFT JOIN coin_path p ON p.mint = c.mint
    LEFT JOIN r0_seen r ON r.mint = c.mint
    LEFT JOIN mapping mp ON mp.mint = c.mint
),
with_counts AS (
    SELECT
        *,
        count(*) OVER () AS n_all,
        count(*) FILTER (WHERE eligible) OVER () AS n_eligible,
        count(*) FILTER (WHERE eligible AND tail10_exec) OVER () AS n_tail10_exec,
        count(*) FILTER (WHERE eligible AND early_crash) OVER () AS n_early_crash,
        count(*) FILTER (WHERE eligible AND mod(mint_hash, 10000) < 200) OVER () AS n_random_2pct,
        count(*) FILTER (WHERE mapped_pool_reversed) OVER () AS n_mapped_reverse_pool,
        count(*) OVER (PARTITION BY cohort_week) AS n_all_week,
        count(*) FILTER (WHERE eligible) OVER (PARTITION BY cohort_week) AS n_eligible_week,
        count(*) FILTER (WHERE eligible) OVER (PARTITION BY cohort_week, t3_bucket) AS n_eligible_week_t3_bucket
    FROM all_coins
)
SELECT
    CASE
        WHEN r0_seen THEN 'r0_qa'
        WHEN eligible AND tail10_exec THEN 'tail10_all'
        ELSE 'random_2pct'
    END AS inclusion_class,
    CASE
        WHEN eligible AND tail10_exec THEN 1.0
        WHEN eligible AND mod(mint_hash, 10000) < 200 THEN 0.02
    END AS objective_inclusion_probability,
    *
FROM with_counts
WHERE r0_seen
   OR (eligible AND tail10_exec)
   OR (eligible AND mod(mint_hash, 10000) < 200)
ORDER BY created_at, mint
