#!/usr/bin/env python3
"""DQ-26 第一步·实体钱包记账查询（卡片_v1.md §3、§4）：给定实体钱包名单 E，生成四条单链 SQL。

- BX  跨池成交：`dex_solana.trades` 中 E 在 R 币上的成交，按（钱包, 币, project）汇总（多跳的每一段各一行，
      只取一侧是 R 币的段；对手币为 SOL/WSOL 的记 SOL 金额，其余记 amount_usd）。曲线与 PumpSwap 在本地按 project 剔除。
- BT  代币转移与小费：`tokens_solana.transfers` 中 E 一侧的行（每笔转移按 from、to 两侧展开）。
      R 币：按“该钱包在该笔交易里是否有成交”（曲线事件或 dex_solana.trades）分为成交腿与非成交转移；
      非成交转移保留对手地址（用于实体内抵消与无法归因转入）。
      原生 SOL：只取该钱包成交交易里转出的、去 Jito 小费账户（任意层级）或顶层 System Program 的转账，保留收款地址。
- BFEE 网络费与优先费：`gas_solana.fees`，E 签名的成交交易；另报找不到费用行或签名者不是该钱包的笔数。
- BBAL 期末余额：`solana_utils.daily_balances` 2026-08 分区，08-16 及之前每个代币账户的最后一行，按（所有者, 币）相加。

只读 2026-08-03～08-16 的分区（BBAL 读 2026-08 月分区、day ≤ 08-16）。
python sql/build_book_sql.py 实体钱包.csv → sql/BOOK_{BX,BT,BFEE,BBAL}_R.sql
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import sqlglot

H = Path(__file__).resolve().parent
R0, R1, CUT = "2026-08-03", "2026-08-09", "2026-08-16"
SOL_MINTS = (
    "'So11111111111111111111111111111111111111111', "
    "'So11111111111111111111111111111111111111112'"
)
SYS = "11111111111111111111111111111111"
JITO = json.loads((H.parent / "raw" / "jito_tip_accounts_20261001.json").read_text())[
    "result"
]
JITO_SQL = ", ".join(f"'{a}'" for a in JITO)


def head(name: str, users: list[str], note: str) -> str:
    vals = ",\n".join(f"        ('{u}')" for u in users)
    return f"""/* DQ-26 第一步·记账 {name}（卡片_v1.md §3、§4）；由 sql/build_book_sql.py 生成。
   实体钱包 {len(users)} 个；R 币＝{R0}～{R1} 创建的 pump 币。{note} */
WITH
ent(usr) AS (
    SELECT usr FROM (VALUES
{vals}
    ) AS v(usr)
),
rm AS (
    SELECT DISTINCT mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{R0}' AND DATE '{R1}'
)"""


TT = f"""tt AS (
    SELECT DISTINCT tx_id, usr
    FROM (
        SELECT t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr
        FROM pumpdotfun_solana.pump_evt_tradeevent t
        WHERE t.evt_block_date BETWEEN DATE '{R0}' AND DATE '{CUT}'
          AND CAST(t."user" AS varchar) IN (SELECT usr FROM ent)
          AND t.mint IN (SELECT mint FROM rm)
        UNION ALL
        SELECT d.tx_id, d.trader_id
        FROM dex_solana.trades d
        WHERE d.block_month = DATE '2026-08-01'
          AND d.block_date BETWEEN DATE '{R0}' AND DATE '{CUT}'
          AND d.trader_id IN (SELECT usr FROM ent)
          AND (d.token_bought_mint_address IN (SELECT mint FROM rm)
               OR d.token_sold_mint_address IN (SELECT mint FROM rm))
    )
)"""


def bx(users: list[str]) -> str:
    return (
        head("BX 跨池成交", users, f"只读 {R0}～{CUT}。")
        + f""",
x AS (
    SELECT
        d.trader_id AS usr, d.project, d.tx_id,
        d.token_bought_mint_address IN (SELECT mint FROM rm) AS buy_r,
        d.token_sold_mint_address IN (SELECT mint FROM rm) AS sell_r,
        d.token_bought_mint_address AS mb, d.token_sold_mint_address AS ms,
        d.token_bought_amount AS ab, d.token_sold_amount AS a_s, d.amount_usd AS usd
    FROM dex_solana.trades d
    WHERE d.block_month = DATE '2026-08-01'
      AND d.block_date BETWEEN DATE '{R0}' AND DATE '{CUT}'
      AND d.trader_id IN (SELECT usr FROM ent)
      AND (d.token_bought_mint_address IN (SELECT mint FROM rm)
           OR d.token_sold_mint_address IN (SELECT mint FROM rm))
)
SELECT
    usr, IF(buy_r, mb, ms) AS mint, project,
    count(DISTINCT tx_id) AS n_tx,
    sum(IF(buy_r, ab, 0)) AS tok_b,
    sum(IF(sell_r, a_s, 0)) AS tok_s,
    sum(IF(buy_r AND ms IN ({SOL_MINTS}), a_s, 0)) AS sol_in,
    sum(IF(sell_r AND mb IN ({SOL_MINTS}), ab, 0)) AS sol_out,
    sum(IF(buy_r AND ms NOT IN ({SOL_MINTS}) AND NOT sell_r, usd, 0)) AS usd_other_in,
    sum(IF(sell_r AND mb NOT IN ({SOL_MINTS}) AND NOT buy_r, usd, 0)) AS usd_other_out
