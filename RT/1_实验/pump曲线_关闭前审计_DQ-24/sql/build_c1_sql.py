#!/usr/bin/env python3
"""DQ-24（C1）：pump +30 分钟做多的关闭前审计——渲染逐周 SQL。

python build_c1_sql.py → sql/C1_SMOKE_20250407.sql、C1_REG_20260601.sql、C1_W<周一>.sql（10 周）与 sha256.txt
池状态与成交链（comp … states）从 DQ-7 冻结的 F2_dev.sql 原样截取，只替换日期，断言命中次数；
其余（创建者滚动 30 天、口径 A/B、三条退出）为新写。
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
F2 = HERE.parents[1] / "pump曲线_退出规则_DQ-7" / "sql" / "F2_dev.sql"
F2_SHA = "9313de984c3aa792cc4e1c7e430cc703a8b41be04081217e38ac66b1741d8764"
DAY = dt.timedelta(days=1)
# 日历规则（卡片 §2）：2025Q2～2026Q2 每季度第 1、第 7 个完整周（周一起，UTC）
WEEKS = [
    dt.date(2025, 4, 7), dt.date(2025, 5, 19),
    dt.date(2025, 7, 7), dt.date(2025, 8, 18),
    dt.date(2025, 10, 6), dt.date(2025, 11, 17),
    dt.date(2026, 1, 5), dt.date(2026, 2, 16),
    dt.date(2026, 4, 6), dt.date(2026, 5, 18),
]  # fmt: skip

TR50 = "(p AND pm <= 0.50 * greatest(1.0, runmax_post))"
DEAD24 = "(rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 86400)"
DEAD1H = "(rn >= entry_rn AND date_diff('second', greatest(ts, t_entry), COALESCE(lead_ts, t_end)) > 3600)"
F5 = "(lead_ts IS NOT NULL AND date_diff('second', ts, lead_ts) <= 5)"
TR50B = "(r2b IS NOT NULL AND rn > r2b AND pm <= 0.50 * greatest(pmb, m2))"
DEAD24B = "(r2b IS NOT NULL AND rn >= r2b AND date_diff('second', ts, COALESCE(lead_ts, t_end)) > 86400)"


def core(c1: dt.date, c2: dt.date, s2: dt.date) -> str:
    """F2 的 comp … states（到 s1 之前），替换日期；创建费缺失时补 100 bps（2025-05 前曲线成交事件无费率字段）。"""
    txt = F2.read_text()
    assert hashlib.sha256(txt.encode()).hexdigest() == F2_SHA
    a, b = txt.index("comp AS ("), txt.index("s1 AS (")
    sec = txt[a:b]
    assert sec.count("DATE '2026-06-01' AND DATE '2026-07-08'") == 6
    sec = sec.replace(
        "DATE '2026-06-01' AND DATE '2026-07-08'",
        f"DATE '{c1}' AND DATE '{s2}'",
    )
    old = "COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0) AS fee_bps,"
    assert sec.count(old) == 1
    sec = sec.replace(
        old,
        "COALESCE(CAST(t.fee_basis_points AS DOUBLE) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0), 100) AS fee_bps,",
    )
    return sec


def sql(c1: dt.date, c2: dt.date, title: str) -> str:
    s2 = c2 + 31 * DAY
    h1 = c1 - 31 * DAY
    sec = core(c1, c2, s2)
    lead = ", ".join(
        f"lead({c}) OVER (PARTITION BY mint ORDER BY rn) AS lead_{c}"
        for c in ("sm", "sma", "ts")
    )
    return f"""-- DQ-24（C1）{title}：pump +30 分钟做多关闭前审计。依据 卡片_v1.md。
