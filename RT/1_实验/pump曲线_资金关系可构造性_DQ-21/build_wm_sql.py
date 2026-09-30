#!/usr/bin/env python3
"""WM 谁在赚钱＋阳性对照（卡片_WM_谁在赚钱与阳性对照.md）：生成三条 Dune SQL。

- 样本：raw/s1/S1_{A,B}_dual.csv.gz 中 eligible 且非 r0_seen 的币（S1 主样本），传入 (mint, t3_s)；
  单日冒烟取 A 周中 06-01 创建的币。
- 迁移池映射（mig、cp、cp_norm、fallback_pool、mapping）逐字取自同周 S1 双口径 SQL，只做切片；
  成交现金按 DQ-16 已对账口径（F107②）；排序与 clock 同 S1。
- 输出每（币, 组）一行，附币级列。

python build_wm_sql.py → sql/WM_{SMOKE_20260601,A,B}.sql，并打印 sha256
自检：sqlglot（trino）可解析；三张成交表各引用一次；mint 数与样本一致。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import sqlglot

H = Path(__file__).resolve().parent
SQL = H / "sql"
S1SQL = {
    "SMOKE_20260601": SQL / "S1_SMOKE_20260601_固定退出基础回收_双口径.sql",
    "A": SQL / "S1_A_固定退出基础回收_双口径.sql",
    "B": SQL / "S1_B_固定退出基础回收_双口径.sql",
}
# (创建日起, 创建日止, 成交分区止)：与 S1 相同
DATES = {
    "SMOKE_20260601": ("2026-06-01", "2026-06-01", "2026-07-02"),
    "A": ("2026-06-01", "2026-06-07", "2026-07-08"),
    "B": ("2026-06-08", "2026-06-14", "2026-07-15"),
}
SOL = "So11111111111111111111111111111111111111112"


def sample(label: str) -> pd.DataFrame:
    week = "A" if label != "B" else "B"
    d = pd.read_csv(H / "raw" / "s1" / f"S1_{week}_dual.csv.gz")
    d = d[(d.eligible.astype(str) == "True") & (d.r0_seen.astype(str) != "True")]
    if label.startswith("SMOKE"):
        d = d[d.created_at.str[:10] == "2026-06-01"]
    assert d.t3_s.notna().all()
    return d[["mint", "t3_s"]].sort_values("mint").reset_index(drop=True)


def mapping_ctes(label: str) -> str:
    """S1 双口径 SQL 中 mig … mapping 五个 CTE 的原文。"""
    s = S1SQL[label].read_text()
    i, j = s.index("mig AS ("), s.index("amm_raw AS (")
    block = s[i:j]
    for name in (
        "mig AS (",
        "cp AS (",
        "cp_norm AS (",
        "fallback_pool AS (",
        "mapping AS (",
    ):
        assert block.count("\n" + name) + block.startswith(name) == 1, name
    return block


def build(label: str) -> str:
    d0, d1, d2 = DATES[label]
    smp = sample(label)
    vals = ",\n".join(f"        ('{m}', {int(t)})" for m, t in zip(smp.mint, smp.t3_s))
    fee = "(COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0))"
    sol_raw = "CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE)"
    amm_price = """        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END AS sol_pre_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END AS target_pre_raw,"""
    fees = """        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.protocol_fee AS DOUBLE) / power(10, m.sd)) AS fee_proto,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.coin_creator_fee AS DOUBLE) / power(10, m.sd)) AS fee_creator,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.lp_fee AS DOUBLE) / power(10, m.sd)) AS fee_lp,"""
    return f"""/* WM 谁在赚钱＋阳性对照（卡片_WM_谁在赚钱与阳性对照.md）；由 build_wm_sql.py 生成。
   样本：S1 主样本（{label}，{len(smp)} 币）；只含 {d0}～{d1} 创建的币，成交分区到 {d2}。
   迁移池映射（mig … mapping）逐字取自同周 S1 双口径 SQL。现金为交易者一侧（DQ-16 口径，F107②），
   不含网络费、优先费与小费。输出每（币, 组）一行，附币级列。事后描述，不是信号。 */
