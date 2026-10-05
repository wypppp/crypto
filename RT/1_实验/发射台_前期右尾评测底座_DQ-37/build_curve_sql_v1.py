#!/usr/bin/env python3
"""DQ-37 曲线阶段留存 v1 的 SQL 生成器（10-06；批 1a-ii，设计见 曲线阶段留存_设计_v1.md；SQL 先交 GPT 审，再拉）。

python build_curve_sql_v1.py <层> <周一> <标签> [--sample <起时> <止时>] [--n 100]
  层：M（母体计数）、META（每币一行）、T（每币前 n 笔）、RAWC（曲线成交事件的原始字节尾段，只用于样本对照）、
      MAY（mayhem 储备更新事件）
  → sql/<标签>.sql

吸收 DQ-35 v2.2 的做法（GPT 批 1a-i 五条）：
- 金额与储备一律整数（DECIMAL(38,0)），时间输出 epoch 秒（to_unixtime，DOUBLE，读取按十进制文本解析）；每层带 chain='solana'。
- 事件唯一键（slot、交易内序号、外层、内层指令序号）；排序键 ord 在 SQL 里是 BIGINT，输出转 varchar（Dune API 会丢 2^53 以上的低位）。
- 母体互斥分类：no_symbol → holdout_name → in；M 层输出各类计数与 identity_gap（必须为 0）。检验周照存，开发读取经 dev_gate 式入口。
- 成交止于 2026-10-05 00:00（前向批次的观测止日 R3）；创建后 7 天窗口在止日前不完整的币标 mature_7d = false。
- Dune 的曲线成交表缺 IDL 里的 virtual_quote_reserves、real_quote_reserves、holder_rewards_bps、holder_rewards（F33：
  前两个 2026-05-07 版、后两个 2026-09-12 版追加）。T 层对 2026-05-07 起的事件从 solana.instruction_calls 的原始字节
  逐笔解出这四个字段，按（交易、外层、内层）与解码表对齐；布局里没有字段的记 layout0，对不上的记 missing（验收要求 0），
  同时用 mint、sol_amount、quote_amount 三个字段核对对齐（xchk）。
- mayhem 币的曲线储备会被 set_mayhem_virtual_params 在成交之外改写（UpdateMayhemVirtualParamsEvent），MAY 层单独取，
  估值时并入状态流；这解释了 DQ-35 README §1b 里“mayhem 币成交前后储备对不上”。
TradeEvent 字节布局（1 起；前 8 字节为 e445a52e51cb9a1d，9～16 为判别符 bddb7fd34ee661ee）：
  mint 17～48，sol_amount 49，token_amount 57，is_buy 65，user 66～97，timestamp 98，vsr 106，vtr 114，rsr 122，rtr 130，
  fee_recipient 138～169，fee_bps 170，fee 178，creator 186～217，creator_fee_bps 218，creator_fee 226，track_volume 234，
  total_unclaimed 235，total_claimed 243，current_sol_volume 251，last_update_ts 259，ix_name 长度 267～270、内容 271 起 n 字节，
  mayhem 271+n，cashback_bps 272+n，cashback 280+n，buyback_bps 288+n，buyback_fee 296+n，shareholders 个数 304+n～307+n、
  每个 34 字节（地址 32＋u16），之后 base = 308+n+34k：quote_mint base～base+31，quote_amount base+32，vqr base+40，
  rqr base+48，holder_rewards_bps base+56，holder_rewards base+64。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
DQ35 = H.parent / "pump毕业币_数据留存_DQ-35"
PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
D_TRADE = "0xbddb7fd34ee661ee"
CUTOFF = "2026-10-05"  # 前向批次观测止日（forward.TRADE_CUTOFF）
QUOTE_FIELDS_FROM = (
    "2026-05-07"  # F33：quote 字段追加的 IDL 版本日；更早的事件不扫原始字节
)
HZ = (30, 300, 3600, 86400)

POP = """/* DQ-37 曲线阶段留存 v1（{layer}，10-06，执行模型；批 1a-ii 待审）：曲线创建于 {w0}～{w1} 的全部 pump 新币；只存不分析；build_curve_sql_v1.py 生成 */
WITH
{names},
c0 AS (
    SELECT mint, min(evt_block_time) AS created_at, count(*) AS n_create,
           min_by(name, evt_block_time) AS name, min_by(symbol, evt_block_time) AS symbol,
           min_by(uri, evt_block_time) AS uri, min_by(COALESCE(creator, "user"), evt_block_time) AS creator,
           min_by("user", evt_block_time) AS create_user, min_by(evt_tx_signer, evt_block_time) AS create_signer,
           min_by(evt_tx_id, evt_block_time) AS create_tx, min_by(evt_block_slot, evt_block_time) AS create_slot,
           min_by(token_program, evt_block_time) AS token_program,
           min_by(is_mayhem_mode, evt_block_time) AS is_mayhem_mode,
           min_by(is_cashback_enabled, evt_block_time) AS is_cashback_enabled,
           min_by(quote_mint, evt_block_time) AS quote_mint,
           min_by(CAST(virtual_sol_reserves AS DECIMAL(38,0)), evt_block_time) AS vsr0,
           min_by(CAST(virtual_token_reserves AS DECIMAL(38,0)), evt_block_time) AS vtr0,
           min_by(CAST(real_token_reserves AS DECIMAL(38,0)), evt_block_time) AS rtr0,
           min_by(CAST(virtual_quote_reserves AS DECIMAL(38,0)), evt_block_time) AS vqr0,
           min_by(CAST(token_total_supply AS DECIMAL(38,0)), evt_block_time) AS supply
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{w0}' AND DATE '{w1}'
    GROUP BY 1
),
c1 AS (
    SELECT c0.*,
           CASE WHEN symbol IS NULL OR trim(replace(symbol, '$', '')) = '' THEN 'no_symbol'
                WHEN upper(trim(replace(symbol, '$', ''))) IN (SELECT base FROM excl) THEN 'holdout_name'
                ELSE 'in' END AS pop_class
    FROM c0
    WHERE created_at >= TIMESTAMP '{w0} 00:00:00' AND created_at < TIMESTAMP '{w1} 00:00:00' + INTERVAL '1' DAY{sample}
),
coins AS (SELECT * FROM c1 WHERE pop_class = 'in'),
tr AS (
    SELECT t.mint, k.created_at, t.evt_block_time AS ts,
           CAST(t.evt_block_slot AS BIGINT) * 10000000000 + CAST(t.evt_tx_index AS BIGINT) * 100000
             + CAST(t.evt_outer_instruction_index AS BIGINT) * 1000 + COALESCE(t.evt_inner_instruction_index, 0) AS ord,
           t.evt_block_slot AS slot, t.evt_tx_index AS txi, t.evt_outer_instruction_index AS oix,
           t.evt_inner_instruction_index AS iix, t.evt_tx_id AS tx_id, t.evt_tx_signer AS signer,
           CAST(t."user" AS varchar) AS usr, COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS sol,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DECIMAL(38,0)) AS tok,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DECIMAL(38,0)) AS vsr,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DECIMAL(38,0)) AS vtr,
           CAST(t.real_sol_reserves AS DECIMAL(38,0)) AS rsr, CAST(t.real_token_reserves AS DECIMAL(38,0)) AS rtr,
           CAST(t.fee AS DECIMAL(38,0)) AS f_pr, CAST(t.creator_fee AS DECIMAL(38,0)) AS f_cr,
           CAST(t.cashback AS DECIMAL(38,0)) AS f_cb, CAST(t.buyback_fee AS DECIMAL(38,0)) AS f_bb,
           CAST(t.fee_basis_points AS DECIMAL(38,0)) AS fee_bps, CAST(t.creator_fee_basis_points AS DECIMAL(38,0)) AS cfee_bps,
           t.mayhem_mode AS mayhem, t.ix_name, t.track_volume, t.quote_mint AS q_mint,
           CAST(t.quote_amount AS DECIMAL(38,0)) AS q_amt
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN coins k ON k.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{w0}' AND DATE '{t1}'
      AND t.evt_block_time >= k.created_at AND t.evt_block_time < k.created_at + INTERVAL '{tdays}' DAY
      AND t.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
)"""

M = """
SELECT 'solana' AS chain, '{w0}' AS week, pop_class, count(*) AS n_coins, sum(n_create) AS n_create_events,
       sum(count(*)) OVER () AS n_all,
       (SELECT count(DISTINCT mint) FROM pumpdotfun_solana.pump_evt_createevent
         WHERE evt_block_date BETWEEN DATE '{w0}' AND DATE '{w1}'
           AND evt_block_time >= TIMESTAMP '{w0} 00:00:00' AND evt_block_time < TIMESTAMP '{w1} 00:00:00' + INTERVAL '1' DAY{sample_raw})
         - sum(count(*)) OVER () AS identity_gap
