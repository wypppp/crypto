"""forward.py 的手算预期值测试。"""

import datetime as dt

import pandas as pd
import pytest

import forward as f


def test_boundary_hand():
    # 2026-10-05 是周一：当天 00:00 UTC 起属前向批次，前一秒不属
    assert dt.date(2026, 10, 5).weekday() == 0
    assert f.is_forward("2026-10-05T00:00:00Z")
    assert not f.is_forward("2026-10-04T23:59:59Z")
    # 带时区的时刻先换到 UTC：北京时间 10-05 07:59 是 UTC 10-04 23:59
    bj = dt.timezone(dt.timedelta(hours=8))
    assert not f.is_forward(dt.datetime(2026, 10, 5, 7, 59, tzinfo=bj))
    assert f.is_forward(dt.datetime(2026, 10, 5, 8, 0, tzinfo=bj))


def test_drop_and_guard():
    df = pd.DataFrame(
        {"mint": ["a", "b", "c"], "created": ["2026-09-28", "2026-10-05", "2027-01-01"]}
    )
    kept = f.drop_forward(df, "created")
    assert list(kept["mint"]) == ["a"]
    f.assert_not_forward(["2026-09-28", "2026-10-04"])
    with pytest.raises(ValueError):
        f.assert_not_forward(["2026-09-28", "2026-10-05"])
