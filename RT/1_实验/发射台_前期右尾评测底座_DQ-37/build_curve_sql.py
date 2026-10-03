#!/usr/bin/env python3
"""DQ-37 曲线阶段留存的 SQL 生成器（10-03 草稿，总控第十三轮第二节第 3 条；SQL 先交 GPT 审，再拉）。

python build_curve_sql.py meta   <周一> <标签> [--sample <起时> <止时>]
python build_curve_sql.py trades <周一> <标签> [--n 100] [--hash-mod 8] [--sample <起时> <止时>]
  → sql/<标签>.sql

母体：曲线创建时刻落在该 UTC 周（周一 00:00 起 7 天）的**全部** pump 新币（不只是毕业币）；按日历周取，
开发周与检验周都取（检验周存而不读，见 weeks.py）。封存周 2026-06-15～07-12 与币安留出同名币不取。
- meta：每币一行。创建事件的元数据（名称、代号、URI、创建者、签名者、代币程序、mayhem、cashback、计价资产、
  创建时的虚拟储备），曲线完成时刻（至数据止日），以及创建后 30 秒、5 分钟、1 小时、24 小时四个时点的累计摘要：
  笔数、买入笔数、近似用户数、买入与卖出的 SOL、该时点前最后一笔成交后的虚拟储备、到该时点为止的最高虚拟 SOL。
- trades：每币按 ord 排序的前 N 笔曲线成交（创建后 7 天内），逐笔保留签名者、用户、slot、交易内序号、外层与内层
  指令序号、交易号、方向、金额、成交后虚拟与真实储备、各项费用、mayhem 标志。成交前储备＝成交后 ∓ 金额
  （非 mayhem 币在 DQ-35 小样本里逐笔吻合；mayhem 币不吻合，见 DQ-35 README §1b）。
  --hash-mod K 只取 sha256(mint) 前 4 字节 mod K == 0 的币（无条件随机抽样，约 1/K），K=1 为全部。
排序键 ord 同 DQ-35 v2，输出时转 varchar（Dune API 把超过 2^53 的 BIGINT 当浮点序列化会丢低位）。体量与费用见 曲线阶段留存_设计_v0.md。只存不分析。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
DQ35 = H.parent / "pump毕业币_数据留存_DQ-35"
DATA_END = dt.date(2026, 9, 29)

COMMON = """/* DQ-37 曲线阶段留存（{layer}，10-03 草稿，执行模型）：曲线创建于 {w0}～{w1} 的全部 pump 新币；只存不分析；由 build_curve_sql.py 生成 */
WITH
{names},
c AS (
    SELECT mint, min(evt_block_time) AS created_at,
           min_by(name, evt_block_time) AS name, min_by(symbol, evt_block_time) AS symbol,
           min_by(uri, evt_block_time) AS uri, min_by(COALESCE(creator, "user"), evt_block_time) AS creator,
           min_by("user", evt_block_time) AS create_user, min_by(evt_tx_signer, evt_block_time) AS create_signer,
           min_by(evt_tx_id, evt_block_time) AS create_tx,
           min_by(token_program, evt_block_time) AS token_program,
           min_by(is_mayhem_mode, evt_block_time) AS is_mayhem_mode,
           min_by(is_cashback_enabled, evt_block_time) AS is_cashback_enabled,
           min_by(quote_mint, evt_block_time) AS quote_mint,
           min_by(CAST(virtual_sol_reserves AS varchar), evt_block_time) AS vsr0,
           min_by(CAST(virtual_token_reserves AS varchar), evt_block_time) AS vtr0,
           min_by(CAST(virtual_quote_reserves AS varchar), evt_block_time) AS vqr0,
           min_by(CAST(token_total_supply AS varchar), evt_block_time) AS supply
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{w0}' AND DATE '{w1}'
    GROUP BY 1
),
coins AS (
    SELECT * FROM c
    WHERE created_at >= TIMESTAMP '{w0} 00:00:00' AND created_at < TIMESTAMP '{w1} 00:00:00' + INTERVAL '1' DAY
      AND NOT (created_at >= TIMESTAMP '2026-06-15 00:00:00' AND created_at < TIMESTAMP '2026-07-13 00:00:00')
      AND upper(trim(replace(symbol, '$', ''))) NOT IN (SELECT base FROM excl){hash}{sample}
),
tr AS (
    SELECT t.mint, k.created_at, t.evt_block_time AS ts,
           date_diff('millisecond', k.created_at, t.evt_block_time) / 1000e0 AS age,
           CAST(t.evt_block_slot AS BIGINT) * 10000000000 + CAST(t.evt_tx_index AS BIGINT) * 100000
             + CAST(t.evt_outer_instruction_index AS BIGINT) * 1000 + COALESCE(t.evt_inner_instruction_index, 0) AS ord,
           t.evt_block_slot AS slot, t.evt_tx_index AS txi, t.evt_outer_instruction_index AS oix,
           t.evt_inner_instruction_index AS iix, t.evt_tx_id AS tx_id, t.evt_tx_signer AS signer,
           CAST(t."user" AS varchar) AS usr, COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) AS sol,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) AS tok,
           CAST(t.quote_amount AS DOUBLE) AS qa,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) AS x,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) AS y,
           CAST(t.real_sol_reserves AS DOUBLE) AS xr, CAST(t.real_token_reserves AS DOUBLE) AS yr,
           COALESCE(CAST(t.fee AS DOUBLE), 0) AS f_pr, COALESCE(CAST(t.creator_fee AS DOUBLE), 0) AS f_cr,
           COALESCE(CAST(t.cashback AS DOUBLE), 0) AS f_cb, COALESCE(CAST(t.buyback_fee AS DOUBLE), 0) AS f_bb,
           COALESCE(t.mayhem_mode, false) AS mayhem, t.ix_name
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN coins k ON k.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{w0}' AND DATE '{t1}'
      AND t.evt_block_time >= k.created_at AND t.evt_block_time < k.created_at + INTERVAL '{tdays}' DAY
)"""

META = """,
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '{w0}' AND DATE '{data_end}'
      AND mint IN (SELECT mint FROM coins)
    GROUP BY 1
),
hz AS (
    SELECT h.hz, tr.*
    FROM tr
    CROSS JOIN (VALUES 30, 300, 3600, 86400) AS h(hz)
    WHERE tr.age < h.hz
),
s AS (
    SELECT mint, hz,
           count(*) AS n, count_if(is_buy) AS n_buy, approx_distinct(usr) AS n_users,
           sum(CASE WHEN is_buy THEN sol ELSE 0 END) AS sol_buy,
           sum(CASE WHEN NOT is_buy THEN sol ELSE 0 END) AS sol_sell,
           max_by(x, ord) AS x_last, max_by(y, ord) AS y_last, max(x) AS x_max, min(ts) AS t_first
    FROM hz
    GROUP BY 1, 2
)
SELECT k.*, cp.completed_at, '{data_end}' AS data_end,
       s1.n AS n_30s, s1.n_buy AS nbuy_30s, s1.n_users AS users_30s, s1.sol_buy AS solb_30s, s1.sol_sell AS sols_30s, s1.x_last AS x_30s, s1.y_last AS y_30s, s1.x_max AS xmax_30s,
       s2.n AS n_5m, s2.n_buy AS nbuy_5m, s2.n_users AS users_5m, s2.sol_buy AS solb_5m, s2.sol_sell AS sols_5m, s2.x_last AS x_5m, s2.y_last AS y_5m, s2.x_max AS xmax_5m,
       s3.n AS n_1h, s3.n_buy AS nbuy_1h, s3.n_users AS users_1h, s3.sol_buy AS solb_1h, s3.sol_sell AS sols_1h, s3.x_last AS x_1h, s3.y_last AS y_1h, s3.x_max AS xmax_1h,
       s4.n AS n_24h, s4.n_buy AS nbuy_24h, s4.n_users AS users_24h, s4.sol_buy AS solb_24h, s4.sol_sell AS sols_24h, s4.x_last AS x_24h, s4.y_last AS y_24h, s4.x_max AS xmax_24h,
       s4.t_first AS t_first_trade
