#!/usr/bin/env python3
"""DQ-35 v2.1（10-04）：毕业后留存 SQL，按 GPT 批 0 与 10-04 复核（“修改后重取”）修正。只存不分析。

python build_grad_sql_v21.py <层> <事件起日> <事件止日> <标签> [--sample <起时> <止时>]  → sql/<标签>.sql
层：B＝分桶；P＝池头与固定时点快照；L＝加池、撤池逐笔；M＝母体计数（META2）。
--sample 只用于小样本对照：把母体限制为建池时刻在 [起时, 止时) 的池，其余逻辑与正式片完全相同；
  其后再加 --nonsol 只取非 SOL 计价的池（非 SOL 样本用）。

相对 v2（build_grad_sql_v2.py）的改动：
 1. 金额精度：解码表金额是 uint256，一律 CAST 成 DECIMAL(38,0) 做整数运算与求和，输出时转 varchar
    （不经 DOUBLE；JSON 不会因超过 2^53 丢位）。SOL 用 lamports，其他计价资产保留原始最小单位，decimals 在 P 层。
    价格高低点 px_high/px_low 仍是 DOUBLE 比值（计价资产原单位／代币），只作描述。
 2. 事件唯一键：池＋slot＋交易序号＋外层指令＋内层指令（2026-09-23 探针：买卖各 957.6 万、1346.2 万行，键全唯一，
    买入内层序号无空值）。分桶存首末事件的四个整数列；拼接的 ord 只在 SQL 内部排序用，不输出。
    tx_id 不进分桶层；L 层逐笔保留 tx_id，P 层保留建池交易的 tx_id（映射用）。
 3. 时间：输出 epoch 秒（BIGINT）。epoch 秒只用于日期归属与时长，不承担槽内排序（排序看事件键）。
 4. 分桶：[0,300 秒) 5 秒（S）；[300 秒,1 小时) 1 分钟（M，新增）；[1 小时,7 天) 1 小时（H）；[7 天,180 天) 1 天（D）。
 5. 买入的 cashback、回购费：Dune 解码表 pump_amm_evt_buyevent 没有这两列（10-04 searchTables 核对；卖出表有），
    所以买入一侧输出 NULL（未知），不写 0；卖出一侧照读。买入后报价储备＝前＋quote_amount_in_with_lp_fee 在 v2
    小样本里逐笔吻合，池状态不受影响；未知的只是用户侧返利。
 6. 计价资产：P 层存 quote_mint、decimals 与 quote_class（SOL／USDC／OTHER）；2026-09 的 pump 迁移池里非 SOL 计价约 7%（探针），
    金额与价格按计价资产原单位，不换算。主分析只用 SOL 层；USDC 层另报，换算 SOL 用按分钟的价格序列；OTHER 只计数（总控第十八轮）。
 7. 虚拟报价储备（10-04 第二次修正）：PumpSwap 按“有效报价储备＝池报价储备＋virtual_quote_reserves”成交（官方文档 2026-07-15；
    PROBE21b 逐字段核对）。该字段 Dune 解码表没有；它对 07-18 建的池为 0，对 08-03 起建的 pump 迁移池大多约 17.58 SOL（PROBE21c）。
    v2.1 首版以为 09-30 才生效、按日期截断价格，是错的，已去掉。现在由卖出事件的整数恒等式
      quote_amount_out＝floor((q0＋vq)·base_in／(b0＋base_in))
    反解每笔卖出允许的 vq 整数区间 [vlo, vhi]（真值落在区间内：PROBE21b 55/55；2026-09-23 样本 48 个池全天各只一段、无冲突），
    分桶层输出桶内交集 vq_lo／vq_hi 与所用卖出笔数，价格高低点用本片内池级交集的中点；池级交集为空（vq 在片内变过）或本片无卖出时，
    价格列置空并计入 n_px_unknown。买入的两种指令（buy、buy_exact_quote_in）成交式不同，不用于反解。
    事件止日 2026-10-04（总控第十六轮 R3：开发只用 10-05 之前的成交）。
 8. P 层：每池一行。池头（建池事件键与 tx_id、mint、计价资产与 decimals、曲线创建与完成时刻、名称、代号、URI、
    创建者、mayhem、cashback 标志）＋固定时点快照：建池后 {offsets} 秒各两组——该时点前最后一笔成交的事件键、
    成交后储备与时刻（“截至该时点已可知”）；该时点起第一笔成交的事件键、成交前储备与时刻（该时点发出的单子最早
    面对的状态，不含我方执行延迟；延迟用更晚的时点表示）。快照只服务固定时点实验，不支持任意追踪退出。
 9. L 层：加池、撤池逐笔，按（池，事件键）唯一；越界计数按实际字段计算（v2 恒为 0 是错的）。
10. M 层：候选池数、查到曲线创建事件的、封存周排除、留出同名排除、纳入数（v2 文件头承诺的 META2）。
排除：封存周创建的币；代号与币安留出哈希命中名同名的币（_holdout_names.sqlpart）；查不到曲线创建事件的币。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
PUMPSWAP_START = dt.date(2025, 3, 15)
LAST_EVENT_DAY = dt.date(2026, 10, 4)
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
OFFSETS = (2, 10, 45, 60, 75, 900, 3600, 86400)

HEAD = """/* DQ-35 v2.1 数据留存（10-04，执行模型）：层 {layer}；pump 迁移池在 {e_start}～{e_end} 的事件；只存不分析；由 build_grad_sql_v21.py 生成 */
WITH
{names},
cp AS (
    /* 由 pump 程序在迁移交易里创建、池序号为 0 的 PumpSwap 池 */
    SELECT pool, min(evt_block_time) AS created_at, max(base_mint) AS mint, max(quote_mint) AS quote_mint,
           max(base_mint_decimals) AS bd, max(quote_mint_decimals) AS qd,
           min_by(evt_block_slot, evt_block_time) AS c_slot, min_by(evt_tx_index, evt_block_time) AS c_txi,
           min_by(evt_outer_instruction_index, evt_block_time) AS c_oix,
           min_by(COALESCE(evt_inner_instruction_index, -1), evt_block_time) AS c_iix,
           min_by(evt_tx_id, evt_block_time) AS c_tx
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
pools AS (
    SELECT c.*, s.curve_created_at, s.symbol
    FROM cand c
    JOIN cc s ON s.mint = c.mint
    WHERE NOT (s.curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND s.curve_created_at < TIMESTAMP '2026-07-13 00:00:00')
      AND upper(trim(replace(s.symbol, '$', ''))) NOT IN (SELECT base FROM excl)
)"""

EVENTS = """,
ev AS (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
           evt_outer_instruction_index AS oix, COALESCE(evt_inner_instruction_index, -1) AS iix,
           'B' AS side, "user" AS usr,
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)) AS q0,
           CAST(pool_base_token_reserves AS DECIMAL(38,0)) AS b0,
           CAST(quote_amount_in_with_lp_fee AS DECIMAL(38,0)) AS q_pool,
           CAST(base_amount_out AS DECIMAL(38,0)) AS b_amt,
           CAST(user_quote_amount_in AS DECIMAL(38,0)) AS q_user,
           CAST(lp_fee AS DECIMAL(38,0)) AS f_lp,
           CAST(protocol_fee AS DECIMAL(38,0)) AS f_pr,
           CAST(coin_creator_fee AS DECIMAL(38,0)) AS f_cr,
           CAST(NULL AS DECIMAL(38,0)) AS f_cb, CAST(NULL AS DECIMAL(38,0)) AS f_bb,
           CAST(NULL AS DECIMAL(38,0)) AS q_gross_out
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date BETWEEN DATE '{ev_start}' AND DATE '{ev_end}'
    UNION ALL
    SELECT pool, evt_block_time, evt_block_slot, evt_tx_index,
           evt_outer_instruction_index, COALESCE(evt_inner_instruction_index, -1),
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
k AS (
    SELECT e.*, p.created_at, p.bd, p.qd,
           CASE WHEN e.side = 'B' THEN e.q0 + e.q_pool ELSE e.q0 - e.q_pool END AS q1,
           CASE WHEN e.side = 'B' THEN e.b0 - e.b_amt ELSE e.b0 + e.b_amt END AS b1,
           date_diff('millisecond', p.created_at, e.ts) AS age_ms,
           CAST(e.slot AS BIGINT) * 10000000000 + CAST(e.txi AS BIGINT) * 100000
             + CAST(e.oix AS BIGINT) * 1000 + CAST(e.iix AS BIGINT) AS ord,
           CASE WHEN e.txi >= 100000 OR e.oix >= 100 OR e.iix >= 1000 OR e.iix < 0 OR e.oix IS NULL
                THEN 1 ELSE 0 END AS ovf,
           /* 卖出反解 vq：ceil(a/d)＝(a＋d−1 − mod(a＋d−1, d))/d，全程整数 */
           CASE WHEN e.side = 'S' AND e.b_amt > 0 THEN
                (e.q_gross_out * (e.b0 + e.b_amt) + e.b_amt - 1
                 - mod(e.q_gross_out * (e.b0 + e.b_amt) + e.b_amt - 1, e.b_amt)) / e.b_amt - e.q0 END AS vlo,
           CASE WHEN e.side = 'S' AND e.b_amt > 0 THEN
                ((e.q_gross_out + 1) * (e.b0 + e.b_amt) + e.b_amt - 1
                 - mod((e.q_gross_out + 1) * (e.b0 + e.b_amt) + e.b_amt - 1, e.b_amt)) / e.b_amt - 1 - e.q0 END AS vhi
    FROM ev e
    JOIN pools p ON p.pool = e.pool
    WHERE e.ts >= p.created_at AND e.ts < p.created_at + INTERVAL '{horizon}' DAY
)"""

BUCKETS = """,
kp AS (
    SELECT k.*, max(vlo) OVER (PARTITION BY pool) AS pvlo, min(vhi) OVER (PARTITION BY pool) AS pvhi
    FROM k
),
kb AS (
    SELECT kp.*,
           CASE WHEN age_ms < 300000 THEN 'S' WHEN age_ms < 3600000 THEN 'M'
                WHEN age_ms < 604800000 THEN 'H' ELSE 'D' END AS kind,
           CASE WHEN age_ms < 300000 THEN floor(age_ms / 5000e0)
                WHEN age_ms < 3600000 THEN floor(age_ms / 60000e0)
                WHEN age_ms < 604800000 THEN floor(age_ms / 3600000e0)
                ELSE floor(age_ms / 86400000e0) END AS bkey,
           CASE WHEN age_ms < 300000 THEN 5 WHEN age_ms < 3600000 THEN 60
                WHEN age_ms < 604800000 THEN 3600 ELSE 86400 END AS w,
           CASE WHEN pvlo <= pvhi
                THEN ((CAST(q1 AS DOUBLE) + (CAST(pvlo AS DOUBLE) + CAST(pvhi AS DOUBLE)) / 2) / power(10, qd))
                     / nullif(CAST(b1 AS DOUBLE) / power(10, bd), 0) END AS px
    FROM kp
),
kbs AS (
    SELECT kb.*,
           CASE WHEN created_at + bkey * w * INTERVAL '1' SECOND < TIMESTAMP '{e_start} 00:00:00'
                  OR created_at + (bkey + 1) * w * INTERVAL '1' SECOND > TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
                THEN true ELSE false END AS straddle
    FROM kb
)
SELECT kind, pool, CAST(bkey AS BIGINT) AS bkey, straddle,
       count(*) AS n, count_if(side = 'B') AS n_buy, approx_distinct(usr) AS n_users,
       array_join(array_sort(array_distinct(array_agg(usr) FILTER (WHERE straddle))), ',') AS users_straddle,
       CAST(sum(CASE WHEN side = 'B' THEN q_user ELSE 0 END) AS varchar) AS q_buy_user,
       CAST(sum(CASE WHEN side = 'S' THEN q_user ELSE 0 END) AS varchar) AS q_sell_user,
       CAST(sum(CASE WHEN side = 'B' THEN q_pool ELSE 0 END) AS varchar) AS q_buy_pool,
       CAST(sum(CASE WHEN side = 'S' THEN q_pool ELSE 0 END) AS varchar) AS q_sell_pool,
       CAST(sum(CASE WHEN side = 'B' THEN b_amt ELSE 0 END) AS varchar) AS b_buy,
       CAST(sum(CASE WHEN side = 'S' THEN b_amt ELSE 0 END) AS varchar) AS b_sell,
       CAST(sum(f_lp) AS varchar) AS f_lp, CAST(sum(f_pr) AS varchar) AS f_pr, CAST(sum(f_cr) AS varchar) AS f_cr,
       CAST(sum(f_cb) AS varchar) AS f_cb_sell, CAST(sum(f_bb) AS varchar) AS f_bb_sell,
       count_if(f_lp IS NULL OR f_pr IS NULL OR f_cr IS NULL) AS n_fee_null,
       min_by(slot, ord) AS slot_f, min_by(txi, ord) AS txi_f, min_by(oix, ord) AS oix_f, min_by(iix, ord) AS iix_f,
       max_by(slot, ord) AS slot_l, max_by(txi, ord) AS txi_l, max_by(oix, ord) AS oix_l, max_by(iix, ord) AS iix_l,
       CAST(min_by(q0, ord) AS varchar) AS q0_open, CAST(min_by(b0, ord) AS varchar) AS b0_open, min_by(side, ord) AS side_first,
       CAST(max_by(q1, ord) AS varchar) AS q1_close, CAST(max_by(b1, ord) AS varchar) AS b1_close, max_by(side, ord) AS side_last,
       CAST(max_by(q_pool, ord) AS varchar) AS q_pool_last, CAST(max_by(b_amt, ord) AS varchar) AS b_amt_last,
       CAST(max(vlo) AS varchar) AS vq_lo, CAST(min(vhi) AS varchar) AS vq_hi, count(vlo) AS n_vq_obs,
       max(px) AS px_high, min(px) AS px_low, count_if(px IS NULL) AS n_px_unknown,
       to_unixtime(min(ts)) AS t_first, to_unixtime(max(ts)) AS t_last,
       sum(ovf) AS n_ord_overflow
