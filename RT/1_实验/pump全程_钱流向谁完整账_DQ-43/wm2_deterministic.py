"""第九轮：最小母体与池契约；旧生成器和批准 SQL 保留。

母体 min_by 使用完整链上键；多次创建由首笔契约的 K.q 拒绝。
池只取允许的首次创建时刻，不带用不到的任意首行字段。
"""

import sys

__all__ = ["B"]

# 旧生成器加载冻结 weeks 时临时加入 DQ-37 路径。
# 保留调用者路径，避免随后误导入同名的旧 run_dune/dune_get。
_path_before = sys.path[:]
try:
    import build_wm2_sql as B
finally:
    sys.path[:] = _path_before

KEY = "ARRAY[evt_block_slot,evt_tx_index,evt_outer_instruction_index,COALESCE(evt_inner_instruction_index,-1)]"


def population(f):
    key = KEY
    return """/* 第九轮 {layer}，取数附录 v5。保护过滤先于导出。 */
WITH
{names},
c0 AS (
    SELECT mint,min(evt_block_time) AS created_at,count(*) AS n_create,
           min_by(symbol,{key}) AS symbol,
           min_by(COALESCE(creator,"user"),{key}) AS creator,
           min_by(quote_mint,{key}) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{c0}' AND DATE '{c1}'
    GROUP BY mint
),
c1 AS (
    SELECT c0.*,
           CASE WHEN symbol IS NULL OR trim(replace(symbol,'$',''))='' THEN 'excl'
                WHEN upper(trim(replace(symbol,'$',''))) IN (SELECT base FROM excl) THEN 'excl'
                WHEN quote_mint IS NOT NULL AND quote_mint <> '{sys}' THEN 'excl'
                ELSE 'in' END AS pop_class
    FROM c0
    WHERE created_at >= TIMESTAMP '{c0} 00:00:00' AND created_at < TIMESTAMP '{c1} 00:00:00'+INTERVAL '1' DAY
      AND created_at < TIMESTAMP '{cutoff} 00:00:00'
),
pop AS (SELECT * FROM c1 WHERE pop_class='in'),
coins AS (SELECT * FROM pop{samp})""".format(key=key, **f)


def pools(f):
    return """,
cp AS (
    SELECT c.pool,min(c.evt_block_time) AS created_at,max(c.base_mint) AS mint,
           max(c.quote_mint) AS quote_mint,count(*) AS n_cp
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent c JOIN coins k ON k.mint=c.base_mint
    WHERE c.evt_block_date BETWEEN DATE '{e0}' AND DATE '{e1}'
      AND c.evt_outer_executing_account='{pump}' AND c.index=0
      AND c.evt_block_time >= k.created_at AND c.evt_block_time < k.created_at+INTERVAL '{hz}' DAY
      AND c.evt_block_time < TIMESTAMP '{cutoff} 00:00:00'
    GROUP BY c.pool
),
pools AS (
    SELECT cp.*,k.created_at AS coin_created_at FROM cp JOIN coins k ON k.mint=cp.mint
    WHERE cp.quote_mint='{wsol}'
)""".format(**f)


def integer_time(sql):
    import re

    return re.sub(
        r"CAST\(to_unixtime\(([^()]*)\) AS bigint\)",
        r"date_diff('second',TIMESTAMP '1970-01-01 00:00:00',\1)",
        sql,
        flags=re.IGNORECASE,
    )