-- cohort 创建日 {c1} ~ {c2}；行情扫描至 {s2}（入场后 30 天封顶）；创建者历史回看自 {h1}（滚动 30 天，严格在前）。
-- 池状态与成交链（comp … states）原样取自 DQ-7 冻结的 F2_dev.sql（sha256 {F2_SHA[:8]}…），只换日期；
-- 曲线成交缺费率字段时按 100 bps 补（flags 2048 标出入场时缺失）。
-- 卖出两种口径：B＝旧式（我方仓位留在曲线里，偏乐观，sm）；A＝卖进不含我方仓位的状态（偏保守，sma）。池上两者相同。
-- 退出：b50（50% 回撤＋24 小时沉寂）；x50_1h（50% 回撤＋1 小时沉寂，DQ-1F 主候选的退出）；
-- rb50（主退出）：b50 因价格触发出场后，若价格收复出场前高点 H＝max(1, 入场后最高)，按收复时状态（5 秒内有下一笔则按下一笔后）
--   用第一段全部所得买回，再按 b50（相对买回后最高）出场；只买回一次；30 天封顶按最后状态估值。
-- 只输出活跃池（入场时曲线虚拟 SOL ≥30.5 或已在池上；非 SOL、无法入场、虚拟 SOL >120 不输出），另加一行 __SUMMARY__。
WITH
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        date_diff('day', DATE '{c1}', min(evt_block_date)) + 1 AS cday,
        max(quote_mint) AS quote_mint,
        max("user") AS dev,
        COALESCE(bool_or(CAST(is_mayhem_mode AS varchar) IN ('true', '1')), false) AS mayhem_create
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{c1}' AND DATE '{c2}'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
cr AS (
    SELECT mint, max("user") AS dev, min(evt_block_time) AS t,
           min(evt_block_slot) AS slot, min_by(evt_tx_index, evt_block_slot) AS txi
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{h1}' AND DATE '{c2}'
    GROUP BY 1
),
dev_hist AS (
    -- 修正 §5.1 缺陷：严格在前、滚动 30 天的发币数＝同一创建者按 (slot, txi) 排在前面的发币数 − 其中早于 30 天的
    SELECT mint, (rn_dev - 1) - n_old AS dev_prior_launches
    FROM (
        SELECT
            mint,
            row_number() OVER (PARTITION BY dev ORDER BY slot, txi, mint) AS rn_dev,
            count(*) OVER (PARTITION BY dev ORDER BY to_unixtime(t) RANGE BETWEEN UNBOUNDED PRECEDING AND 2592000 PRECEDING) AS n_old
        FROM cr
    ) z
    WHERE mint IN (SELECT mint FROM sol_cohort)
),
{sec}s1 AS (
    SELECT
        s.*,
        c.created_at + INTERVAL '30' MINUTE AS t_entry,
        LEAST(c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY, TIMESTAMP '{s2} 23:59:59 UTC') AS t_end,
        date_diff('second', c.created_at + INTERVAL '30' MINUTE, s.ts) AS dt,
        row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.iix) AS rn
    FROM states s
    JOIN sol_cohort c ON c.mint = s.mint
    WHERE s.ts <= c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY
      AND s.x > 0 AND s.y > 0
),
s2 AS (
    SELECT *, max(CASE WHEN dt <= 0 THEN rn END) OVER (PARTITION BY mint) AS entry_rn
    FROM s1
),
s3 AS (
    SELECT
        *,
        rn > entry_rn AS p,
        max(CASE WHEN rn = entry_rn THEN x END) OVER (PARTITION BY mint) AS ex,
        max(CASE WHEN rn = entry_rn THEN y END) OVER (PARTITION BY mint) AS ey,
        max(CASE WHEN rn = entry_rn THEN fee_bps END) OVER (PARTITION BY mint) AS efee,
        COALESCE(bool_or(CASE WHEN rn = entry_rn THEN fee_missing END) OVER (PARTITION BY mint), false) AS efee_missing,
        max(CASE WHEN rn = entry_rn THEN venue END) OVER (PARTITION BY mint) AS evenue
    FROM s2
),
s4 AS (
    SELECT *, ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4)) AS tok, (x / y) / (ex / ey) AS pm
    FROM s3
),
s5 AS (
    SELECT
        *,
        LEAST(
            CASE WHEN venue = 0 AND y > tok THEN (x * y / (y - tok) - x) * (1 - fee_bps / 1e4)
                 WHEN venue = 0 THEN NULL
                 ELSE (x - x * y / (y + tok)) * (1 - fee_bps / 1e4) END,
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - efee / 1e4)), 1e18)) / 0.5 AS sm,
        LEAST(
            (x - x * y / (y + tok)) * (1 - fee_bps / 1e4),
            COALESCE(IF(venue = 0, xr + 0.5 * (1 - efee / 1e4)), 1e18)) / 0.5 AS sma
    FROM s4
),
s6 AS (
    SELECT
        *,
        max(CASE WHEN rn >= entry_rn THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS runmax_post,
        {lead}
    FROM s5
),
s7 AS (
    SELECT *, min(CASE WHEN {TR50} OR {DEAD24} THEN rn END) OVER (PARTITION BY mint) AS ex1_rn
    FROM s6
),
s8 AS (
    SELECT
        *,
        COALESCE(bool_or(CASE WHEN rn = ex1_rn THEN {TR50} END) OVER (PARTITION BY mint), false) AS ex1_price,
        max(CASE WHEN rn = ex1_rn THEN greatest(1.0, runmax_post) END) OVER (PARTITION BY mint) AS hh,
        max(CASE WHEN rn = ex1_rn THEN (CASE WHEN {TR50} AND {F5} THEN lead_sm ELSE sm END) END) OVER (PARTITION BY mint) AS v1b,
        max(CASE WHEN rn = ex1_rn THEN (CASE WHEN {TR50} AND {F5} THEN lead_sma ELSE sma END) END) OVER (PARTITION BY mint) AS v1a
    FROM s7
),
s9 AS (
    SELECT *, min(CASE WHEN ex1_price AND rn > ex1_rn AND pm >= hh THEN rn END) OVER (PARTITION BY mint) AS r2
    FROM s8
),
s10 AS (
    SELECT *, r2 + IF(COALESCE(bool_or(CASE WHEN rn = r2 THEN {F5} END) OVER (PARTITION BY mint), false), 1, 0) AS r2b
    FROM s9
),
s11 AS (
    SELECT
        *,
        max(CASE WHEN rn = r2b THEN x END) OVER (PARTITION BY mint) AS xb,
        max(CASE WHEN rn = r2b THEN y END) OVER (PARTITION BY mint) AS yb,
        max(CASE WHEN rn = r2b THEN fee_bps END) OVER (PARTITION BY mint) AS feeb,
        max(CASE WHEN rn = r2b THEN pm END) OVER (PARTITION BY mint) AS pmb,
        max(CASE WHEN rn = r2b THEN dt END) OVER (PARTITION BY mint) AS dtb,
        max(CASE WHEN rn >= r2b THEN pm END) OVER (PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS m2
    FROM s10
),
s12 AS (
    SELECT
        *,
        yb - xb * yb / (xb + 0.5 * v1b * (1 - feeb / 1e4)) AS tok2b,
        yb - xb * yb / (xb + 0.5 * v1a * (1 - feeb / 1e4)) AS tok2a
    FROM s11
),
s13 AS (
    SELECT
        *,
        LEAST(
            CASE WHEN venue = 0 AND y > tok2b THEN (x * y / (y - tok2b) - x) * (1 - fee_bps / 1e4)
                 WHEN venue = 0 THEN NULL
                 ELSE (x - x * y / (y + tok2b)) * (1 - fee_bps / 1e4) END,
            COALESCE(IF(venue = 0, xr + 0.5 * v1b * (1 - feeb / 1e4)), 1e18)) / 0.5 AS sm2,
        LEAST(
            (x - x * y / (y + tok2a)) * (1 - fee_bps / 1e4),
            COALESCE(IF(venue = 0, xr + 0.5 * v1a * (1 - feeb / 1e4)), 1e18)) / 0.5 AS sm2a
    FROM s12
),
s14 AS (
    SELECT
        *,
        lead(sm2) OVER (PARTITION BY mint ORDER BY rn) AS lead_sm2,
        lead(sm2a) OVER (PARTITION BY mint ORDER BY rn) AS lead_sm2a
    FROM s13
),
agg AS (
    SELECT
        mint,
        max(entry_rn) AS entry_rn,
        max(ex) AS ex,
        max(efee) AS efee,
        bool_or(efee_missing) AS efee_missing,
        max(evenue) AS evenue,
        bool_or(venue = 0 AND x > 120) AS anomaly,
        bool_or(mayhem) AS mayhem_trade,
        max(pm) FILTER (WHERE p) AS ms_30d,
        max_by(sm, rn) FILTER (WHERE p) AS sm_last,
        max_by(sma, rn) FILTER (WHERE p) AS sma_last,
        min_by(CASE WHEN {TR50} AND {F5} THEN lead_sm ELSE sm END, rn) FILTER (WHERE {TR50} OR {DEAD24}) AS b50_b,
        min_by(CASE WHEN {TR50} AND {F5} THEN lead_sma ELSE sma END, rn) FILTER (WHERE {TR50} OR {DEAD24}) AS b50_a,
        min_by(CASE WHEN {TR50} AND {F5} THEN lead_sm ELSE sm END, rn) FILTER (WHERE {TR50} OR {DEAD1H}) AS x50_1h_b,
        min_by(CASE WHEN {TR50} AND {F5} THEN lead_sma ELSE sma END, rn) FILTER (WHERE {TR50} OR {DEAD1H}) AS x50_1h_a,
        max(r2b) AS r2b,
        bool_or(ex1_price) AS ex1_price,
        max(hh) AS hh,
        max(dtb) AS rebuy_dt,
        min_by(CASE WHEN {TR50B} AND {F5} THEN lead_sm2 ELSE sm2 END, rn) FILTER (WHERE {TR50B} OR {DEAD24B}) AS rb2_b,
        min_by(CASE WHEN {TR50B} AND {F5} THEN lead_sm2a ELSE sm2a END, rn) FILTER (WHERE {TR50B} OR {DEAD24B}) AS rb2_a,
        max_by(sm2, rn) FILTER (WHERE rn >= r2b) AS sm2_last,
        max_by(sm2a, rn) FILTER (WHERE rn >= r2b) AS sm2a_last,
        count(*) AS n_rows
    FROM s14
    GROUP BY 1
),
final AS (
    SELECT
        c.mint,
        c.cday,
        (CASE WHEN co.mint IS NOT NULL THEN 4 ELSE 0 END)
          + (CASE WHEN c.mayhem_create OR a.mayhem_trade THEN 128 ELSE 0 END)
          + (CASE WHEN a.evenue = 1 THEN 1024 ELSE 0 END)
          + (CASE WHEN a.efee_missing THEN 2048 ELSE 0 END) AS flags,
        round(a.ex, 3) AS entry_x_sol,
        COALESCE(h.dev_prior_launches, 0) AS dev_prior_launches,
        round(COALESCE(a.ms_30d, 1.0), 6) AS ms_30d,
        round(COALESCE(a.b50_b, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS b50_b,
        round(COALESCE(a.b50_a, a.sma_last, power(1 - a.efee / 1e4, 2)), 6) AS b50_a,
        round(COALESCE(a.x50_1h_b, a.sm_last, power(1 - a.efee / 1e4, 2)), 6) AS x50_1h_b,
        round(COALESCE(a.x50_1h_a, a.sma_last, power(1 - a.efee / 1e4, 2)), 6) AS x50_1h_a,
        round(CASE WHEN a.r2b IS NULL THEN COALESCE(a.b50_b, a.sm_last, power(1 - a.efee / 1e4, 2))
                   ELSE COALESCE(a.rb2_b, a.sm2_last) END, 6) AS rb50_b,
        round(CASE WHEN a.r2b IS NULL THEN COALESCE(a.b50_a, a.sma_last, power(1 - a.efee / 1e4, 2))
                   ELSE COALESCE(a.rb2_a, a.sm2a_last) END, 6) AS rb50_a,
        CASE WHEN a.r2b IS NOT NULL THEN 2 WHEN a.ex1_price THEN 1 ELSE 0 END AS rb_state,
        a.rebuy_dt,
        round(a.hh, 4) AS hh,
        a.n_rows
    FROM cohort c
    JOIN sol_cohort s ON s.mint = c.mint
    JOIN agg a ON a.mint = c.mint
    LEFT JOIN comp co ON co.mint = c.mint
    LEFT JOIN dev_hist h ON h.mint = c.mint
    WHERE a.entry_rn IS NOT NULL
      AND NOT COALESCE(a.anomaly, false)
      AND (a.ex >= 30.5 OR a.evenue = 1)
)
SELECT * FROM final
UNION ALL
SELECT
    '__SUMMARY__' AS mint,
    (SELECT count(*) FROM sol_cohort) AS cday,
    (SELECT count(*) FROM cohort) - (SELECT count(*) FROM sol_cohort) AS flags,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
ORDER BY cday, mint
"""


def main() -> None:
    out = {}
    smoke = WEEKS[0]
    out[f"C1_SMOKE_{smoke:%Y%m%d}.sql"] = sql(smoke, smoke, "一日冒烟")
    reg = dt.date(
        2026, 6, 1
    )  # 回归：与 DQ-7 F2_dev.csv 的 b50（口径 B）逐币对照，只核实现，不看新结果
    out[f"C1_REG_{reg:%Y%m%d}.sql"] = sql(reg, reg, "回归冒烟（A 周第 1 天）")
    for w in WEEKS:
        out[f"C1_W{w:%Y%m%d}.sql"] = sql(w, w + 6 * DAY, f"周 {w}")
    lines = []
    for name, txt in out.items():
        (HERE / name).write_text(txt)
        lines.append(f"{hashlib.sha256(txt.encode()).hexdigest()}  {name}")
    (HERE / "sha256.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
