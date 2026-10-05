#!/usr/bin/env python3
"""DQ-35 v2.2（10-05）：毕业前留存 SQL（曲线完成前 300 秒的曲线成交，5 秒桶）。只存不分析。链固定为 Solana。

v2.2 相对 v2.1（GPT 批 1a-i）：查不到代号（symbol 为 NULL）单列 no_symbol 类并排除，M 层类别互斥、输出 identity_gap；
首末事件输出 tx_id（只为保留的事件键建映射）；cashback、回购费分别计缺失（n_cb_null、n_bb_null）；ovf 另查 slot、交易序号为空；
时间列由 to_unixtime 输出 DOUBLE。以下为 v2.1 的说明。

python build_gradpre_sql_v22.py <层> <完成起日> <完成止日> <标签> [--sample <起时> <止时>]  → sql/<标签>.sql
层：B＝分桶；M＝母体计数。--sample 只用于小样本对照：把母体限制为曲线完成时刻在 [起时, 止时) 的币。

“截至何时可知”：每个币的桶都以曲线完成时刻为锚（bkey＝完成前第几个 5 秒），只有在完成之后才知道这个币属于母体。
所以本表只能服务“完成（毕业）之后才决策”的实验；用于曲线阶段入场即按结局选样，禁止。

相对 v2（build_gradpre_sql_v2.py）的改动：
 1. 金额精度：一律 CAST 成 DECIMAL(38,0) 做整数运算与求和，输出 varchar；SOL 用 lamports，代币用原始最小单位（pump 为 6 位）。
 2. 事件唯一键：mint＋slot＋交易序号＋外层＋内层（内层为空记 −1），首末事件各输出四个整数列；ord 只在 SQL 内部排序用。
 3. 时间输出 epoch 秒；不承担槽内排序。
 4. mayhem 币（2026-04 起）的 TradeEvent 虚拟 SOL 不满足“成交后＝成交前±金额”（v2 样本 2,349/5,139），
    成交前储备的推算对它无效：x_pre_first、y_pre_first 对 mayhem 币输出 NULL，另给 pre_valid 标志；
    成交后原值（x_post_first 等）与首笔金额照存。不硬编码 v2 样本里的倍数。
 5. 非 SOL 计价的曲线（quote_mint 非空，且既不是 wSOL 也不是默认公钥 111…1）：Dune 解码表没有 virtual_quote_reserves、real_quote_reserves
    （官方 IDL 有），sol_amount 与虚拟 SOL 储备在这些币上的单位未经核实，所以 sol_unit_ok＝false、pre_valid＝false；
    quote_amount 按原始最小单位照存，decimals 不在曲线事件里，取同一币 P 层的 qd。主分析只用 SOL 计价（总控第十八轮）。
 6. 费用：协议费、创作者费、cashback、回购费按原始整数求和；n_fee_null 计空值笔数（不把空值当 0）。
 7. 完成止日最晚 2026-10-04（总控第十六轮 R3；v2 截至 09-29 的理由只适用于 PumpSwap，GPT 10-04 复核第 6 条）。
 8. M 层：完成事件数、查不到曲线创建事件的、封存周排除、留出同名排除、纳入数，及纳入币按计价资产与 mayhem 分层计数。
排除（与 GRAD v2.1 同口径）：封存周按曲线创建时刻；代号与币安留出哈希命中名同名的币（_holdout_names.sqlpart）；查不到曲线创建事件的币。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
LAST_DAY = dt.date(2026, 10, 4)
WSOL = "So11111111111111111111111111111111111111112"
# 曲线账户在新增 quote_mint 字段之前创建的币，该字段为默认公钥，计价资产是 SOL（F27③；2026-09-23 样本 51/51 个完成事件如此）
DEFAULT_PK = "11111111111111111111111111111111"

HEAD = """/* DQ-35 v2.2 数据留存（10-05，执行模型）：层 {layer}；Solana；曲线完成于 {e_start}～{e_end} 的 pump 币；只存不分析；由 build_gradpre_sql_v22.py 生成 */
WITH
{names},
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at, min_by(quote_mint, evt_block_time) AS c_quote_mint
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
    GROUP BY 1
),
cc AS (
    SELECT mint, min(evt_block_time) AS curve_created_at, min_by(symbol, evt_block_time) AS symbol
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{e_end}'
      AND mint IN (SELECT mint FROM comp)
    GROUP BY 1
),
call AS (
    /* 互斥类别，按此顺序：无曲线创建 → 封存 → 无代号 → 留出同名 → 纳入 */
    SELECT c.mint, c.completed_at, c.c_quote_mint, s.curve_created_at, s.symbol,
           CASE WHEN s.curve_created_at IS NULL THEN 'no_create'
                WHEN s.curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND s.curve_created_at < TIMESTAMP '2026-07-13 00:00:00' THEN 'sealed'
                WHEN s.symbol IS NULL THEN 'no_symbol'
                WHEN upper(trim(replace(s.symbol, '$', ''))) IN (SELECT base FROM excl) THEN 'holdout_name'
                ELSE 'in' END AS cls
    FROM comp c
    LEFT JOIN cc s ON s.mint = c.mint
    WHERE c.completed_at >= TIMESTAMP '{e_start} 00:00:00'{sample}
),
mints AS (
    SELECT mint, completed_at, c_quote_mint, curve_created_at,
           (c_quote_mint IS NULL OR c_quote_mint IN ('{wsol}', '{default_pk}')) AS sol_quote
    FROM call
    WHERE cls = 'in'
)"""

BUCKETS = """,
tr AS (
    SELECT t.mint, m.completed_at, m.curve_created_at, m.c_quote_mint, m.sol_quote, t.evt_block_time AS ts,
           t.evt_block_slot AS slot, t.evt_tx_index AS txi, t.evt_outer_instruction_index AS oix,
           COALESCE(t.evt_inner_instruction_index, -1) AS iix, t.evt_tx_id AS tx_id,
           CAST(t.evt_block_slot AS BIGINT) * 10000000000 + CAST(t.evt_tx_index AS BIGINT) * 100000
             + CAST(t.evt_outer_instruction_index AS BIGINT) * 1000 + CAST(COALESCE(t.evt_inner_instruction_index, -1) AS BIGINT) AS ord,
           CASE WHEN t.evt_block_slot IS NULL OR t.evt_tx_index IS NULL OR t.evt_tx_index < 0 OR t.evt_outer_instruction_index < 0
                  OR t.evt_tx_index >= 100000 OR t.evt_outer_instruction_index >= 100 OR t.evt_outer_instruction_index IS NULL
                  OR COALESCE(t.evt_inner_instruction_index, -1) >= 1000 OR t.evt_inner_instruction_index IS NULL
                THEN 1 ELSE 0 END AS ovf,
           COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DECIMAL(38,0)) AS sol,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DECIMAL(38,0)) AS tok,
           CAST(t.quote_amount AS DECIMAL(38,0)) AS qa,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DECIMAL(38,0)) AS x,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DECIMAL(38,0)) AS y,
           CAST(t.real_sol_reserves AS DECIMAL(38,0)) AS xr,
           CAST(t.fee AS DECIMAL(38,0)) AS f_pr,
           CAST(t.creator_fee AS DECIMAL(38,0)) AS f_cr,
           CAST(t.cashback AS DECIMAL(38,0)) AS f_cb,
           CAST(t.buyback_fee AS DECIMAL(38,0)) AS f_bb,
           COALESCE(t.mayhem_mode, false) AS mayhem
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN mints m ON m.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{t_start}' AND DATE '{e_end}'
      AND t.evt_block_time > m.completed_at - INTERVAL '300' SECOND
      AND t.evt_block_time <= m.completed_at
)
SELECT 'solana' AS chain, mint, to_unixtime(completed_at) AS completed_t, to_unixtime(curve_created_at) AS curve_created_t, c_quote_mint,
       sol_quote AS sol_unit_ok, max(CASE WHEN mayhem THEN 1 ELSE 0 END) AS mayhem,
       CAST(floor(date_diff('millisecond', ts, completed_at) / 5000e0) AS BIGINT) AS bkey,
       count(*) AS n, count_if(is_buy) AS n_buy, approx_distinct(usr) AS n_users,
       CAST(sum(CASE WHEN is_buy THEN sol ELSE 0 END) AS varchar) AS sol_buy,
       CAST(sum(CASE WHEN NOT is_buy THEN sol ELSE 0 END) AS varchar) AS sol_sell,
       CAST(sum(CASE WHEN is_buy THEN tok ELSE 0 END) AS varchar) AS tok_buy,
       CAST(sum(CASE WHEN NOT is_buy THEN tok ELSE 0 END) AS varchar) AS tok_sell,
       CAST(sum(CASE WHEN is_buy THEN qa END) AS varchar) AS qa_buy,
       CAST(sum(CASE WHEN NOT is_buy THEN qa END) AS varchar) AS qa_sell,
       CAST(max(CASE WHEN is_buy THEN sol END) AS varchar) AS max_buy_sol,
       CAST(sum(f_pr) AS varchar) AS f_pr, CAST(sum(f_cr) AS varchar) AS f_cr,
       CAST(sum(f_cb) AS varchar) AS f_cb, CAST(sum(f_bb) AS varchar) AS f_bb,
       count_if(f_pr IS NULL OR f_cr IS NULL) AS n_fee_null,
       count_if(f_cb IS NULL) AS n_cb_null, count_if(f_bb IS NULL) AS n_bb_null,
       min_by(slot, ord) AS slot_f, min_by(txi, ord) AS txi_f, min_by(oix, ord) AS oix_f, min_by(iix, ord) AS iix_f,
       min_by(tx_id, ord) AS tx_f,
       max_by(slot, ord) AS slot_l, max_by(txi, ord) AS txi_l, max_by(oix, ord) AS oix_l, max_by(iix, ord) AS iix_l,
       max_by(tx_id, ord) AS tx_l,
       min_by(is_buy, ord) AS buy_first, CAST(min_by(sol, ord) AS varchar) AS sol_first, CAST(min_by(tok, ord) AS varchar) AS tok_first,
       CAST(min_by(x, ord) AS varchar) AS x_post_first, CAST(min_by(y, ord) AS varchar) AS y_post_first,
       CASE WHEN sol_quote AND max(CASE WHEN mayhem THEN 1 ELSE 0 END) = 0 THEN true ELSE false END AS pre_valid,
       CASE WHEN sol_quote AND max(CASE WHEN mayhem THEN 1 ELSE 0 END) = 0
            THEN CAST(min_by(CASE WHEN is_buy THEN x - sol ELSE x + sol END, ord) AS varchar) END AS x_pre_first,
       CASE WHEN sol_quote AND max(CASE WHEN mayhem THEN 1 ELSE 0 END) = 0
            THEN CAST(min_by(CASE WHEN is_buy THEN y + tok ELSE y - tok END, ord) AS varchar) END AS y_pre_first,
       max_by(is_buy, ord) AS buy_last,
       CAST(max_by(x, ord) AS varchar) AS x_last, CAST(max_by(y, ord) AS varchar) AS y_last, CAST(max_by(xr, ord) AS varchar) AS xr_last,
       to_unixtime(min(ts)) AS t_first, to_unixtime(max(ts)) AS t_last,
       sum(ovf) AS n_ord_overflow
