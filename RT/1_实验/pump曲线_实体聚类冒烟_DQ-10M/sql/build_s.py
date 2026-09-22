"""DQ-10M 冒烟 SQL 生成器。S1：入场前买家、同笔交易、前 30 覆盖、前一日广度（不读任何收益列）。
S2：抽样钱包的首笔交易与签名者（MELT first-signer 代理）。参数 TOP_N / REST_N 为每万分之几的抽样率。"""
import csv, sys, hashlib
MINTS = [r["mint"] for r in csv.DictReader(open("../raw/smoke_mints_20260607.csv"))]
VALUES = ",\n        ".join(f"('{m}')" for m in MINTS)
D0, D1, DPREV = "2026-06-07", "2026-06-08", "2026-06-06"

HEAD = f"""WITH
m (mint) AS (
    VALUES
        {VALUES}
),
c AS (
    SELECT mint, min(evt_block_time) AS created_at, max("user") AS dev
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date = DATE '{D0}' AND mint IN (SELECT mint FROM m)
    GROUP BY 1
),"""

S1 = f"""-- DQ-10M 冒烟 S1：P1 人群（A 周 06-07 创建、net_sol_pre ≥5.3445，共 {len(MINTS)} 个币）入场前曲线买入的买家结构。
-- 不读取任何收益或结局列。输出每币一行，外加 is_total = 1 的全体汇总行（GROUPING SETS）。
-- 同笔交易：一笔交易中有 ≥2 个不同买家（MELT 同笔交易关系）。广度：钱包在入场日前一自然日（UTC 06-06）买过的不同币数。
-- 冒烟只含曲线买入；入场前已毕业的币单列计数（grad_before_entry），正式版补 PumpSwap 买入。
{HEAD}
g AS (
    SELECT mint, min(evt_block_time) AS grad_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '{D0}' AND DATE '{D1}' AND mint IN (SELECT mint FROM m)
    GROUP BY 1
),
b AS (
    SELECT t.mint, t."user" AS usr, t.evt_tx_id AS tx,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol,
           c.created_at, c.dev, g.grad_at
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN c ON c.mint = t.mint
    LEFT JOIN g ON g.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{D0}' AND DATE '{D1}'
      AND t.mint IN (SELECT mint FROM m)
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.evt_block_time <= c.created_at + INTERVAL '30' MINUTE
),
b1 AS (
    SELECT b.*, dense_rank() OVER (PARTITION BY mint, tx ORDER BY usr) AS dr FROM b
),
b2 AS (
    SELECT b1.*, max(dr) OVER (PARTITION BY mint, tx) AS tx_users FROM b1
),
w AS (
    SELECT mint, usr, max(created_at) AS created_at, max(dev) AS dev, max(grad_at) AS grad_at,
           sum(sol) AS buy_sol, bool_or(tx_users >= 2) AS in_multi_tx,
           sum(CASE WHEN tx_users >= 2 THEN sol ELSE 0 END) AS sol_multi
    FROM b2
    GROUP BY 1, 2
),
d6 AS (
    SELECT "user" AS usr, count(DISTINCT mint) AS breadth
    FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE evt_block_date = DATE '{DPREV}' AND COALESCE(is_buy, isBuy)
    GROUP BY 1
),
w2 AS (
    SELECT w.*, COALESCE(d6.breadth, 0) AS breadth,
           row_number() OVER (PARTITION BY w.mint ORDER BY w.buy_sol DESC, w.usr) AS rk
    FROM w
    LEFT JOIN d6 ON d6.usr = w.usr
)
SELECT
    grouping(mint) AS is_total,
    mint,
    max(created_at) AS created_at,
    count_if(grad_at <= created_at + INTERVAL '30' MINUTE) > 0 AS grad_before_entry,
    count(*) AS n_pairs,
    approx_distinct(usr) AS n_wallets,
    approx_distinct(CASE WHEN rk <= 30 THEN usr END) AS n_wallets_top30,
    round(sum(buy_sol), 4) AS buy_sol,
    round(sum(CASE WHEN rk <= 30 THEN buy_sol ELSE 0 END) / sum(buy_sol), 4) AS top30_sol_share,
    count_if(in_multi_tx) AS n_pairs_multi_tx,
    round(sum(sol_multi) / sum(buy_sol), 4) AS sol_share_multi_tx,
    round(sum(CASE WHEN usr = dev THEN buy_sol ELSE 0 END) / sum(buy_sol), 4) AS dev_sol_share,
    count_if(breadth = 0) AS n_pairs_breadth0,
    approx_percentile(breadth, 0.5) AS breadth_p50,
    approx_percentile(breadth, 0.9) AS breadth_p90,
    approx_percentile(breadth, 0.99) AS breadth_p99,
    round(sum(CASE WHEN breadth >= 10 THEN buy_sol ELSE 0 END) / sum(buy_sol), 4) AS sol_share_b10,
    round(sum(CASE WHEN breadth >= 50 THEN buy_sol ELSE 0 END) / sum(buy_sol), 4) AS sol_share_b50,
    round(sum(CASE WHEN breadth >= 200 THEN buy_sol ELSE 0 END) / sum(buy_sol), 4) AS sol_share_b200
FROM w2
GROUP BY GROUPING SETS ((mint), ())
ORDER BY is_total DESC, mint
"""