FROM c1 GROUP BY pop_class
"""

META = """,
comp AS (
    SELECT mint, to_unixtime(min(evt_block_time)) AS completed_t, count(*) AS n_complete
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '{w0}' AND DATE '{cutoff_m1}'
      AND evt_block_time < TIMESTAMP '{cutoff} 00:00:00' AND mint IN (SELECT mint FROM coins)
    GROUP BY 1
),
mig AS (
    SELECT mint, to_unixtime(min(evt_block_time)) AS migrated_t, min_by(pool, evt_block_time) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '{w0}' AND DATE '{cutoff_m1}'
      AND evt_block_time < TIMESTAMP '{cutoff} 00:00:00' AND mint IN (SELECT mint FROM coins)
    GROUP BY 1
),
hz AS (
    SELECT h.hz, tr.* FROM tr CROSS JOIN (VALUES {hz_values}) AS h(hz)
    WHERE date_diff('millisecond', tr.created_at, tr.ts) < h.hz * 1000
),
s AS (
    SELECT mint, hz, count(*) AS n, count_if(is_buy) AS n_buy, count(DISTINCT usr) AS n_users,
           sum(CASE WHEN is_buy THEN sol ELSE DECIMAL '0' END) AS sol_buy,
           sum(CASE WHEN NOT is_buy THEN sol ELSE DECIMAL '0' END) AS sol_sell,
           max_by(vsr, ord) AS x_last, max_by(vtr, ord) AS y_last, max(vsr) AS x_max,
           count_if(mayhem) AS n_mayhem
    FROM hz GROUP BY 1, 2
),
a7 AS (
    SELECT mint, count(*) AS n_7d, to_unixtime(min(ts)) AS first_trade_t, to_unixtime(max(ts)) AS last_trade_t FROM tr GROUP BY 1
)
SELECT 'solana' AS chain, k.mint, to_unixtime(k.created_at) AS created_t, k.n_create, k.name, k.symbol, k.uri, k.creator,
       k.create_user, k.create_signer, k.create_tx, k.create_slot, k.token_program, k.is_mayhem_mode, k.is_cashback_enabled,
       k.quote_mint, CAST(k.vsr0 AS varchar) AS vsr0, CAST(k.vtr0 AS varchar) AS vtr0, CAST(k.rtr0 AS varchar) AS rtr0,
       CAST(k.vqr0 AS varchar) AS vqr0, CAST(k.supply AS varchar) AS supply,
       cp.completed_t, cp.n_complete, mg.migrated_t, mg.pool,
       k.created_at + INTERVAL '7' DAY <= TIMESTAMP '{cutoff} 00:00:00' AS mature_7d,
       COALESCE(a7.n_7d, 0) AS n_7d, a7.first_trade_t, a7.last_trade_t,
{hz_cols}
FROM coins k
LEFT JOIN comp cp ON cp.mint = k.mint
LEFT JOIN mig mg ON mg.mint = k.mint
LEFT JOIN a7 ON a7.mint = k.mint
{hz_joins}
"""

RAW = """,
ic AS (
    SELECT tx_id, outer_instruction_index AS oix, inner_instruction_index AS iix, block_slot AS slot, tx_index AS txi, data AS b
    FROM solana.instruction_calls
    WHERE block_date BETWEEN DATE '{r0}' AND DATE '{t1}'
      AND executing_account = '{program}' AND is_inner = true AND tx_success = true
      AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
      AND bytearray_substring(data, 9, 8) = {d_trade}
      AND tx_id IN (SELECT tx_id FROM tr)
),
icn AS (
    SELECT ic.*, CAST(bytearray_to_bigint(reverse(bytearray_substring(b, 267, 4))) AS INTEGER) AS n FROM ic
),
ick AS (
    SELECT icn.*,
           CASE WHEN length(b) >= 307 + n THEN CAST(bytearray_to_bigint(reverse(bytearray_substring(b, 304 + n, 4))) AS INTEGER) END AS k
    FROM icn
),
icb AS (SELECT ick.*, 308 + n + 34 * k AS base FROM ick),
rv AS (
    SELECT tx_id, oix, iix,
           to_base58(bytearray_substring(b, 17, 32)) AS r_mint,
           {u64_sol} AS r_sol,
           CASE WHEN base IS NOT NULL AND length(b) >= base + 39 THEN {u64_qa} END AS r_qa,
           CASE WHEN base IS NOT NULL AND length(b) >= base + 55 THEN {u64_vqr} END AS vqr,
           CASE WHEN base IS NOT NULL AND length(b) >= base + 55 THEN {u64_rqr} END AS rqr,
           CASE WHEN base IS NOT NULL AND length(b) >= base + 71 THEN {u64_hrb} END AS hr_bps,
           CASE WHEN base IS NOT NULL AND length(b) >= base + 71 THEN {u64_hr} END AS hr,
           length(b) AS blen
    FROM icb
)"""

T = """,
r AS (
    SELECT tr.*, row_number() OVER (PARTITION BY mint ORDER BY ord) AS rn,
           count(*) OVER (PARTITION BY mint, ord) AS n_dup_key
    FROM tr
){raw}
SELECT 'solana' AS chain, r.mint, to_unixtime(r.created_at) AS created_t, r.rn, to_unixtime(r.ts) AS ts,
       CAST(r.ord AS varchar) AS ord, r.slot, r.txi, r.oix, r.iix, r.n_dup_key, r.tx_id, r.signer, r.usr, r.is_buy,
       CAST(r.sol AS varchar) AS sol, CAST(r.tok AS varchar) AS tok,
       CAST(r.vsr AS varchar) AS vsr, CAST(r.vtr AS varchar) AS vtr, CAST(r.rsr AS varchar) AS rsr, CAST(r.rtr AS varchar) AS rtr,
       CAST(r.f_pr AS varchar) AS f_pr, CAST(r.f_cr AS varchar) AS f_cr, CAST(r.f_cb AS varchar) AS f_cb, CAST(r.f_bb AS varchar) AS f_bb,
       CAST(r.fee_bps AS varchar) AS fee_bps, CAST(r.cfee_bps AS varchar) AS cfee_bps,
       r.mayhem, r.ix_name, r.track_volume, r.q_mint, CAST(r.q_amt AS varchar) AS q_amt{raw_cols}
