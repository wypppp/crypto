"""run_all_v2.halves 的手算预期值测试（10-03）。"""

import datetime as dt

from run_all_v2 import halves


def test_halves_start_and_end_hand():
    # 2025-03 上半月整段早于 PumpSwap 起点 03-16，跳过；下半月从 03-16 起
    assert halves("2025-03", "2025-04", "GRAD2") == [
        ("GRAD2_202503b", dt.date(2025, 3, 16), dt.date(2025, 3, 31)),
        ("GRAD2_202504a", dt.date(2025, 4, 1), dt.date(2025, 4, 15)),
        ("GRAD2_202504b", dt.date(2025, 4, 16), dt.date(2025, 4, 30)),
    ]
    # 2026-09 下半月止于 09-29（负虚拟报价储备，事件止日）
    assert halves("2026-09", "2026-09", "GRADPRE2")[-1] == (
        "GRADPRE2_202609b",
        dt.date(2026, 9, 16),
        dt.date(2026, 9, 29),
    )
    # 跨年：2025-12 → 2026-01
    labs = [x[0] for x in halves("2025-12", "2026-01", "G")]
    assert labs == ["G_202512a", "G_202512b", "G_202601a", "G_202601b"]


def test_full_range_count():
    # 2025-03b 到 2026-09b：1 + 18 个月 × 2 = 37 片
    assert len(halves("2025-03", "2026-09", "GRAD2")) == 37