def s2(top_n, rest_n, tag):
    return f"""-- DQ-10M 冒烟 S2{tag}：抽样买家钱包的首笔交易与签名者（MELT first_sig_signer 代理，不等于真实出资方）。
-- 人群同 S1（{len(MINTS)} 个币）。抽样：前 30 买家钱包按哈希取万分之 {top_n}，其余钱包取万分之 {rest_n}。
-- 首笔交易：solana.account_activity 中该地址在 2026-06-08 01:00 UTC 之前最早的一行；签名者：solana.transactions.signer。
-- 不读取任何收益或结局列。每个抽样钱包一行；找不到首笔交易的钱包 first_tx 为空。
{HEAD}
b AS (
    SELECT t.mint, t."user" AS usr, CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN c ON c.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{D0}' AND DATE '{D1}'
      AND t.mint IN (SELECT mint FROM m)
      AND COALESCE(t.is_buy, t.isBuy)
      AND t.evt_block_time <= c.created_at + INTERVAL '30' MINUTE
),
wr AS (
    SELECT mint, usr, sum(sol) AS buy_sol,
           row_number() OVER (PARTITION BY mint ORDER BY sum(sol) DESC, usr) AS rk
    FROM b
    GROUP BY 1, 2
),
ws AS (
    SELECT usr, bool_or(rk <= 30) AS in_top30, count(*) AS n_mints, sum(buy_sol) AS buy_sol
    FROM wr
    GROUP BY 1
    HAVING (bool_or(rk <= 30) AND bitwise_and(from_big_endian_64(xxhash64(to_utf8(usr))), 9223372036854775807) % 10000 < {top_n})
        OR (NOT bool_or(rk <= 30) AND bitwise_and(from_big_endian_64(xxhash64(to_utf8(usr))), 9223372036854775807) % 10000 < {rest_n})
),
fa AS (
    SELECT ws.usr,
           arbitrary(ws.in_top30) AS in_top30, arbitrary(ws.n_mints) AS n_mints, arbitrary(ws.buy_sol) AS buy_sol,
           min(a.block_time) AS first_time,
           min_by(a.tx_id, a.block_slot * 100000 + a.tx_index) AS first_tx,
           min_by(a.block_date, a.block_slot * 100000 + a.tx_index) AS first_date,
           min_by(a.signed, a.block_slot * 100000 + a.tx_index) AS first_signed
    FROM solana.account_activity a
    RIGHT JOIN ws ON a.address = ws.usr AND a.block_time < TIMESTAMP '2026-06-08 01:00:00'
    GROUP BY 1
)
SELECT fa.usr, fa.in_top30, fa.n_mints, round(fa.buy_sol, 4) AS buy_sol,
       fa.first_time, fa.first_tx, fa.first_signed,
       t.signer, cardinality(t.signers) AS n_signers
FROM solana.transactions t
RIGHT JOIN fa ON t.id = fa.first_tx AND t.block_date = fa.first_date
ORDER BY fa.in_top30 DESC, fa.usr
"""

open("S1_smoke.sql", "w").write(S1)
open("S2_calib.sql", "w").write(s2(100, 10, "（成本校准，约 120 个钱包）"))
for f in ["S1_smoke.sql", "S2_calib.sql"]:
    print(f, hashlib.sha256(open(f, "rb").read()).hexdigest(), len(open(f).read()))