FROM r{raw_join}
WHERE r.rn <= {n}
"""

RAW_COLS = """,
       CAST(rv.vqr AS varchar) AS vqr, CAST(rv.rqr AS varchar) AS rqr, CAST(rv.hr_bps AS varchar) AS hr_bps, CAST(rv.hr AS varchar) AS hr,
       CASE WHEN r.ts < TIMESTAMP '{r0} 00:00:00' THEN 'layout0' WHEN rv.tx_id IS NULL THEN 'missing'
            WHEN rv.vqr IS NOT NULL THEN 'raw' ELSE 'layout0' END AS q_src,
       CASE WHEN rv.tx_id IS NULL THEN NULL
            WHEN rv.r_mint = r.mint AND rv.r_sol = r.sol AND (rv.r_qa IS NULL OR r.q_amt IS NULL OR rv.r_qa = r.q_amt) THEN 1 ELSE 0 END AS xchk_ok,
       rv.blen"""

RAWC = """,
r AS (SELECT DISTINCT tx_id FROM tr WHERE ts >= TIMESTAMP '{r0} 00:00:00')
SELECT 'solana' AS chain, ic.tx_id, ic.outer_instruction_index AS oix, ic.inner_instruction_index AS iix,
       ic.block_slot AS slot, ic.tx_index AS txi, to_hex(bytearray_substring(ic.data, 17, length(ic.data) - 16)) AS hex_tail
