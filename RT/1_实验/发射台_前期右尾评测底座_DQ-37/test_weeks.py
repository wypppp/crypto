"""weeks.py 的手算预期值测试。哈希预期值用 shell 的 sha256sum 独立算出（见各条注释），
只用范围外的 2024 年周一做哈希样例，不暴露范围内任何一周的类别。"""

import datetime as dt

import pytest

import weeks as w


def test_week_monday_hand():
    # 2025-03-05 是周三 -> 周一 2025-03-03；2026-09-30 是周三 -> 2026-09-28
    assert w.week_monday(dt.date(2025, 3, 5)) == dt.date(2025, 3, 3)
    assert w.week_monday(dt.date(2026, 9, 30)) == dt.date(2026, 9, 28)
    # 周日 23:59 UTC 仍属本周；北京时间周一 07:00 = UTC 周日 23:00
    assert w.week_monday(dt.datetime(2025, 3, 9, 23, 59)) == dt.date(2025, 3, 3)
    bj = dt.timezone(dt.timedelta(hours=8))
    assert w.week_monday(dt.datetime(2025, 3, 10, 7, 0, tzinfo=bj)) == dt.date(
        2025, 3, 3
    )
    assert w.week_monday("2025-03-10T00:00:00Z") == dt.date(2025, 3, 10)
    assert w.week_monday("2025-03-09 23:59:59.000 UTC") == dt.date(2025, 3, 3)


def test_hash_hand_values():
    # printf 'RT-DQ37-testweek-v1|7ad8e42504f6adb637881bd57a73a7681d847ba4|2024-01-01' | sha256sum
    # -> 50fb92d4...，首字节 0x50=80，80 mod 4 = 0 -> 检验
    assert w._hash_says_test(dt.date(2024, 1, 1)) is True
    # 2024-01-08 -> b778dcd1...，0xb7=183，mod 4 = 3
    assert w._hash_says_test(dt.date(2024, 1, 8)) is False
    # 2024-01-15 -> bb9eefca...，0xbb=187，mod 4 = 3
    assert w._hash_says_test(dt.date(2024, 1, 15)) is False
    # 2024-01-22 -> 9736109e...，0x97=151，mod 4 = 3
    assert w._hash_says_test(dt.date(2024, 1, 22)) is False


def test_scope_and_sealed():
    # 范围外：即使哈希命中（2024-01-01）也只返回 out_of_scope
    assert w.week_class(dt.date(2024, 1, 3)) == w.OUT
    assert w.week_class(dt.date(2025, 2, 23)) == w.OUT  # 周一 02-17
    assert w.week_class(dt.date(2026, 10, 5)) == w.OUT
    # 封存周 06-15～07-12 四周，边界两侧
    for d in (dt.date(2026, 6, 15), dt.date(2026, 6, 30), dt.date(2026, 7, 12)):
        assert w.week_class(d) == w.SEALED
    assert w.week_class(dt.date(2026, 7, 13)) != w.SEALED
    assert w.week_class(dt.date(2026, 6, 14)) != w.SEALED


def test_in_scope_only_dev_or_test():
    d = dt.date(2025, 2, 24)
    while d <= dt.date(2026, 9, 28):
        c = w.week_class(d)
        assert c in (w.DEV, w.TEST, w.SEALED)
        # 同一周内七天类别相同
        assert all(w.week_class(d + dt.timedelta(days=k)) == c for k in range(7))
        d += dt.timedelta(days=7)


def test_assert_dev_raises_without_naming_week():
    with pytest.raises(ValueError) as e:
        w.assert_dev([dt.date(2026, 6, 20)])
    assert "2026" not in str(e.value)
