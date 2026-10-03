#!/usr/bin/env python3
"""DQ-35 v2 小样本对照（10-03，总控第十三轮第二节第 2 条）：取逐笔原始事件，供 compare_sample_v2.py 与分桶结果逐项比对。

python build_sample_raw_v2.py grad <事件日> <建池起时> <建池止时> <标签>
python build_sample_raw_v2.py pre  <完成日> <完成起时> <完成止时> <标签>
母体条件（建池或完成时刻窗口、封存周、留出同名、全历史代号）与 v2 正式 SQL 相同，逐笔输出全部字段，不分桶。
样本日只用 DQ-37 开发周（2025-10-07、2026-09-23）。
"""

import sys
from pathlib import Path

H = Path(__file__).resolve().parent

GRAD = """/* DQ-35 v2 小样本逐笔（10-03，执行模型）：建池于 {w0}～{w1} 的 pump 迁移池在 {day} 的全部买卖、加撤池事件；只用于核对分桶 SQL */
WITH
{names},
cp AS (
    SELECT pool, min(evt_block_time) AS created_at, max(base_mint) AS mint
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date = DATE '{day}'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1
),
cc AS (
    SELECT mint, min(evt_block_time) AS curve_created_at, min_by(symbol, evt_block_time) AS symbol
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{day}'
      AND mint IN (SELECT mint FROM cp)
    GROUP BY 1
),
pools AS (
    SELECT c.pool FROM cp c JOIN cc s ON s.mint = c.mint
    WHERE c.created_at >= TIMESTAMP '{w0}' AND c.created_at < TIMESTAMP '{w1}'
      AND NOT (s.curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND s.curve_created_at < TIMESTAMP '2026-07-13 00:00:00')
      AND upper(trim(replace(s.symbol, '$', ''))) NOT IN (SELECT base FROM excl)
)
SELECT 'B' AS ev, pool, evt_block_time AS ts, evt_block_slot AS slot, evt_tx_index AS txi,
       evt_outer_instruction_index AS oix, evt_inner_instruction_index AS iix, evt_tx_id AS tx_id, "user" AS usr,
       CAST(pool_quote_token_reserves AS varchar) AS q0, CAST(pool_base_token_reserves AS varchar) AS b0,
       CAST(quote_amount_in AS varchar) AS q_amt, CAST(quote_amount_in_with_lp_fee AS varchar) AS q_amt_lp,
       CAST(user_quote_amount_in AS varchar) AS q_user, CAST(base_amount_out AS varchar) AS b_amt,
       CAST(lp_fee AS varchar) AS f_lp, CAST(protocol_fee AS varchar) AS f_pr, CAST(coin_creator_fee AS varchar) AS f_cr,
       CAST(NULL AS varchar) AS f_cb, CAST(NULL AS varchar) AS f_bb
FROM pumpdotfun_solana.pump_amm_evt_buyevent
WHERE evt_block_date = DATE '{day}' AND pool IN (SELECT pool FROM pools)
UNION ALL
SELECT 'S', pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index,
       evt_tx_id, "user",
       CAST(pool_quote_token_reserves AS varchar), CAST(pool_base_token_reserves AS varchar),
       CAST(quote_amount_out AS varchar), CAST(quote_amount_out_without_lp_fee AS varchar),
       CAST(user_quote_amount_out AS varchar), CAST(base_amount_in AS varchar),
       CAST(lp_fee AS varchar), CAST(protocol_fee AS varchar), CAST(coin_creator_fee AS varchar),
       CAST(cashback AS varchar), CAST(buyback_fee AS varchar)
FROM pumpdotfun_solana.pump_amm_evt_sellevent
WHERE evt_block_date = DATE '{day}' AND pool IN (SELECT pool FROM pools)
UNION ALL
SELECT 'D', pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index,
       evt_tx_id, "user",
       CAST(pool_quote_token_reserves AS varchar), CAST(pool_base_token_reserves AS varchar),
       CAST(quote_amount_in AS varchar), NULL, NULL, CAST(base_amount_in AS varchar), NULL, NULL, NULL, NULL, NULL
FROM pumpdotfun_solana.pump_amm_evt_depositevent
WHERE evt_block_date = DATE '{day}' AND pool IN (SELECT pool FROM pools)
UNION ALL
SELECT 'W', pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index,
       evt_tx_id, "user",
       CAST(pool_quote_token_reserves AS varchar), CAST(pool_base_token_reserves AS varchar),
       CAST(quote_amount_out AS varchar), NULL, NULL, CAST(base_amount_out AS varchar), NULL, NULL, NULL, NULL, NULL
FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
WHERE evt_block_date = DATE '{day}' AND pool IN (SELECT pool FROM pools)
"""

PRE = """/* DQ-35 v2 小样本逐笔（10-03，执行模型）：曲线完成于 {w0}～{w1} 的 pump 币，完成前 300 秒的全部曲线成交；只用于核对分桶 SQL */
WITH
{names},
comp AS (
    SELECT mint, min(evt_block_time) AS completed_at
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date = DATE '{day}'
    GROUP BY 1
),
cc AS (
    SELECT mint, min(evt_block_time) AS curve_created_at, min_by(symbol, evt_block_time) AS symbol
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{day}'
      AND mint IN (SELECT mint FROM comp)
    GROUP BY 1
),
mints AS (
    SELECT c.mint, c.completed_at FROM comp c JOIN cc s ON s.mint = c.mint
    WHERE c.completed_at >= TIMESTAMP '{w0}' AND c.completed_at < TIMESTAMP '{w1}'
      AND NOT (s.curve_created_at >= TIMESTAMP '2026-06-15 00:00:00' AND s.curve_created_at < TIMESTAMP '2026-07-13 00:00:00')
      AND upper(trim(replace(s.symbol, '$', ''))) NOT IN (SELECT base FROM excl)
)
SELECT t.mint, m.completed_at, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
       t.evt_outer_instruction_index AS oix, t.evt_inner_instruction_index AS iix, t.evt_tx_id AS tx_id,
       COALESCE(t.is_buy, t.isBuy) AS is_buy, CAST(t."user" AS varchar) AS usr,
       CAST(COALESCE(t.sol_amount, t.solAmount) AS varchar) AS sol, CAST(COALESCE(t.token_amount, t.tokenAmount) AS varchar) AS tok,
       CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS varchar) AS x,
       CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS varchar) AS y,
       CAST(t.real_sol_reserves AS varchar) AS xr, CAST(t.fee AS varchar) AS f_pr, CAST(t.creator_fee AS varchar) AS f_cr,
       CAST(t.cashback AS varchar) AS f_cb, CAST(t.buyback_fee AS varchar) AS f_bb,
       t.quote_mint, CAST(t.quote_amount AS varchar) AS qa, t.mayhem_mode
FROM pumpdotfun_solana.pump_evt_tradeevent t
JOIN mints m ON m.mint = t.mint
WHERE t.evt_block_date BETWEEN DATE '{day}' - INTERVAL '1' DAY AND DATE '{day}'
  AND t.evt_block_time > m.completed_at - INTERVAL '300' SECOND
  AND t.evt_block_time <= m.completed_at
"""


def main():
    kind, day, w0, w1, label = sys.argv[1:6]
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    tpl = {"grad": GRAD, "pre": PRE}[kind]
    sql = tpl.format(names=names, day=day, w0=w0, w1=w1)
    (H / "sql" / ("%s.sql" % label)).write_text(sql)
    print("sql/%s.sql" % label)


if __name__ == "__main__":
    main()
