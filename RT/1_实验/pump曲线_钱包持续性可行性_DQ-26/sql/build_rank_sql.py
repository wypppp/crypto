#!/usr/bin/env python3
"""DQ-26 第一步·排名查询（卡片_v1.md §1～§3）：生成 Dune SQL。

- 迁移池映射（mig … mapping）与 PumpSwap 成交（amm_raw）逐字取自 DQ-21 `sql/WM_A.sql`，只换日期；
  曲线成交现金口径同 WM（交易者一侧，含平台费；DQ-16 已对账，F107②）。
- t3 同 S0 v1.3：第三个买入 ≥0.1 SOL、非创建者的独立买家所在事件。
- 期末持仓按截止时最后一笔成交后的池状态清算（卡片 §3），不按边际价。
- 三种查询，各为一条单链（v0 合在一条里，Dune 报“阶段过多”未执行）：
  C 币级状态（t3、期末池状态、曲线现金闭合）；
  W 合格钱包汇总（≥5 币且 ≥2 SOL），初排在本地做；
  D 给定钱包名单的（钱包, 币）明细，附该币 t3 与期末状态。

python sql/build_rank_sql.py [D 名单 csv] → sql/RANK_{C,W}_{REG_20260601,SMOKE_20260803,R}.sql（给名单时另出 RANK_D_R.sql）
自检：sqlglot（trino）可解析；日期围栏只含所列分区。
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import sqlglot

H = Path(__file__).resolve().parent
WM = H.parents[1] / "pump曲线_资金关系可构造性_DQ-21" / "sql" / "WM_A.sql"
# (创建日起, 创建日止, 成交截止日（含）)
RUNS = {
    "REG_20260601": ("2026-06-01", "2026-06-01", "2026-06-03"),
    "SMOKE_20260803": ("2026-08-03", "2026-08-03", "2026-08-05"),
    "R": ("2026-08-03", "2026-08-09", "2026-08-16"),
}
SOL_RAW = "CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE)"
FEE_BPS = (
    "(COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0)"
    " + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0))"
)


def wm_blocks(c0: str, cut: str) -> str:
    """WM_A.sql 中 mig … amm_raw 的原文，日期换成本次窗口。"""
    s = WM.read_text()
    i, k = s.index("mig AS ("), s.index("\nev AS (")
    block = s[i:k]
    dates = sorted(set(re.findall(r"DATE '[0-9-]+'", block)))
    assert dates == ["DATE '2026-06-01'", "DATE '2026-07-08'"], dates
    block = block.replace("DATE '2026-06-01'", f"DATE '{c0}'")
    return block.replace("DATE '2026-07-08'", f"DATE '{cut}'")


def chain(c0: str, c1: str, cut: str, extra: bool = False) -> str:
    """cohort → … → q3：逐事件，附 rn、dt、t3_s 与期末池状态（窗口函数，按币）。

    extra＝True（只用于 D）：曲线成交另带事件里的实际费用字段（fee、creator_fee、buyback_fee）与 cashback，
    用来核对按费率推算的现金；C、W 已按 extra＝False 执行，文本不变。
    """
    x_curve = (
        ",\n        (COALESCE(CAST(t.fee AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee AS DOUBLE), 0)"
        " + COALESCE(CAST(t.buyback_fee AS DOUBLE), 0)) / 1e9 AS fee_evt,\n"
        "        COALESCE(CAST(t.cashback AS DOUBLE), 0) / 1e9 AS cashback,\n"
        "        t.evt_tx_id AS tx_id"
        if extra
        else ""
    )
    x_amm = (
        ",\n        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE), CAST(NULL AS varchar)"
        if extra
        else ""
    )
    return f"""cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        max(CAST("user" AS varchar)) AS dev,
        max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{c0}' AND DATE '{c1}'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
{wm_blocks(c0, cut)}
ev AS (
    SELECT
        t.mint, 0 AS venue, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
        COALESCE(t.evt_outer_instruction_index, 0) AS oix,
        COALESCE(t.evt_inner_instruction_index, -1) AS iix,
        CAST(t."user" AS varchar) AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CASE WHEN COALESCE(t.is_buy, t.isBuy)
             THEN {SOL_RAW} + ceiling({SOL_RAW} * {FEE_BPS} / 1e4)
             ELSE {SOL_RAW} - ceiling({SOL_RAW} * {FEE_BPS} / 1e4) END / 1e9 AS sol_user,
        {SOL_RAW} / 1e9 AS sol_gross,
        CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok,
        ceiling({SOL_RAW} * {FEE_BPS} / 1e4) / 1e9 AS fee_all,
        {FEE_BPS} AS fee_bps,
        CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
        CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
        CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr{x_curve}
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '{c0}' AND DATE '{cut}'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mint, 1, ts, slot, txi, oix, iix, usr, is_buy, sol_user,
        IF(is_buy, sol_user - COALESCE(fee_proto, 0) - COALESCE(fee_creator, 0) - COALESCE(fee_lp, 0),
                   sol_user + COALESCE(fee_proto, 0) + COALESCE(fee_creator, 0) + COALESCE(fee_lp, 0)),
        tok,
        COALESCE(fee_proto, 0) + COALESCE(fee_creator, 0) + COALESCE(fee_lp, 0),
        CAST(NULL AS DOUBLE),
        (sol_pre_raw + dsol_raw) / power(10, sd), (target_pre_raw + dtarget_raw) / power(10, td),
        CAST(NULL AS DOUBLE){x_amm}
    FROM amm_raw
),
ev2 AS (
    SELECT
        e.*, c.created_at, c.created_slot, c.dev,
        row_number() OVER (PARTITION BY e.mint ORDER BY e.slot, e.txi, e.oix, e.iix, e.venue) AS rn,
        date_diff('second', c.created_at, max(e.ts) OVER (
            PARTITION BY e.mint ORDER BY e.slot, e.txi, e.oix, e.iix, e.venue
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) AS dt
    FROM ev e
    JOIN sol_cohort c ON c.mint = e.mint
    WHERE e.ts >= c.created_at
      AND e.ts < DATE '{cut}' + INTERVAL '1' DAY
),
q1 AS (
    SELECT
        *,
        min(CASE WHEN is_buy AND sol_gross >= 0.1 AND usr IS NOT NULL AND usr <> dev THEN rn END)
          OVER (PARTITION BY mint, usr) AS first_q_rn
    FROM ev2
),
q2 AS (
    SELECT
        *,
        rn = first_q_rn AS q_new,
        sum(IF(rn = first_q_rn, 1, 0)) OVER (
            PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS q_count,
        max_by(venue, rn) OVER (PARTITION BY mint) AS v_end,
        max_by(x, rn) OVER (PARTITION BY mint) AS x_end,
        max_by(y, rn) OVER (PARTITION BY mint) AS y_end,
        max_by(IF(venue = 0, xr), IF(venue = 0, rn)) OVER (PARTITION BY mint) AS xr_end,
        max_by(IF(venue = 0, fee_bps), IF(venue = 0, rn)) OVER (PARTITION BY mint) AS fee_end,
        sum(IF(venue = 1, fee_all)) OVER (PARTITION BY mint)
          / sum(IF(venue = 1, sol_gross)) OVER (PARTITION BY mint) AS amm_fee_rate
    FROM q1
),
q3 AS (
    SELECT
        *,
        max(IF(q_new AND q_count = 3, dt)) OVER (PARTITION BY mint) AS t3_s
    FROM q2
)"""


def liq(h: str) -> str:
    """h 枚代币按期末池状态卖出可得（SOL）。"""
    return f"""CASE
            WHEN {h} <= 0 OR max(y_end) IS NULL OR max(y_end) <= 0 THEN 0.0
            WHEN max(v_end) = 0 THEN least(
                max(x_end) * ({h}) / (max(y_end) + {h}), COALESCE(max(xr_end), 0)
            ) * (1 - COALESCE(max(fee_end), 0) / 1e4)
            ELSE max(x_end) * ({h}) / (max(y_end) + {h}) * (1 - COALESCE(max(amm_fee_rate), 0.0125))
        END"""


W_COLS = """
        count_if(is_buy) AS n_buy,
        count_if(NOT is_buy) AS n_sell,
        sum(IF(is_buy, sol_user, 0)) AS in_sol,
        sum(IF(is_buy, 0, sol_user)) AS out_sol,
        sum(IF(is_buy, tok, 0)) AS tok_b,
        sum(IF(is_buy, 0, tok)) AS tok_s,
        min(IF(is_buy, dt)) AS fb_dt,
        min(IF(NOT is_buy, dt)) AS fs_dt,
        bool_or(is_buy AND slot = created_slot) AS same_slot,
        sum(IF(is_buy AND t3_s <= 300 AND dt < t3_s + 5, sol_user, 0)) AS in_pre_t35,
        sum(IF(is_buy AND t3_s <= 300, sol_user, 0)) AS in_t3coin,
        max(t3_s) AS t3_s,"""
HOLD = "sum(IF(is_buy, tok, 0)) - sum(IF(is_buy, 0, tok))"


def build(kind: str, label: str, users: list[str] | None = None) -> str:
    c0, c1, cut = RUNS[label]
    head = f"""/* DQ-26 第一步·排名查询 {kind}（卡片_v1.md §1～§3）；由 sql/build_rank_sql.py 生成（{label}）。
   币：{c0}～{c1} 创建的 SOL 计价 pump 币；成交（曲线＋PumpSwap）截至 {cut} 24:00 UTC；只读 {c0}～{cut} 的分区。
   mig … amm_raw 逐字取自 DQ-21 sql/WM_A.sql（只换日期）；t3 同 S0 v1.3；期末持仓按池状态清算。 */
WITH
{chain(c0, c1, cut, extra=(kind == "D"))}"""
    if kind == "C":
        return (
            head
            + """
SELECT
    mint,
    max(created_at) AS created_at, max(created_slot) AS created_slot, max(dev) AS dev,
    max(t3_s) AS t3_s, count(*) AS n_ev, count_if(venue = 1) AS n_amm,
    max(v_end) AS v_end, max(x_end) AS x_end, max(y_end) AS y_end, max(xr_end) AS xr_end,
    max(fee_end) AS fee_end, max(amm_fee_rate) AS amm_fee_rate,
    sum(IF(venue = 0 AND is_buy, sol_gross, 0)) AS curve_in,
    sum(IF(venue = 0 AND NOT is_buy, sol_gross, 0)) AS curve_out,
    count(DISTINCT usr) AS n_users
FROM q3
GROUP BY 1
"""
        )
    if kind == "W":
        return (
            head
            + f""",
w AS (
    SELECT
        mint, usr,{W_COLS}
        {liq(HOLD)} AS liq_sol
    FROM q3
    WHERE usr IS NOT NULL
    GROUP BY 1, 2
)
SELECT
    usr,
    count_if(n_buy > 0) AS n_coins,
    sum(n_buy) AS n_buy,
    sum(n_sell) AS n_sell,
    sum(in_sol) AS in_sol,
    sum(out_sol) AS out_sol,
    sum(liq_sol) AS liq_sol,
    sum(out_sol + liq_sol - in_sol) AS pnl0,
    sum(in_pre_t35) AS in_pre_t35,
    sum(in_t3coin) AS in_t3coin,
    count_if(same_slot) AS n_same_slot,
    count_if(n_buy = 0 AND n_sell > 0) AS n_sellonly,
    approx_percentile(IF(fs_dt >= fb_dt, fs_dt - fb_dt), 0.5) AS hold_med
FROM w
GROUP BY 1
HAVING count_if(n_buy > 0) >= 5 AND sum(in_sol) >= 2
"""
        )
    assert kind == "D" and users
    vals = ",\n".join(f"        ('{u}')" for u in users)
    return (
        head.replace(
            "WITH\ncohort AS (",
            f"WITH\nsel(usr) AS (\n    SELECT usr FROM (VALUES\n{vals}\n    ) AS v(usr)\n),\ncohort AS (",
            1,
        )
        + f"""
SELECT
    mint, usr,{W_COLS}
    {liq(HOLD)} AS liq_sol,
    max(created_at) AS created_at, max(v_end) AS v_end, max(x_end) AS x_end, max(y_end) AS y_end,
    max(xr_end) AS xr_end, max(fee_end) AS fee_end, max(amm_fee_rate) AS amm_fee_rate,
    sum(IF(venue = 0, fee_all, 0)) AS fee_calc, sum(IF(venue = 0, fee_evt, 0)) AS fee_evt,
    sum(IF(venue = 0, cashback, 0)) AS cashback, count(DISTINCT tx_id) AS n_curve_tx
FROM q3
WHERE usr IN (SELECT usr FROM sel)
GROUP BY 1, 2
"""
    )


def write(name: str, sql: str, lines: list[str], c0: str, cut: str) -> None:
    sqlglot.parse_one(sql, read="trino")
    dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
    assert dates[0] >= c0 and dates[-1] <= cut, dates
    out = H / name
    out.write_text(sql)
    h = hashlib.sha256(out.read_bytes()).hexdigest()
    lines.append(f"{name} {h}")
    print(name, h[:12], len(sql))


def main() -> None:
    lines = [f"WM_A.sql {hashlib.sha256(WM.read_bytes()).hexdigest()}"]
    for label, (c0, _, cut) in RUNS.items():
        for kind in ("C", "W"):
            write(f"RANK_{kind}_{label}.sql", build(kind, label), lines, c0, cut)
    if len(sys.argv) > 1:
        users = pd.read_csv(sys.argv[1]).usr.tolist()
        c0, _, cut = RUNS["R"]
        write("RANK_D_R.sql", build("D", "R", users), lines, c0, cut)
    (H / "sha256.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
