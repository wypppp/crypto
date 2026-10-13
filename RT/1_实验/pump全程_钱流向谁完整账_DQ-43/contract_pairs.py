#!/usr/bin/env python3
"""DQ-43 窗口对清单（10-13，WM2 v5 §7“窗口选法”，GPT X03）。只读周的分类，不读任何数据。

python contract_pairs.py   打印全部合格的相邻开发周对与选中的窗口对

规则（写进冻结卡，冻结后再取数）：
1. 相邻开发周对 (W, W+1)：W 与 W+1 都是 DQ-37 开发周（weeks.py）；
   W+1 的观察窗终点＝W+1 周一 + 7 天 + 30 天，须不晚于 2026-10-05 00:00 UTC。
2. A、B 两周（2026-06-01、2026-06-08）是一对，入选的前提是它满足第 1 条。
3. 另从 W 周一不早于 2026-07-13 的合格对里，按 sha256(TAG|SALT|W 周一 ISO) 升序取前 2 对；
   不足 2 对就报实有对数，不用保护周凑，不把“下一个可用周”当相邻周。
   SALT 取第十九轮第 0 步的提交号（35b21a05…），选规则时已固定，不能挑。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "发射台_前期右尾评测底座_DQ-37")
)
import weeks as W  # noqa: E402

TAG = "RT-DQ43-pairs-v1"
SALT = "35b21a05"  # 第十九轮第 0 步提交 35b21a05220ede66…（入库）的 8 位前缀
LAST_OBS = dt.date(2026, 10, 5)  # 观察窗终点不得晚于此日 00:00 UTC
AB = dt.date(2026, 6, 1)
LATE_FROM = dt.date(2026, 7, 13)
N_LATE = 2


def all_mondays():
    m = W.FIRST_MONDAY
    while m <= W.LAST_MONDAY:
        yield m
        m += dt.timedelta(days=7)


def pair_ok(w: dt.date) -> bool:
    w1 = w + dt.timedelta(days=7)
    end = w1 + dt.timedelta(days=7 + 30)
    return W.week_class(w) == W.DEV and W.week_class(w1) == W.DEV and end <= LAST_OBS


def eligible_pairs() -> list[dt.date]:
    return [w for w in all_mondays() if pair_ok(w)]


def pair_key(w: dt.date, salt: str = SALT) -> str:
    return hashlib.sha256(f"{TAG}|{salt}|{w.isoformat()}".encode()).hexdigest()


def select(salt: str = SALT) -> dict:
    el = eligible_pairs()
    late = sorted((w for w in el if w >= LATE_FROM), key=lambda w: pair_key(w, salt))
    return {
        "ab": AB if AB in el else None,
        "late": sorted(late[:N_LATE]),
        "n_late_eligible": len(late),
        "n_eligible": len(el),
    }


if __name__ == "__main__":
    s = select()
    print("合格的相邻开发周对（W 周一）：", [w.isoformat() for w in eligible_pairs()])
    print(
        "A/B 对：",
        s["ab"],
        "；07-13 之后合格：",
        s["n_late_eligible"],
        "；选中：",
        [w.isoformat() for w in s["late"]],
    )
