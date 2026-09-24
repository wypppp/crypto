"""DQ-18 D 段（信号后路径）SQL 生成器：一个时间块扫一次，覆盖该块内所有活跃的样本信号。

用法：python make_d_block.py YYYY-MM [YYYY-MM]     # 块的起止月（含）
      python make_d_block.py --duckdb-test          # 用合成数据在 DuckDB 上跑同一逻辑

口径（README v2.1 §3.6 + P1）：
- 成交：毕业后池子、报价 SOL（≥0.001）或 USDC/USDT（≥0.10）、数量为正；价格 = 报价美元 ÷ 代币数量；平台市值 = 价格 × 10 亿。
- 路径价：每小时 VWAP（比最后一笔更抗小池异常；在小时结束时可知）。
- 入场：信号时刻 t_s + L（L = 10 秒 / 5 分钟 / 60 分钟）之后，在“穿越小时成交额最大的池”里的第一笔成交。
- b50：离线判定。SQL 输出压缩路径：每 2% 的新高档一行；每段内相对段内最高每 2% 的新低档一行；
  到“段内回撤 ≥50%”（必然已触发）为止。离线按时间顺序、结合入场价与前一块的最高，逐行判定，价格误差 ≤2%。
  每行附“该小时结束后，同一小时主池里的下一笔成交”作为退出成交。
- 固定时点 1/7/30/90/180 天：取时点前最后一个小时的 VWAP（代理），块内没有时由离线从前一块沿用。
- 汇总：块内最高小时 VWAP 及时间、最后一个小时 VWAP 及时间、有成交的小时数。
不计算收益；收益在离线合并所有块之后计算。
"""
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