FROM tr
GROUP BY mint, completed_at, curve_created_at, c_quote_mint, sol_quote,
         CAST(floor(date_diff('millisecond', ts, completed_at) / 5000e0) AS BIGINT)
"""

META = """
SELECT 'solana' AS chain, count(*) AS n_completed,
       count_if(cls = 'no_create') AS n_no_curve_create, count_if(cls = 'sealed') AS n_sealed,
       count_if(cls = 'no_symbol') AS n_no_symbol, count_if(cls = 'holdout_name') AS n_holdout_name,
       count_if(cls = 'in') AS n_included,
       (SELECT count_if(sol_quote) FROM mints) AS n_included_sol,
       (SELECT count_if(c_quote_mint = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v') FROM mints) AS n_included_usdc,
       (SELECT count_if(NOT sol_quote AND c_quote_mint <> 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v') FROM mints) AS n_included_other,
       count(*) - count_if(cls IN ('no_create', 'sealed', 'no_symbol', 'holdout_name', 'in')) AS identity_gap
FROM call
"""


def build(layer, e_start, e_end, sample=None):
    if e_end > LAST_DAY:
        raise SystemExit("完成止日不能晚于 %s（总控第十六轮 R3）" % LAST_DAY)
    if layer not in ("B", "M"):
        raise SystemExit("层只能是 B、M")
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    smp = ""
    if sample:
        smp = (
            "\n      AND c.completed_at >= TIMESTAMP '%s' AND c.completed_at < TIMESTAMP '%s'"
            % sample
        )
    fmt = dict(
        layer=layer,
        names=names,
        e_start=e_start.isoformat(),
        e_end=e_end.isoformat(),
        t_start=(e_start - dt.timedelta(days=1)).isoformat(),
        sample=smp,
        wsol=WSOL,
        default_pk=DEFAULT_PK,
    )
    head = HEAD.format(**fmt)
    return head + (BUCKETS.format(**fmt) if layer == "B" else META)


def main():
    a = sys.argv[1:]
    layer, e_start, e_end, label = (
        a[0],
        dt.date.fromisoformat(a[1]),
        dt.date.fromisoformat(a[2]),
        a[3],
    )
    sample = None
    if len(a) > 4 and a[4] == "--sample":
        sample = (a[5], a[6])
    (H / "sql" / ("%s.sql" % label)).write_text(build(layer, e_start, e_end, sample))
    print("sql/%s.sql" % label)


if __name__ == "__main__":
    main()
