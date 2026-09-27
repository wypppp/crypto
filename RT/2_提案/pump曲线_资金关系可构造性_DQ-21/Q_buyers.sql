/* DQ-21 R0 早买名单（README v1.2 §7）。生成：make_q_buyers.py。平台单次费用上限：10 credits（请在 Dune 网页设置）。
   105 个 A/B 周样本币（06-01～06-14 创建），不触碰封存周（06-15 起创建的币）；成交扫描到 06-15 只为覆盖 06-14 深夜创建的币的前 30 分钟。
   早买 = 创建后 30 分钟内、>=0.1 SOL、非创建者（曲线 + pump 创建的 PumpSwap 池）；每个（钱包, 币）取第一笔。 */
WITH
s AS (
    SELECT mint FROM (VALUES
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
    SELECT mint, min(evt_block_time) AS created_at, min(evt_block_slot) AS create_slot,
           min_by(evt_tx_id, evt_block_slot) AS create_tx, max(CAST("user" AS varchar)) AS dev
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'
      AND mint IN (SELECT mint FROM s)
    GROUP BY 1
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-15'
      AND base_mint IN (SELECT mint FROM s)
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0
    GROUP BY 1
),
buys AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           COALESCE(t.evt_inner_instruction_index, 0) AS iix, t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt, 'curve' AS venue,
           (CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9)
             / NULLIF(CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6, 0) AS price
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-15'
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.mint IN (SELECT mint FROM s)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, COALESCE(e.evt_inner_instruction_index, 0),
           e.evt_tx_id, CAST(e."user" AS varchar), CAST(e.quote_amount_in AS DOUBLE) / 1e9, 'pumpswap',
           (CAST(e.pool_quote_token_reserves AS DOUBLE) / 1e9) / NULLIF(CAST(e.pool_base_token_reserves AS DOUBLE) / 1e6, 0)
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-15'
),
early AS (
    SELECT b.*, c.created_at,
           row_number() OVER (PARTITION BY b.usr, b.mint ORDER BY b.slot, b.txi, b.iix) AS rn
    FROM buys b
    JOIN cohort c ON c.mint = b.mint
    WHERE b.ts >= c.created_at AND b.ts < c.created_at + INTERVAL '30' MINUTE
      AND b.sol_amt >= 0.1 AND b.usr <> c.dev AND b.usr IS NOT NULL
),
firsts AS (
    SELECT *, row_number() OVER (PARTITION BY mint ORDER BY slot, txi, iix) AS buyer_rank,
           count(*) OVER (PARTITION BY mint) AS n_early
    FROM early
    WHERE rn = 1
)
SELECT 'create' AS kind, mint, dev AS usr, created_at AS ts, create_slot AS slot, CAST(NULL AS BIGINT) AS txi,
       CAST(NULL AS BIGINT) AS iix, create_tx AS tx_id, CAST(NULL AS DOUBLE) AS sol_amt, CAST(NULL AS VARCHAR) AS venue,
       CAST(NULL AS DOUBLE) AS price, CAST(NULL AS BIGINT) AS buyer_rank, CAST(NULL AS BIGINT) AS n_early
FROM cohort
UNION ALL
SELECT 'buy', mint, usr, ts, slot, CAST(txi AS BIGINT), CAST(iix AS BIGINT), tx_id, sol_amt, venue, price,
       buyer_rank, n_early
FROM firsts
