#!/usr/bin/env python3
"""DQ-35 v2（10-03）：按 GPT 提取 SQL 审计修正的毕业前留存 SQL（曲线完成前 300 秒的曲线成交，5 秒桶）。

python build_gradpre_sql_v2.py <起日> <止日> <标签> [--sample <起时> <止时>]  → sql/<标签>.sql
--sample 只用于小样本对照：把母体限制为曲线完成时刻在 [起时, 止时) 的币。

相对 v1（build_gradpre_sql.py）的改动，编号对应审计表：
 1. 代号与曲线创建时刻按全历史查（v1 只回查 120 天，晚毕业的老币整币漏掉）。
 2. 封存周按曲线创建时刻定义（v1 按完成时刻），与 GRAD v2、DQ-37 一致。
 3. TradeEvent 的虚拟储备是成交后状态：v1 的 x_first/y_first 改名 x_post_first/y_post_first，
    另存首笔方向与金额，并给出首笔成交前储备 x_pre_first＝x_post−sol（买）或＋sol（卖），y 同理反向。
 4. 排序键同 GRAD v2（含外层指令序号），每桶存首末 ord（转 varchar，见 GRAD v2 第 4 条）与越界计数；ord 唯一性在小样本对照里核。
 5. 每个币的 300 秒窗口整体落在按完成日分的同一片里，不跨片，用户数可直接用；仍为 approx_distinct
    （小基数下近似精确；精确去重的费用见 build_grad_sql_v2.py 第 5 条）。
另：存曲线的计价资产（quote_mint）、非 SOL 计价时的 quote_amount 合计、mayhem 标志与各项费用合计；
2026-05 起出现非 SOL 计价与 mayhem 模式的币，这些币的 sol 与虚拟 SOL 储备字段含义待小样本核对。只存不分析。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent

TEMPLATE = """/* DQ-35 v2 数据留存（10-03，执行模型）：曲线完成于 {e_start}～{e_end} 的 pump 币，完成前 300 秒的曲线成交（5 秒桶）；只存不分析；由 build_gradpre_sql_v2.py 生成 */
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
mints AS (
    SELECT c.mint, c.completed_at, c.c_quote_mint, s.curve_created_at
    FROM comp c
    JOIN cc s ON s.mint = c.mint
    WHERE c.completed_at >= TIMESTAMP '{e_start} 00:00:00'
      AND NOT (s.curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND s.curve_created_at < TIMESTAMP '2026-07-13 00:00:00')
      AND upper(trim(replace(s.symbol, '$', ''))) NOT IN (SELECT base FROM excl){sample}
),
tr AS (
    SELECT t.mint, m.completed_at, m.curve_created_at, m.c_quote_mint, t.evt_block_time AS ts,
           CAST(t.evt_block_slot AS BIGINT) * 10000000000 + CAST(t.evt_tx_index AS BIGINT) * 100000
             + CAST(t.evt_outer_instruction_index AS BIGINT) * 1000 + COALESCE(t.evt_inner_instruction_index, 0) AS ord,
           CASE WHEN t.evt_tx_index >= 100000 OR t.evt_outer_instruction_index >= 100
                  OR COALESCE(t.evt_inner_instruction_index, 0) >= 1000 OR t.evt_outer_instruction_index IS NULL
                THEN 1 ELSE 0 END AS ovf,
           COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok,
           CAST(t.quote_amount AS DOUBLE) AS qa_raw,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
           CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr,
           COALESCE(CAST(t.fee AS DOUBLE), 0) / 1e9 AS f_pr,
           COALESCE(CAST(t.creator_fee AS DOUBLE), 0) / 1e9 AS f_cr,
           COALESCE(CAST(t.cashback AS DOUBLE), 0) / 1e9 AS f_cb,
           COALESCE(CAST(t.buyback_fee AS DOUBLE), 0) / 1e9 AS f_bb,
           COALESCE(t.mayhem_mode, false) AS mayhem
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN mints m ON m.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{t_start}' AND DATE '{e_end}'
      AND t.evt_block_time > m.completed_at - INTERVAL '300' SECOND
      AND t.evt_block_time <= m.completed_at
)
SELECT mint, completed_at, curve_created_at, c_quote_mint,
       floor(date_diff('millisecond', ts, completed_at) / 5000e0) AS bkey,
       count(*) AS n, count_if(is_buy) AS n_buy, approx_distinct(usr) AS n_users,
       sum(CASE WHEN is_buy THEN sol ELSE 0 END) AS sol_buy, sum(CASE WHEN NOT is_buy THEN sol ELSE 0 END) AS sol_sell,
       sum(CASE WHEN is_buy THEN tok ELSE 0 END) AS tok_buy, sum(CASE WHEN NOT is_buy THEN tok ELSE 0 END) AS tok_sell,
       sum(CASE WHEN is_buy THEN qa_raw ELSE 0 END) AS qa_buy_raw, sum(CASE WHEN NOT is_buy THEN qa_raw ELSE 0 END) AS qa_sell_raw,
       max(CASE WHEN is_buy THEN sol END) AS max_buy_sol,
       sum(f_pr) AS f_pr, sum(f_cr) AS f_cr, sum(f_cb) AS f_cb, sum(f_bb) AS f_bb, max(CASE WHEN mayhem THEN 1 ELSE 0 END) AS mayhem,
       CAST(min(ord) AS varchar) AS ord_first, CAST(max(ord) AS varchar) AS ord_last,
       min_by(is_buy, ord) AS buy_first, min_by(sol, ord) AS sol_first, min_by(tok, ord) AS tok_first,
       min_by(x, ord) AS x_post_first, min_by(y, ord) AS y_post_first,
       min_by(CASE WHEN is_buy THEN x - sol ELSE x + sol END, ord) AS x_pre_first,
       min_by(CASE WHEN is_buy THEN y + tok ELSE y - tok END, ord) AS y_pre_first,
       max_by(is_buy, ord) AS buy_last,
       max_by(x, ord) AS x_last, max_by(y, ord) AS y_last, max_by(xr, ord) AS xr_last,
       min(ts) AS t_first, max(ts) AS t_last,
       sum(ovf) AS n_ord_overflow
FROM tr
GROUP BY 1, 2, 3, 4, 5
"""


def build(e_start, e_end, sample=None):
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    smp = ""
    if sample:
        smp = (
            "\n      AND c.completed_at >= TIMESTAMP '%s' AND c.completed_at < TIMESTAMP '%s'"
            % sample
        )
    return TEMPLATE.format(
        names=names,
        e_start=e_start.isoformat(),
        e_end=e_end.isoformat(),
        t_start=(e_start - dt.timedelta(days=1)).isoformat(),
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
