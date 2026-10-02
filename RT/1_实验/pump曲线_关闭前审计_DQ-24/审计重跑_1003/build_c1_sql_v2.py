#!/usr/bin/env python3
"""DQ-24（C1）审计重跑 v2：代码审计 10-03 第 2、12 处的修正版 SQL。原 sql/build_c1_sql.py 与 DQ-7 F2_dev.sql 不改。

python build_c1_sql_v2.py → sql/C1_W<周一>.sql（与 v1 同样的 10 周）、C1_SMOKE_20250407.sql 与 sql/sha256.txt
做法：调用 v1 的 sql() 生成原文，再做下面五处文本替换（每处断言恰好命中一次；①含两处），其余逐字不变：
  ①第 2 处：PumpSwap 成交后的池状态改为“本笔交易前储备＋本笔变动”，
    不再取同池下一笔的交易前储备（那会把两笔之间的加池、撤池提前算进本笔）；
    买入的 quote 变动改用 quote_amount_in_with_lp_fee（10-02 DQ-35 LPCHK3 核实：三个抽样日 100% 与下一笔交易前储备吻合；
    v1 里只在每池最后一笔用到的 F59 旧式在 2025 年 0% 吻合），卖出仍用 F59 式（100% 吻合）；
  ②第 12 处：异常（曲线虚拟 SOL >120）只按入场及之前的状态判定（入场时可知），
    不再因入场后路径出现该状态而整币剔除；入场后才出现的记 flags 4096，单列；
  ③只加标记、不改估值：持有期内已完成曲线、但最后一个状态仍在曲线上（迁移后没有池上成交）的记 flags 8192
    （第 4 处同型问题在 C1 的出现次数）；
  ④重跑中发现的排序并列（见 ORDER_REPL 注释）：排序键加外层指令序号；
  ⑤头部注释说明以上改动。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "sql"))
import build_c1_sql as V1  # noqa: E402

REPL = [
    (
        "CAST(quote_amount_in AS DOUBLE) - COALESCE(CAST(protocol_fee AS DOUBLE), 0)"
        " - COALESCE(CAST(coin_creator_fee AS DOUBLE), 0) AS dq,",
        "CAST(quote_amount_in_with_lp_fee AS DOUBLE) AS dq,"
        "  -- v2：买入后 quote＝交易前＋quote_amount_in_with_lp_fee（DQ-35 LPCHK3：三个抽样日逐位吻合 100%，F59 旧式 2025 年为 0%）",
    ),
    (
        "COALESCE(lead(qraw) OVER (PARTITION BY pool ORDER BY slot, txi, iix), qraw + dq) AS qraw,",
        "qraw + dq AS qraw,  -- v2（审计第 2 处）：本笔交易后＝本笔交易前＋本笔变动",
    ),
    (
        "COALESCE(lead(braw) OVER (PARTITION BY pool ORDER BY slot, txi, iix), braw + db) AS braw",
        "braw + db AS braw",
    ),
    (
        "bool_or(venue = 0 AND x > 120) AS anomaly,",
        "bool_or(venue = 0 AND x > 120 AND rn <= entry_rn) AS anomaly,  -- v2（审计第 12 处）：只看入场及之前\n"
        "        bool_or(venue = 0 AND x > 120 AND rn > entry_rn) AS anomaly_post,\n"
        "        max_by(venue, rn) AS venue_last,",
    ),
    (
        "+ (CASE WHEN a.efee_missing THEN 2048 ELSE 0 END) AS flags,",
        "+ (CASE WHEN a.efee_missing THEN 2048 ELSE 0 END)\n"
        "          + (CASE WHEN a.anomaly_post THEN 4096 ELSE 0 END)\n"
        "          + (CASE WHEN co.completed_at <= c.created_at + INTERVAL '30' MINUTE + INTERVAL '30' DAY"
        " AND a.venue_last = 0 THEN 8192 ELSE 0 END) AS flags,",
    ),
]

# ④ 重跑中发现（不在 GPT 的 14 处里）：同一交易内多笔成交的排序键 (时间, slot, tx, 内层指令) 会并列，只靠外层指令序号区分；
#    v1 未带外层序号，入场状态在并列行之间任取，同一 SQL 两次运行结果不同（10-02 TIECHK_20250407：第一周 v1/v2 进出的
#    43 个第 1 天币全部有带不同 x 的并列，对照 40 个中 9 个）。v2 把外层指令序号加进排序键。（旧值, 新值, 应命中次数）
ORDER_REPL = [
    (
        "        t.evt_inner_instruction_index AS iix,",
        "        t.evt_outer_instruction_index AS oix,\n        t.evt_inner_instruction_index AS iix,",
        1,
    ),
    (
        "mp.mint, p.ts, 1 AS venue, p.slot, p.txi, p.iix,",
        "mp.mint, p.ts, 1 AS venue, p.slot, p.txi, p.oix, p.iix,",
        1,
    ),
    (
        "SELECT pool, ts, slot, txi, iix, fee_bps, fee_missing, usr, is_buy, sraw, traw,",
        "SELECT pool, ts, slot, txi, oix, iix, fee_bps, fee_missing, usr, is_buy, sraw, traw,",
        1,
    ),
    (
        "evt_tx_index AS txi, evt_inner_instruction_index AS iix,",
        "evt_tx_index AS txi, evt_outer_instruction_index AS oix, evt_inner_instruction_index AS iix,",
        2,
    ),
    (
        "row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.iix) AS rn",
        "row_number() OVER (PARTITION BY s.mint ORDER BY s.ts, s.venue, s.slot, s.txi, s.oix, s.iix) AS rn",
        1,
    ),
]

HEAD = (
    "-- 审计重跑 v2（10-02，代码审计 10-03 第 2、12 处；由 审计重跑_1003/build_c1_sql_v2.py 从 v1 文本替换生成）：\n"
    "--   PumpSwap 成交后状态＝本笔交易前储备＋本笔变动（不再用下一笔的交易前储备）；买入 quote 变动＝quote_amount_in_with_lp_fee；\n"
    "--   虚拟 SOL >120 的异常只按入场及之前判定，入场后才出现的不剔除、记 flags 4096；\n"
    "--   持有期内已完成曲线但最后状态仍在曲线上的记 flags 8192（只标记，不改估值）；\n"
    "--   排序键加外层指令序号（同一交易内多笔成交原先会并列，结果随运行而变；重跑中发现，不在审计 14 处里）。\n"
)


def v2(text: str) -> str:
    for old, new in REPL:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    for old, new, k in ORDER_REPL:
        assert text.count(old) == k, old
        text = text.replace(old, new)
    return HEAD + text


def sql(c1: dt.date, c2: dt.date, title: str) -> str:
    return v2(V1.sql(c1, c2, title))


def main() -> None:
    out = {}
    s = V1.WEEKS[0]
    out[f"C1_SMOKE_{s:%Y%m%d}.sql"] = sql(s, s, "一日冒烟")
    for w in V1.WEEKS:
        out[f"C1_W{w:%Y%m%d}.sql"] = sql(w, w + 6 * V1.DAY, f"周 {w}")
    lines = []
    for name, txt in out.items():
        (HERE / "sql" / name).write_text(txt)
        lines.append(f"{hashlib.sha256(txt.encode()).hexdigest()}  {name}")
    (HERE / "sql" / "sha256.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
