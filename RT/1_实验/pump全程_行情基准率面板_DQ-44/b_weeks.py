#!/usr/bin/env python3
"""DQ-44（B）允许周清单（10-13，B v2 §3、§4）。只读周的分类，不读任何数据。

python b_weeks.py

规则（写进冻结卡）：
- 周：DQ-37 开发周（weeks.py）；创建周归属。
- 7 天主格成熟：该周最后一个可能的决策时刻（周日 24:00 前创建，P2＝创建后 5 分钟；P5＝建池后 5 分钟，建池最晚取到创建后 30 天的观察窗内）
  ＋7 天，须不晚于 2026-10-05 00:00 UTC。P2 周按“周一＋7 天＋5 分钟＋7 天”判；P5 周毕业时刻不定，
  按“周一＋7 天＋30 天＋5 分钟＋7 天”判整周成熟，不成熟的周照列、标“部分未成熟”，未成熟的币按 contract_filter.label_status 单列。
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
            p2 = _end(m, dt.timedelta(minutes=5, days=7)) <= CUT
            p5_on = m >= PUMPSWAP_MONDAY
            p5 = p5_on and _end(m, dt.timedelta(days=37, minutes=5)) <= CUT
            out.append(
                {
                    "monday": m,
                    "lag_ok": CF.lagged_week(m) is not None,
                    "p2_mature": p2,
                    "p5_available": p5_on,
                    "p5_mature": p5,
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
        "；P2×7天整周成熟",
        sum(r["p2_mature"] for r in rs),
        "；P5 可用",
        sum(r["p5_available"] for r in rs),
        "；P5×7天整周成熟",
        sum(r["p5_mature"] for r in rs),
    )
    for r in rs:
        print(
            r["monday"],
            int(r["lag_ok"]),
            int(r["p2_mature"]),
            int(r["p5_available"]),
            int(r["p5_mature"]),
        )
