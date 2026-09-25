/* DQ-20 第 0 段 Q0a：A 周早买履历。生成：make_q0a.py。只看 A 周（创建于 2026-06-01 00:00 至 06-06 23:29:59 UTC 的 SOL 币）。
   平台单次费用上限：40 credits（请在 Dune 网页设置；本 SQL 无法自行停机）。
   早买 = 创建后 30 分钟内、≥0.1 SOL、非创建者的买入（曲线 TradeEvent + pump 创建的 PumpSwap 池 BuyEvent）。
   赢家 = F3 面板中入场（+30 分钟）后 24 小时内路径最高 ≥10× 的币（96 个，VALUES 传入）。
   格：币龄 [0,2)/[2,10)/[10,60)/[60,300)/[300,1800) 秒 × 曲线 real_sol_reserves [0,1)/[1,5)/[5,20)/[20,60)/≥60 SOL（池买入单列 P）
       × 此前累计买入额（全部买家，含 <0.1 SOL 与创建者）[0,1)/[1,10)/[10,50)/≥50 SOL。
   每个 (钱包, 币) 只取第一笔合格早买。重扫描链：tradeevent 与 buyevent 各只扫描一次；小表 createevent/createpoolevent 可多次引用。 */
WITH
cohort AS (
    SELECT mint, min(evt_block_time) AS created_at, min(evt_block_slot) AS created_slot,
           max(CAST("user" AS varchar)) AS dev, max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-06'
    GROUP BY 1
),
sol AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
      AND created_at < TIMESTAMP '2026-06-06 23:30:00'
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
      AND base_mint IN (SELECT mint FROM sol)
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0
    GROUP BY 1
),
win AS (
    SELECT mint FROM (VALUES
        ('2Cn914VFmRasAJyhEQrjuxXoLqTR6b66Cx6vcDWwpump'),
        ('2HrQ5THKdRnqzMM2ZDd4jviQQKWwrEmVtyBZUN9Epump'),
        ('2NK1zUACYojPGdVESHwHT8shKHusNWxiMSAgMRcwpump'),
        ('2QT3eVHT8WQHZYdemSZcmGTdjzGeJsjWYtqQ9xZWpump'),
        ('2QruGDNEcbvojXbCBmBzPwN6fsTxaqyLptRrcNFvpump'),
        ('2YXsdwFiK15JYSfERjUXaJrr71MVU5Uwfe72DQedpump'),
        ('2bqW58sVYxsDjp4kcfdLhVtyx7mkJFgdrFRbvMKipump'),
        ('2hqdBdkd5YqagpBcV7QBPiQvdU3V1y8C8dWsv4nQpump'),
        ('3757xRe9ejGDXNFbwNyM64KLX1fkf2jgyHAunZfspump'),
        ('3FDvp4d7RVqU1Ng6DQXBpVnyG844CeJYx8WW5PBHpump'),
        ('3G8zFxHAnuWXiiC9MobE9EUUqV6m6MjL51YnN6tGpump'),
        ('3MEEuA4AqM9MxxM6dJ8H5gdWpiKy2HxNDiBZ4u4Gpump'),
        ('3arTam6F1LMDb5V6KeVujjz6rGFu8sP6Xk75E3CBpump'),
        ('3ghKZfLZJawWRWhSvgreiTDeyFPS4Kriy6v4Fbk3pump'),
        ('3hsCeM7CvB4CTyzKLXhpqakj5tjwQ2nHWhMjBbgcpump'),
        ('3to2HzpTG49t1saZCtTgUMRTkXg9MaPEP1Rdyvnwpump'),
        ('3uRnHKeooz6NyiCrD1Dq5JEpM5XPKe3abxAsJvNGpump'),
        ('4CneEEm2QbuXeemXzpDaTctydnX7fqWRHj8WeGfdpump'),
        ('4hHzQSjiKJspR3nmV8wTicjaLuUuSYMddVSybQcJs5Nb'),
        ('54xoZoi2At3Hjnhw7BpScGDGSK3b8gSM35WGqrwWpump'),
        ('5GbhDpdSdE693wi3huTbjc9TtSXoKKQgezAt3e24pump'),
        ('5KWKsTS1gqc2JR765NjmEzVSBKVMwogjdWY9Ph2hpump'),
        ('5Sgx4R6W2e7ZH2toZ2J5x9zYmEAsrZg4ay4Bk7Jtpump'),
        ('5VQL7aJcjfWWHbmhW25AKxMZ8ErPETRR8uTnPeDDpump'),
        ('5cMcYeG4PSebuurzSpW1C36igxTyV3WaGhzUEFmppump'),
        ('5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump'),
        ('5zmMpN8S8VNNi6XqcSH2QovtNFNFWNguYiQbFzJGpump'),
        ('6S6oBHETSaAcH2XVxAciSnhawtZzfq6VVP6PZ6RFpump'),
        ('6tiHWcMKpdzffutC1VsoLcjfPkwzqAJWDbTVpWHmpump'),
        ('6xUoG8JtjYxKfBD3nsLGp8n9pGzKUigF5WTwWyy1pump'),
        ('7AyGRkob1epwwqutVomL9EYCdfZ4KYHSwbyfYQyEpump'),
        ('7HzXuJB4yJKFvGz5meJey8EhE6xuW2w2t4a8Jjd8pump'),
        ('7Lk9YBi2hD1eYbqGoPVhzn4aPSJw8qwdEJUshLwepump'),
        ('7szB6Gvan3wNoqaJe7cwfeoEZ6ydeCRRytD8RpT5pump'),
        ('8NVjhoPS7zjTrAkKECG3kJVVLTooSXbWCJn3y1smpump'),
        ('8TtwS9htVP7fUgeKBZDMy3P5WiCbfxFvk8biDc4pump'),
        ('8jyUQyUuHMua72KebwnyJ5hybycjTPSkB3b8zqjHpump'),
        ('9L1tgYt2XpSvdQTfCS1oRKrvRpekvrumXbNJjAZHpump'),
        ('9UuLsJ3jf8ViBNeRcwXD53re5G3ypgfKK3s2EiMMpump'),
        ('9cEVQL4eTyLvqjoRo4pYUhwJZ6ampRsSxdixCdd6pump'),
        ('9zgMFv4VyfK4ywTAT75GXab7fvuCJRv1CnE1HeFopump'),
        ('9zwhS3b1oYuUEqWNpu2SPkEH24JMVWFEVQvHuYXZpump'),
        ('AKQsb5XKL7RohnLGWjRui5ArUYVSZWJ5VwDSa2EEpump'),
        ('AKUYQxitb6GqqJnoSbwgzJJphRW5emgn2ykEiPpKpump'),
        ('AbKcanX7kFZENoRLe7FnMgbzJWpnkmLzKpAbLv1gpump'),
        ('AyLn7YdHqh3pGSNC1YrdEtEdSCVjG7BxQedxBvkTpump'),
        ('B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump'),
        ('B7MJFpekGZRfsqQJh48ciaA27rA7SoC8cLYkShzCpump'),
        ('BHSKdQQ8mrjtSkMwpgzGedEbTMWuHwXq7x5VSkispump'),
        ('BUvuChjfCJxfUyCRMNWtm2W5ygTc7vV7mK4N22tGpump'),
        ('BgJb11D5NG9h8hTxDxxSnFZ3xMns5XeC1trY4kBSpump'),
        ('BhxC2Bc1tUxa8Y3zbLMCjMNvqMD8JgSTekScPhGepump'),
        ('BxVHLVaDaFAVtuuEsqUr5s12R4Nn5KxM8XB2uk4Fpump'),
        ('C3x6wHmu4kJ1HrLj2ueUzHndTS7cQTDvBbAUDetGpump'),
        ('C6sbkjPjyUbRHY91K4T4Wigz6WyFA6NsrNq8THpZpump'),
        ('CeYDoTwBmHkAxoEGj7ViJJ4aPCa24yx7byKoJ4eupump'),
        ('CgHE4SAtNuzbCpQmkPzwYZ7cBMQLK7R4J2gVSVrDpump'),
        ('CgoBzH5qyF68Y8a77MvGdxY33JVt3UHBT1UbNrT6pump'),
        ('CxAWgKiq4AfsaqQhR7td4m8vege82hNhDioRFWCspump'),
        ('Cxtd4j9mVysEoE8JRiiyhPoqa59mfU6JW58jy34GPump'),
        ('DMU6LRnRBV7URLdpCYadHNKxXxyf4MRkdqSqC2tkpump'),
        ('DVSHrizCpD2thBW1Nrtieo4p3SERgmGZqWpZvtkPpump'),
        ('DXWHKus2pkwrQrU4vwM3sWcW3f2n6JYjJKaet4zvpump'),
        ('DpPowzjETiU6421ReuwBB8XmDB7sMyB2JGzFLssYpump'),
        ('Dx2D6mU8jXSmV6UefwYvX1B9X62aSMeXnK5tF5XRpump'),
        ('E6QZmyAi86yhXieF4TSvF2ChkNMFwLxTJRdseRbXpump'),
        ('E9UBCCStMo3JyzfLbVxpbZ2JpQmJ1f5sPQhNBbtnpump'),
        ('EGcyghBEZ3A1t32FkcPzbKnMjE9UpBgK7789rq1W4JcR'),
        ('ES6ZcfTUTVET37RaYW9qDhX1DBBDEaTuvg87Lw9epump'),
        ('Eb3ExVkmnNayuUm8r9BStHqo1UwaEW7fRhJDn9MFpump'),
        ('EeSHyt1ahSvm91CSa8ASqvenmxxQn2WU5VeNhdmepump'),
        ('F1nRpCjND1FjQtgVScRhgEgLp95Q3z4vDDhe8fgKpump'),
        ('FDVu3VmwoeF2rymVkkmptNBAZxmBLqpjRBcGfZ4npump'),
        ('FUXKe7MFMjBgRU9P6zdNKowSuEwgHh2nC5jtfh43CB8q'),
        ('FZ8a7XbvtWKKJV5uJk3DYjnEgLN54EKwrHsrWCttpump'),
        ('FZbjXNy5PtFQuP83kGL2HMP1DK131vtyBGKfbmjGpump'),
        ('FoygxJyRSJiExgRWW9owFRVJjru9sjhScANWkyEgpump'),
        ('Fyc2fmukseRMx5k2Pk4MXBpzzEbmaECBUHQDDh89pump'),
        ('GCQXDSHVTrjoXta1kUoupeQSEPeh8DtfGeRne3h8pump'),
        ('GDccKDY21aDjthH7UTNKb7Gi4DfJ44cbbzoEPqhBpump'),
        ('GHHyenjmTaMPbck5EmxLRRKkNCXeuawZxbzaNDGDpump'),
        ('GPtCfu9VciaW6CTR7MNT2BAK5zSuD2jPiSPxLUGrpump'),
        ('GZD2Ti3FxnXgkLzpUSzeFZqMq43eksujZMP6bPuNpump'),
        ('GtnfYNhhEQgjwuhCzybGqT4cUEh7f5HozGqF7z3wpump'),
        ('Gw7YRUTc4uc4uBv1WLgciu2sZNeaBdcuYkkyGejzpump'),
        ('H7KuuMRvcTu4KpRMmxeHTZR8BM29xTrMZmgAYM9ipump'),
        ('HAJAeRURXJrniiEcsVU3Y7VBXi7zxB5k5AiYyNpqpump'),
        ('HmmV6MbfUt1FTSSmVj4Sx1gHiJnYkgCsmbxg1kjypump'),
        ('HrkKpjDdgMGCA16LsgkK2a4kQYznv8Sjx5LM5Ad3pump'),
        ('J4x1EMmQjF6WEzXq2tUtzY89x5aMhYz5CzfevcJEpump'),
        ('Jt6i35KkeFiDV8jH6A6nzaRFfTpA1u8VwiwdiBNpump'),
        ('WeHXjXSmCpaMJN2zBDvWz8N7dgKbXi5G61VyWWwpump'),
        ('hMZnN3vvdWHiWbBsGaqVVRSxrXAPPXUr7VH8QB1pump'),
        ('iRGHXZjvVsfAodUzPbvWwY11K4WdX8p3WP1wEn6pump'),
        ('iyQdD1hTYvyYv6CVoQ2GmKi2bQVkpJUtY1UxvxMpump'),
        ('wXfe7vz2t8an9Ca5dy72ChU54fRvtefDRmb4rzUpump')
    ) AS v(mint)
),
buys AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           t.evt_inner_instruction_index AS iix, CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt,
           CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr, 0 AS venue
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.mint IN (SELECT mint FROM sol)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, e.evt_inner_instruction_index,
           CAST(e."user" AS varchar), CAST(e.quote_amount_in AS DOUBLE) / 1e9, CAST(NULL AS DOUBLE), 1
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
),
early AS (
    SELECT b.*, s.dev, date_diff('millisecond', s.created_at, b.ts) / 1000.0 AS age_s,
           b.slot = s.created_slot AS in_create_slot
    FROM buys b
    JOIN sol s ON s.mint = b.mint
    WHERE b.ts >= s.created_at AND b.ts < s.created_at + INTERVAL '30' MINUTE
),
cum AS (
    SELECT *,
           COALESCE(sum(sol_amt) OVER (PARTITION BY mint ORDER BY slot, txi, iix
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prior_sol
    FROM early
),
firsts AS (
    SELECT *, row_number() OVER (PARTITION BY usr, mint ORDER BY slot, txi, iix) AS rn
    FROM cum
    WHERE sol_amt >= 0.1 AND usr <> dev AND usr IS NOT NULL
),
cells AS (
    SELECT f.usr, f.mint, f.ts, f.sol_amt, f.age_s, f.in_create_slot,
           CASE WHEN f.age_s < 2 THEN 'a0' WHEN f.age_s < 10 THEN 'a1' WHEN f.age_s < 60 THEN 'a2'
                WHEN f.age_s < 300 THEN 'a3' ELSE 'a4' END
           || CASE WHEN f.venue = 1 THEN 'P' WHEN f.xr < 1 THEN 'x0' WHEN f.xr < 5 THEN 'x1' WHEN f.xr < 20 THEN 'x2'
                   WHEN f.xr < 60 THEN 'x3' ELSE 'x4' END
           || CASE WHEN f.prior_sol < 1 THEN 'c0' WHEN f.prior_sol < 10 THEN 'c1' WHEN f.prior_sol < 50 THEN 'c2'
                   ELSE 'c3' END AS cell,
           CASE WHEN w.mint IS NOT NULL THEN 1 ELSE 0 END AS hit
    FROM firsts f
    LEFT JOIN win w ON w.mint = f.mint
    WHERE f.rn = 1
),
rated AS (
    SELECT *, avg(CAST(hit AS DOUBLE)) OVER (PARTITION BY cell) AS cell_rate,
           count(*) OVER (PARTITION BY cell) AS cell_n
    FROM cells
),
per_wallet AS (
    SELECT usr,
           count(*) AS n_coins,
           sum(hit) AS obs,
           sum(cell_rate) AS expct,
           sum(sol_amt) AS sol_total,
           count_if(age_s < 2) AS n_age_lt2s,
           count_if(in_create_slot) AS n_create_slot,
           count(DISTINCT date(ts)) AS n_days,
           min(ts) AS first_ts, max(ts) AS last_ts,
           array_join(array_agg(CASE WHEN hit = 1 THEN mint END) FILTER (WHERE hit = 1), ',') AS hit_mints,
           min(cell_n) AS min_cell_n
    FROM rated
    GROUP BY 1
)
SELECT *
FROM per_wallet
WHERE n_coins >= 3
  AND (obs >= 1 OR mod(from_big_endian_64(xxhash64(to_utf8(usr))), 4) = 0)
ORDER BY obs DESC, expct
