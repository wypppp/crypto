#!/usr/bin/env python3
"""DQ-31 狙击钱包全成本（卡片_v1.md §2～§4）：生成 Dune SQL。

- T1 SN_TRADES：DQ-26 成交链（extra=True），窗口币上名单钱包的（币, 钱包）现金、成交量、期末清算、首次买入距创建的 slot 差。
- T2 SN_FEES：`gas_solana.fees` 中名单钱包作为签名者的全部交易费用，并标出其中的窗口币成交交易。
- T3 SN_XFER：名单钱包转给 Jito 小费账户的原生 SOL（全部，并标出成交交易），以及窗口币在名单钱包上的全部转入转出。

python sql/build_sn_sql.py → sql/SN_{TRADES,FEES,XFER}.sql，哈希写入 sql/sha256.txt
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
DQ26 = H.parents[1] / "pump曲线_钱包持续性可行性_DQ-26" / "sql"
sys.path.insert(0, str(DQ26))
from build_rank_sql import HOLD, chain, liq  # noqa: E402

C0, C1 = "2026-09-14", "2026-09-21"
SYS = "11111111111111111111111111111111"
JITO = json.loads((H.parent / "raw" / "jito_tip_accounts_20261001.json").read_text())[
    "result"
]
JITO_SQL = ", ".join(f"'{a}'" for a in JITO)


def head(name: str, users: list[str]) -> str:
    vals = ",\n".join(f"        ('{u}')" for u in users)
    return f"""/* DQ-31 狙击钱包全成本 {name}（卡片_v1.md）；由 sql/build_sn_sql.py 生成。
   名单 {len(users)} 个钱包；窗口币＝{C0}～{C1} 创建的 SOL 计价 pump 币；只读 {C0}～{C1} 的分区。 */
WITH
sel(usr) AS (
    SELECT usr FROM (VALUES
{vals}
    ) AS v(usr)
),
"""


TT = f"""cr AS (
    SELECT DISTINCT mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND (quote_mint IS NULL OR quote_mint = '{SYS}')
),
tt AS (
    SELECT DISTINCT t.evt_tx_id AS tx_id
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND CAST(t."user" AS varchar) IN (SELECT usr FROM sel)
      AND t.mint IN (SELECT mint FROM cr)
)"""


def trades(users: list[str]) -> str:
    return (
        head("T1 成交与现金", users)
        + chain(C0, C1, C1, extra=True)
        + f"""
SELECT
    q.mint, q.usr, max(q.created_at) AS created_at,
    min(IF(q.is_buy, q.slot - q.created_slot)) AS first_buy_slot_gap,
    sum(IF(q.is_buy, IF(q.venue = 0, q.sol_gross + q.fee_evt, q.sol_user), 0)) AS pay,
    sum(IF(q.is_buy, 0, IF(q.venue = 0, q.sol_gross - q.fee_evt, q.sol_user))) AS recv,
    sum(IF(q.is_buy, q.tok, 0)) AS tok_b,
    sum(IF(q.is_buy, 0, q.tok)) AS tok_s,
    count_if(q.is_buy) AS n_buy, count_if(NOT q.is_buy) AS n_sell, count_if(q.venue = 1) AS n_amm,
    {liq(HOLD)} AS liq_sol
FROM q3 q
WHERE q.usr IN (SELECT usr FROM sel)
GROUP BY 1, 2
"""
    )


def fees(users: list[str]) -> str:
    return (
        head("T2 网络费", users)
        + TT
        + f"""
SELECT
    g.signer AS usr,
    count(*) AS n_tx_all,
    sum(g.tx_fee) AS fee_all,
    count(tt.tx_id) AS n_tx_trade,
    sum(IF(tt.tx_id IS NOT NULL, g.tx_fee, 0)) AS fee_trade
FROM gas_solana.fees g
LEFT JOIN tt ON tt.tx_id = g.tx_hash
WHERE g.block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
  AND g.signer IN (SELECT usr FROM sel)
GROUP BY 1
"""
    )


def xfer(users: list[str]) -> str:
    return (
        head("T3 小费与筹码转移", users)
        + TT
        + f""",
tip AS (
    SELECT
        'TIP' AS kind, t.from_owner AS usr, CAST(NULL AS varchar) AS mint,
        sum(t.amount_display) AS a1,
        sum(IF(tt.tx_id IS NOT NULL, t.amount_display, 0)) AS a2,
        count(*) AS n
    FROM tokens_solana.transfers t
    LEFT JOIN tt ON tt.tx_id = t.tx_id
    WHERE t.block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND t.token_version = 'native' AND t.action = 'transfer'
      AND t.to_owner IN ({JITO_SQL})
      AND t.from_owner IN (SELECT usr FROM sel)
    GROUP BY 1, 2, 3
),
tok AS (
    SELECT
        'TOK' AS kind, u.owner AS usr, t.token_mint_address AS mint,
        sum(IF(u.sgn < 0, t.amount_display, 0)) AS a1,
        sum(IF(u.sgn > 0, t.amount_display, 0)) AS a2,
        count(*) AS n
    FROM tokens_solana.transfers t
    CROSS JOIN UNNEST(ARRAY[t.from_owner, t.to_owner], ARRAY[-1, 1]) AS u(owner, sgn)
    WHERE t.block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND t.token_mint_address IN (SELECT mint FROM cr)
      AND t.from_owner <> t.to_owner
      AND u.owner IN (SELECT usr FROM sel)
    GROUP BY 1, 2, 3
)
SELECT * FROM tip
UNION ALL
SELECT * FROM tok
"""
    )


def main() -> None:
    users = pd.read_csv(H.parent / "runs" / "snipers_S.csv").usr.tolist()
    assert len(users) == 794
    lines = []
    for name, sql in (
        ("SN_TRADES", trades(users)),
        ("SN_FEES", fees(users)),
        ("SN_XFER", xfer(users)),
    ):
        sqlglot.parse_one(sql, read="trino")
        dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
        assert dates[0] >= C0 and dates[-1] <= C1, (name, dates)
        out = H / f"{name}.sql"
        out.write_text(sql)
        lines.append(f"{out.name} {hashlib.sha256(out.read_bytes()).hexdigest()}")
        print(lines[-1][:40], len(sql))
    (H / "sha256.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