WITH
s(mint, t3_s) AS (
    SELECT mint, t3_s FROM (VALUES
{vals}
    ) AS v(mint, t3_s)
),
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        max(CAST("user" AS varchar)) AS dev,
        max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{d0}' AND DATE '{d1}'
      AND mint IN (SELECT mint FROM s)
    GROUP BY 1
),
sol_cohort AS (
    SELECT c.mint, c.created_at, c.created_slot, c.dev, s.t3_s
    FROM cohort c
    JOIN s ON s.mint = c.mint
    WHERE c.quote_mint IS NULL OR c.quote_mint = '11111111111111111111111111111111'
),
{mapping_ctes(label)}amm_raw AS (
    SELECT
        m.mint, m.pool_reversed, m.td, m.sd,
        a.evt_block_time AS ts, a.evt_block_slot AS slot, a.evt_tx_index AS txi,
        COALESCE(a.evt_outer_instruction_index, 0) AS oix,
        COALESCE(a.evt_inner_instruction_index, -1) AS iix,
        CAST(a."user" AS varchar) AS usr,
        NOT m.pool_reversed AS is_buy,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_out AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.user_quote_amount_in AS DOUBLE) / power(10, m.sd) END AS sol_user,
        CASE WHEN m.pool_reversed THEN CAST(a.user_quote_amount_in AS DOUBLE) / power(10, m.td)
             ELSE CAST(a.base_amount_out AS DOUBLE) / power(10, m.td) END AS tok,
{fees}
{amm_price}
        CASE WHEN m.pool_reversed THEN -CAST(a.base_amount_out AS DOUBLE)
             ELSE CAST(a.quote_amount_in_with_lp_fee AS DOUBLE) END AS dsol_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.quote_amount_in_with_lp_fee AS DOUBLE)
             ELSE -CAST(a.base_amount_out AS DOUBLE) END AS dtarget_raw
    FROM pumpdotfun_solana.pump_amm_evt_buyevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '{d0}' AND DATE '{d2}'
    UNION ALL
    SELECT
        m.mint, m.pool_reversed, m.td, m.sd,
        a.evt_block_time, a.evt_block_slot, a.evt_tx_index,
        COALESCE(a.evt_outer_instruction_index, 0), COALESCE(a.evt_inner_instruction_index, -1),
        CAST(a."user" AS varchar),
        m.pool_reversed,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.user_quote_amount_out AS DOUBLE) / power(10, m.sd) END,
        CASE WHEN m.pool_reversed THEN CAST(a.user_quote_amount_out AS DOUBLE) / power(10, m.td)
             ELSE CAST(a.base_amount_in AS DOUBLE) / power(10, m.td) END,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.protocol_fee AS DOUBLE) / power(10, m.sd)),
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.coin_creator_fee AS DOUBLE) / power(10, m.sd)),
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.lp_fee AS DOUBLE) / power(10, m.sd)),
        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE)
             ELSE -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0)) END,
        CASE WHEN m.pool_reversed THEN -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0))
             ELSE CAST(a.base_amount_in AS DOUBLE) END
    FROM pumpdotfun_solana.pump_amm_evt_sellevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '{d0}' AND DATE '{d2}'
),
ev AS (
    SELECT
        t.mint, 0 AS venue, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
        COALESCE(t.evt_outer_instruction_index, 0) AS oix,
        COALESCE(t.evt_inner_instruction_index, -1) AS iix,
        CAST(t."user" AS varchar) AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CASE WHEN COALESCE(t.is_buy, t.isBuy)
             THEN {sol_raw} + ceiling({sol_raw} * {fee} / 1e4)
             ELSE {sol_raw} - ceiling({sol_raw} * {fee} / 1e4) END / 1e9 AS sol_user,
        CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok,
        ceiling({sol_raw} * COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) / 1e4) / 1e9 AS fee_proto,
        ceiling({sol_raw} * COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0) / 1e4) / 1e9 AS fee_creator,
        0.0 AS fee_lp,
        CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
        CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
        CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr,
        {sol_raw} / 1e9 AS curve_sol,
        false AS rev
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '{d0}' AND DATE '{d2}'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mint, 1, ts, slot, txi, oix, iix, usr, is_buy, sol_user, tok, fee_proto, fee_creator, fee_lp,
        (sol_pre_raw + dsol_raw) / power(10, sd), (target_pre_raw + dtarget_raw) / power(10, td),
        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE), pool_reversed
    FROM amm_raw
),
ev2 AS (
    SELECT
        e.*, c.created_at, c.created_slot, c.dev, c.t3_s,
        date_diff('second', c.created_at, max(e.ts) OVER (
            PARTITION BY e.mint ORDER BY e.slot, e.txi, e.oix, e.iix, e.venue
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) AS dt,
        row_number() OVER (
            PARTITION BY e.mint ORDER BY e.slot DESC, e.txi DESC, e.oix DESC, e.iix DESC, e.venue DESC
        ) AS rn_last,
        row_number() OVER (
            PARTITION BY e.mint, e.venue ORDER BY e.slot DESC, e.txi DESC, e.oix DESC, e.iix DESC
        ) AS rn_last_venue
    FROM ev e
    JOIN sol_cohort c ON c.mint = e.mint
    WHERE e.ts >= c.created_at
      AND e.ts <= c.created_at + INTERVAL '30' DAY
),
w AS (
    SELECT
        mint, usr,
        max(created_slot) AS created_slot, max(dev) AS dev, max(t3_s) AS t3_s,
        min(IF(is_buy, slot)) AS fb_slot,
        min(IF(is_buy, dt)) AS fb_dt,
        count_if(is_buy) AS n_buy,
        count_if(NOT is_buy) AS n_sell,
        sum(IF(is_buy, sol_user, 0)) AS in_sol,
        sum(IF(is_buy, 0, sol_user)) AS out_sol,
        sum(IF(is_buy, tok, 0)) AS tok_b,
        sum(IF(is_buy, 0, tok)) AS tok_s
    FROM ev2
    GROUP BY 1, 2
),
g AS (
    SELECT
        *,
        CASE
            WHEN usr = dev THEN 'creator'
            WHEN n_buy = 0 THEN 'sellonly'
            WHEN fb_slot = created_slot THEN 'sameslot'
            WHEN fb_dt <= 10 THEN 'open10'
            WHEN fb_dt < t3_s + 5 THEN 'pre'
            WHEN fb_dt < t3_s + 30 THEN 'e5'
            WHEN fb_dt < t3_s + 120 THEN 'e30'
            WHEN fb_dt < t3_s + 600 THEN 'e120'
            WHEN fb_dt < 86400 THEN 'd1'
            ELSE 'late'
        END AS grp
    FROM w
),
gs AS (
    SELECT
        mint, grp,
        count(*) AS n_w,
        count_if(n_buy > 0 AND tok_s > tok_b * 1.0001) AS n_oversold,
        sum(in_sol) AS in_sol,
        sum(out_sol) AS out_sol,
        sum(tok_b) AS tok_b,
        sum(tok_s) AS tok_s,
        sum(greatest(tok_b - tok_s, 0)) AS held_tok,
        max(out_sol - in_sol) AS max_net_w,
        min(out_sol - in_sol) AS min_net_w
    FROM g
    GROUP BY 1, 2
),
coin AS (
    SELECT
        mint,
        count(*) AS n_ev,
        count_if(venue = 1) AS n_amm,
        count_if(rev) AS n_rev,
        sum(COALESCE(fee_proto, 0)) AS fee_proto,
        sum(COALESCE(fee_creator, 0)) AS fee_creator,
        sum(COALESCE(fee_lp, 0)) AS fee_lp,
        sum(IF(venue = 0 AND is_buy, curve_sol, 0)) AS curve_in,
        sum(IF(venue = 0 AND NOT is_buy, curve_sol, 0)) AS curve_out,
        max(IF(venue = 0 AND rn_last_venue = 1, xr)) AS xr_end,
        max(IF(rn_last = 1 AND y > 0, x / y)) AS p_end,
        max(IF(rn_last = 1, venue)) AS last_venue
    FROM ev2
    GROUP BY 1
)
SELECT gs.*, coin.n_ev, coin.n_amm, coin.n_rev, coin.fee_proto, coin.fee_creator, coin.fee_lp,
       coin.curve_in, coin.curve_out, coin.xr_end, coin.p_end, coin.last_venue
FROM gs
JOIN coin ON coin.mint = gs.mint
ORDER BY gs.mint, gs.grp
"""


def main() -> None:
    for label in DATES:
        sql = build(label)
        sqlglot.parse_one(sql, read="trino")
        for tbl in (
            "pump_evt_tradeevent",
            "pump_amm_evt_buyevent",
            "pump_amm_evt_sellevent",
        ):
            assert sql.count(f"pumpdotfun_solana.{tbl}") == 1, tbl
        n = len(sample(label))
        assert sql.count("\n        ('") == n
        out = SQL / f"WM_{label}.sql"
        out.write_text(sql)
        print(out.name, n, "币", hashlib.sha256(sql.encode()).hexdigest())


if __name__ == "__main__":
    main()