FROM x
GROUP BY 1, 2, 3
"""
    )


def bt(users: list[str]) -> str:
    return (
        head("BT 代币转移与小费", users, f"只读 {R0}～{CUT}。")
        + f""",
{TT},
tr AS (
    SELECT
        t.tx_id, t.token_mint_address AS mint, t.token_version, t.action,
        t.outer_executing_account AS oea, s.owner, s.cp, s.sgn * t.amount_display AS amt
    FROM tokens_solana.transfers t
    CROSS JOIN UNNEST(
        ARRAY[t.from_owner, t.to_owner], ARRAY[t.to_owner, t.from_owner], ARRAY[-1, 1]
    ) AS s(owner, cp, sgn)
    WHERE t.block_date BETWEEN DATE '{R0}' AND DATE '{CUT}'
      AND (t.from_owner IN (SELECT usr FROM ent) OR t.to_owner IN (SELECT usr FROM ent))
      AND t.from_owner <> t.to_owner
      AND (
          t.token_mint_address IN (SELECT mint FROM rm)
          OR (
              t.token_version = 'native' AND t.action = 'transfer'
              AND (t.to_owner IN ({JITO_SQL}) OR t.outer_executing_account = '{SYS}')
          )
      )
),
tr2 AS (
    SELECT tr.*, tt.tx_id IS NOT NULL AS is_trade
    FROM tr
    LEFT JOIN tt ON tt.tx_id = tr.tx_id AND tt.usr = tr.owner
    WHERE tr.owner IN (SELECT usr FROM ent)
      AND (tr.token_version <> 'native' OR (tr.amt < 0 AND tt.tx_id IS NOT NULL))
)
SELECT
    IF(token_version = 'native', 'SOL', 'TOK') AS kind,
    owner, mint, action, is_trade,
    IF(is_trade AND token_version <> 'native', CAST(NULL AS varchar), cp) AS cp,
    oea = '{SYS}' AS top_sys,
    count(*) AS n,
    sum(IF(amt > 0, amt, 0)) AS amt_in,
    sum(IF(amt < 0, -amt, 0)) AS amt_out
FROM tr2
GROUP BY 1, 2, 3, 4, 5, 6, 7
"""
    )


def bfee(users: list[str]) -> str:
    return (
        head("BFEE 网络费", users, f"只读 {R0}～{CUT}。")
        + f""",
{TT},
f AS (
    SELECT g.tx_hash, g.signer, g.tx_fee
    FROM gas_solana.fees g
    WHERE g.block_date BETWEEN DATE '{R0}' AND DATE '{CUT}'
      AND g.signer IN (SELECT usr FROM ent)
)
SELECT
    tt.usr,
    count(*) AS n_trade_tx,
    count(f.tx_hash) AS n_fee_found,
    sum(IF(f.signer = tt.usr, f.tx_fee, 0)) AS fee_sol
FROM tt
LEFT JOIN f ON f.tx_hash = tt.tx_id
GROUP BY 1
"""
    )


def bbal(users: list[str]) -> str:
    return (
        head("BBAL 期末余额", users, f"读 2026-08 月分区，day ≤ {CUT}。")
        + f""",
b AS (
    SELECT
        address, token_balance_owner AS owner, token_mint_address AS mint,
        max_by(token_balance, day) AS bal, max(day) AS last_day
    FROM solana_utils.daily_balances
    WHERE month = DATE '2026-08-01'
      AND day <= TIMESTAMP '{CUT} 00:00:00'
      AND token_balance_owner IN (SELECT usr FROM ent)
      AND token_mint_address IN (SELECT mint FROM rm)
    GROUP BY 1, 2, 3
)
SELECT owner, mint, sum(bal) AS bal, count(*) AS n_accounts, max(last_day) AS last_day
FROM b
GROUP BY 1, 2
"""
    )


def main() -> None:
    users = pd.read_csv(sys.argv[1]).iloc[:, 0].astype(str).tolist()
    for name, fn in (("BX", bx), ("BT", bt), ("BFEE", bfee), ("BBAL", bbal)):
        sql = fn(users)
        sqlglot.parse_one(sql, read="trino")
        dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
        assert dates[0] >= "2026-08-01" and dates[-1] <= CUT, dates
        out = H / f"BOOK_{name}_R.sql"
        out.write_text(sql)
        h = hashlib.sha256(out.read_bytes()).hexdigest()
        with open(H / "sha256.txt", "a") as fh:
            fh.write(f"{out.name} {h}\n")
        print(out.name, h[:12], len(sql))


if __name__ == "__main__":
    main()
