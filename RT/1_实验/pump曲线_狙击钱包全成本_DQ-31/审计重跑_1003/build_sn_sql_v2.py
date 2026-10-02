#!/usr/bin/env python3
"""DQ-31（F131）审计重跑 v2：代码审计 10-03 第 3、6、8 处（并补第 1 处的交易号）。原 sql/build_sn_sql.py 与 DQ-26 build_rank_sql.py 不改。

python build_sn_sql_v2.py → sql/SN2_{TRADES,FEES,TIP}.sql 与 sql/sha256.txt
- 成交链：调用 DQ-26 chain(extra=True) 生成原文，再做文本替换（每处断言恰好命中一次）：
  ①第 3 处：曲线成交的实际费用去掉 buyback_fee（回购费是协议费的一半，不是另收；F59、IDL、DQ-26 G1b 残差）；
  ②第 1 处：PumpSwap 成交带上交易号（amm_raw 两支各加 evt_tx_id），实际费用记为协议＋创作者＋LP 费，cashback 记 0。
- SN2_TRADES：与 v1 SN_TRADES 同样的输出（现金用修正后的链）。
- SN2_FEES（第 6、8 处）：名单钱包签名的全部交易费按（钱包, 窗口币）拆开——“成交交易”取曲线与 PumpSwap 两种成交
  （v1 只取曲线，漏了只含 PumpSwap 的交易）；一笔交易含多个窗口币时按币数平分；非成交交易记 mint 为空。
  评分时可以把被剔除的转移格（X）连同它们的费用一起去掉（v1 只能按钱包合计，删了现金却留下费用）。
- SN2_TIP（第 6、8 处）：名单钱包转给 Jito 小费账户的原生 SOL，同样按（钱包, 窗口币）拆开；非成交交易的小费 mint 为空。
筹码转移（X 格判定）仍用 v1 SN_XFER 的 TOK 部分，不重跑。
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import sqlglot

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / "sql"
sys.path.insert(0, str(V1))
sys.path.insert(0, str(HERE.parents[1] / "pump曲线_钱包持续性可行性_DQ-26" / "sql"))
import build_sn_sql as S1  # noqa: E402
from build_rank_sql import chain  # noqa: E402

C0, C1 = S1.C0, S1.C1

CHAIN_REPL = [
    (
        " + COALESCE(CAST(t.buyback_fee AS DOUBLE), 0)) / 1e9 AS fee_evt",
        ") / 1e9 AS fee_evt",  # v2 第 3 处
    ),
    (
        "        COALESCE(a.evt_inner_instruction_index, -1) AS iix,",
        "        COALESCE(a.evt_inner_instruction_index, -1) AS iix,\n        a.evt_tx_id AS tx_id,",  # v2 第 1 处
    ),
    (
        "COALESCE(a.evt_outer_instruction_index, 0), COALESCE(a.evt_inner_instruction_index, -1),",
        "COALESCE(a.evt_outer_instruction_index, 0), COALESCE(a.evt_inner_instruction_index, -1), a.evt_tx_id,",
    ),
    (
        ",\n        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE), CAST(NULL AS varchar)",
        ",\n        COALESCE(fee_proto, 0) + COALESCE(fee_creator, 0) + COALESCE(fee_lp, 0), CAST(0 AS DOUBLE), tx_id",
    ),
]


def chain_v2() -> str:
    s = chain(C0, C1, C1, extra=True)
    for old, new in CHAIN_REPL:
        assert s.count(old) == 1, old
        s = s.replace(old, new)
    return s


def prefix_v2() -> str:
    """chain_v2 中 cohort … amm_raw 的部分（不含逐事件链），供费用与小费查询构造成交交易集合。"""
    s = chain_v2()
    return s[: s.index("\nev AS (")].rstrip().rstrip(",")


TT2 = f""",
tt2 AS (
    SELECT DISTINCT t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr, t.mint
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND CAST(t."user" AS varchar) IN (SELECT usr FROM sel)
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION
    SELECT DISTINCT tx_id, usr, mint FROM amm_raw WHERE usr IN (SELECT usr FROM sel)
),
tn AS (
    SELECT tx_id, usr, mint, count(*) OVER (PARTITION BY tx_id, usr) AS n_mint FROM tt2
)"""


def head(name: str, users: list[str]) -> str:
    return S1.head(name + "（审计重跑 v2：代码审计 10-03 第 1、3、6、8 处）", users)


def trades(users: list[str]) -> str:
    v1 = S1.trades(users)
    body = v1[v1.index("\nSELECT\n    q.mint, q.usr") :]
    return head("T1 成交与现金", users) + chain_v2() + body


def fees(users: list[str]) -> str:
    return (
        head("T2 网络费（按钱包×窗口币）", users)
        + prefix_v2()
        + TT2
        + f""",
gf AS (
    SELECT g.tx_hash, g.signer, g.tx_fee
    FROM gas_solana.fees g
    WHERE g.block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND g.signer IN (SELECT usr FROM sel)
),
j AS (
    SELECT gf.signer AS usr, gf.tx_fee, tn.mint, tn.n_mint
    FROM gf
    LEFT JOIN tn ON tn.tx_id = gf.tx_hash AND tn.usr = gf.signer
)
SELECT usr, mint, count(*) AS n_tx, sum(IF(mint IS NULL, tx_fee, tx_fee / n_mint)) AS fee
FROM j
GROUP BY 1, 2
"""
    )


def tip(users: list[str]) -> str:
    return (
        head("T3 小费（按钱包×窗口币）", users)
        + prefix_v2()
        + TT2
        + f""",
tp AS (
    SELECT t.tx_id, t.from_owner AS usr, t.amount_display AS amt
    FROM tokens_solana.transfers t
    WHERE t.block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND t.token_version = 'native' AND t.action = 'transfer'
      AND t.to_owner IN ({S1.JITO_SQL})
      AND t.from_owner IN (SELECT usr FROM sel)
),
j AS (
    SELECT tp.usr, tp.amt, tn.mint, tn.n_mint
    FROM tp
    LEFT JOIN tn ON tn.tx_id = tp.tx_id AND tn.usr = tp.usr
)
SELECT usr, mint, count(*) AS n, sum(IF(mint IS NULL, amt, amt / n_mint)) AS tip
FROM j
GROUP BY 1, 2
"""
    )


def main() -> None:
    users = pd.read_csv(HERE.parent / "runs" / "snipers_S.csv").usr.tolist()
    assert len(users) == 794
    lines = []
    for name, sql in (
        ("SN2_TRADES", trades(users)),
        ("SN2_FEES", fees(users)),
        ("SN2_TIP", tip(users)),
    ):
        sqlglot.parse_one(sql, read="trino")
        dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
        assert dates[0] >= C0 and dates[-1] <= C1, (name, dates)
        out = HERE / "sql" / f"{name}.sql"
        out.write_text(sql)
        lines.append(f"{out.name} {hashlib.sha256(out.read_bytes()).hexdigest()}")
        print(lines[-1][:40], len(sql))
    (HERE / "sql" / "sha256.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
