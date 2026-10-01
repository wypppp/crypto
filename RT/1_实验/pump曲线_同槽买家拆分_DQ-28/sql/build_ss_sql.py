#!/usr/bin/env python3
"""DQ-28 同槽买家拆分（卡片_v1.md §2～§4）：生成 Dune SQL。

- A  SS_CELLS：成交链调用 DQ-26 `build_rank_sql.chain`（extra=True，曲线成交带事件实际费用与交易号）；
     格＝（币, 钱包）在创建 slot 内有买入且不是创建者；输出付出、收回、成交代币量、期末清算值、是否与创建同一笔交易。
- B  SS_FEES：这些格的曲线成交交易在 `gas_solana.fees` 中的网络费（签名者为该钱包；一笔交易含多个币时按币数平分）。
- C1 SS_XFER：`tokens_solana.transfers` 08-04～08-12：这些格的钱包转给 Jito 小费账户的原生 SOL（限其成交交易），
     以及这些币在这些钱包上的全部转入、转出（含成交腿；本地与成交量比较判“筹码转移”）。
- C2 SS_LINK：`tokens_solana.transfers` 07-28～08-05：创建者与格钱包之间任一方向的原生 SOL 直接转账（创建前 7 天内）。

python sql/build_ss_sql.py → sql/SS_{CELLS,FEES,XFER,LINK}.sql，哈希写入 sql/sha256.txt
自检：sqlglot（trino）可解析；日期围栏只含 2026-07-28～08-12。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import sqlglot

H = Path(__file__).resolve().parent
DQ26 = H.parents[1] / "pump曲线_钱包持续性可行性_DQ-26" / "sql"
sys.path.insert(0, str(DQ26))
from build_rank_sql import HOLD, chain, liq  # noqa: E402

C0, C1, CUT, LB = "2026-08-04", "2026-08-05", "2026-08-12", "2026-07-28"
SYS = "11111111111111111111111111111111"
JITO = json.loads((H.parent / "raw" / "jito_tip_accounts_20261001.json").read_text())[
    "result"
]
JITO_SQL = ", ".join(f"'{a}'" for a in JITO)
HEAD = "/* DQ-28 同槽买家拆分 {name}（卡片_v1.md）；由 sql/build_ss_sql.py 生成。\n   币：{c0}～{c1} 创建的 SOL 计价 pump 币；格＝创建 slot 内有买入的非创建者钱包。{note} */\nWITH\n"

# 只用创建事件与曲线成交事件重建“格”，供 B、C1、C2 使用（单链，避免多处引用整条成交链）
CELLS_LITE = f"""cr AS (
    SELECT mint, min(evt_block_slot) AS cslot, min(evt_block_time) AS created_at,
           max(CAST("user" AS varchar)) AS dev
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
      AND (quote_mint IS NULL OR quote_mint = '{SYS}')
    GROUP BY 1
),
ev AS (
    SELECT
        t.evt_tx_id AS tx_id, CAST(t."user" AS varchar) AS usr, t.mint, c.dev, c.created_at,
        max(IF(COALESCE(t.is_buy, t.isBuy) AND t.evt_block_slot = c.cslot
               AND CAST(t."user" AS varchar) <> c.dev, 1, 0))
            OVER (PARTITION BY t.mint, CAST(t."user" AS varchar)) AS is_cell
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN cr c ON c.mint = t.mint
    WHERE t.evt_block_date BETWEEN DATE '{C0}' AND DATE '{CUT}'
),
tt AS (
    SELECT DISTINCT tx_id, usr, mint, dev, created_at FROM ev WHERE is_cell = 1
)"""


def cells() -> str:
    head = HEAD.format(
        name="A 格与现金",
        c0=C0,
        c1=C1,
        note=f"成交（曲线＋PumpSwap）截至 {CUT} 24:00 UTC；只读 {C0}～{CUT} 的分区。",
    )
    return (
        head
        + chain(C0, C1, CUT, extra=True)
        + f""",
ctx AS (
    SELECT mint, min_by(evt_tx_id, evt_block_slot) AS create_tx
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{C0}' AND DATE '{C1}'
    GROUP BY 1
)
SELECT
    q.mint, q.usr, max(q.dev) AS dev, max(q.created_at) AS created_at, max(q.t3_s) AS t3_s,
    bool_or(q.is_buy AND q.slot = q.created_slot AND q.tx_id = c.create_tx) AS same_tx,
    sum(IF(q.is_buy AND q.slot = q.created_slot, q.sol_gross, 0)) AS ss_buy_sol,
    sum(IF(q.is_buy, IF(q.venue = 0, q.sol_gross + q.fee_evt, q.sol_user), 0)) AS pay,
    sum(IF(q.is_buy, 0, IF(q.venue = 0, q.sol_gross - q.fee_evt, q.sol_user))) AS recv,
    sum(IF(q.is_buy, q.sol_user, 0)) AS pay_rate,
    sum(IF(q.is_buy, 0, q.sol_user)) AS recv_rate,
    sum(IF(q.is_buy, q.tok, 0)) AS tok_b,
    sum(IF(q.is_buy, 0, q.tok)) AS tok_s,
    count_if(q.is_buy) AS n_buy, count_if(NOT q.is_buy) AS n_sell,
    count_if(q.venue = 1) AS n_amm,
    min(IF(NOT q.is_buy, q.dt)) AS first_sell_dt,
    {liq(HOLD)} AS liq_sol
