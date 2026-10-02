#!/usr/bin/env python3
"""DQ-35 数据留存：pump 迁移到 PumpSwap 的币，毕业后的池状态、前 300 秒逐笔、前 7 天按小时、7～180 天按天（10-02）。

python build_grad_sql.py <事件起日> <事件止日> <标签>  → sql/<标签>.sql
按“成交发生的日期”分片：每个事件分区只扫一次；池的范围是事件起日前 180 天到事件止日之间创建的迁移池。
一次分组输出三类行（kind）：
  S  建池后 [0, 300) 秒按 5 秒分桶（bkey＝第几个 5 秒）；每桶带首笔成交前与末笔成交后的池储备，所以任一 5 秒边界上的池状态都可知；
     总控要的是逐笔，但一天就有约 15 万笔、全期约 8,000 万行，下载不现实，改为 5 秒桶（执行决定，可推翻）；
  H  建池后 [300 秒, 7 天) 按“建池后第几小时”分桶（第 0 小时只含 300 秒之后）；
  D  建池后 [7, 180) 天按“建池后第几天”分桶。
同一个桶跨两个事件分片时会出现两行，合并规则：笔数与金额相加，开盘取 t_first 较早者，收盘取 t_last 较晚者，高低取极值。
价格＝成交后报价储备/成交后基础储备（按各池小数位换算）；成交后储备沿用 DQ-1M build_m2.py 已核对的写法。
排除：①封存周 2026-06-15～07-12 创建的池；②代号与币安现货命中留出哈希规则的 152 个基础资产同名的币（名单与规则取自 DQ-29）；
③查不到代号的币（保守排除，数量另报）。只存不分析：在使用这些数据的卡片冻结之前，不做收益分析。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
PUMPSWAP_START = dt.date(2025, 3, 15)

TEMPLATE = """/* DQ-35 数据留存（10-02，执行模型）：pump 迁移池在 {e_start}～{e_end} 的成交；只存不分析；由 build_grad_sql.py 生成 */
WITH
{names},
cp AS (
    /* 由 pump 程序在迁移交易里创建、池序号为 0 的 PumpSwap 池（DQ-1M 的 by_pump 口径；迁移事件表 2025 年为空） */
    SELECT pool, min(evt_block_time) AS created_at, max(base_mint) AS mint, max(quote_mint) AS quote_mint,
           max(base_mint_decimals) AS bd, max(quote_mint_decimals) AS qd
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '{p_start}' AND DATE '{e_end}'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1
),
sym AS (
    SELECT mint, arbitrary(symbol) AS symbol
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{s_start}' AND DATE '{e_end}'
      AND mint IN (SELECT mint FROM cp)
    GROUP BY 1
),
pools AS (
    SELECT c.pool, c.mint, c.quote_mint, c.created_at, c.bd, c.qd
    FROM cp c
    LEFT JOIN sym s ON s.mint = c.mint
    WHERE c.created_at >= TIMESTAMP '{e_start} 00:00:00' - INTERVAL '180' DAY
      AND c.created_at < TIMESTAMP '{e_end} 00:00:00' + INTERVAL '1' DAY
      AND NOT (c.created_at >= TIMESTAMP '2026-06-15 00:00:00' AND c.created_at < TIMESTAMP '2026-07-13 00:00:00')
      AND s.symbol IS NOT NULL
      AND upper(trim(replace(s.symbol, '$', ''))) NOT IN (SELECT base FROM excl)
),
ev AS (
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
           COALESCE(evt_inner_instruction_index, 0) AS iix, 'B' AS side, "user" AS usr,
           CAST(pool_quote_token_reserves AS DOUBLE) AS q0,
           CAST(pool_base_token_reserves AS DOUBLE) AS b0,
           CAST(quote_amount_in AS DOUBLE) AS q_amt,
           CAST(base_amount_out AS DOUBLE) AS b_amt,
           CAST(user_quote_amount_in AS DOUBLE) AS q_user,
           CAST(pool_quote_token_reserves AS DOUBLE) + CAST(quote_amount_in AS DOUBLE)
             - COALESCE(CAST(protocol_fee AS DOUBLE), 0) - COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS q1,
           CAST(pool_base_token_reserves AS DOUBLE) - CAST(base_amount_out AS DOUBLE) AS b1
    FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
      AND pool IN (SELECT pool FROM pools)
    UNION ALL
    SELECT pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
           COALESCE(evt_inner_instruction_index, 0) AS iix, 'S' AS side, "user" AS usr,
           CAST(pool_quote_token_reserves AS DOUBLE) AS q0,
           CAST(pool_base_token_reserves AS DOUBLE) AS b0,
           CAST(quote_amount_out AS DOUBLE) AS q_amt,
           CAST(base_amount_in AS DOUBLE) AS b_amt,
           CAST(user_quote_amount_out AS DOUBLE) AS q_user,
           CAST(pool_quote_token_reserves AS DOUBLE)
             - (CAST(quote_amount_out AS DOUBLE) - COALESCE(CAST(lp_fee AS DOUBLE), 0)) AS q1,
           CAST(pool_base_token_reserves AS DOUBLE) + CAST(base_amount_in AS DOUBLE) AS b1
    FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
      AND pool IN (SELECT pool FROM pools)
),
k AS (
    SELECT e.*, p.mint, p.quote_mint, p.created_at, p.bd, p.qd,
           date_diff('second', p.created_at, e.ts) AS age,
           (e.q1 / power(10, p.qd)) / nullif(e.b1 / power(10, p.bd), 0) AS px,
           CAST(e.slot AS DOUBLE) * 1e7 + e.txi * 1e3 + e.iix AS ord
    FROM ev e
    JOIN pools p ON p.pool = e.pool
    WHERE e.ts >= p.created_at AND e.ts < p.created_at + INTERVAL '180' DAY
)
SELECT CASE WHEN age < 300 THEN 'S' WHEN age < 604800 THEN 'H' ELSE 'D' END AS kind,
       mint, pool, quote_mint, created_at, bd, qd,
       CASE WHEN age < 300 THEN floor(age / 5e0) WHEN age < 604800 THEN floor(age / 3600e0)
            ELSE floor(age / 86400e0) END AS bkey,
       count(*) AS n, count_if(side = 'B') AS n_buy, approx_distinct(usr) AS n_users,
       sum(CASE WHEN side = 'B' THEN q_user END) AS q_buy_user,
       sum(CASE WHEN side = 'S' THEN q_user END) AS q_sell_user,
       sum(CASE WHEN side = 'B' THEN b_amt END) AS b_buy,
       sum(CASE WHEN side = 'S' THEN b_amt END) AS b_sell,
       min_by(q0, ord) AS q0_open, min_by(b0, ord) AS b0_open,
       max_by(q1, ord) AS q1_close, max_by(b1, ord) AS b1_close,
       min_by(px, ord) AS px_open, max_by(px, ord) AS px_close, max(px) AS px_high, min(px) AS px_low,
       min(ts) AS t_first, max(ts) AS t_last
FROM k
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
"""


def main() -> None:
    e_start = dt.date.fromisoformat(sys.argv[1])
    e_end = dt.date.fromisoformat(sys.argv[2])
    label = sys.argv[3]
    p_start = max(PUMPSWAP_START, e_start - dt.timedelta(days=181))
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    sql = TEMPLATE.format(
        names=names,
        e_start=e_start.isoformat(),
        e_end=e_end.isoformat(),
        p_start=p_start.isoformat(),
        s_start=(p_start - dt.timedelta(days=90)).isoformat(),
    )
    (H / "sql" / f"{label}.sql").write_text(sql)
    print(f"sql/{label}.sql")


if __name__ == "__main__":
    main()
