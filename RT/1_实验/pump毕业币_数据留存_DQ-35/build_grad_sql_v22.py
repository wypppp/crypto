#!/usr/bin/env python3
"""DQ-35 v2.2（10-05）：毕业后留存 SQL，按 GPT 批 1a-i（基于 9021a53f，“改后重取”）与总控第十九轮整改。只存不分析。

python build_grad_sql_v22.py <层> <事件起日> <事件止日> <标签> [--sample <起时> <止时> [--nonsol]]  → sql/<标签>.sql
层：B＝分桶；P＝池头与固定时点快照；L＝加撤池与 boost 逐笔；M＝母体计数。链固定为 Solana。

相对 v2.1（build_grad_sql_v21.py）的改动：
 1. 虚拟报价储备 vq 逐笔解码（总控第十九轮第二节）：事件日期 ≥ 2026-07-15（官方文档引入该字段）的买卖，从
    solana.instruction_calls 里 PumpSwap 的事件自调用原始字节解码 vq（i128 小端有符号）与买入的 cashback、回购费，
    按（交易、外层、内层指令号、方向）与解码事件表对齐（PROBE22e：129,916 笔一一对上、两边多出 0、重复键 0）。
    每笔成交带成交时的 vq，“可知时点”就是这笔成交；不假设池内恒定。07-15 之前、以及 07-15～07-16 升级前的事件布局没有 vq 字段，
    按协议记 0（vq_src='layout0'，按事件字节长度判断）；对不上原始字节的记缺失（'missing'，vq 为空）。
    高 8 字节超出 ±4e18 的记溢出、vq 置空并计数（DECIMAL(38,0) 放不下）。vq 是有符号值。
 2. 区间反解只作交叉核对：每笔卖出由 quote_out＝floor((q0＋vq)·b_in／(b0＋b_in)) 反解的整数区间应含该笔的 vq，
    越界计数 n_xchk_fail 必须为 0；乘法前检查量级（b0＋b_in＜1e19、quote_out＋1＜1e18），超出则不核并计 n_xchk_skip。
 3. 价格：每笔用自己的 vq 算成交后价格 ((q1＋vq)／10^qd)／(b1／10^bd)（DOUBLE，只作描述）；vq 未知的笔价格置空、计数。
    有效报价储备（q＋vq）决定报价；真实金库 q 决定支付能力，vq 不是现金。
 4. 快照（GPT 批 1a-i 第 2 条）：状态流＝建池事件＋成交＋加撤池（解码表）＋boost 两类事件（原始字节：InitBoost、
    BoostBuyAndBurn，PROBE22e 10 分钟内 7＋144 笔）。每个时点 T＝建池＋o 秒存五个字段：
      target_time＝T；state_time＝T 之前最后一个状态事件的时刻；known_at＝state_time（链上确认时刻，不含我方数据接收延迟）；
      coverage：ok／gap（该事件后状态与下一事件前状态不符：有无事件的变化，如直接转入金库）／partial（最后事件是 InitBoost，
      不给代币储备）／unverified（前后事件有一方不带储备，如下一事件是 boost，核不了）／no_next（窗口内再无事件）／
      immature（T 晚于事件止日）；gap_flag＝coverage 不是 ok。
    同一秒的事件一律算在 T 之后（block_time 只到秒，保守）。快照只给 T 时的池状态；执行延迟按每张卡登记的 τ＋δ，
    卡要用的时点必须在网格里，不拿“下一笔成交”代替。另存 mature_7d（建池＋7 天不晚于事件止日次日零点）。
 5. 保留事件的交易映射：分桶首末笔、快照前后事件都输出 tx_id（只为被保留的事件键建映射，不建全量映射）。
 6. 唯一性与越界：ovf 另查 slot、交易序号、外层为空；B 层输出 n_ord_overflow，验收要求全为 0（check_manifest_v22 阻断）。
 7. 母体：查不到代号（symbol 为 NULL）单列 no_symbol 类并排除（v2.1 被 NOT IN 静默排除）；M 层输出 identity_gap＝
    候选−(无曲线创建＋封存＋无代号＋留出同名＋纳入)，必须为 0。类别按此顺序互斥。
 8. cashback、回购费分别计缺失：n_cb_null、n_bb_null（07-15 之前的买入为未知，不并入 0）。
 9. 时间列由 to_unixtime 输出 DOUBLE（epoch 秒，带小数），读取时按十进制文本解析（dev_gate.to_epoch）。
沿用 v2.1：金额 DECIMAL(38,0) 整数运算、输出文本；事件唯一键四列；分桶 S／M／H／D；非 SOL 分层；事件止日 2026-10-04。

10-06 收口整改（总控第二十一轮第三节；GPT 批 1a-i 增量复核①～③，“现在”各项）：
 a. 解码版本固定：官方 IDL 取 pump-fun/pump-public-docs 提交 e0687ae9b7e064a0f54efc7297c65eecfbba3a8f（pump_amm.json、pump.json），
    另存 vq 字段引入时的 2c22246b670812e2392e5f94b9543f500d6c9e15；副本与 sha256 在 idl/。偏移按这两版逐字段核对一致。
 b. 旧布局规则：只有“已核对的旧布局”记 vq＝0（layout0）。已核对＝升级完成（2026-07-15 18:07:32 UTC）之前、且（事件, 字节长度）
    在白名单里：卖出 320/368/384/400，买入 320/368/401/416/431/432/447/448/463（PROBE21c 与 PROBE24 按月核对：2025-03～2026-06
    每月一个开发周日、2026-07-14 与 07-15 升级前，全部池子，升级前没有一笔带 vq 字段）。07-15 之前的事件不扫原始字节，
    按升级时刻记 layout0_date。升级后缺 vq 字段、异常长度、白名单外的旧长度，一律记 unknown（vq 为空），与 missing 一样阻断验收。
 c. 高 8 字节用上下界比较（不用 abs，避免 −2^63 越界）；费用（cashback、回购费）与 boost 储备按无符号 u64 解码（负值加 2^64）。
 d. 唯一性：聚合前按源事件键（slot、交易序号、外层、内层）计重复，B 层输出 n_src_dup，P 层输出 n_src_dup_7d，验收要求 0；
    B 层另出 n_vq_unknown、n_vq_missing，P 层出 n_vq_bad_7d。
 f. B 层 n_users 改为精确去重 count(DISTINCT)（原 approx_distinct，0714x 样本 57 个桶与精确值不同；执行模型自查，数据失真类）。
 e. 快照质量的可知时间：coverage 用了 T 之后的下一个事件，所以另存 qknown{o}_at（下一个事件的时刻；没有下一个事件时为事件止日次日
    零点；immature 为空）。coverage 与 gap_flag 只作事后诊断，T 时的决策不能用。known_at 仍是状态本身的可知时间。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
PUMPSWAP_START = dt.date(2025, 3, 15)
LAST_EVENT_DAY = dt.date(2026, 10, 4)
VQ_START = dt.date(2026, 7, 15)
UPGRADE_END = (
    "2026-07-15 18:07:32"  # 带 vq 字段的最早一笔（PROBE 07-14 组）；此前为旧程序
)
KNOWN_OLD = dict(  # 已核对的旧布局（事件字节长度，含 16 字节前缀）：PROBE21c、PROBE24
    sell=(320, 368, 384, 400),
    buy=(320, 368, 401, 416, 431, 432, 447, 448, 463),
)
U64 = "(CAST({e} AS DECIMAL(38,0)) + CASE WHEN {e} < 0 THEN DECIMAL '18446744073709551616' ELSE DECIMAL '0' END)"


def u64(e):
    """有符号 BIGINT 读出的 u64 → 无符号 DECIMAL。"""
    return U64.format(e=e)


OFFSETS = (2, 10, 45, 60, 75, 900, 3600, 86400)
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
DISC = dict(
    buy="0x67f4521f2cf57777",
    sell="0x3e2f370aa503dc2a",
    init_boost="0xae7c4af90451f611",
    buy_burn="0x3f451c16305cc2b9",
)

HEAD = """/* DQ-35 v2.2 数据留存（10-05，执行模型）：层 {layer}；Solana；pump 迁移池在 {e_start}～{e_end} 的事件；只存不分析；由 build_grad_sql_v22.py 生成 */
WITH
{names},
cp AS (
    /* 由 pump 程序在迁移交易里创建、池序号为 0 的 PumpSwap 池；建池后储备＝pool_*_amount */
    SELECT pool, min(evt_block_time) AS created_at, max(base_mint) AS mint, max(quote_mint) AS quote_mint,
           max(base_mint_decimals) AS bd, max(quote_mint_decimals) AS qd,
           min_by(evt_block_slot, evt_block_time) AS c_slot, min_by(evt_tx_index, evt_block_time) AS c_txi,
           min_by(evt_outer_instruction_index, evt_block_time) AS c_oix,
           min_by(COALESCE(evt_inner_instruction_index, -1), evt_block_time) AS c_iix,
           min_by(evt_tx_id, evt_block_time) AS c_tx,
           CAST(min_by(pool_quote_amount, evt_block_time) AS DECIMAL(38,0)) AS c_q,
           CAST(min_by(pool_base_amount, evt_block_time) AS DECIMAL(38,0)) AS c_b
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '{p_start}' AND DATE '{e_end}'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1
),
cand AS (
    SELECT * FROM cp
    WHERE created_at >= TIMESTAMP '{e_start} 00:00:00' - INTERVAL '180' DAY
      AND created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY{sample}
),
cc AS (
    /* 曲线创建事件，全历史 */
    SELECT mint, min(evt_block_time) AS curve_created_at, min_by(symbol, evt_block_time) AS symbol
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{e_end}'
      AND mint IN (SELECT mint FROM cand)
    GROUP BY 1
),
lab AS (
    /* 互斥类别，按此顺序：无曲线创建 → 封存 → 无代号 → 留出同名 → 纳入 */
    SELECT c.*, s.curve_created_at, s.symbol,
           CASE WHEN s.curve_created_at IS NULL THEN 'no_create'
                WHEN s.curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND s.curve_created_at < TIMESTAMP '2026-07-13 00:00:00' THEN 'sealed'
                WHEN s.symbol IS NULL THEN 'no_symbol'
                WHEN upper(trim(replace(s.symbol, '$', ''))) IN (SELECT base FROM excl) THEN 'holdout_name'
                ELSE 'in' END AS cls
    FROM cand c
    LEFT JOIN cc s ON s.mint = c.mint
),
pools AS (SELECT * FROM lab WHERE cls = 'in')"""

# 07-15 起：PumpSwap 事件自调用的原始字节（只取成功交易）。偏移按官方 IDL main（PROBE21b 逐字段核对，1 起算）：
#   买入：ix_name 长度在 410～413，cashback_bps 在 414＋n，cashback 422＋n，回购 bps 430＋n，回购费 438＋n，vq 446＋n；
#   卖出：cashback_bps 369，cashback 377，回购 bps 385，回购费 393，vq 401；
#   InitBoost：pool 89～120，vq 121～136，真实报价储备 137～144；
#   BoostBuyAndBurn：pool 89～120，vq 177～192，真实报价储备 193～200，代币储备 201～208。
RAW = """,
ic AS (
    SELECT tx_id, block_slot AS slot, tx_index AS txi, outer_instruction_index AS oix, inner_instruction_index AS iix,
           block_time AS ts, data AS b, bytearray_substring(data, 9, 8) AS disc
    FROM solana.instruction_calls
    WHERE block_date BETWEEN DATE '{r_start}' AND DATE '{r_end}'
      AND executing_account = '{program}'
      AND is_inner = true AND tx_success = true
      AND bytearray_substring(data, 1, 8) = 0xe445a52e51cb9a1d
      AND bytearray_substring(data, 9, 8) IN ({d_buy}, {d_sell}, {d_init}, {d_burn})
),
icp AS (
    SELECT ic.*,
           CASE WHEN disc = {d_buy} THEN 446 + CAST(bytearray_to_bigint(reverse(bytearray_substring(b, 410, 4))) AS INTEGER)
                WHEN disc = {d_sell} THEN 401 WHEN disc = {d_init} THEN 121 WHEN disc = {d_burn} THEN 177 END AS pv,
           CASE WHEN disc = {d_buy} THEN 414 + CAST(bytearray_to_bigint(reverse(bytearray_substring(b, 410, 4))) AS INTEGER) END AS pc
    FROM ic
),
icv AS (
    SELECT icp.*,
           CASE WHEN length(b) >= pv + 15 THEN bytearray_to_bigint(reverse(bytearray_substring(b, pv, 8))) END AS lo_s,
           CASE WHEN length(b) >= pv + 15 THEN bytearray_to_bigint(reverse(bytearray_substring(b, pv + 8, 8))) END AS hi_s
    FROM icp
),
icl AS (
    /* 布局类别：raw＝带完整 vq 字段；layout0＝升级前、且（事件, 长度）在已核对白名单里；其余 unknown（阻断验收） */
    SELECT icv.*, length(b) AS blen,
           CASE WHEN hi_s IS NOT NULL THEN 'raw'
                WHEN ts < TIMESTAMP '{upgrade_end}'
                     AND ((disc = {d_sell} AND length(b) IN ({old_sell})) OR (disc = {d_buy} AND length(b) IN ({old_buy})))
                THEN 'layout0'
                ELSE 'unknown' END AS layout,
           hi_s IS NOT NULL AND hi_s > -4000000000000000000 AND hi_s < 4000000000000000000 AS hi_ok
    FROM icv
),
rv AS (
    SELECT tx_id, slot, txi, oix, iix, ts, disc, blen, layout,
           CASE WHEN disc = {d_buy} THEN 'B' WHEN disc = {d_sell} THEN 'S' WHEN disc = {d_init} THEN 'I' ELSE 'U' END AS kind,
           CASE WHEN layout = 'layout0' THEN DECIMAL '0'
                WHEN layout = 'raw' AND hi_ok
                THEN CAST(hi_s AS DECIMAL(38,0)) * DECIMAL '18446744073709551616' + CAST(lo_s AS DECIMAL(38,0))
                     + CASE WHEN lo_s < 0 THEN DECIMAL '18446744073709551616' ELSE DECIMAL '0' END END AS vq,
           CASE WHEN layout = 'raw' AND NOT hi_ok THEN 1 ELSE 0 END AS vq_ovf,
           CASE WHEN disc = {d_buy} AND length(b) >= pc + 31 THEN {u_cb} END AS cb,
           CASE WHEN disc = {d_buy} AND length(b) >= pc + 31 THEN {u_bb} END AS bb,
           CASE WHEN disc IN ({d_init}, {d_burn}) THEN to_base58(bytearray_substring(b, 89, 32)) END AS boost_pool,
           CASE WHEN disc = {d_init} THEN {u_iq}
                WHEN disc = {d_burn} THEN {u_uq} END AS boost_q1,
           CASE WHEN disc = {d_burn} THEN {u_ub} END AS boost_b1
    FROM icl
)"""

EVENTS = """,
ev0 AS (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
           evt_outer_instruction_index AS oix, evt_inner_instruction_index AS iix0, evt_tx_id AS tx_id,
           'B' AS side, "user" AS usr,
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)) AS q0,
           CAST(pool_base_token_reserves AS DECIMAL(38,0)) AS b0,
           CAST(quote_amount_in_with_lp_fee AS DECIMAL(38,0)) AS q_pool,
           CAST(base_amount_out AS DECIMAL(38,0)) AS b_amt,
           CAST(user_quote_amount_in AS DECIMAL(38,0)) AS q_user,
           CAST(lp_fee AS DECIMAL(38,0)) AS f_lp,
           CAST(protocol_fee AS DECIMAL(38,0)) AS f_pr,
           CAST(coin_creator_fee AS DECIMAL(38,0)) AS f_cr,
           CAST(NULL AS DECIMAL(38,0)) AS f_cb0, CAST(NULL AS DECIMAL(38,0)) AS f_bb0,
           CAST(NULL AS DECIMAL(38,0)) AS q_gross_out
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date BETWEEN DATE '{ev_start}' AND DATE '{ev_end}'
    UNION ALL
    SELECT pool, evt_block_time, evt_block_slot, evt_tx_index,
           evt_outer_instruction_index, evt_inner_instruction_index, evt_tx_id,
           'S', "user",
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)),
           CAST(pool_base_token_reserves AS DECIMAL(38,0)),
           CAST(quote_amount_out AS DECIMAL(38,0)) - COALESCE(CAST(lp_fee AS DECIMAL(38,0)), 0),
           CAST(base_amount_in AS DECIMAL(38,0)),
           CAST(user_quote_amount_out AS DECIMAL(38,0)),
           CAST(lp_fee AS DECIMAL(38,0)),
           CAST(protocol_fee AS DECIMAL(38,0)),
           CAST(coin_creator_fee AS DECIMAL(38,0)),
           CAST(cashback AS DECIMAL(38,0)),
           CAST(buyback_fee AS DECIMAL(38,0)),
           CAST(quote_amount_out AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date BETWEEN DATE '{ev_start}' AND DATE '{ev_end}'
),
ev AS (
    SELECT e.pool, e.ts, e.slot, e.txi, e.oix, COALESCE(e.iix0, -1) AS iix, e.tx_id, e.side, e.usr,
           e.q0, e.b0, e.q_pool, e.b_amt, e.q_user, e.f_lp, e.f_pr, e.f_cr, e.q_gross_out,
           CASE WHEN e.side = 'S' THEN e.f_cb0 ELSE {cb_expr} END AS f_cb,
           CASE WHEN e.side = 'S' THEN e.f_bb0 ELSE {bb_expr} END AS f_bb,
           {vq_expr} AS vq, {vq_src_expr} AS vq_src, {vq_ovf_expr} AS vq_ovf
    FROM ev0 e{rv_join}
),
k AS (
    SELECT e.*, p.created_at, p.bd, p.qd,
           count(*) OVER (PARTITION BY e.slot, e.txi, e.oix, e.iix) AS n_key,  /* 源事件键重复（聚合前；含原始字节连接造成的重复） */
           CASE WHEN e.side = 'B' THEN e.q0 + e.q_pool ELSE e.q0 - e.q_pool END AS q1,
           CASE WHEN e.side = 'B' THEN e.b0 - e.b_amt ELSE e.b0 + e.b_amt END AS b1,
           date_diff('millisecond', p.created_at, e.ts) AS age_ms,
           CAST(e.slot AS BIGINT) * 10000000000 + CAST(e.txi AS BIGINT) * 100000
             + CAST(e.oix AS BIGINT) * 1000 + CAST(e.iix AS BIGINT) AS ord,
           CASE WHEN e.slot IS NULL OR e.txi IS NULL OR e.oix IS NULL OR e.txi >= 100000 OR e.txi < 0
                  OR e.oix >= 100 OR e.oix < 0 OR e.iix >= 1000 OR e.iix < 0
                THEN 1 ELSE 0 END AS ovf,
           /* 卖出交叉核对：整数反解区间，量级受限时不核 */
           CASE WHEN e.side = 'S' AND e.b_amt > 0 AND e.b0 + e.b_amt < DECIMAL '10000000000000000000'
                     AND e.q_gross_out + 1 < DECIMAL '1000000000000000000' THEN
                (e.q_gross_out * (e.b0 + e.b_amt) + e.b_amt - 1
                 - mod(e.q_gross_out * (e.b0 + e.b_amt) + e.b_amt - 1, e.b_amt)) / e.b_amt - e.q0 END AS vlo,
           CASE WHEN e.side = 'S' AND e.b_amt > 0 AND e.b0 + e.b_amt < DECIMAL '10000000000000000000'
                     AND e.q_gross_out + 1 < DECIMAL '1000000000000000000' THEN
                ((e.q_gross_out + 1) * (e.b0 + e.b_amt) + e.b_amt - 1
                 - mod((e.q_gross_out + 1) * (e.b0 + e.b_amt) + e.b_amt - 1, e.b_amt)) / e.b_amt - 1 - e.q0 END AS vhi
    FROM ev e
    JOIN pools p ON p.pool = e.pool
    WHERE e.ts >= p.created_at AND e.ts < p.created_at + INTERVAL '{horizon}' DAY
)"""

BUCKETS = """,
kb AS (
    SELECT k.*,
           CASE WHEN age_ms < 300000 THEN 'S' WHEN age_ms < 3600000 THEN 'M'
                WHEN age_ms < 604800000 THEN 'H' ELSE 'D' END AS kind,
           CASE WHEN age_ms < 300000 THEN floor(age_ms / 5000e0)
                WHEN age_ms < 3600000 THEN floor(age_ms / 60000e0)
                WHEN age_ms < 604800000 THEN floor(age_ms / 3600000e0)
                ELSE floor(age_ms / 86400000e0) END AS bkey,
           CASE WHEN age_ms < 300000 THEN 5 WHEN age_ms < 3600000 THEN 60
                WHEN age_ms < 604800000 THEN 3600 ELSE 86400 END AS w,
           CASE WHEN vq IS NOT NULL
                THEN ((CAST(q1 AS DOUBLE) + CAST(vq AS DOUBLE)) / power(10, qd)) / nullif(CAST(b1 AS DOUBLE) / power(10, bd), 0) END AS px
    FROM k
),
kbs AS (
    SELECT kb.*,
           CASE WHEN created_at + bkey * w * INTERVAL '1' SECOND < TIMESTAMP '{e_start} 00:00:00'
                  OR created_at + (bkey + 1) * w * INTERVAL '1' SECOND > TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
                THEN true ELSE false END AS straddle
    FROM kb
)
SELECT 'solana' AS chain, kind, pool, CAST(bkey AS BIGINT) AS bkey, straddle,
       count(*) AS n, count_if(side = 'B') AS n_buy, count(DISTINCT usr) AS n_users,
       array_join(array_sort(array_distinct(array_agg(usr) FILTER (WHERE straddle))), ',') AS users_straddle,
       CAST(sum(CASE WHEN side = 'B' THEN q_user ELSE 0 END) AS varchar) AS q_buy_user,
       CAST(sum(CASE WHEN side = 'S' THEN q_user ELSE 0 END) AS varchar) AS q_sell_user,
       CAST(sum(CASE WHEN side = 'B' THEN q_pool ELSE 0 END) AS varchar) AS q_buy_pool,
       CAST(sum(CASE WHEN side = 'S' THEN q_pool ELSE 0 END) AS varchar) AS q_sell_pool,
       CAST(sum(CASE WHEN side = 'B' THEN b_amt ELSE 0 END) AS varchar) AS b_buy,
       CAST(sum(CASE WHEN side = 'S' THEN b_amt ELSE 0 END) AS varchar) AS b_sell,
       CAST(sum(f_lp) AS varchar) AS f_lp, CAST(sum(f_pr) AS varchar) AS f_pr, CAST(sum(f_cr) AS varchar) AS f_cr,
       CAST(sum(CASE WHEN side = 'B' THEN f_cb END) AS varchar) AS f_cb_buy, CAST(sum(CASE WHEN side = 'B' THEN f_bb END) AS varchar) AS f_bb_buy,
       CAST(sum(CASE WHEN side = 'S' THEN f_cb END) AS varchar) AS f_cb_sell, CAST(sum(CASE WHEN side = 'S' THEN f_bb END) AS varchar) AS f_bb_sell,
       count_if(f_lp IS NULL OR f_pr IS NULL OR f_cr IS NULL) AS n_fee_null,
       count_if(f_cb IS NULL) AS n_cb_null, count_if(f_bb IS NULL) AS n_bb_null,
       min_by(slot, ord) AS slot_f, min_by(txi, ord) AS txi_f, min_by(oix, ord) AS oix_f, min_by(iix, ord) AS iix_f,
       min_by(tx_id, ord) AS tx_f,
       max_by(slot, ord) AS slot_l, max_by(txi, ord) AS txi_l, max_by(oix, ord) AS oix_l, max_by(iix, ord) AS iix_l,
       max_by(tx_id, ord) AS tx_l,
       CAST(min_by(q0, ord) AS varchar) AS q0_open, CAST(min_by(b0, ord) AS varchar) AS b0_open, min_by(side, ord) AS side_first,
       CAST(max_by(q1, ord) AS varchar) AS q1_close, CAST(max_by(b1, ord) AS varchar) AS b1_close, max_by(side, ord) AS side_last,
       CAST(max_by(q_pool, ord) AS varchar) AS q_pool_last, CAST(max_by(b_amt, ord) AS varchar) AS b_amt_last,
       CAST(min_by(vq, ord) AS varchar) AS vq_open, CAST(max_by(vq, ord) AS varchar) AS vq_close,
       CAST(min(vq) AS varchar) AS vq_min, CAST(max(vq) AS varchar) AS vq_max,
       min_by(vq_src, ord) AS vq_src, count_if(vq IS NULL) AS n_vq_null, sum(vq_ovf) AS n_vq_ovf,
       count(vlo) AS n_xchk, count_if(vlo IS NOT NULL AND (vq < vlo OR vq > vhi)) AS n_xchk_fail,
       count_if(side = 'S' AND vlo IS NULL) AS n_xchk_skip,
       max(px) AS px_high, min(px) AS px_low, count_if(px IS NULL) AS n_px_null,
       to_unixtime(min(ts)) AS t_first, to_unixtime(max(ts)) AS t_last,
       sum(ovf) AS n_ord_overflow,
       count_if(n_key > 1) AS n_src_dup, count_if(vq_src = 'unknown') AS n_vq_unknown, count_if(vq_src = 'missing') AS n_vq_missing