FROM q3 q
LEFT JOIN ctx c ON c.mint = q.mint
WHERE q.usr IS NOT NULL AND q.usr <> q.dev
GROUP BY 1, 2
HAVING bool_or(q.is_buy AND q.slot = q.created_slot)
"""
    )


def fees() -> str:
    head = HEAD.format(name="B 网络费", c0=C0, c1=C1, note=f"只读 {C0}～{CUT} 的分区。")
    return (
        head
        + CELLS_LITE
        + f""",
tn AS (
    SELECT tx_id, usr, mint, count(*) OVER (PARTITION BY tx_id, usr) AS n_mint FROM tt
)
SELECT
    tn.mint, tn.usr,
    count(*) AS n_tx,
    count(g.tx_hash) AS n_fee_found,
    sum(IF(g.signer = tn.usr, g.tx_fee / tn.n_mint, 0)) AS fee_sol,
    count_if(g.signer IS NOT NULL AND g.signer <> tn.usr) AS n_other_signer
FROM tn
LEFT JOIN gas_solana.fees g
  ON g.tx_hash = tn.tx_id AND g.block_date BETWEEN DATE '{C0}' AND DATE '{CUT}'
GROUP BY 1, 2
"""
    )


def xfer() -> str:
    head = HEAD.format(
        name="C1 小费与筹码转移", c0=C0, c1=C1, note=f"只读 {C0}～{CUT} 的分区。"
    )
    return (
        head
        + CELLS_LITE
        + f""",
tn AS (
    SELECT tx_id, usr, mint, count(*) OVER (PARTITION BY tx_id, usr) AS n_mint FROM tt
),
tr AS (
    SELECT t.tx_id, t.token_mint_address AS mint, t.token_version, t.from_owner, t.to_owner, t.amount_display AS amt
    FROM tokens_solana.transfers t
    WHERE t.block_date BETWEEN DATE '{C0}' AND DATE '{CUT}'
      AND t.from_owner <> t.to_owner
      AND (
          (t.token_version = 'native' AND t.action = 'transfer' AND t.to_owner IN ({JITO_SQL})
           AND t.tx_id IN (SELECT tx_id FROM tn))
          OR (t.token_mint_address IN (SELECT mint FROM cr)
              AND (t.from_owner IN (SELECT usr FROM tn) OR t.to_owner IN (SELECT usr FROM tn)))
      )
),
tip AS (
    SELECT tn.mint, tn.usr, sum(tr.amt / tn.n_mint) AS tip_sol, count(*) AS n_tip
    FROM tr
    JOIN tn ON tn.tx_id = tr.tx_id AND tn.usr = tr.from_owner
    WHERE tr.token_version = 'native'
    GROUP BY 1, 2
),
tok AS (
    SELECT s.mint, s.usr, sum(IF(s.sgn < 0, s.amt, 0)) AS tok_out, sum(IF(s.sgn > 0, s.amt, 0)) AS tok_in
    FROM (
        SELECT tr.mint, tr.from_owner AS usr, -1 AS sgn, tr.amt FROM tr WHERE tr.token_version <> 'native'
        UNION ALL
        SELECT tr.mint, tr.to_owner, 1, tr.amt FROM tr WHERE tr.token_version <> 'native'
    ) s
    GROUP BY 1, 2
)
SELECT
    COALESCE(tip.mint, tok.mint) AS mint, COALESCE(tip.usr, tok.usr) AS usr,
    tip.tip_sol, tip.n_tip, tok.tok_out, tok.tok_in
FROM tip
FULL OUTER JOIN tok ON tok.mint = tip.mint AND tok.usr = tip.usr
"""
    )


def link() -> str:
    head = HEAD.format(
        name="C2 创建者资金往来",
        c0=C0,
        c1=C1,
        note=f"原生 SOL 只读 {LB}～{C1} 的分区；成交读 {C0}～{CUT}。",
    )
    return (
        head
        + CELLS_LITE
        + f""",
cell AS (
    SELECT DISTINCT mint, usr, dev, created_at FROM tt
),
pr AS (
    SELECT dev AS src, usr AS dst, mint, usr, created_at, 1 AS dev_to_usr FROM cell
    UNION ALL
    SELECT usr, dev, mint, usr, created_at, 0 FROM cell
)
SELECT
    pr.mint, pr.usr,
    count(*) AS n_link,
    sum(t.amount_display) AS link_sol,
    sum(pr.dev_to_usr) AS n_dev_to_usr
FROM tokens_solana.transfers t
JOIN pr ON t.from_owner = pr.src AND t.to_owner = pr.dst
WHERE t.block_date BETWEEN DATE '{LB}' AND DATE '{C1}'
  AND t.token_version = 'native' AND t.action = 'transfer'
  AND t.block_time <= pr.created_at
  AND t.block_time >= pr.created_at - INTERVAL '7' DAY
GROUP BY 1, 2
"""
    )


def main() -> None:
    lines = []
    for name, sql in (
        ("SS_CELLS", cells()),
        ("SS_FEES", fees()),
        ("SS_XFER", xfer()),
        ("SS_LINK", link()),
    ):
        sqlglot.parse_one(sql, read="trino")
        dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
        assert dates[0] >= LB and dates[-1] <= CUT, (name, dates)
        out = H / f"{name}.sql"
        out.write_text(sql)
        h = hashlib.sha256(out.read_bytes()).hexdigest()
        lines.append(f"{out.name} {h}")
        print(out.name, h[:12], len(sql))
    (H / "sha256.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