FROM kbs
GROUP BY 1, 2, 3, 4
"""

SNAP_COLS = """,
       max_by(slot, ord) FILTER (WHERE age_ms < {ms}) AS a{o}_slot, max_by(txi, ord) FILTER (WHERE age_ms < {ms}) AS a{o}_txi,
       max_by(oix, ord) FILTER (WHERE age_ms < {ms}) AS a{o}_oix, max_by(iix, ord) FILTER (WHERE age_ms < {ms}) AS a{o}_iix,
       CAST(max_by(q1, ord) FILTER (WHERE age_ms < {ms}) AS varchar) AS a{o}_q1,
       CAST(max_by(b1, ord) FILTER (WHERE age_ms < {ms}) AS varchar) AS a{o}_b1,
       to_unixtime(max_by(ts, ord) FILTER (WHERE age_ms < {ms})) AS a{o}_t,
       min_by(slot, ord) FILTER (WHERE age_ms >= {ms}) AS b{o}_slot, min_by(txi, ord) FILTER (WHERE age_ms >= {ms}) AS b{o}_txi,
       min_by(oix, ord) FILTER (WHERE age_ms >= {ms}) AS b{o}_oix, min_by(iix, ord) FILTER (WHERE age_ms >= {ms}) AS b{o}_iix,
       CAST(min_by(q0, ord) FILTER (WHERE age_ms >= {ms}) AS varchar) AS b{o}_q0,
       CAST(min_by(b0, ord) FILTER (WHERE age_ms >= {ms}) AS varchar) AS b{o}_b0,
       to_unixtime(min_by(ts, ord) FILTER (WHERE age_ms >= {ms})) AS b{o}_t"""

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
sn AS (
    SELECT pool, count(*) AS n_7d, CAST(max(vlo) AS varchar) AS vq_lo_7d, CAST(min(vhi) AS varchar) AS vq_hi_7d,
           count(vlo) AS n_vq_obs_7d{snap_cols}
    FROM k
    GROUP BY 1
)
SELECT p.pool, p.mint, p.quote_mint,
       CASE WHEN p.quote_mint = '{wsol}' THEN 'SOL' WHEN p.quote_mint = '{usdc}' THEN 'USDC' ELSE 'OTHER' END AS quote_class,
       p.bd, p.qd, to_unixtime(p.created_at) AS created_t,
       p.c_slot, p.c_txi, p.c_oix, p.c_iix, p.c_tx,
       to_unixtime(p.curve_created_at) AS curve_created_t, to_unixtime(cm.completed_at) AS curve_completed_t,
       p.symbol, m.name, m.uri, m.creator, m.mayhem, m.cashback, m.curve_quote_mint,
       {sn_cols}
FROM pools p
LEFT JOIN meta m ON m.mint = p.mint
LEFT JOIN comp cm ON cm.mint = p.mint
LEFT JOIN sn ON sn.pool = p.pool
WHERE p.created_at >= TIMESTAMP '{e_start} 00:00:00' AND p.created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
"""

