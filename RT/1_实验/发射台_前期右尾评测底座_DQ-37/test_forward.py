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


def test_trade_cutoff_hand():
    # 老币（09 月创建）10-04 23:59:59 UTC 的成交可读，10-05 00:00 起不可读
    assert not f.is_after_cutoff("2026-10-04T23:59:59Z")
    assert f.is_after_cutoff("2026-10-05T00:00:00Z")
    # 北京时间 10-05 07:59 是 UTC 10-04 23:59，可读
    bj = dt.timezone(dt.timedelta(hours=8))
    assert not f.is_after_cutoff(dt.datetime(2026, 10, 5, 7, 59, tzinfo=bj))
    tr = pd.DataFrame(
        {"ts": ["2026-09-29 12:00", "2026-10-04 23:00", "2026-10-06 01:00"]}
    )
    assert len(f.drop_after_cutoff(tr, "ts")) == 2
    f.assert_before_cutoff(["2026-10-04 23:00"])
    with pytest.raises(ValueError):
        f.assert_before_cutoff(["2026-10-04 23:00", "2026-10-05 00:00"])


def test_numeric_epoch_hand():
    # 1970-01-01 到 2026-10-05：56 年×365＋14 个闰日＝20,454 天到 2026-01-01，
    # 再加 1～9 月 273 天＝20,731 天；×86,400＝1,791,158,400 秒
    t0 = 1_791_158_400
    assert f.is_forward(t0) and not f.is_forward(t0 - 1)
    assert f.is_after_cutoff(float(t0)) and not f.is_after_cutoff(t0 - 0.5)
    # 冻结的 weeks._to_date 不接受数值 epoch：调用方须先转成时间
    import weeks

    with pytest.raises(TypeError):
        weeks._to_date(t0)
