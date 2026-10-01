#!/usr/bin/env python3
"""DQ-26 第一步·实体关系查询（卡片_v1.md §2；只用 t_R 之前的信息）。

E1：候选钱包的直接往来（`tokens_solana.transfers`）。
  - S 行：原生 SOL，顶层 System Program 转账（outer_executing_account＝System Program），≥0.05 SOL，
    回看期 2026-07-27～08-16；成交中的付款是程序内转账，不在此列。
  - T 行：R 的币，由代币程序或关联账户程序在顶层执行的转移（直接转账，不含成交腿），08-03～08-16。
  按（from, to, mint）汇总：笔数、数量、首末时间。第一笔资金来源在本地取（每个候选的最早入账 S 行）。
E2：资金来源的扇出——给定来源地址，回看期内收到 ≥0.05 SOL 顶层转账的不同地址数；
  扇出 ≤200 的来源列出全部接收方，>200 的只出一行计数（服务节点）。

python sql/build_edge_sql.py E1 候选.csv → sql/EDGE_E1_R.sql
python sql/build_edge_sql.py E2 来源.csv → sql/EDGE_E2_R.sql
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import sqlglot

H = Path(__file__).resolve().parent
LB0, R0, R1, CUT = "2026-07-27", "2026-08-03", "2026-08-09", "2026-08-16"
SYS = "11111111111111111111111111111111"
TOKEN_PROGRAMS = (
    "'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA', "
    "'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb', "
    "'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'"
)


def values(name: str, col: str, items: list[str]) -> str:
    vals = ",\n".join(f"        ('{a}')" for a in items)
    return f"{name}({col}) AS (\n    SELECT {col} FROM (VALUES\n{vals}\n    ) AS v({col})\n)"


def e1(users: list[str]) -> str:
    return f"""/* DQ-26 第一步·实体关系 E1（卡片_v1.md §2）；由 sql/build_edge_sql.py 生成。
   候选钱包 {len(users)} 个（排名查询 W 初排前 {len(users)}）。只读 {LB0}～{CUT} 的分区；不读 08-17 及之后。
   S＝顶层 System Program 的 SOL 转账 ≥0.05；T＝R 币的直接代币转移（顶层代币程序或关联账户程序）。 */
WITH
{values("sel", "usr", users)},
rm AS (
    SELECT DISTINCT mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{R0}' AND DATE '{R1}'
),
tr AS (
    SELECT
        IF(token_version = 'native', 'S', 'T') AS kind,
        from_owner, to_owner,
        IF(token_version = 'native', CAST(NULL AS varchar), token_mint_address) AS mint,
        amount_display AS amt,
        block_time
    FROM tokens_solana.transfers
    WHERE block_date BETWEEN DATE '{LB0}' AND DATE '{CUT}'
      AND action = 'transfer'
      AND from_owner <> to_owner
      AND (from_owner IN (SELECT usr FROM sel) OR to_owner IN (SELECT usr FROM sel))
      AND (
          (token_version = 'native' AND outer_executing_account = '{SYS}' AND amount_display >= 0.05)
          OR (
              block_date >= DATE '{R0}'
              AND token_version <> 'native'
              AND outer_executing_account IN ({TOKEN_PROGRAMS})
              AND token_mint_address IN (SELECT mint FROM rm)
          )
      )
)
SELECT kind, from_owner, to_owner, mint,
       count(*) AS n, sum(amt) AS amt, min(block_time) AS first_ts, max(block_time) AS last_ts
FROM tr
GROUP BY 1, 2, 3, 4
"""


def e2(funders: list[str]) -> str:
    return f"""/* DQ-26 第一步·资金来源扇出 E2（卡片_v1.md §2 服务节点定义）；由 sql/build_edge_sql.py 生成。
   来源地址 {len(funders)} 个（E1 中候选钱包的第一笔 ≥0.05 SOL 来源，已去掉交易所严格标签）。
   回看期 {LB0}～{CUT}，顶层 System Program 的 SOL 转账 ≥0.05。扇出 >200 的来源只出一行。 */
WITH
{values("fund", "addr", funders)},
tr AS (
    SELECT from_owner, to_owner, count(*) AS n, sum(amount_display) AS amt, min(block_time) AS first_ts
    FROM tokens_solana.transfers
    WHERE block_date BETWEEN DATE '{LB0}' AND DATE '{CUT}'
      AND token_version = 'native'
      AND action = 'transfer'
      AND outer_executing_account = '{SYS}'
      AND amount_display >= 0.05
      AND from_owner <> to_owner
      AND from_owner IN (SELECT addr FROM fund)
    GROUP BY 1, 2
),
f AS (
    SELECT
        *,
        count(*) OVER (PARTITION BY from_owner) AS fanout,
        row_number() OVER (PARTITION BY from_owner ORDER BY first_ts, to_owner) AS rn
    FROM tr
)
SELECT from_owner, to_owner, n, amt, first_ts, fanout
FROM f
WHERE fanout <= 200 OR rn = 1
"""


def main() -> None:
    which, src = sys.argv[1], sys.argv[2]
    items = pd.read_csv(src).iloc[:, 0].astype(str).tolist()
    sql = e1(items) if which == "E1" else e2(items)
    sqlglot.parse_one(sql, read="trino")
    dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
    assert dates[0] >= LB0 and dates[-1] <= CUT, dates
    out = H / f"EDGE_{which}_R.sql"
    out.write_text(sql)
    h = hashlib.sha256(out.read_bytes()).hexdigest()
    with open(H / "sha256.txt", "a") as fh:
        fh.write(f"{out.name} {h}\n")
    print(out.name, h[:12], len(sql))


if __name__ == "__main__":
    main()