LIQ = """
SELECT l.pool, l.lk AS kind, l.slot, l.txi, l.oix, l.iix, to_unixtime(l.ts) AS t, l.usr, l.tx_id,
       CAST(l.q0 AS varchar) AS q0, CAST(l.b0 AS varchar) AS b0, CAST(l.dq AS varchar) AS dq, CAST(l.db AS varchar) AS db,
       CASE WHEN l.txi >= 100000 OR l.oix >= 100 OR l.iix >= 1000 OR l.iix < 0 OR l.oix IS NULL THEN 1 ELSE 0 END AS ovf
FROM (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi, evt_outer_instruction_index AS oix,
           COALESCE(evt_inner_instruction_index, -1) AS iix, "user" AS usr, evt_tx_id AS tx_id, 'D' AS lk,
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)) AS q0, CAST(pool_base_token_reserves AS DECIMAL(38,0)) AS b0,
           CAST(quote_amount_in AS DECIMAL(38,0)) AS dq, CAST(base_amount_in AS DECIMAL(38,0)) AS db
    FROM pumpdotfun_solana.pump_amm_evt_depositevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
    UNION ALL
    SELECT pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index,
           COALESCE(evt_inner_instruction_index, -1), "user", evt_tx_id, 'W',
           CAST(pool_quote_token_reserves AS DECIMAL(38,0)), CAST(pool_base_token_reserves AS DECIMAL(38,0)),
           -CAST(quote_amount_out AS DECIMAL(38,0)), -CAST(base_amount_out AS DECIMAL(38,0))
    FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
) l
JOIN pools p ON p.pool = l.pool
WHERE l.ts >= p.created_at AND l.ts < p.created_at + INTERVAL '180' DAY
"""

