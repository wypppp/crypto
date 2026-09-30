#!/usr/bin/env python3
"""组合门探针 P-C1（09-30）：生成创建者滚动 30 天履历查询，A 周、B 周各一条。

mint 名单取自 S1 A/B 双口径结果（= 冻结 S0 框架，每周全部行），按字母序写入 VALUES。
合约与预注册见 探针_组合门_2026-09-30.md。

python build_probe_creator_sql.py → sql/PROBE_CREATOR_{A,B}.sql
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from analyze_s1_baseline import read_rows

HERE = Path(__file__).resolve().parent
S1 = HERE / "raw" / "s1"
LOOKBACK_DAYS = 30
WEEKS = {"A": ("2026-06-01", "2026-06-07"), "B": ("2026-06-08", "2026-06-14")}
FENCE = dt.date(2026, 6, 14)  # 不读 06-15 起任何分区

TEMPLATE = """/* 组合门探针 P-C1（09-30）：创建者滚动 30 天发币与毕业履历，挂在 S1 冻结框架（{week} 周 {n} 币）上。
   由 build_probe_creator_sql.py 生成；合约与预注册见 探针_组合门_2026-09-30.md。
   只读 {lo}～{hi} 的创建事件与完成（毕业）事件；不读成交表；不读 06-15 起任何分区。
   创建者 = 创建事件的 user 字段（与 DQ-1F/DQ-8A 的 dev 相同）；另报 creator 字段与签名者，供核对。
   此前发币：同一创建者、严格早于本币创建事件（按 slot、交易序号），且不早于本币创建时刻前 30 天。
   此前毕业：上述此前发币中，完成事件时刻严格早于本币创建时刻的个数。
   修正 §5.1 缺陷“此前 30 天实为固定起日累计”。 */
WITH
frame(mint) AS (
    SELECT mint FROM (VALUES
{values}
    ) AS t(mint)
),
cr_all AS (
    SELECT
        mint,
        "user" AS dev,
        creator AS creator_field,
        tx_signer AS signer,
        evt_block_time AS t,
        evt_block_slot AS slot,
        evt_tx_index AS txi,
        row_number() OVER (
            PARTITION BY mint
            ORDER BY evt_block_slot, evt_tx_index, evt_outer_instruction_index
        ) AS rn
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '{lo}' AND DATE '{hi}'
),
cr AS (
    SELECT mint, dev, creator_field, signer, t, slot, txi
    FROM cr_all
    WHERE rn = 1
),
tgt AS (
    SELECT c.*
    FROM cr c
    JOIN frame f ON f.mint = c.mint
),
grad AS (
    SELECT mint, min(evt_block_time) AS tg
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date BETWEEN DATE '{lo}' AND DATE '{hi}'
    GROUP BY 1
),
hist AS (
    SELECT
        g.mint,
        count(p.mint) AS n_launch_30d,
        count(CASE WHEN gr.tg < g.t THEN 1 END) AS n_grad_30d
    FROM tgt g
    LEFT JOIN cr p
        ON p.dev = g.dev
        AND p.t >= g.t - INTERVAL '{days}' DAY
        AND (p.slot < g.slot OR (p.slot = g.slot AND p.txi < g.txi))
    LEFT JOIN grad gr ON gr.mint = p.mint
    GROUP BY 1
)
SELECT
    g.mint,
    g.dev,
    g.creator_field,
    g.signer,
    g.t AS created_at_evt,
    g.slot AS created_slot,
    h.n_launch_30d,
    h.n_grad_30d
FROM tgt g
JOIN hist h ON h.mint = g.mint
ORDER BY g.mint
"""


def main() -> None:
    for week, (first, last) in WEEKS.items():
        rows = read_rows(S1 / f"S1_{week}_dual.csv.gz")
        mints = sorted(rows)
        if any(r["cohort_week"] != week for r in rows.values()):
            raise RuntimeError(f"S1_{week} 含其他周的行")
        lo = dt.date.fromisoformat(first) - dt.timedelta(days=LOOKBACK_DAYS)
        hi = dt.date.fromisoformat(last)
        if hi > FENCE:
            raise RuntimeError("日期窗口越过 06-14")
        sql = TEMPLATE.format(
            week=week,
            n=len(mints),
            lo=lo.isoformat(),
            hi=hi.isoformat(),
            days=LOOKBACK_DAYS,
            values=",\n".join(f"        ('{m}')" for m in mints),
        )
        out = HERE / "sql" / f"PROBE_CREATOR_{week}.sql"
        out.write_text(sql)
        print(out.name, len(mints), lo, hi, hashlib.sha256(sql.encode()).hexdigest())


if __name__ == "__main__":
    main()
