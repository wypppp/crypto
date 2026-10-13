"""b_weeks 的手算测试（10-13）。"""

import datetime as dt

import b_weeks as B


def test_counts_and_edges():
    rs = {r["monday"]: r for r in B.rows()}
    assert len(rs) == 57  # 检验周预登记：开发 57 周
    assert dt.date(2026, 6, 8) not in rs  # 检验周
    assert rs[dt.date(2026, 6, 1)]["lag_ok"]  # 上一周 05-25 是开发周
    # 09-21 周：周一＋7 天＋5 分钟＋7 天＝10-05 00:05，晚于止日 → P2 不整周成熟
    if dt.date(2026, 9, 21) in rs:
        assert not rs[dt.date(2026, 9, 21)]["p2_mature"]
    assert (
        not rs[dt.date(2025, 3, 3)]["p5_available"]
        if dt.date(2025, 3, 3) in rs
        else True
    )
