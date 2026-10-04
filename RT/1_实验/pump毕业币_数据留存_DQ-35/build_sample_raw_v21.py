#!/usr/bin/env python3
"""DQ-35 v2.1 扩大样本的逐笔原始事件（10-04，GPT 10-04 复核第 5 条）：独立母体、多日事件，供 compare_sample_v21.py 逐项比对。

python build_sample_raw_v21.py grad <事件起日> <事件止日> <建池起时> <建池止时> <标签> [--nonsol]
python build_sample_raw_v21.py pre  <完成起日> <完成止日> <完成起时> <完成止时> <标签>

与正式生成器（build_grad_sql_v21.py、build_gradpre_sql_v21.py）分开实现，不共用 CTE：
- 母体：grad 从建池事件按建池时刻窗口取候选，pre 从完成事件按完成时刻窗口取候选；曲线创建时刻与代号按全历史另查。
- 排除另写一遍：封存按曲线创建时刻落在 [2026-06-15, 2026-07-13)；留出同名按 _holdout_names.sqlpart；查不到曲线创建事件的排除。
- 输出：'C' 行＝每个纳入的池（或币）一行，含零成交的；'X' 行＝排除计数（只给计数，不给被排除池的任何字段）；
  其余为纳入池的逐笔事件，金额精确整数（varchar）。对照脚本以 'C' 行为母体，SQL 结果里整池缺失也能发现。
  grad 的 'C' 行借用列：q0＝quote_mint，b0＝quote decimals，q_amt＝mint，q_amt_lp＝base decimals，q_user＝曲线创建 epoch 秒；
  'X' 行：pool＝排除类别，q0＝个数。pre 的 'C' 行：qa＝曲线创建 epoch 秒。
样本只用 DQ-37 开发周创建的池或币；只用于核对提取 SQL 的齐全、精度与一致性，不看价格或收益分布。
"""

import datetime as dt
import sys
from pathlib import Path

H = Path(__file__).resolve().parent

SEALED = (
    "TIMESTAMP '2026-06-15 00:00:00' <= {c} AND {c} < TIMESTAMP '2026-07-13 00:00:00'"
)