FROM kbs
GROUP BY 2, 3, 4, 5
"""

# 快照状态流：建池事件（C）＋成交（B／S）＋加撤池（D／W）＋boost（I／U，07-15 起）。q0/b0＝事件前，q1/b1＝事件后。
STREAM = """,
lq AS (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_outer_instruction_index AS oix,
           COALESCE(evt_inner_instruction_index, -1) AS iix, evt_tx_id AS tx_id, 'D' AS kind,
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)) AS q0, CAST(pool_base_token_reserves AS DECIMAL(38,0)) AS b0,
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)) + CAST(quote_amount_in AS DECIMAL(38,0)) AS q1,
           CAST(pool_base_token_reserves AS DECIMAL(38,0)) + CAST(base_amount_in AS DECIMAL(38,0)) AS b1
    FROM pumpdotfun_solana.pump_amm_evt_depositevent
    WHERE evt_block_date BETWEEN DATE '{ev_start}' AND DATE '{ev_end}'
    UNION ALL
    SELECT pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index,
           COALESCE(evt_inner_instruction_index, -1), evt_tx_id, 'W',
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)), CAST(pool_base_token_reserves AS DECIMAL(38,0)),
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)) - CAST(quote_amount_out AS DECIMAL(38,0)),
           CAST(pool_base_token_reserves AS DECIMAL(38,0)) - CAST(base_amount_out AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
    WHERE evt_block_date BETWEEN DATE '{ev_start}' AND DATE '{ev_end}'
),
st AS (
    SELECT pool, created_at, ts, slot, txi, oix, iix, tx_id, side AS kind, q0, b0, q1, b1, vq, age_ms, ord, vq_src FROM k
    UNION ALL
    SELECT l.pool, p.created_at, l.ts, l.slot, l.txi, l.oix, l.iix, l.tx_id, l.kind, l.q0, l.b0, l.q1, l.b1,
           CAST(NULL AS DECIMAL(38,0)), date_diff('millisecond', p.created_at, l.ts),
           CAST(l.slot AS BIGINT) * 10000000000 + CAST(l.txi AS BIGINT) * 100000 + CAST(l.oix AS BIGINT) * 1000 + CAST(l.iix AS BIGINT),
           'n/a'
    FROM lq l JOIN pools p ON p.pool = l.pool
    WHERE l.ts >= p.created_at AND l.ts < p.created_at + INTERVAL '7' DAY
    UNION ALL
    SELECT pool, created_at, created_at, c_slot, c_txi, c_oix, c_iix, c_tx, 'C', CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)),
           c_q, c_b, CAST(NULL AS DECIMAL(38,0)), 0,
           CAST(c_slot AS BIGINT) * 10000000000 + CAST(c_txi AS BIGINT) * 100000 + CAST(c_oix AS BIGINT) * 1000 + CAST(c_iix AS BIGINT),
           'n/a'
    FROM pools{boost_union}
)"""

BOOST_UNION = """
    UNION ALL
    SELECT r.boost_pool, p.created_at, r.ts, r.slot, r.txi, r.oix, COALESCE(r.iix, -1), r.tx_id, r.kind,
           CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)), r.boost_q1, r.boost_b1, r.vq,
           date_diff('millisecond', p.created_at, r.ts),
           CAST(r.slot AS BIGINT) * 10000000000 + CAST(r.txi AS BIGINT) * 100000 + CAST(r.oix AS BIGINT) * 1000 + CAST(COALESCE(r.iix, -1) AS BIGINT),
           r.layout
    FROM rv r JOIN pools p ON p.pool = r.boost_pool
    WHERE r.kind IN ('I', 'U') AND r.ts >= p.created_at AND r.ts < p.created_at + INTERVAL '7' DAY"""

SNAP_COLS = """,
       max_by(slot, ord) FILTER (WHERE ts < tt{o}) AS a{o}_slot, max_by(txi, ord) FILTER (WHERE ts < tt{o}) AS a{o}_txi,
       max_by(oix, ord) FILTER (WHERE ts < tt{o}) AS a{o}_oix, max_by(iix, ord) FILTER (WHERE ts < tt{o}) AS a{o}_iix,
       max_by(kind, ord) FILTER (WHERE ts < tt{o}) AS a{o}_kind, max_by(tx_id, ord) FILTER (WHERE ts < tt{o}) AS a{o}_tx,
       CAST(max_by(q1, ord) FILTER (WHERE ts < tt{o}) AS varchar) AS a{o}_q1,
       CAST(max_by(b1, ord) FILTER (WHERE ts < tt{o}) AS varchar) AS a{o}_b1,
       to_unixtime(max_by(ts, ord) FILTER (WHERE ts < tt{o})) AS a{o}_t,
       CAST(max_by(vq, ord) FILTER (WHERE ts < tt{o} AND vq IS NOT NULL) AS varchar) AS vq{o},
       count_if(kind IN ('I', 'U') AND ts < tt{o}) AS nboost{o},
       min_by(slot, ord) FILTER (WHERE ts >= tt{o}) AS b{o}_slot, min_by(txi, ord) FILTER (WHERE ts >= tt{o}) AS b{o}_txi,
       min_by(oix, ord) FILTER (WHERE ts >= tt{o}) AS b{o}_oix, min_by(iix, ord) FILTER (WHERE ts >= tt{o}) AS b{o}_iix,
       min_by(kind, ord) FILTER (WHERE ts >= tt{o}) AS b{o}_kind, min_by(tx_id, ord) FILTER (WHERE ts >= tt{o}) AS b{o}_tx,
       CAST(min_by(q0, ord) FILTER (WHERE ts >= tt{o}) AS varchar) AS b{o}_q0,
       CAST(min_by(b0, ord) FILTER (WHERE ts >= tt{o}) AS varchar) AS b{o}_b0,
       to_unixtime(min_by(ts, ord) FILTER (WHERE ts >= tt{o})) AS b{o}_t"""

SNAP = """,
meta AS (
    SELECT mint, min_by(name, evt_block_time) AS name, min_by(uri, evt_block_time) AS uri,
           min_by(COALESCE(creator, "user"), evt_block_time) AS creator,
           min_by(is_mayhem_mode, evt_block_time) AS mayhem, min_by(is_cashback_enabled, evt_block_time) AS cashback,
           min_by(quote_mint, evt_block_time) AS curve_quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{e_end}'
      AND mint IN (SELECT mint FROM pools)
    GROUP BY 1
),
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{e_end}'
      AND mint IN (SELECT mint FROM pools)
    GROUP BY 1
),
stt AS (
    SELECT st.*, count(*) OVER (PARTITION BY st.slot, st.txi, st.oix, st.iix) AS n_skey{tt_cols}
    FROM st
),
sn AS (
    SELECT pool, count_if(kind IN ('B', 'S')) AS n_7d, count_if(kind IN ('D', 'W')) AS n_lp_7d,
           count_if(kind IN ('I', 'U')) AS n_boost_7d,
           CAST(min(vq) AS varchar) AS vq_min_7d, CAST(max(vq) AS varchar) AS vq_max_7d,
           count_if(n_skey > 1) AS n_src_dup_7d, count_if(vq_src IN ('unknown', 'missing')) AS n_vq_bad_7d{snap_cols}
    FROM stt
    GROUP BY 1
)
SELECT 'solana' AS chain, p.pool, p.mint, p.quote_mint,
       CASE WHEN p.quote_mint = '{wsol}' THEN 'SOL' WHEN p.quote_mint = '{usdc}' THEN 'USDC' ELSE 'OTHER' END AS quote_class,
       p.bd, p.qd, to_unixtime(p.created_at) AS created_t,
       p.c_slot, p.c_txi, p.c_oix, p.c_iix, p.c_tx, CAST(p.c_q AS varchar) AS c_q, CAST(p.c_b AS varchar) AS c_b,
       to_unixtime(p.curve_created_at) AS curve_created_t, to_unixtime(cm.completed_at) AS curve_completed_t,
       p.symbol, m.name, m.uri, m.creator, m.mayhem, m.cashback, m.curve_quote_mint,
       p.created_at + INTERVAL '7' DAY <= TIMESTAMP '{last_day} 00:00:00' + INTERVAL '1' DAY AS mature_7d,
       {sn_cols}
