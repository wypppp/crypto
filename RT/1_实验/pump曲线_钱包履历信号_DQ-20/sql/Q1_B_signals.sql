/* DQ-20 第 1 段 Q1（卡片_v3.1.md）。生成：make_q1.py。平台单次费用上限：40 credits（请在 Dune 网页设置）。
   历史窗口：2026-05-21 00:00 至 06-06 23:29:59 创建；B 周：06-08 00:00 至 06-14 23:59:59 创建（SOL 币）。
   早买 = 创建后 30 分钟内、≥0.1 SOL、非创建者（曲线 + pump 创建的 PumpSwap 池）；每个（钱包, 币）取第一笔。
   h(w) = 钱包在历史窗口早买过的不同币数（只用 B 周之前的数据）。输出：每个有早买的 B 周币一行。
   连接的钱包名单 wl 地址唯一，不会复制买入行；金额在每个（钱包, 币）第一笔上汇总。
   重扫描链：tradeevent 与 buyevent 各扫描一次（05-21 至 06-15）；扫描 06-15 只为覆盖 06-14 深夜创建的币，结果只含 B 周币。 */
WITH
cohort AS (
    SELECT mint, min(evt_block_time) AS created_at, max(CAST("user" AS varchar)) AS dev, max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-14'
    GROUP BY 1
),
sol AS (
    SELECT mint, created_at, dev,
           CASE WHEN created_at < TIMESTAMP '2026-06-06 23:30:00' THEN 'H'
                WHEN created_at >= TIMESTAMP '2026-06-08 00:00:00' THEN 'B' END AS period
    FROM cohort
    WHERE (quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111')
      AND (created_at < TIMESTAMP '2026-06-06 23:30:00' OR created_at >= TIMESTAMP '2026-06-08 00:00:00')
),
pools AS (
    SELECT pool, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-15'
      AND base_mint IN (SELECT mint FROM sol)
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0
    GROUP BY 1
),
wl AS (
    SELECT usr, w_idx FROM (VALUES
        ('5i8rFRKn3TEWHTPC9JH7B6QQSNRmBx5TgUGiub1kAbJA', 0),
        ('BwrUsUUMoFFpYY4pf3eXLwxi3foecucjBH3Gzn1693Qb', 1),
        ('FK5z4HVnGCLbMNATcAVm81551Ng6NZU6uRFezzMKdF3k', 2),
        ('2p2mgFLmzN82sShZeAaBGmj9zFpam4xu8g4g3wqx2ks6', 3),
        ('7r2mbmfUsxGqTkDZctEmdvq2ZrkdShW4ehsr4N8QNC5t', 4),
        ('CVmALeGQhYJ5BP2q6CkK4nNc4sWLts8xW1yfP3QLWzsX', 5),
        ('7jvgMTjDM6Tzu5daNVrK1RkRpv7HQMX63RdFSB1rnnkq', 6),
        ('HrQnXknU7odiKPcZMw6V52wrzJFsGYRowhR9oyagSunU', 7),
        ('CCnFjFovBp8mfHbAhWWFNh6CSWsdMRvAhcKRUdgpPZm5', 8),
        ('FHVBANvGDmgcCxqJxc9wQ7M6VGURZuUJtEyvKvcaM4Q6', 9)
    ) AS v(usr, w_idx)
),
buys AS (
    SELECT t.mint, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
           COALESCE(t.evt_inner_instruction_index, 0) AS iix, CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_amt
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-15'
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.mint IN (SELECT mint FROM sol)
    UNION ALL
    SELECT p.mint, e.evt_block_time, e.evt_block_slot, e.evt_tx_index, COALESCE(e.evt_inner_instruction_index, 0),
           CAST(e."user" AS varchar), CAST(e.quote_amount_in AS DOUBLE) / 1e9
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN pools p ON p.pool = e.pool
    WHERE e.evt_block_date BETWEEN DATE '2026-05-21' AND DATE '2026-06-15'
),
early AS (
    SELECT b.*, s.period, s.created_at, s.dev,
           row_number() OVER (PARTITION BY b.usr, b.mint ORDER BY b.slot, b.txi, b.iix) AS rn
    FROM buys b
    JOIN sol s ON s.mint = b.mint
    WHERE b.ts >= s.created_at AND b.ts < s.created_at + INTERVAL '30' MINUTE
      AND b.sol_amt >= 0.1 AND b.usr <> s.dev AND b.usr IS NOT NULL
),
hist AS (
    SELECT *, sum(CASE WHEN period = 'H' THEN 1 ELSE 0 END) OVER (PARTITION BY usr) AS h
    FROM early
    WHERE rn = 1
),
bw AS (
    SELECT x.mint, x.usr, x.ts, x.slot, x.sol_amt, x.h, x.created_at,
           w.w_idx AS w_idx
    FROM hist x
    LEFT JOIN wl w ON w.usr = x.usr
    WHERE x.period = 'B'
)
SELECT mint,
       min(created_at) AS created_at,
       count(DISTINCT usr) AS n_buyers,
       sum(sol_amt) AS sol_total,
       count(DISTINCT CASE WHEN h >= 30 THEN usr END) AS n_hi30,
       count(DISTINCT CASE WHEN h >= 10 THEN usr END) AS n_hi10,
       count(DISTINCT CASE WHEN h = 0 THEN usr END) AS n_new,
       sum(CASE WHEN h >= 30 THEN sol_amt ELSE 0 END) AS sol_hi30,
       array_join(array_distinct(array_agg(CAST(w_idx AS varchar)) FILTER (WHERE w_idx IS NOT NULL)), ',') AS w_idx_list,
       min(CASE WHEN w_idx IS NOT NULL THEN ts END) AS w_first_ts
FROM bw
GROUP BY 1
