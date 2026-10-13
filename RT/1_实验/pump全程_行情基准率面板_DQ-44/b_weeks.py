#!/usr/bin/env python3
"""DQ-44（B）允许周清单（10-13，B v2 §3、§4）。只读周的分类，不读任何数据。

python b_weeks.py

规则（写进冻结卡）：
- 周：DQ-37 开发周（weeks.py）；创建周归属。
- 整周未受止日截断（v2，GPT 23：不再叫“整周未截断”）：该周最晚的退出时刻严格早于 2026-10-05 00:00 UTC。
  P2：创建后 5 分钟入场、7 天退出 → 周一＋7 天＋5 分钟＋7 天；
  P5：B 自有观察窗＝创建后 30 天内毕业，建池后 305 秒入场（[300,305) 秒桶收盘），在建池后 7 天的桶边界退出
  → 周一＋7 天＋30 天＋7 天。逐币是否成熟另按 contract_filter.label_status 判，未成熟的币单列。
- 毕业进场点（P4、P5）从 PumpSwap 上线那周起算（F36：2025-03-20，周一 2025-03-17）。
- 行情变量：上一周不是开发周的记缺失（contract_filter.lagged_week），不用“上一个可用周”顶替。
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "发射台_前期右尾评测底座_DQ-37"))
sys.path.insert(0, str(HERE.parents[0] / "pump全程_钱流向谁完整账_DQ-43"))
import contract_filter as CF  # noqa: E402
import weeks as W  # noqa: E402

PUMPSWAP_MONDAY = dt.date(2025, 3, 17)
CUT = CF.CUTOFF


def _end(monday: dt.date, extra: dt.timedelta) -> dt.datetime:
    return (
        dt.datetime.combine(monday, dt.time(), dt.timezone.utc)
        + dt.timedelta(days=7)
        + extra
    )


def rows():
    m = W.FIRST_MONDAY
    out = []
    while m <= W.LAST_MONDAY:
        if W.week_class(m) == W.DEV:
            p2 = _end(m, dt.timedelta(minutes=5, days=7)) < CUT
            p5_on = m >= PUMPSWAP_MONDAY
            p5 = p5_on and _end(m, dt.timedelta(days=37)) < CUT
            out.append(
                {
                    "monday": m,
                    "lag_ok": CF.lagged_week(m) is not None,
                    "p2_uncut": p2,
                    "p5_available": p5_on,
                    "p5_uncut": p5,
                }
            )
        m += dt.timedelta(days=7)
    return out


if __name__ == "__main__":
    rs = rows()
    print(
        "开发周",
        len(rs),
        "；行情变量可用（上一周是开发周）",
        sum(r["lag_ok"] for r in rs),
        "；P2×7天整周未截断",
        sum(r["p2_uncut"] for r in rs),
        "；P5 可用",
        sum(r["p5_available"] for r in rs),
        "；P5×7天整周未截断",
        sum(r["p5_uncut"] for r in rs),
    )
    for r in rs:
        print(
            r["monday"],
            int(r["lag_ok"]),
            int(r["p2_uncut"]),
            int(r["p5_available"]),
            int(r["p5_uncut"]),
        )
