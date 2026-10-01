#!/usr/bin/env python3
"""DQ-26 Q2 外部跟随（卡片_Q2_执行_v1.md）：生成 Dune SQL。

- 成交与池状态链（cohort … q3）直接调用第一步 build_rank_sql.chain（迁移池映射逐字取自 DQ-21 WM_A.sql）；
- 估值照搬 DQ-21 S1 双口径 SQL 的 s9/s10：入场代币、口径 A/B 卖出、曲线 xr 封顶；
- 每个触发只与同币、触发之后到 H（7 天）为止的状态连接一次（q3 只被引用两次：找触发、连状态），延迟 2/5/15/30 秒的入场与跟随退出、
  以及 2 秒的 b50 都在同一遍窗口计算里得到；输出每个触发的卖出所得（SOL），全成本与统计在 q2.py。

三种运行：
  REG   06-01 创建的币（成交至 06-03），触发＝每币 t3 事件，卖出信号＝t3+30 秒，b50 用 5 秒入场
        （与 S1 的 e5 状态、ret_d5_30s、b50_ret_d5 对照）；
  SMOKE 08-17 创建的币（成交至 08-24），触发＝冻结的 146 个钱包；
  T     08-17～08-30 创建的币（成交至 09-06），同上。

python sql/build_q2_sql.py → sql/Q2_{REG_20260601,SMOKE_20260817,T}.sql，哈希追加到 sql/sha256.txt
自检：sqlglot（trino）可解析；日期围栏只含所列分区。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd
import sqlglot

from build_rank_sql import chain

H = Path(__file__).resolve().parent
D = H.parent
RUNS = {
    "REG_20260601": ("2026-06-01", "2026-06-01", "2026-06-03"),
    "SMOKE_20260817": ("2026-08-17", "2026-08-17", "2026-08-24"),
    "T": ("2026-08-17", "2026-08-30", "2026-09-06"),
}
DELAYS = (2, 5, 15, 30)
HOLD = 7 * 86400


def sell(tok: str, fe: str, b: bool) -> str:
    """S1 s10：按当前行状态卖出 tok 枚代币可得（SOL）；fe 为入场状态费率（封顶用）。"""
    curve = (
        f"CASE WHEN y > {tok} THEN (x * y / (y - {tok}) - x) * (1 - fee_bps / 1e4) END"
        if b
        else f"(x * {tok} / (y + {tok})) * (1 - fee_bps / 1e4)"
    )
    return f"""LEAST(
            CASE WHEN venue = 0 THEN {curve}
                 ELSE (x - x * y / (y + {tok})) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - {fe} / 1e4), 1e18))"""


def trig_main() -> str:
    return """ent AS (
    SELECT
        q.mint, s.entity, q.rn, q.dt, q.is_buy, q.slot, q.created_slot, q.created_at, q.t3_s,
        q.sol_user, q.venue,
        min(IF(q.is_buy, q.rn)) OVER (PARTITION BY q.mint, s.entity) AS b_rn0
    FROM q3 q
    JOIN sel s ON s.usr = q.usr
),
trig AS (
    SELECT
        mint, entity,
        max(b_rn0) AS b_rn,
        max(IF(rn = b_rn0, dt)) AS b_dt,
        bool_or(rn = b_rn0 AND slot = created_slot) AS b_same_slot,
        max(IF(rn = b_rn0, venue)) AS b_venue,
        max(IF(rn = b_rn0, sol_user)) AS b_sol,
        min_by(dt, rn) FILTER (WHERE NOT is_buy AND rn > b_rn0) AS s_dt,
        max(t3_s) AS t3_s,
        max(created_at) AS created_at,
        count_if(is_buy) AS ent_n_buy,
        count_if(NOT is_buy) AS ent_n_sell,
        sum(IF(is_buy, sol_user, 0)) AS ent_buy_sol
    FROM ent
    WHERE b_rn0 IS NOT NULL
    GROUP BY 1, 2
),"""


def trig_reg() -> str:
    return """trig AS (
    SELECT
        mint, 't3' AS entity,
        rn AS b_rn, dt AS b_dt, slot = created_slot AS b_same_slot, venue AS b_venue,
        sol_user AS b_sol, dt + 30 AS s_dt, t3_s, created_at,
        1 AS ent_n_buy, 0 AS ent_n_sell, sol_user AS ent_buy_sol
    FROM q3
    WHERE q_new AND q_count = 3
),"""


def tail(bd: int) -> str:
    """bd：b50 用的入场延迟（主运行 2 秒；回归用 5 秒，对照 S1 b50_ret_d5）。"""
    win = "OVER (PARTITION BY mint, entity)"
    e_cols = ",\n        ".join(
        f"max(IF(dt <= b_dt + {d}, rn)) {win} AS e{d},\n"
        f"        max(IF(dt <= LEAST(COALESCE(s_dt + {d}, b_dt + {HOLD}), b_dt + {HOLD}), rn)) {win} AS x{d}"
        for d in DELAYS
    )
    st_cols = ",\n        ".join(
        f"max(IF(rn = e{d}, x)) {win} AS ex{d}, max(IF(rn = e{d}, y)) {win} AS ey{d}, "
        f"max(IF(rn = e{d}, fee_bps)) {win} AS ef{d}, max(IF(rn = e{d}, dt)) {win} AS edt{d}"
        for d in DELAYS
    )
    tok_cols = ",\n        ".join(
        f"ey{d} - ex{d} * ey{d} / (ex{d} + 0.5 * (1 - ef{d} / 1e4)) AS tok{d}"
        for d in DELAYS
    )
    agg = []
    for d in DELAYS:
        for b, s in ((False, "a"), (True, "b")):
            agg.append(
                f"max(IF(rn = x{d}, {sell(f'tok{d}', f'ef{d}', b)})) AS sell_{s}_d{d}"
            )
        agg.append(f"max(edt{d}) AS edt{d}, max(IF(rn = x{d}, dt)) AS xdt{d}")
        agg.append(f"max(IF(rn = x{d}, venue)) AS xvenue{d}")
    agg_s = ",\n    ".join(agg)
    return f"""path AS (
    SELECT
        t.mint, t.entity, t.b_rn, t.b_dt, t.s_dt,
        t.created_at, t.t3_s, t.b_same_slot, t.b_venue, t.b_sol,
        t.ent_n_buy, t.ent_n_sell, t.ent_buy_sol,
        q.rn, q.dt, q.venue, q.x, q.y, q.xr,
        CASE WHEN q.venue = 0 THEN q.fee_bps
             WHEN q.fee_all > 0 AND q.sol_gross > 0 THEN q.fee_all / q.sol_gross * 1e4
             ELSE 125 END AS fee_bps,
        q.x / q.y AS price
    FROM trig t
    JOIN q3 q ON q.mint = t.mint AND q.rn >= t.b_rn AND q.dt <= t.b_dt + {HOLD}
    WHERE q.x > 0 AND q.y > 0
),
p1 AS (
    SELECT
        *,
        {e_cols}
    FROM path
),
p2 AS (
    SELECT
        *,
        {st_cols},
        max(IF(rn = e{bd}, venue)) {win} AS evenue_b,
        max(IF(rn = e{bd}, x / y)) {win} AS eprice_b
    FROM p1
),
p3 AS (
    SELECT
        *,
        {tok_cols},
        price / NULLIF(eprice_b, 0) AS pm_b
    FROM p2
),
p4 AS (
    SELECT
        *,
        {sell(f"tok{bd}", f"ef{bd}", False)} AS m_ab,
        {sell(f"tok{bd}", f"ef{bd}", True)} AS m_bb,
        max(IF(rn >= e{bd}, pm_b)) OVER (
            PARTITION BY mint, entity ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS runmax_b
    FROM p3
),
res AS (
    SELECT
        mint, entity,
    max(created_at) AS created_at, max(t3_s) AS t3_s, max(b_dt) AS b_dt, max(s_dt) AS s_dt,
    bool_or(b_same_slot) AS b_same_slot, max(b_venue) AS b_venue, max(b_sol) AS b_sol,
    max(ent_n_buy) AS ent_n_buy, max(ent_n_sell) AS ent_n_sell, max(ent_buy_sol) AS ent_buy_sol,
    {agg_s},
    NULLIF(min_by(COALESCE(m_ab, -1.0), rn) FILTER (WHERE rn >= e{bd} AND pm_b <= 0.5 * greatest(1.0, runmax_b)), -1.0) AS b50_stop_a,
    NULLIF(min_by(COALESCE(m_bb, -1.0), rn) FILTER (WHERE rn >= e{bd} AND pm_b <= 0.5 * greatest(1.0, runmax_b)), -1.0) AS b50_stop_b,
    min(dt) FILTER (WHERE rn >= e{bd} AND pm_b <= 0.5 * greatest(1.0, runmax_b)) AS b50_stop_dt,
    NULLIF(max_by(COALESCE(m_ab, -1.0), rn), -1.0) AS hor_a,
    NULLIF(max_by(COALESCE(m_bb, -1.0), rn), -1.0) AS hor_b,
    {bd} AS b50_delay,
    max(dt) AS last_dt,
    max(evenue_b) AS e_venue_b,
    max(tok{bd}) AS tok_b,
    count(*) AS n_path
    FROM p4
    GROUP BY 1, 2
)
SELECT *
FROM res
"""


def build(label: str, wallets: pd.DataFrame | None) -> str:
    c0, c1, cut = RUNS[label]
    reg = label.startswith("REG")
    who = (
        "触发＝每币 t3 事件，卖出信号＝t3+30 秒（回归，对照 S1）"
        if reg
        else f"触发＝冻结的 {len(wallets)} 个钱包（前 50 实体）的首次买入"
    )
    head = f"""/* DQ-26 Q2 外部跟随（卡片_Q2_执行_v1.md）；由 sql/build_q2_sql.py 生成（{label}）。
   币：{c0}～{c1} 创建的 SOL 计价 pump 币；成交（曲线＋PumpSwap）截至 {cut} 24:00 UTC；只读 {c0}～{cut} 的分区。
   {who}；延迟 2/5/15/30 秒；跟随退出与 {5 if reg else 2} 秒 b50；估值同 S1 s9/s10（口径 A/B）。 */
WITH
"""
    sel = ""
    if not reg:
        vals = ",\n".join(
            f"        ('{u}', '{e}')" for u, e in zip(wallets.usr, wallets.entity)
        )
        sel = f"sel(usr, entity) AS (\n    SELECT usr, entity FROM (VALUES\n{vals}\n    ) AS v(usr, entity)\n),\n"
    body = chain(c0, c1, cut) + ",\n" + (trig_reg() if reg else trig_main()) + "\n"
    return head + sel + body + tail(5 if reg else 2)


def main() -> None:
    wallets = pd.read_csv(D / "runs" / "top50_wallets.csv")
    assert len(wallets) == 146 and wallets.entity.nunique() == 50
    lines = []
    for label, (c0, _, cut) in RUNS.items():
        sql = build(label, None if label.startswith("REG") else wallets)
        sqlglot.parse_one(sql, read="trino")
        dates = sorted(set(re.findall(r"DATE '([0-9-]+)'", sql)))
        assert dates[0] >= c0 and dates[-1] <= cut, dates
        out = H / f"Q2_{label}.sql"
        out.write_text(sql)
        h = hashlib.sha256(out.read_bytes()).hexdigest()
        lines.append(f"{out.name} {h}")
        print(out.name, h[:12], len(sql))
    with open(H / "sha256.txt", "a") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