FROM solana.instruction_calls ic
WHERE ic.block_date BETWEEN DATE '{r0}' AND DATE '{t1}'
  AND ic.executing_account = '{program}' AND ic.is_inner = true AND ic.tx_success = true
  AND bytearray_substring(ic.data, 1, 8) = 0xe445a52e51cb9a1d
  AND bytearray_substring(ic.data, 9, 8) = {d_trade}
  AND ic.tx_id IN (SELECT tx_id FROM r)
"""

MAY = """
SELECT 'solana' AS chain, u.mint, to_unixtime(u.evt_block_time) AS ts, u.evt_block_slot AS slot, u.evt_tx_index AS txi,
       u.evt_outer_instruction_index AS oix, u.evt_inner_instruction_index AS iix, u.evt_tx_id AS tx_id,
       CAST(u.virtual_token_reserves AS varchar) AS vtr_old, CAST(u.virtual_sol_reserves AS varchar) AS vsr_old,
       CAST(u.new_virtual_token_reserves AS varchar) AS vtr_new, CAST(u.new_virtual_sol_reserves AS varchar) AS vsr_new,
       CAST(u.real_token_reserves AS varchar) AS rtr, CAST(u.real_sol_reserves AS varchar) AS rsr
FROM pumpdotfun_solana.pump_evt_updatemayhemvirtualparamsevent u
JOIN coins k ON k.mint = u.mint
WHERE u.evt_block_date BETWEEN DATE '{w0}' AND DATE '{t1}'
  AND u.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