CORE = """p1v AS (
    SELECT tr.mint, tr.block_time, tr.tx_id, tr.pool,
           CASE WHEN tr.quote_mint = '{SOL}' THEN tr.quote_amount * s.sol_usd
                ELSE tr.quote_amount END AS quote_usd,
           tr.token_amount,
           1e9 * (CASE WHEN tr.quote_mint = '{SOL}' THEN tr.quote_amount * s.sol_usd
                       ELSE tr.quote_amount END) / tr.token_amount AS cap
    FROM tr
    LEFT JOIN sol_minute s
      ON tr.quote_mint = '{SOL}' AND s.minute = date_trunc('minute', tr.block_time)
    WHERE tr.token_amount > 0
      AND ((tr.quote_mint = '{SOL}' AND tr.quote_amount >= 0.001 AND s.sol_usd > 0)
        OR (tr.quote_mint IN ('{USDC}', '{USDT}') AND tr.quote_amount >= 0.10))
), hp AS (
    SELECT mint, date_trunc('hour', block_time) AS h, pool, SUM(quote_usd) AS usd
    FROM p1v GROUP BY 1, 2, 3
), mainpool AS (
    SELECT mint, h, {MAXBY}(pool, usd) AS pool FROM hp GROUP BY 1, 2
), hourly AS (
    SELECT mint, date_trunc('hour', block_time) AS h,
           1e9 * SUM(quote_usd) / SUM(token_amount) AS c, COUNT(*) AS n
    FROM p1v GROUP BY 1, 2
), pf AS (
    SELECT mint, pool, date_trunc('hour', block_time) AS h,
           {MINBY}(cap, block_time) AS fcap, MIN(block_time) AS ftime,
           {MINBY}(tx_id, block_time) AS ftx
    FROM p1v GROUP BY 1, 2, 3
), pn AS (
    SELECT mint, pool, h,
           LEAD(fcap) OVER (PARTITION BY mint, pool ORDER BY h) AS ncap,
           LEAD(ftime) OVER (PARTITION BY mint, pool ORDER BY h) AS ntime,
           LEAD(ftx) OVER (PARTITION BY mint, pool ORDER BY h) AS ntx
    FROM pf
), path AS (
    SELECT s.mint, s.tier, s.signal_time, hr.h, hr.c, hr.n
    FROM sig s JOIN hourly hr ON hr.mint = s.mint
    WHERE hr.h >= s.signal_time AND hr.h < s.signal_time + INTERVAL '180' DAY
), b1 AS (
    SELECT *,
           FIRST_VALUE(c) OVER (PARTITION BY mint, tier ORDER BY h
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS c0
    FROM path
), b2 AS (
    SELECT *, CAST(floor(ln(c / c0) / ln(1.02)) AS BIGINT) AS hb FROM b1
), b3 AS (
    SELECT *, COALESCE(MAX(hb) OVER (PARTITION BY mint, tier ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), -1000000) AS prev_hb
    FROM b2
), b4 AS (
    SELECT *, SUM(CASE WHEN hb > prev_hb THEN 1 ELSE 0 END)
                OVER (PARTITION BY mint, tier ORDER BY h ROWS UNBOUNDED PRECEDING) AS seg,
              hb > prev_hb AS is_hi
    FROM b3
), b5 AS (
    SELECT *, MAX(c) OVER (PARTITION BY mint, tier, seg ORDER BY h
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS segmax
    FROM b4
), b6 AS (
    SELECT *, CAST(floor(ln(c / segmax) / ln(0.98)) AS BIGINT) AS lb FROM b5
), b7 AS (
    SELECT *, COALESCE(MAX(lb) OVER (PARTITION BY mint, tier, seg ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prev_lb,
              MIN(CASE WHEN c <= 0.5 * segmax THEN h END)
                OVER (PARTITION BY mint, tier) AS certain_h
    FROM b6
), prow AS (
    SELECT b.mint, b.tier, b.signal_time, b.h, b.c, b.segmax, b.n,
           CASE WHEN b.is_hi THEN 'hi' WHEN b.c <= 0.5 * b.segmax THEN 'dd50' ELSE 'lo' END AS kind,
           x.ncap, x.ntime, x.ntx, m.pool
    FROM b7 b
    LEFT JOIN mainpool m ON m.mint = b.mint AND m.h = b.h
    LEFT JOIN pn x ON x.mint = b.mint AND x.pool = m.pool AND x.h = b.h
    WHERE (b.certain_h IS NULL OR b.h <= b.certain_h)
      AND (b.is_hi OR (b.lb > b.prev_lb AND b.lb >= 1))
), lags(lag_label, lag_s) AS (
    VALUES ('L10s', 10), ('L5m', 300), ('L60m', 3600)
), ent AS (
    SELECT s.mint, s.tier, s.signal_time, l.lag_label,
           {MINBY}(p.cap, p.block_time) AS ecap, MIN(p.block_time) AS etime,
           {MINBY}(p.tx_id, p.block_time) AS etx, MIN(m.pool) AS pool
    FROM sig s
    CROSS JOIN lags l
    JOIN mainpool m ON m.mint = s.mint AND m.h = s.signal_time - INTERVAL '1' HOUR
    JOIN p1v p ON p.mint = s.mint AND p.pool = m.pool
     AND p.block_time >= s.signal_time + l.lag_s * INTERVAL '1' SECOND
     AND p.block_time < s.signal_time + l.lag_s * INTERVAL '1' SECOND + INTERVAL '24' HOUR
    GROUP BY 1, 2, 3, 4
), hz(hz_label, hz_d) AS (
    VALUES ('D1', 1), ('D7', 7), ('D30', 30), ('D90', 90), ('D180', 180)
), hzr AS (
    SELECT p.mint, p.tier, p.signal_time, z.hz_label,
           {MAXBY}(p.c, p.h) AS hc, MAX(p.h) AS hh
    FROM path p CROSS JOIN hz z
    WHERE p.h + INTERVAL '1' HOUR <= p.signal_time + z.hz_d * INTERVAL '1' DAY
      AND p.signal_time + z.hz_d * INTERVAL '1' DAY >= TIMESTAMP '{START} 00:00:00'
      AND p.signal_time + z.hz_d * INTERVAL '1' DAY < TIMESTAMP '{END} 00:00:00'
    GROUP BY 1, 2, 3, 4
), summ AS (
    SELECT mint, tier, signal_time, MAX(c) AS maxc, {MAXBY}(h, c) AS maxh,
           {MAXBY}(c, h) AS lastc, MAX(h) AS lasth, COUNT(*) AS nh
    FROM path GROUP BY 1, 2, 3
)
SELECT 'P' AS rt, mint, tier, signal_time, h AS t, kind AS k, c AS x1, segmax AS x2,
       ncap AS x3, ntime AS t2, ntx AS s1, pool AS s2, n AS i1
FROM prow
UNION ALL
SELECT 'E', mint, tier, signal_time, etime, lag_label, ecap, NULL, NULL, NULL, etx, pool, NULL
FROM ent
UNION ALL
SELECT 'H', mint, tier, signal_time, hh, hz_label, hc, NULL, NULL, NULL, NULL, NULL, NULL
FROM hzr
UNION ALL
SELECT 'S', mint, tier, signal_time, maxh, 'sum', maxc, lastc, NULL, lasth, NULL, NULL, nh
FROM summ
ORDER BY 2, 3, 4, 1, 5
"""

TRINO_HEAD = """-- DQ-18 D 段路径块：{LABEL}（生成器 make_d_block.py；口径见文件头）
-- 活跃样本信号 {NSIG} 个（样本 raw/census/sample_D.csv，sha256 1ec965c0…）。不计算收益。
-- 运行时单条费用上限 100 credits。
WITH sig AS (
    SELECT mint, tier * 1000000 AS tier, from_unixtime(eh * 3600) AS signal_time
    FROM (VALUES
{VALUES}
    ) AS v(mint, tier, eh)
), sm AS (
    SELECT DISTINCT mint FROM sig
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '{START} 00:00:00' AND minute < TIMESTAMP '{END} 00:00:00'
    GROUP BY minute
), tr AS (
    SELECT t.block_time, t.tx_id, t.project_program_id AS pool, leg.mint,
           IF(t.token_bought_mint_address = leg.mint, t.token_sold_mint_address,
              t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = leg.mint, t.token_bought_amount,
              t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = leg.mint, t.token_sold_amount,
              t.token_bought_amount) AS quote_amount
    FROM dex_solana.trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address, t.token_sold_mint_address]) AS leg(mint)
    JOIN sm ON sm.mint = leg.mint
    WHERE t.block_month >= DATE '{START}' AND t.block_month < DATE '{END}'
      AND t.block_time >= TIMESTAMP '{START} 00:00:00' AND t.block_time < TIMESTAMP '{END} 00:00:00'
      AND t.project <> 'pumpdotfun'
      AND t.token_bought_mint_address <> t.token_sold_mint_address
), """