# ---- 冒烟修订（Dune account_activity 超时后）：S2w 只取钱包名单与整周钱包数，首笔签名者改由 Helius 解析 ----
S2W = f"""-- DQ-10M 冒烟 S2w：S2_calib 在 Dune 超过 5 分钟（solana.account_activity 按地址过滤无法剪枝），首笔签名者改由 Helius 解析。
-- 本查询不读 account_activity，也不读取任何收益或结局列。两部分输出（section 列区分）：
--   week：A 周（06-01～06-07 创建）入场前曲线净流入 ≥5.3445 SOL 的币（P1 近似，未套活跃池其余条件），其入场前买家（曲线 + PumpSwap）的币数、买家-币对数、不同钱包数，按创建日分组并含全周汇总；
--   sample：06-07 冒烟人群（{len(MINTS)} 个币）中的抽样钱包，前 30 买家（含 PumpSwap 买入）按哈希取万分之 120，其余取万分之 25。
WITH
m (mint) AS (
    VALUES
        {VALUES}
),
c AS (
    SELECT mint, min(evt_block_time) AS created_at
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-07'
    GROUP BY 1
),
mig AS (
    SELECT mint, arbitrary(pool) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-08'
    GROUP BY 1
),
ev AS (
    SELECT t.mint, c.created_at, t."user" AS usr, 0 AS venue, COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN c ON c.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-08'
      AND t.evt_block_time <= c.created_at + INTERVAL '30' MINUTE
    UNION ALL
    SELECT mg.mint, c.created_at, e."user" AS usr, 1 AS venue, true AS is_buy,
           CAST(e.quote_amount_in AS DOUBLE) / 1e9 AS sol
    FROM pumpdotfun_solana.pump_amm_evt_buyevent e
    JOIN mig mg ON mg.pool = e.pool
    JOIN c ON c.mint = mg.mint
    WHERE e.evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-08'
      AND e.evt_block_time <= c.created_at + INTERVAL '30' MINUTE
),
ew AS (
    SELECT ev.*, sum(CASE WHEN venue = 0 THEN IF(is_buy, sol, -sol) ELSE 0 END) OVER (PARTITION BY mint) AS net_pre
    FROM ev
),
pairs AS (
    SELECT mint, usr, max(created_at) AS created_at, sum(IF(is_buy, sol, 0)) AS buy_sol
    FROM ew
    WHERE net_pre >= 5.3445
    GROUP BY 1, 2
    HAVING bool_or(is_buy)
),
pr AS (
    SELECT pairs.*, CAST(date(created_at) AS varchar) AS cday,
           row_number() OVER (PARTITION BY mint ORDER BY buy_sol DESC, usr) AS rk,
           mint IN (SELECT mint FROM m) AS in_smoke
    FROM pairs
)
SELECT section, cday, usr, in_top30, n_mints, n_pairs, n_wallets, buy_sol
FROM (
    SELECT 'week' AS section, cday, CAST(NULL AS varchar) AS usr, CAST(NULL AS boolean) AS in_top30,
           count(DISTINCT mint) AS n_mints, count(*) AS n_pairs, approx_distinct(usr) AS n_wallets, round(sum(buy_sol), 2) AS buy_sol
    FROM pr
    GROUP BY GROUPING SETS ((cday), ())
    UNION ALL
    SELECT 'sample', CAST(NULL AS varchar), usr, bool_or(rk <= 30), count(*), CAST(NULL AS bigint), CAST(NULL AS bigint), round(sum(buy_sol), 4)
    FROM pr
    WHERE in_smoke
    GROUP BY usr
    HAVING (bool_or(rk <= 30) AND bitwise_and(from_big_endian_64(xxhash64(to_utf8(usr))), 9223372036854775807) % 10000 < 120)
        OR (NOT bool_or(rk <= 30) AND bitwise_and(from_big_endian_64(xxhash64(to_utf8(usr))), 9223372036854775807) % 10000 < 25)
) x
ORDER BY section DESC, cday, in_top30 DESC, usr
"""
if __name__ == "__main__" and "--s2w" in sys.argv:
    open("S2w_wallets.sql", "w").write(S2W)
    print("S2w_wallets.sql", hashlib.sha256(open("S2w_wallets.sql", "rb").read()).hexdigest())
