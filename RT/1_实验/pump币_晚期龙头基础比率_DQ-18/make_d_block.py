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
           (tr.project = 'pumpswap' OR (tr.project = 'raydium' AND tr.version IN (4, 5))) AS is_cp,
           CASE WHEN tr.quote_mint = '{SOL}' THEN tr.quote_amount * s.sol_usd
                ELSE tr.quote_amount END AS quote_usd,
           tr.token_amount
    FROM tr
    LEFT JOIN sol_minute s
      ON tr.quote_mint = '{SOL}' AND s.minute = date_trunc('minute', tr.block_time)
    WHERE tr.token_amount > 0
      AND ((tr.quote_mint = '{SOL}' AND tr.quote_amount >= 0.001 AND s.sol_usd > 0)
        OR (tr.quote_mint IN ('{USDC}', '{USDT}') AND tr.quote_amount >= 0.10))
), ph AS (
    SELECT mint, pool, date_trunc('hour', block_time) AS h, bool_or(is_cp) AS is_cp,
           SUM(quote_usd) AS usd, SUM(token_amount) AS tok, COUNT(*) AS n,
           {MINBY}(1e9 * quote_usd / token_amount, block_time) AS f_cap,
           MIN(block_time) AS f_time, {MINBY}(tx_id, block_time) AS f_tx,
           {MINBY}(1e9 * quote_usd / token_amount, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '10' SECOND) AS f10_cap,
           MIN(block_time) FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '10' SECOND) AS f10_time,
           {MINBY}(tx_id, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '10' SECOND) AS f10_tx,
           {MINBY}(1e9 * quote_usd / token_amount, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '5' MINUTE) AS f5_cap,
           MIN(block_time) FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '5' MINUTE) AS f5_time,
           {MINBY}(tx_id, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '5' MINUTE) AS f5_tx
    FROM p1v GROUP BY 1, 2, 3
), ph2 AS (
    SELECT *,
           SUM(usd) OVER (PARTITION BY mint, h) AS h_usd,
           SUM(tok) OVER (PARTITION BY mint, h) AS h_tok,
           SUM(n) OVER (PARTITION BY mint, h) AS h_n,
           ROW_NUMBER() OVER (PARTITION BY mint, h ORDER BY is_cp DESC, usd DESC, pool) AS prk,
           LEAD(h, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS h1,
           LEAD(f_cap, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_cap,
           LEAD(f_time, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_time,
           LEAD(f_tx, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_tx,
           LEAD(f10_cap, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_10_cap,
           LEAD(f10_time, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_10_time,
           LEAD(f10_tx, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_10_tx,
           LEAD(f5_cap, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_5_cap,
           LEAD(f5_time, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_5_time,
           LEAD(f5_tx, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_5_tx,
           LEAD(f_cap, 2) OVER (PARTITION BY mint, pool ORDER BY h) AS n2_cap,
           LEAD(f_time, 2) OVER (PARTITION BY mint, pool ORDER BY h) AS n2_time,
           LEAD(f_tx, 2) OVER (PARTITION BY mint, pool ORDER BY h) AS n2_tx
    FROM ph
), hm AS (
    SELECT mint, h, pool, is_cp, h_n, h_usd, 1e9 * h_usd / h_tok AS c,
           (h_n >= 5 AND h_usd >= 100.0) AS valid,
           -- 下一小时起点（h+1h）之后，本池第一笔：路径行的退出成交（延迟≈10 秒）
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_10_cap, n2_cap) ELSE n1_cap END AS x_cap,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_10_time, n2_time) ELSE n1_time END AS x_time,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_10_tx, n2_tx) ELSE n1_tx END AS x_tx,
           -- 入场：本行若是穿越小时（h = t_s - 1h），t_s = h + 1h
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_5_cap, n2_cap) ELSE n1_cap END AS e5_cap,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_5_time, n2_time) ELSE n1_time END AS e5_time,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_5_tx, n2_tx) ELSE n1_tx END AS e5_tx,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN n2_cap ELSE n1_cap END AS e60_cap,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN n2_time ELSE n1_time END AS e60_time,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN n2_tx ELSE n1_tx END AS e60_tx
    FROM ph2 WHERE prk = 1
), j AS (
    SELECT s.mint, s.tier, s.signal_time, m.*,
           m.h = s.signal_time - INTERVAL '1' HOUR AS is_entry,
           m.h >= s.signal_time AND m.valid AS is_path
    FROM sig s JOIN hm m
      ON m.mint = s.mint
     AND m.h >= s.signal_time - INTERVAL '1' HOUR
     AND m.h < s.signal_time + INTERVAL '180' DAY
    WHERE m.h = s.signal_time - INTERVAL '1' HOUR OR (m.h >= s.signal_time AND m.valid)
), b1 AS (
    SELECT *,
           FIRST_VALUE(c) OVER (PARTITION BY mint, tier, is_path ORDER BY h
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS c0,
           LEAD(h) OVER (PARTITION BY mint, tier, is_path ORDER BY h) AS next_h,
           MAX(c) OVER (PARTITION BY mint, tier, is_path) AS maxc,
           {MAXBY}(h, c) OVER (PARTITION BY mint, tier, is_path) AS maxh,
           COUNT(*) OVER (PARTITION BY mint, tier, is_path) AS nh
    FROM j
), b2 AS (
    SELECT *, CAST(floor(ln(c / c0) / ln(1.02)) AS BIGINT) AS hb FROM b1
), b3 AS (
    SELECT *, COALESCE(MAX(hb) OVER (PARTITION BY mint, tier, is_path ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), -1000000) AS prev_hb
    FROM b2
), b4 AS (
    SELECT *, SUM(CASE WHEN hb > prev_hb THEN 1 ELSE 0 END)
                OVER (PARTITION BY mint, tier, is_path ORDER BY h ROWS UNBOUNDED PRECEDING) AS seg,
              hb > prev_hb AS is_hi
    FROM b3
), b5 AS (
    SELECT *, MAX(c) OVER (PARTITION BY mint, tier, is_path, seg ORDER BY h
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS segmax
    FROM b4
), b6 AS (
    SELECT *, CAST(floor(ln(c / segmax) / ln(0.98)) AS BIGINT) AS lb FROM b5
), b7 AS (
    SELECT *, COALESCE(MAX(lb) OVER (PARTITION BY mint, tier, is_path, seg ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prev_lb,
              MIN(CASE WHEN c <= 0.5 * segmax THEN h END)
                OVER (PARTITION BY mint, tier, is_path) AS certain_h,
              concat_ws(',',
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '1' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '1' DAY), 'D1', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '7' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '7' DAY), 'D7', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '30' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '30' DAY), 'D30', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '90' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '90' DAY), 'D90', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '180' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '180' DAY), 'D180', NULL)
              ) AS hz
    FROM b6
)
SELECT CASE WHEN is_entry THEN 'E' ELSE 'P' END AS rt,
       mint, tier, signal_time, h, pool, is_cp, h_n, h_usd, c,
       CASE WHEN is_entry THEN 'entry' WHEN is_hi THEN 'hi' WHEN c <= 0.5 * segmax THEN 'dd50'
            WHEN lb > prev_lb AND lb >= 1 THEN 'lo' ELSE 'keep' END AS kind,
       segmax, CASE WHEN is_entry THEN '' ELSE hz END AS hz,
       CASE WHEN is_entry THEN FALSE ELSE next_h IS NULL END AS is_last, maxc, maxh, nh,
       x_cap, x_time, x_tx,
       e5_cap, e5_time, e5_tx, e60_cap, e60_time, e60_tx
FROM b7
WHERE is_entry
   OR (is_path AND (
          ((certain_h IS NULL OR h <= certain_h) AND (is_hi OR (lb > prev_lb AND lb >= 1)))
          OR hz <> '' OR next_h IS NULL))
ORDER BY mint, tier, h
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
    SELECT t.block_time, t.tx_id, t.project_program_id AS pool, t.project, t.version, leg.mint,
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
        if 30 <= hr < 31 and i % 3:  # 第 30 小时只留 3 笔：市场不足，路径应跳过该小时
            continue
        pool, proj, ver = ("POOL_A", "pumpswap", 1) if i % 3 else ("POOL_B", "meteora", 2)
        q_sol = 0.5 if pool == "POOL_A" else 2.0  # 非恒定乘积池成交额更大，但主池仍应选 POOL_A
        rows.append((ts, f"tx{tx}", pool, proj, ver, "MINT", SOL, q_sol * 200 / p, q_sol))
        tx += 1
    rows.append((t0 + timedelta(hours=10, minutes=3), "dust", "POOL_A", "pumpswap", 1, "MINT", SOL, 1e-6, 1e-9))
    con.execute("CREATE TABLE tr(block_time TIMESTAMP, tx_id VARCHAR, pool VARCHAR, project VARCHAR, "
                "version INTEGER, mint VARCHAR, quote_mint VARCHAR, token_amount DOUBLE, quote_amount DOUBLE)")
    con.executemany("INSERT INTO tr VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.execute("CREATE TABLE sol_minute AS SELECT * FROM (SELECT range AS minute FROM "
                "range(TIMESTAMP '2025-01-01', TIMESTAMP '2025-01-04', INTERVAL 1 MINUTE)) CROSS JOIN "
                "(SELECT 200.0 AS sol_usd)")
    con.execute("CREATE TABLE sig AS SELECT 'MINT' AS mint, 1000000 AS tier, "
                "TIMESTAMP '2025-01-01 01:00:00' AS signal_time")
    core = CORE.format(SOL=SOL, USDC=USDC, USDT=USDT, MINBY="arg_min", MAXBY="arg_max",
                       START="2025-01-01", END="2025-01-04")
    cur = con.execute("WITH " + core)
    cols = [d[0] for d in cur.description]
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        print(d["rt"], d["h"], d["pool"], d["kind"], round(d["c"]), d["hz"], d["is_last"],
              d["x_time"], d["x_tx"], d["e5_time"], d["e60_time"], d["h_n"])


if __name__ == "__main__":
    if sys.argv[1:] == ["--duckdb-test"]:
        duckdb_test()
    else:
        p, n, size = render(*sys.argv[1:3])
        print(p.name, "signals", n, "sql_kb", round(size / 1024))
