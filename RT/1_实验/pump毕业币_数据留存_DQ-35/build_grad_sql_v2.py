#!/usr/bin/env python3
"""DQ-35 v2（10-03）：按 GPT 提取 SQL 审计（基于 b089732c，存档见 3_审计/2026-10-03_总控第十三轮…）修正的毕业后留存 SQL。

python build_grad_sql_v2.py <事件起日> <事件止日> <标签> [--sample <起时> <止时>]  → sql/<标签>.sql
--sample 只用于小样本对照：把母体限制为建池时刻在 [起时, 止时) 的池，其余逻辑与正式片完全相同。

相对 v1（build_grad_sql.py）的改动，编号对应审计表：
 1. 代号与曲线创建时刻按全历史查（解码表 2024-04 起），不再只回查 90 天；查不到曲线创建事件的币仍排除，个数由 META2 另报。
 2. 封存周按“币创建”（曲线创建时刻）定义，与总入口、GRADPRE v2、DQ-37 检验周一致；代号规范化为 upper(trim(去 $))。
 3. 买入后报价储备＝交易前＋quote_amount_in_with_lp_fee（v1 用了 F59 旧式）；卖出＝交易前−(quote_amount_out−lp_fee)。
    每桶另存首笔交易前储备与方向、末笔方向与金额、各项费用合计，桶末状态可独立复算。
    另输出 kind='L' 的加池、撤池事件逐笔（少见，见 README §1a），使任一时刻的池状态可知：
    side_first＝D（加池）/W（撤池），q0_open/b0_open 为事件前储备，q_pool_last/b_amt_last 为带符号的变动量，
    q1_close/b1_close＝前＋变动，users_straddle 放操作者地址，bkey 为空。
 4. 排序键 ord＝slot·1e10＋tx·1e5＋外层指令·1e3＋内层指令（BIGINT）；每桶存首末 ord，跨片合并按 ord 取首末；
    另存越界计数 n_ord_overflow（外层 ≥100、内层 ≥1000 或 tx ≥1e5），应全为 0；ord 唯一性在小样本对照里核。
    ord 超过 2^53，Dune API 把 BIGINT 当浮点序列化会丢低位（10-03 小样本发现），所以输出时转成 varchar。
 5. 桶跨分片边界时另存该桶的用户名单 users_straddle（同一次聚合里 FILTER 收集、聚合后去重），合并时求并集；
    其余桶的 n_users 仍用 approx_distinct（小基数下近似精确）。10-03 小样本：三个 DISTINCT 聚合使一小时母体的
    一天样本耗 72.49 credits、859 秒（去掉后 1.05）；改成单独子查询后 3.4～5.2（母体 CTE 被展开计算 9 次），
    所以再改为单次聚合、去掉显式 IN 过滤（与 pools 的 JOIN 自带动态过滤），母体只算两次。
    精确去重与 ord 重复检查放在小样本对照里用逐笔数据做。
10. 新标签（GRAD2_*），不与 v1 文件混；齐全性由 manifest 核对（check_manifest_v2.py）。
另：事件止日最晚 2026-09-29。PumpSwap 自 2026-09-30 起池子带有符号的 virtual_quote_reserves（官方文档
NEGATIVE_VIRTUAL_QUOTE_RESERVES，2026-09-29 提交），Dune 解码表尚无此字段，09-30 起的价格不能由事件储备算出。
排除：封存周创建的币；代号与币安留出哈希命中名同名的币（_holdout_names.sqlpart）；查不到曲线创建事件的币。只存不分析。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
PUMPSWAP_START = dt.date(2025, 3, 15)
LAST_EVENT_DAY = dt.date(2026, 9, 29)

TEMPLATE = """/* DQ-35 v2 数据留存（10-03，执行模型）：pump 迁移池在 {e_start}～{e_end} 的成交；只存不分析；由 build_grad_sql_v2.py 生成 */
WITH
{names},
cp AS (
    /* 由 pump 程序在迁移交易里创建、池序号为 0 的 PumpSwap 池 */
    SELECT pool, min(evt_block_time) AS created_at, max(base_mint) AS mint, max(quote_mint) AS quote_mint,
           max(base_mint_decimals) AS bd, max(quote_mint_decimals) AS qd
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '{p_start}' AND DATE '{e_end}'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1
),
cc AS (
    /* 曲线创建事件，全历史（审计第 1 条） */
    SELECT mint, min(evt_block_time) AS curve_created_at, min_by(symbol, evt_block_time) AS symbol
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{e_end}'
      AND mint IN (SELECT mint FROM cp)
    GROUP BY 1
),
pools AS (
    SELECT c.pool, c.mint, c.quote_mint, c.created_at, c.bd, c.qd, s.curve_created_at
    FROM cp c
    JOIN cc s ON s.mint = c.mint
    WHERE c.created_at >= TIMESTAMP '{e_start} 00:00:00' - INTERVAL '180' DAY
      AND c.created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
      AND NOT (s.curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND s.curve_created_at < TIMESTAMP '2026-07-13 00:00:00')
      AND upper(trim(replace(s.symbol, '$', ''))) NOT IN (SELECT base FROM excl){sample}
),
ev AS (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
           evt_outer_instruction_index AS oix, COALESCE(evt_inner_instruction_index, 0) AS iix,
           'B' AS side, "user" AS usr,
           CAST(pool_quote_token_reserves AS DOUBLE) AS q0,
           CAST(pool_base_token_reserves AS DOUBLE) AS b0,
           CAST(quote_amount_in_with_lp_fee AS DOUBLE) AS q_pool,
           CAST(base_amount_out AS DOUBLE) AS b_amt,
           CAST(user_quote_amount_in AS DOUBLE) AS q_user,
           COALESCE(CAST(lp_fee AS DOUBLE), 0) AS f_lp,
           COALESCE(CAST(protocol_fee AS DOUBLE), 0) AS f_pr,
           COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS f_cr,
           0e0 AS f_cb, 0e0 AS f_bb
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
    UNION ALL
    SELECT pool, evt_block_time, evt_block_slot, evt_tx_index,
           evt_outer_instruction_index, COALESCE(evt_inner_instruction_index, 0),
           'S', "user",
           CAST(pool_quote_token_reserves AS DOUBLE),
           CAST(pool_base_token_reserves AS DOUBLE),
           CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0),
           CAST(base_amount_in AS DOUBLE),
           CAST(user_quote_amount_out AS DOUBLE),
           COALESCE(CAST(lp_fee AS DOUBLE), 0),
           COALESCE(CAST(protocol_fee AS DOUBLE), 0),
           COALESCE(CAST(coin_creator_fee AS DOUBLE), 0),
           COALESCE(CAST(cashback AS DOUBLE), 0),
           COALESCE(CAST(buyback_fee AS DOUBLE), 0)
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
),
k AS (
    SELECT e.*, p.mint, p.quote_mint, p.created_at, p.curve_created_at, p.bd, p.qd,
           CASE WHEN e.side = 'B' THEN e.q0 + e.q_pool ELSE e.q0 - e.q_pool END AS q1,
           CASE WHEN e.side = 'B' THEN e.b0 - e.b_amt ELSE e.b0 + e.b_amt END AS b1,
           date_diff('second', p.created_at, e.ts) AS age,
           CAST(e.slot AS BIGINT) * 10000000000 + CAST(e.txi AS BIGINT) * 100000
             + CAST(e.oix AS BIGINT) * 1000 + CAST(e.iix AS BIGINT) AS ord,
           CASE WHEN e.txi >= 100000 OR e.oix >= 100 OR e.iix >= 1000 OR e.oix IS NULL THEN 1 ELSE 0 END AS ovf
    FROM ev e
    JOIN pools p ON p.pool = e.pool
    WHERE e.ts >= p.created_at AND e.ts < p.created_at + INTERVAL '180' DAY
),
kb AS (
    SELECT k.*,
           CASE WHEN age < 300 THEN 'S' WHEN age < 604800 THEN 'H' ELSE 'D' END AS kind,
           CASE WHEN age < 300 THEN floor(age / 5e0) WHEN age < 604800 THEN floor(age / 3600e0)
                ELSE floor(age / 86400e0) END AS bkey,
           CASE WHEN age < 300 THEN 5 WHEN age < 604800 THEN 3600 ELSE 86400 END AS w,
           (q1 / power(10, qd)) / nullif(b1 / power(10, bd), 0) AS px,
           (q0 / power(10, qd)) / nullif(b0 / power(10, bd), 0) AS px_pre
    FROM k
),
kbs AS (
    SELECT kb.*,
           CASE WHEN created_at + bkey * w * INTERVAL '1' SECOND < TIMESTAMP '{e_start} 00:00:00'
                  OR created_at + (bkey + 1) * w * INTERVAL '1' SECOND > TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
                THEN true ELSE false END AS straddle
    FROM kb
)
SELECT kind, mint, pool, quote_mint, created_at, curve_created_at, bd, qd, bkey, straddle,
       count(*) AS n, count_if(side = 'B') AS n_buy, approx_distinct(usr) AS n_users,
       array_join(array_sort(array_distinct(array_agg(usr) FILTER (WHERE straddle))), ',') AS users_straddle,
       sum(CASE WHEN side = 'B' THEN q_user ELSE 0 END) AS q_buy_user,
       sum(CASE WHEN side = 'S' THEN q_user ELSE 0 END) AS q_sell_user,
       sum(CASE WHEN side = 'B' THEN q_pool ELSE 0 END) AS q_buy_pool,
       sum(CASE WHEN side = 'S' THEN q_pool ELSE 0 END) AS q_sell_pool,
       sum(CASE WHEN side = 'B' THEN b_amt ELSE 0 END) AS b_buy,
       sum(CASE WHEN side = 'S' THEN b_amt ELSE 0 END) AS b_sell,
       sum(f_lp) AS f_lp, sum(f_pr) AS f_pr, sum(f_cr) AS f_cr, sum(f_cb) AS f_cb, sum(f_bb) AS f_bb,
       CAST(min(ord) AS varchar) AS ord_first, CAST(max(ord) AS varchar) AS ord_last,
       min_by(q0, ord) AS q0_open, min_by(b0, ord) AS b0_open, min_by(side, ord) AS side_first,
       max_by(q1, ord) AS q1_close, max_by(b1, ord) AS b1_close, max_by(side, ord) AS side_last,
       max_by(q_pool, ord) AS q_pool_last, max_by(b_amt, ord) AS b_amt_last,
       min_by(px_pre, ord) AS px_pre_open, min_by(px, ord) AS px_open, max_by(px, ord) AS px_close,
       max(px) AS px_high, min(px) AS px_low,
       min(ts) AS t_first, max(ts) AS t_last,
       sum(ovf) AS n_ord_overflow