GRAD = """/* DQ-35 v2.1 扩大样本逐笔（10-04，执行模型）：建池于 {w0}～{w1} 的 pump 迁移池在 {d0}～{d1} 的全部买卖、加撤池事件；独立母体；只用于核对 */
WITH
{names},
c0 AS (
    SELECT pool, min(evt_block_time) AS created_at, max(base_mint) AS mint, max(quote_mint) AS quote_mint,
           max(base_mint_decimals) AS bd, max(quote_mint_decimals) AS qd
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '{wd0}' AND DATE '{wd1}'
      AND evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND index = 0
    GROUP BY 1
    HAVING min(evt_block_time) >= TIMESTAMP '{w0}' AND min(evt_block_time) < TIMESTAMP '{w1}'{nonsol}
),
cr AS (
    SELECT mint, min(evt_block_time) AS cct, min_by(symbol, evt_block_time) AS sym
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{wd1}'
      AND mint IN (SELECT mint FROM c0)
    GROUP BY 1
),
lab AS (
    SELECT c0.*, cr.cct,
           CASE WHEN cr.cct IS NULL THEN 'no_create'
                WHEN {sealed} THEN 'sealed'
                WHEN upper(trim(replace(cr.sym, '$', ''))) IN (SELECT base FROM excl) THEN 'holdout_name'
                ELSE 'in' END AS cls
    FROM c0 LEFT JOIN cr ON cr.mint = c0.mint
),
inp AS (SELECT * FROM lab WHERE cls = 'in')
SELECT 'C' AS ev, pool, created_at AS ts, NULL AS slot, NULL AS txi, NULL AS oix, NULL AS iix, NULL AS tx_id, NULL AS usr,
       quote_mint AS q0, CAST(qd AS varchar) AS b0, mint AS q_amt, CAST(bd AS varchar) AS q_amt_lp,
       CAST(to_unixtime(cct) AS varchar) AS q_user, NULL AS b_amt, NULL AS f_lp, NULL AS f_pr, NULL AS f_cr, NULL AS f_cb, NULL AS f_bb
FROM inp
UNION ALL
SELECT 'X', cls, NULL, NULL, NULL, NULL, NULL, NULL, NULL, CAST(count(*) AS varchar), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM lab WHERE cls <> 'in' GROUP BY cls
UNION ALL
SELECT 'B', pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index,
       evt_tx_id, "user",
       CAST(pool_quote_token_reserves AS varchar), CAST(pool_base_token_reserves AS varchar),
       CAST(quote_amount_in AS varchar), CAST(quote_amount_in_with_lp_fee AS varchar),
       CAST(user_quote_amount_in AS varchar), CAST(base_amount_out AS varchar),
       CAST(lp_fee AS varchar), CAST(protocol_fee AS varchar), CAST(coin_creator_fee AS varchar), NULL, NULL
FROM pumpdotfun_solana.pump_amm_evt_buyevent
WHERE evt_block_date BETWEEN DATE '{d0}' AND DATE '{d1}' AND pool IN (SELECT pool FROM inp)
UNION ALL
SELECT 'S', pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index,
       evt_tx_id, "user",
       CAST(pool_quote_token_reserves AS varchar), CAST(pool_base_token_reserves AS varchar),
       CAST(quote_amount_out AS varchar), CAST(quote_amount_out_without_lp_fee AS varchar),
       CAST(user_quote_amount_out AS varchar), CAST(base_amount_in AS varchar),
       CAST(lp_fee AS varchar), CAST(protocol_fee AS varchar), CAST(coin_creator_fee AS varchar),
       CAST(cashback AS varchar), CAST(buyback_fee AS varchar)
FROM pumpdotfun_solana.pump_amm_evt_sellevent
WHERE evt_block_date BETWEEN DATE '{d0}' AND DATE '{d1}' AND pool IN (SELECT pool FROM inp)
UNION ALL
SELECT 'D', pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index,
       evt_tx_id, "user",
       CAST(pool_quote_token_reserves AS varchar), CAST(pool_base_token_reserves AS varchar),
       CAST(quote_amount_in AS varchar), NULL, NULL, CAST(base_amount_in AS varchar), NULL, NULL, NULL, NULL, NULL
FROM pumpdotfun_solana.pump_amm_evt_depositevent
WHERE evt_block_date BETWEEN DATE '{d0}' AND DATE '{d1}' AND pool IN (SELECT pool FROM inp)
UNION ALL
SELECT 'W', pool, evt_block_time, evt_block_slot, evt_tx_index, evt_outer_instruction_index, evt_inner_instruction_index,
       evt_tx_id, "user",
       CAST(pool_quote_token_reserves AS varchar), CAST(pool_base_token_reserves AS varchar),
       CAST(quote_amount_out AS varchar), NULL, NULL, CAST(base_amount_out AS varchar), NULL, NULL, NULL, NULL, NULL
FROM pumpdotfun_solana.pump_amm_evt_withdrawevent
WHERE evt_block_date BETWEEN DATE '{d0}' AND DATE '{d1}' AND pool IN (SELECT pool FROM inp)
"""