FROM pools p
LEFT JOIN meta m ON m.mint = p.mint
LEFT JOIN comp cm ON cm.mint = p.mint
LEFT JOIN sn ON sn.pool = p.pool
WHERE p.created_at >= TIMESTAMP '{e_start} 00:00:00' AND p.created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
"""

LIQ = """
SELECT 'solana' AS chain, l.pool, l.lk AS kind, l.slot, l.txi, l.oix, l.iix, to_unixtime(l.ts) AS t, l.usr, l.tx_id,
       CAST(l.q0 AS varchar) AS q0, CAST(l.b0 AS varchar) AS b0, CAST(l.dq AS varchar) AS dq, CAST(l.db AS varchar) AS db,
       CAST(l.q1 AS varchar) AS q1_after, CAST(l.b1 AS varchar) AS b1_after, CAST(l.vq AS varchar) AS vq,
       CASE WHEN l.slot IS NULL OR l.txi IS NULL OR l.oix IS NULL OR l.txi >= 100000 OR l.txi < 0
              OR l.oix >= 100 OR l.oix < 0 OR l.iix >= 1000 OR l.iix < 0 THEN 1 ELSE 0 END AS ovf
FROM (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_outer_instruction_index AS oix,
           COALESCE(evt_inner_instruction_index, -1) AS iix, "user" AS usr, evt_tx_id AS tx_id, 'D' AS lk,
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)) AS q0, CAST(pool_base_token_reserves AS DECIMAL(38,0)) AS b0,
           CAST(quote_amount_in AS DECIMAL(38,0)) AS dq, CAST(base_amount_in AS DECIMAL(38,0)) AS db,
           CAST(NULL AS DECIMAL(38,0)) AS q1, CAST(NULL AS DECIMAL(38,0)) AS b1, CAST(NULL AS DECIMAL(38,0)) AS vq
    FROM pumpdotfun_solana.pump_amm_evt_depositevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
    UNION ALL
    SELECT pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index,
           COALESCE(evt_inner_instruction_index, -1), "user", evt_tx_id, 'W',
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)), CAST(pool_base_token_reserves AS DECIMAL(38,0)),
           -CAST(quote_amount_out AS DECIMAL(38,0)), -CAST(base_amount_out AS DECIMAL(38,0)),
           CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'{boost_liq}
) l
JOIN pools p ON p.pool = l.pool
WHERE l.ts >= p.created_at AND l.ts < p.created_at + INTERVAL '180' DAY
"""

BOOST_LIQ = """
    UNION ALL
    SELECT boost_pool, ts, slot, txi, oix, COALESCE(iix, -1), CAST(NULL AS varchar), tx_id, kind,
           CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)),
           boost_q1, boost_b1, vq
    FROM rv WHERE kind IN ('I', 'U')"""

META = """
SELECT 'solana' AS chain, count(*) AS n_candidate,
       count_if(cls = 'no_create') AS n_no_curve_create, count_if(cls = 'sealed') AS n_sealed,
       count_if(cls = 'no_symbol') AS n_no_symbol, count_if(cls = 'holdout_name') AS n_holdout_name,
       count_if(cls = 'in') AS n_included,
       count_if(cls = 'in' AND quote_mint = '{wsol}') AS n_included_sol,
       count_if(cls = 'in' AND quote_mint = '{usdc}') AS n_included_usdc,
       count_if(cls = 'in' AND quote_mint NOT IN ('{wsol}', '{usdc}')) AS n_included_other,
       count(*) - count_if(cls IN ('no_create', 'sealed', 'no_symbol', 'holdout_name', 'in')) AS identity_gap