def month_start(s):
    y, m = map(int, s.split("-"))
    return date(y, m, 1)


def next_month(d):
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def signals():
    sample = {r["mint"] for r in csv.DictReader(open(ROOT / "raw" / "census" / "sample_D.csv"))}
    out = []
    for r in csv.DictReader(open(ROOT / "raw" / "census" / "first_crossings.csv")):
        if r["mint"] in sample and "2024-06-01" <= r["hour_start"][:10] <= "2026-03-15":
            st = datetime.strptime(r["signal_time"][:19], "%Y-%m-%d %H:%M:%S")
            out.append((r["mint"], int(r["threshold_usd"]), st))
    return out


def render(a, b=None):
    start = month_start(a)
    end = next_month(month_start(b or a))
    s0 = datetime(start.year, start.month, 1)
    s1 = datetime(end.year, end.month, 1)
    act = [x for x in signals() if x[2] < s1 and x[2] + timedelta(days=180) > s0]
    # 入场需要穿越小时（t_s − 1h）的主池；若穿越小时落在上一块，入场行缺失，离线用上一块补
    epoch = datetime(1970, 1, 1)
    vals = ",\n".join(f"('{m}',{t // 1000000},{int((st - epoch).total_seconds()) // 3600})" for m, t, st in act)
    label = a if not b or b == a else f"{a}～{b}"
    sql = (TRINO_HEAD + CORE).format(LABEL=label, NSIG=len(act), VALUES=vals, START=start.isoformat(),
                                     END=end.isoformat(), SOL=SOL, USDC=USDC, USDT=USDT,
                                     MINBY="MIN_BY", MAXBY="MAX_BY")
    name = start.strftime("%Y%m") + ("" if not b or b == a else "_" + month_start(b).strftime("%Y%m"))
    p = ROOT / "sql" / f"D_{name}.sql"
    p.write_text(sql)
    return p, len(act), len(sql)


def duckdb_test():
    """合成数据：一个币在 2 天内先涨 4 倍再跌到 1/3，检查入场、路径压缩、dd50 与退出成交。"""
    import duckdb
    con = duckdb.connect()
    t0 = datetime(2025, 1, 1, 0, 0, 0)
    rows = []
    price = 1.0e-3  # USD per token -> cap 1e6
    tx = 0
    for i in range(0, 48 * 60, 7):  # 每 7 分钟一笔
        ts = t0 + timedelta(minutes=i)
        hr = i / 60
        mult = (1 + 3 * hr / 20) if hr < 20 else max(4 * (1 - (hr - 20) / 20), 0.3)
        p = price * mult
        pool = "POOL_A" if i % 3 else "POOL_B"
        q_sol = 0.5
        rows.append((ts, f"tx{tx}", pool, "MINT", SOL, q_sol * 200 / p, q_sol))
        tx += 1
    rows.append((t0 + timedelta(hours=10, minutes=3), "dust", "POOL_A", "MINT", SOL, 1e-6, 1e-9))
    con.execute("CREATE TABLE tr(block_time TIMESTAMP, tx_id VARCHAR, pool VARCHAR, mint VARCHAR, "
                "quote_mint VARCHAR, token_amount DOUBLE, quote_amount DOUBLE)")
    con.executemany("INSERT INTO tr VALUES (?,?,?,?,?,?,?)", rows)
    con.execute("CREATE TABLE sol_minute AS SELECT * FROM (SELECT range AS minute FROM "
                "range(TIMESTAMP '2025-01-01', TIMESTAMP '2025-01-04', INTERVAL 1 MINUTE)) CROSS JOIN "
                "(SELECT 200.0 AS sol_usd)")
    con.execute("CREATE TABLE sig AS SELECT 'MINT' AS mint, 1000000 AS tier, "
                "TIMESTAMP '2025-01-01 01:00:00' AS signal_time")
    core = CORE.format(SOL=SOL, USDC=USDC, USDT=USDT, MINBY="arg_min", MAXBY="arg_max",
                       START="2025-01-01", END="2025-01-04")
    core = core.replace("l.lag_s * INTERVAL '1' SECOND", "to_seconds(l.lag_s)")
    core = core.replace("z.hz_d * INTERVAL '1' DAY", "to_days(z.hz_d)")
    res = con.execute("WITH " + core).fetchall()
    for r in res:
        print(r)


if __name__ == "__main__":
    if sys.argv[1:] == ["--duckdb-test"]:
        duckdb_test()
    else:
        p, n, size = render(*sys.argv[1:3])
        print(p.name, "signals", n, "sql_kb", round(size / 1024))