PRE = """/* DQ-35 v2.1 扩大样本逐笔（10-04，执行模型）：曲线完成于 {w0}～{w1} 的 pump 币，完成前 300 秒的全部曲线成交；独立母体；只用于核对 */
WITH
{names},
c0 AS (
    SELECT mint, min(evt_block_time) AS completed_at, min_by(quote_mint, evt_block_time) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '{wd0}' AND DATE '{wd1}'
    GROUP BY 1
    HAVING min(evt_block_time) >= TIMESTAMP '{w0}' AND min(evt_block_time) < TIMESTAMP '{w1}'
),
cr AS (
    SELECT mint, min(evt_block_time) AS cct, min_by(symbol, evt_block_time) AS sym
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2024-01-01' AND DATE '{wd1}'
      AND mint IN (SELECT mint FROM c0)
    GROUP BY 1
),
lab AS (
    SELECT c0.*, cr.cct,
           CASE WHEN cr.cct IS NULL THEN 'no_create'
                WHEN {sealed} THEN 'sealed'
                WHEN upper(trim(replace(cr.sym, '$', ''))) IN (SELECT base FROM excl) THEN 'holdout_name'
                ELSE 'in' END AS cls
    FROM c0 LEFT JOIN cr ON cr.mint = c0.mint
),
inp AS (SELECT * FROM lab WHERE cls = 'in')
SELECT 'C' AS kind, mint, completed_at AS ts, NULL AS slot, NULL AS txi, NULL AS oix, NULL AS iix, NULL AS tx_id,
       NULL AS is_buy, NULL AS usr, NULL AS sol, NULL AS tok, NULL AS x, NULL AS y, NULL AS xr, NULL AS f_pr, NULL AS f_cr,
       NULL AS f_cb, NULL AS f_bb, quote_mint, CAST(to_unixtime(cct) AS varchar) AS qa, NULL AS mayhem_mode
FROM inp
UNION ALL
SELECT 'X', cls, NULL, NULL, NULL, NULL, NULL, NULL, NULL, CAST(count(*) AS varchar), NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL
FROM lab WHERE cls <> 'in' GROUP BY cls
UNION ALL
SELECT 'T', t.mint, t.evt_block_time, t.evt_block_slot, t.evt_tx_index, t.evt_outer_instruction_index, t.evt_inner_instruction_index,
       t.evt_tx_id, COALESCE(t.is_buy, t.isBuy), CAST(t."user" AS varchar),
       CAST(COALESCE(t.sol_amount, t.solAmount) AS varchar), CAST(COALESCE(t.token_amount, t.tokenAmount) AS varchar),
       CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS varchar),
       CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS varchar),
       CAST(t.real_sol_reserves AS varchar), CAST(t.fee AS varchar), CAST(t.creator_fee AS varchar),
       CAST(t.cashback AS varchar), CAST(t.buyback_fee AS varchar), t.quote_mint, CAST(t.quote_amount AS varchar), t.mayhem_mode
FROM pumpdotfun_solana.pump_evt_tradeevent t
JOIN inp m ON m.mint = t.mint
WHERE t.evt_block_date BETWEEN DATE '{d0}' - INTERVAL '1' DAY AND DATE '{d1}'
  AND t.evt_block_time > m.completed_at - INTERVAL '300' SECOND
  AND t.evt_block_time <= m.completed_at
"""


def last_day(w1):
    """窗口 [w0, w1) 最后可能落入的日期：w1 恰为零点时是前一天。"""
    d = dt.date.fromisoformat(w1[:10])
    return (d - dt.timedelta(days=1) if w1[11:19] == "00:00:00" else d).isoformat()


def main():
    kind, d0, d1, w0, w1, label = sys.argv[1:7]
    nonsol = len(sys.argv) > 7 and sys.argv[7] == "--nonsol"
    names = (H / "sql" / "_holdout_names.sqlpart").read_text().rstrip().rstrip(",")
    tpl = {"grad": GRAD, "pre": PRE}[kind]
    col = "cr.cct"
    sql = tpl.format(
        names=names,
        d0=d0,
        d1=d1,
        w0=w0,
        w1=w1,
        wd0=w0[:10],
        wd1=last_day(w1),
        sealed=SEALED.format(c=col),
        nonsol=(
            "\n       AND max(quote_mint) <> 'So11111111111111111111111111111111111111112'"
            if nonsol
            else ""
        ),
    )
    (H / "sql" / ("%s.sql" % label)).write_text(sql)
    print("sql/%s.sql" % label)


if __name__ == "__main__":
    main()