FROM lab
WHERE created_at >= TIMESTAMP '{e_start} 00:00:00' AND created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
"""


def raw_parts(ev_start, ev_end):
    """事件区间与 07-15 的交集：有交集时返回 RAW CTE 与对齐、取值表达式；否则 vq 按布局记 0。"""
    r_start = max(ev_start, VQ_START)
    if r_start > ev_end:
        return (
            "",
            dict(
                rv_join="",
                vq_expr="CAST(0 AS DECIMAL(38,0))",
                vq_src_expr="'layout0_date'",
                vq_ovf_expr="0",
                cb_expr="CAST(NULL AS DECIMAL(38,0))",
                bb_expr="CAST(NULL AS DECIMAL(38,0))",
            ),
            False,
        )
    bi = "bytearray_to_bigint(reverse(bytearray_substring(b, %s, 8)))"
    raw = RAW.format(
        r_start=r_start.isoformat(),
        r_end=ev_end.isoformat(),
        program=PROGRAM,
        d_buy=DISC["buy"],
        d_sell=DISC["sell"],
        d_init=DISC["init_boost"],
        d_burn=DISC["buy_burn"],
        upgrade_end=UPGRADE_END,
        old_sell=", ".join(str(x) for x in KNOWN_OLD["sell"]),
        old_buy=", ".join(str(x) for x in KNOWN_OLD["buy"]),
        u_cb=u64(bi % "pc + 8"),
        u_bb=u64(bi % "pc + 24"),
        u_iq=u64(bi % "137"),
        u_uq=u64(bi % "193"),
        u_ub=u64(bi % "201"),
    )
    cut = "TIMESTAMP '%s 00:00:00'" % VQ_START.isoformat()
    return (
        raw,
        dict(
            rv_join="\n    LEFT JOIN rv r ON r.tx_id = e.tx_id AND r.oix = e.oix AND r.iix = e.iix0 AND r.kind = e.side",
            vq_expr="CASE WHEN e.ts < %s THEN CAST(0 AS DECIMAL(38,0)) ELSE r.vq END"
            % cut,
            vq_src_expr="CASE WHEN e.ts < %s THEN 'layout0_date' WHEN r.tx_id IS NULL THEN 'missing' "
            "ELSE r.layout END" % cut,
            vq_ovf_expr="COALESCE(r.vq_ovf, 0)",
            cb_expr="r.cb",
            bb_expr="r.bb",
        ),
        True,
    )


def build(layer, e_start, e_end, sample=None):
    if e_end > LAST_EVENT_DAY:
        raise SystemExit("事件止日不能晚于 %s（总控第十六轮 R3）" % LAST_EVENT_DAY)
    if layer not in ("B", "P", "L", "M"):
        raise SystemExit("层只能是 B、P、L、M")
    p_start = max(PUMPSWAP_START, e_start - dt.timedelta(days=181))
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    smp = ""
    if sample:
        smp = (
            "\n      AND created_at >= TIMESTAMP '%s' AND created_at < TIMESTAMP '%s'"
            % sample[:2]
        )
        if len(sample) > 2:  # 只用于非 SOL 计价样本
            smp += "\n      AND quote_mint <> '%s'" % WSOL
    fmt = dict(
        layer=layer,
        names=names,
        e_start=e_start.isoformat(),
        e_end=e_end.isoformat(),
        p_start=p_start.isoformat(),
        sample=smp,
        wsol=WSOL,
        usdc=USDC,
        last_day=LAST_EVENT_DAY.isoformat(),
    )
    head = HEAD.format(**fmt)
    if layer == "M":
        return head + META.format(**fmt)
    if layer == "L":
        raw, _, has = raw_parts(e_start, e_end)
        return head + raw + LIQ.format(boost_liq=BOOST_LIQ if has else "", **fmt)
    if layer == "B":
        raw, ex, _ = raw_parts(e_start, e_end)
        evr = dict(ev_start=fmt["e_start"], ev_end=fmt["e_end"])
        return (
            head
            + raw
            + EVENTS.format(horizon=180, **evr, **ex, **fmt)
            + BUCKETS.format(**fmt)
        )
    # P：快照要建池后 1 天起的第一笔：事件日期取到片尾＋8 天（不超过事件止日）
    ev_end = min(LAST_EVENT_DAY, e_end + dt.timedelta(days=8))
    raw, ex, has = raw_parts(e_start, ev_end)
    evr = dict(ev_start=fmt["e_start"], ev_end=ev_end.isoformat())
    tt_cols = "".join(
        ",\n           created_at + INTERVAL '%d' SECOND AS tt%d" % (o, o)
        for o in OFFSETS
    )
    cols = "".join(SNAP_COLS.format(o=o) for o in OFFSETS)
    names_out = [
        "n_7d",
        "n_lp_7d",
        "n_boost_7d",
        "vq_min_7d",
        "vq_max_7d",
        "n_src_dup_7d",
        "n_vq_bad_7d",
    ]
    for o in OFFSETS:
        names_out += [
            "%s%d_%s" % ("a", o, f)
            for f in ("slot", "txi", "oix", "iix", "kind", "tx", "q1", "b1", "t")
        ]
        names_out += ["vq%d" % o, "nboost%d" % o]
        names_out += [
            "%s%d_%s" % ("b", o, f)
            for f in ("slot", "txi", "oix", "iix", "kind", "tx", "q0", "b0", "t")
        ]
    sn_cols = ", ".join("sn.%s" % c for c in names_out)
    # 五个字段：target_time、state_time、known_at、coverage、gap_flag（由前后事件与止日在 SQL 里算出）
    five = []
    end_ts = "TIMESTAMP '%s 00:00:00' + INTERVAL '1' DAY" % LAST_EVENT_DAY.isoformat()
    for o in OFFSETS:
        cov = (
            "CASE WHEN p.created_at + INTERVAL '{o}' SECOND >= {end} THEN 'immature' "
            "WHEN sn.a{o}_kind = 'I' THEN 'partial' "
            "WHEN sn.b{o}_slot IS NULL THEN 'no_next' "
            "WHEN sn.a{o}_q1 IS NULL OR sn.a{o}_b1 IS NULL OR sn.b{o}_q0 IS NULL OR sn.b{o}_b0 IS NULL THEN 'unverified' "
            "WHEN sn.a{o}_q1 IS DISTINCT FROM sn.b{o}_q0 OR sn.a{o}_b1 IS DISTINCT FROM sn.b{o}_b0 THEN 'gap' "
            "ELSE 'ok' END"
        ).format(o=o, end=end_ts)
        qk = (
            "CASE WHEN p.created_at + INTERVAL '{o}' SECOND >= {end} THEN NULL "
            "WHEN sn.b{o}_slot IS NULL THEN to_unixtime({end}) ELSE sn.b{o}_t END"
        ).format(o=o, end=end_ts)
        five.append(
            "to_unixtime(p.created_at + INTERVAL '{o}' SECOND) AS target{o}_time, sn.a{o}_t AS state{o}_time, "
            "sn.a{o}_t AS known{o}_at, {cov} AS coverage{o}, ({cov}) <> 'ok' AS gap{o}_flag, "
            "{qk} AS qknown{o}_at".format(o=o, cov=cov, qk=qk)
        )
    sn_cols += ",\n       " + ",\n       ".join(five)
    stream = STREAM.format(boost_union=BOOST_UNION if has else "", **evr)
    return (
        head
        + raw
        + EVENTS.format(horizon=7, **evr, **ex, **fmt)
        + stream
        + SNAP.format(tt_cols=tt_cols, snap_cols=cols, sn_cols=sn_cols, **fmt)
    )


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
        if len(a) > 7 and a[7] == "--nonsol":
            sample = sample + ("nonsol",)
    (H / "sql" / ("%s.sql" % label)).write_text(build(layer, e_start, e_end, sample))
    print("sql/%s.sql" % label)


if __name__ == "__main__":
    main()
