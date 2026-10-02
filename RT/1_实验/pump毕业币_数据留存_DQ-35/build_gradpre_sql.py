#!/usr/bin/env python3
"""DQ-35 数据留存（总控第八轮第二节②的毕业前部分）：pump 曲线完成（毕业）前 300 秒的曲线成交，5 秒分桶（10-02）。

python build_gradpre_sql.py <起日> <止日> <标签>  → sql/<标签>.sql
范围：曲线完成时刻在 [起日, 止日] 的币。毕业后部分已在 GRAD_* 的 S 行（建池后 300 秒，5 秒分桶）。
每桶：笔数、买入笔数、不同用户数、买卖 SOL 与代币量、桶首成交前与桶末成交后的虚拟储备、真实 SOL 储备。
bkey＝完成前第几个 5 秒（0 表示完成前 0～5 秒）。排除规则同 build_grad_sql.py：封存周 2026-06-15～07-12 完成的币、
代号与币安留出哈希命中名同名的币、查不到代号的币。只存不分析。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent

TEMPLATE = """/* DQ-35 数据留存（10-02，执行模型）：曲线完成于 {e_start}～{e_end} 的 pump 币，完成前 300 秒的曲线成交（5 秒桶）；只存不分析；由 build_gradpre_sql.py 生成 */
WITH
{names},
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '{e_start}' AND DATE '{e_end}'
    GROUP BY 1
),
sym AS (
    SELECT mint, arbitrary(symbol) AS symbol
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{s_start}' AND DATE '{e_end}'
      AND mint IN (SELECT mint FROM comp)
    GROUP BY 1
),
mints AS (
    SELECT c.mint, c.completed_at
    FROM comp c
    LEFT JOIN sym s ON s.mint = c.mint
    WHERE c.completed_at >= TIMESTAMP '{e_start} 00:00:00'
      AND NOT (c.completed_at >= TIMESTAMP '2026-06-15 00:00:00' AND c.completed_at < TIMESTAMP '2026-07-13 00:00:00')
      AND s.symbol IS NOT NULL
      AND upper(trim(replace(s.symbol, '$', ''))) NOT IN (SELECT base FROM excl)
),
tr AS (
    SELECT t.mint, m.completed_at, t.evt_block_time AS ts,
           CAST(t.evt_block_slot AS DOUBLE) * 1e7 + t.evt_tx_index * 1e3 + COALESCE(t.evt_inner_instruction_index, 0) AS ord,
           COALESCE(t.is_buy, t.isBuy) AS is_buy,
           CAST(t."user" AS varchar) AS usr,
           CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol,
           CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok,
           CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
           CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
           CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN mints m ON m.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{t_start}' AND DATE '{e_end}'
      AND t.evt_block_time > m.completed_at - INTERVAL '300' SECOND
      AND t.evt_block_time <= m.completed_at
)
SELECT mint, completed_at,
       floor(date_diff('millisecond', ts, completed_at) / 5000e0) AS bkey,
       count(*) AS n, count_if(is_buy) AS n_buy, approx_distinct(usr) AS n_users,
       sum(CASE WHEN is_buy THEN sol END) AS sol_buy, sum(CASE WHEN NOT is_buy THEN sol END) AS sol_sell,
       sum(CASE WHEN is_buy THEN tok END) AS tok_buy, sum(CASE WHEN NOT is_buy THEN tok END) AS tok_sell,
       max_by(sol, CASE WHEN is_buy THEN sol END) AS max_buy_sol,
       min_by(x, ord) AS x_first, min_by(y, ord) AS y_first,
       max_by(x, ord) AS x_last, max_by(y, ord) AS y_last, max_by(xr, ord) AS xr_last,
       min(ts) AS t_first, max(ts) AS t_last
FROM tr
GROUP BY 1, 2, 3
"""


def main() -> None:
    e_start = dt.date.fromisoformat(sys.argv[1])
    e_end = dt.date.fromisoformat(sys.argv[2])
    label = sys.argv[3]
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    sql = TEMPLATE.format(
        names=names,
        e_start=e_start.isoformat(),
        e_end=e_end.isoformat(),
        s_start=(e_start - dt.timedelta(days=120)).isoformat(),
        t_start=(e_start - dt.timedelta(days=1)).isoformat(),
    )
    (H / "sql" / f"{label}.sql").write_text(sql)
    print(f"sql/{label}.sql")


if __name__ == "__main__":
    main()