META = """,
ccall AS (
    SELECT c.pool, s.curve_created_at, s.symbol
    FROM cand c
    LEFT JOIN cc s ON s.mint = c.mint
    WHERE c.created_at >= TIMESTAMP '{e_start} 00:00:00' AND c.created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
)
SELECT count(*) AS n_candidate,
       count_if(curve_created_at IS NULL) AS n_no_curve_create,
       count_if(curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND curve_created_at < TIMESTAMP '2026-07-13 00:00:00') AS n_sealed,
       count_if(curve_created_at IS NOT NULL
                AND NOT (curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND curve_created_at < TIMESTAMP '2026-07-13 00:00:00')
                AND upper(trim(replace(symbol, '$', ''))) IN (SELECT base FROM excl)) AS n_holdout_name,
       (SELECT count(*) FROM pools
         WHERE created_at >= TIMESTAMP '{e_start} 00:00:00' AND created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY) AS n_included,
       (SELECT count_if(quote_mint = '{wsol}') FROM pools
         WHERE created_at >= TIMESTAMP '{e_start} 00:00:00' AND created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY) AS n_included_sol,
       (SELECT count_if(quote_mint = '{usdc}') FROM pools
         WHERE created_at >= TIMESTAMP '{e_start} 00:00:00' AND created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY) AS n_included_usdc,
       (SELECT count_if(quote_mint NOT IN ('{wsol}', '{usdc}')) FROM pools
         WHERE created_at >= TIMESTAMP '{e_start} 00:00:00' AND created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY) AS n_included_other
FROM ccall
"""


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
    )
    head = HEAD.format(**fmt)
    if layer == "B":
        evr = dict(ev_start=fmt["e_start"], ev_end=fmt["e_end"])
        return head + EVENTS.format(horizon=180, **evr, **fmt) + BUCKETS.format(**fmt)
    if layer == "P":
        # 快照要建池后 1 天起的第一笔：事件日期取到片尾＋8 天（不超过事件止日）
        ev_end = min(LAST_EVENT_DAY, e_end + dt.timedelta(days=8))
        evr = dict(ev_start=fmt["e_start"], ev_end=ev_end.isoformat())
        cols = "".join(SNAP_COLS.format(o=o, ms=o * 1000) for o in OFFSETS)
        names_out = ["n_7d", "vq_lo_7d", "vq_hi_7d", "n_vq_obs_7d"] + [
            "%s%d_%s" % (ab, o, f)
            for o in OFFSETS
            for ab, fs in (
                ("a", ("slot", "txi", "oix", "iix", "q1", "b1", "t")),
                ("b", ("slot", "txi", "oix", "iix", "q0", "b0", "t")),
            )
            for f in fs
        ]
        sn_cols = ", ".join("sn.%s" % c for c in names_out)
        return (
            head
            + EVENTS.format(horizon=7, **evr, **fmt)
            + SNAP.format(snap_cols=cols, sn_cols=sn_cols, **fmt)
        )
    if layer == "L":
        return head + LIQ.format(**fmt)
    return head + META.format(**fmt)


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