FROM coins k
LEFT JOIN comp cp ON cp.mint = k.mint
LEFT JOIN s s1 ON s1.mint = k.mint AND s1.hz = 30
LEFT JOIN s s2 ON s2.mint = k.mint AND s2.hz = 300
LEFT JOIN s s3 ON s3.mint = k.mint AND s3.hz = 3600
LEFT JOIN s s4 ON s4.mint = k.mint AND s4.hz = 86400
"""

TRADES = """,
r AS (
    SELECT tr.*, row_number() OVER (PARTITION BY mint ORDER BY ord) AS rn,
           CASE WHEN txi >= 100000 OR oix >= 100 OR COALESCE(iix, 0) >= 1000 OR oix IS NULL THEN 1 ELSE 0 END AS ovf
    FROM tr
)
SELECT mint, created_at, rn, ts, age, CAST(ord AS varchar) AS ord, slot, txi, oix, iix, tx_id, signer, usr, is_buy, sol, tok, qa,
       x, y, xr, yr, f_pr, f_cr, f_cb, f_bb, mayhem, ix_name, ovf
FROM r
WHERE rn <= {n}
"""


def build(layer, monday, n=100, hash_mod=1, sample=None):
    if monday.weekday() != 0:
        raise SystemExit("周一才是周的起点")
    w1 = monday + dt.timedelta(days=6)
    if w1 > DATA_END:
        raise SystemExit("周末晚于数据止日 %s" % DATA_END)
    names = (DQ35 / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    hsh = ""
    if hash_mod > 1:
        hsh = (
            "\n      AND mod(from_big_endian_32(substr(sha256(to_utf8(mint)), 1, 4)), %d) = 0"
            % hash_mod
        )
    smp = ""
    if sample:
        smp = (
            "\n      AND created_at >= TIMESTAMP '%s' AND created_at < TIMESTAMP '%s'"
            % sample
        )
    tdays = 1 if layer == "meta" else 7
    t1 = min(DATA_END, w1 + dt.timedelta(days=tdays))
    head = COMMON.format(
        layer=layer,
        names=names,
        w0=monday.isoformat(),
        w1=w1.isoformat(),
        t1=t1.isoformat(),
        tdays=tdays,
        hash=hsh,
        sample=smp,
    )
    if layer == "meta":
        return head + META.format(w0=monday.isoformat(), data_end=DATA_END.isoformat())
    return head + TRADES.format(n=int(n))


def main():
    a = sys.argv[1:]
    layer, monday, label = a[0], dt.date.fromisoformat(a[1]), a[2]
    n, hm, sample = 100, 1, None
    i = 3
    while i < len(a):
        if a[i] == "--n":
            n = int(a[i + 1])
            i += 2
        elif a[i] == "--hash-mod":
            hm = int(a[i + 1])
            i += 2
        elif a[i] == "--sample":
            sample = (a[i + 1], a[i + 2])
            i += 3
        else:
            raise SystemExit("未知参数 %s" % a[i])
    (H / "sql" / ("%s.sql" % label)).write_text(build(layer, monday, n, hm, sample))
    print("sql/%s.sql" % label)


if __name__ == "__main__":
    main()