FROM kbs
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
UNION ALL
SELECT 'L' AS kind, p.mint, l.pool, p.quote_mint, p.created_at, p.curve_created_at, p.bd, p.qd,
       CAST(NULL AS DOUBLE) AS bkey, false AS straddle,
       1 AS n, 0 AS n_buy, 1 AS n_users, l.usr AS users_straddle,
       0 AS q_buy_user, 0 AS q_sell_user, 0 AS q_buy_pool, 0 AS q_sell_pool, 0 AS b_buy, 0 AS b_sell,
       0 AS f_lp, 0 AS f_pr, 0 AS f_cr, 0 AS f_cb, 0 AS f_bb,
       CAST(l.ord AS varchar) AS ord_first, CAST(l.ord AS varchar) AS ord_last,
       l.q0 AS q0_open, l.b0 AS b0_open, l.lk AS side_first,
       l.q0 + l.dq AS q1_close, l.b0 + l.db AS b1_close, l.lk AS side_last,
       l.dq AS q_pool_last, l.db AS b_amt_last,
       NULL AS px_pre_open, NULL AS px_open, NULL AS px_close, NULL AS px_high, NULL AS px_low,
       l.ts AS t_first, l.ts AS t_last, 0 AS n_ord_overflow
FROM (
    SELECT pool, evt_block_time AS ts, "user" AS usr, 'D' AS lk,
           CAST(evt_block_slot AS BIGINT) * 10000000000 + CAST(evt_tx_index AS BIGINT) * 100000
             + CAST(evt_outer_instruction_index AS BIGINT) * 1000 + COALESCE(evt_inner_instruction_index, 0) AS ord,
           CAST(pool_quote_token_reserves AS DOUBLE) AS q0, CAST(pool_base_token_reserves AS DOUBLE) AS b0,
           CAST(quote_amount_in AS DOUBLE) AS dq, CAST(base_amount_in AS DOUBLE) AS db
    FROM pumpdotfun_solana.pump_amm_evt_depositevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
    UNION ALL
    SELECT pool, evt_block_time, "user", 'W',
           CAST(evt_block_slot AS BIGINT) * 10000000000 + CAST(evt_tx_index AS BIGINT) * 100000
             + CAST(evt_outer_instruction_index AS BIGINT) * 1000 + COALESCE(evt_inner_instruction_index, 0),
           CAST(pool_quote_token_reserves AS DOUBLE), CAST(pool_base_token_reserves AS DOUBLE),
           -CAST(quote_amount_out AS DOUBLE), -CAST(base_amount_out AS DOUBLE)
    FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
) l
JOIN pools p ON p.pool = l.pool
WHERE l.ts >= p.created_at AND l.ts < p.created_at + INTERVAL '180' DAY
"""


def build(e_start, e_end, sample=None):
    if e_end > LAST_EVENT_DAY:
        raise SystemExit("事件止日不能晚于 %s（负虚拟报价储备）" % LAST_EVENT_DAY)
    p_start = max(PUMPSWAP_START, e_start - dt.timedelta(days=181))
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    smp = ""
    if sample:
        smp = (
            "\n      AND c.created_at >= TIMESTAMP '%s' AND c.created_at < TIMESTAMP '%s'"
            % sample
        )
    return TEMPLATE.format(
        names=names,
        e_start=e_start.isoformat(),
        e_end=e_end.isoformat(),
        p_start=p_start.isoformat(),
        sample=smp,
    )


def main():
    e_start = dt.date.fromisoformat(sys.argv[1])
    e_end = dt.date.fromisoformat(sys.argv[2])
    label = sys.argv[3]
    sample = None
    if len(sys.argv) > 4 and sys.argv[4] == "--sample":
        sample = (sys.argv[5], sys.argv[6])
    (H / "sql" / ("%s.sql" % label)).write_text(build(e_start, e_end, sample))
    print("sql/%s.sql" % label)


if __name__ == "__main__":
    main()