"""


def u64(off):
    """原始字节第 off 起 8 字节小端 u64 → DECIMAL（bytearray_to_bigint 是有符号的，负值加 2^64）。"""
    e = "bytearray_to_bigint(reverse(bytearray_substring(b, %s, 8)))" % off
    return (
        "(CAST(%s AS DECIMAL(38,0)) + CASE WHEN %s < 0 THEN DECIMAL '18446744073709551616' ELSE DECIMAL '0' END)"
        % (e, e)
    )


def build(layer, monday, n=100, sample=None):
    if monday.weekday() != 0:
        raise SystemExit("周一才是周的起点")
    w1 = monday + dt.timedelta(days=6)
    cutoff = dt.date.fromisoformat(CUTOFF)
    if monday >= cutoff:
        raise SystemExit("前向批次的周不取")
    names = (DQ35 / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    smp = smp_raw = ""
    if sample:
        smp = (
            "\n      AND created_at >= TIMESTAMP '%s' AND created_at < TIMESTAMP '%s'"
            % sample
        )
        smp_raw = (
            " AND evt_block_time >= TIMESTAMP '%s' AND evt_block_time < TIMESTAMP '%s'"
            % sample
        )
    tdays = 1 if layer == "META" else 7
    t1 = min(cutoff - dt.timedelta(days=1), w1 + dt.timedelta(days=tdays))
    r0 = max(monday, dt.date.fromisoformat(QUOTE_FIELDS_FROM))
    f = dict(
        layer=layer,
        names=names,
        w0=monday.isoformat(),
        w1=w1.isoformat(),
        t1=t1.isoformat(),
        tdays=tdays,
        sample=smp,
        sample_raw=smp_raw,
        cutoff=CUTOFF,
        cutoff_m1=(cutoff - dt.timedelta(days=1)).isoformat(),
        program=PROGRAM,
        d_trade=D_TRADE,
        r0=r0.isoformat(),
        n=int(n),
    )
    head = POP.format(**f)
    if layer == "M":
        return head + M.format(**f)
    if layer == "META":
        cols, joins = [], []
        for h in HZ:
            a = "s%d" % h
            sfx = {30: "30s", 300: "5m", 3600: "1h", 86400: "24h"}[h]
            cols.append(
                "       COALESCE({a}.n, 0) AS n_{s}, COALESCE({a}.n_buy, 0) AS nbuy_{s}, COALESCE({a}.n_users, 0) AS users_{s}, "
                "CAST({a}.sol_buy AS varchar) AS solb_{s}, CAST({a}.sol_sell AS varchar) AS sols_{s}, CAST({a}.x_last AS varchar) AS x_{s}, "
                "CAST({a}.y_last AS varchar) AS y_{s}, CAST({a}.x_max AS varchar) AS xmax_{s}, COALESCE({a}.n_mayhem, 0) AS nmay_{s}".format(
                    a=a, s=sfx
                )
            )
            joins.append(
                "LEFT JOIN s {a} ON {a}.mint = k.mint AND {a}.hz = {h}".format(a=a, h=h)
            )
        f.update(
            hz_values=", ".join(str(h) for h in HZ),
            hz_cols=",\n".join(cols),
            hz_joins="\n".join(joins),
        )
        return head + META.format(**f)
    if layer == "T":
        use_raw = t1 >= r0
        raw = (
            RAW.format(
                u64_sol=u64(49),
                u64_qa=u64("base + 32"),
                u64_vqr=u64("base + 40"),
                u64_rqr=u64("base + 48"),
                u64_hrb=u64("base + 56"),
                u64_hr=u64("base + 64"),
                **f,
            )
            if use_raw
            else ""
        )
        return head + T.format(
            raw=raw,
            raw_cols=RAW_COLS.format(**f) if use_raw else "",
            raw_join="\nLEFT JOIN rv ON rv.tx_id = r.tx_id AND rv.oix = r.oix AND rv.iix IS NOT DISTINCT FROM r.iix"
            if use_raw
            else "",
            **f,
        )
    if layer == "RAWC":
        return head + RAWC.format(**f)
    if layer == "MAY":
        return head + MAY.format(**f)
    raise SystemExit("未知层 %s" % layer)


def main():
    a = sys.argv[1:]
    layer, monday, label = a[0], dt.date.fromisoformat(a[1]), a[2]
    n, sample = 100, None
    i = 3
    while i < len(a):
        if a[i] == "--n":
            n = int(a[i + 1])
            i += 2
        elif a[i] == "--sample":
            sample = (a[i + 1], a[i + 2])
            i += 3
        else:
            raise SystemExit("未知参数 %s" % a[i])
    (H / "sql" / ("%s.sql" % label)).write_text(build(layer, monday, n, sample))
    print("sql/%s.sql" % label)


if __name__ == "__main__":
    main()
