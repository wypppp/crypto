"""d3_alpha_cost 的手算预期值测试（10-06）。"""

import d3_alpha_cost as D


def test_claims_per_window_hand():
    # 每日 17 分：15 天 255 分；门槛 241 → 领 1 次后剩 240，不够第二次
    assert D.claims_per_window(17, 241) == 1
    # 每日 18 分：270 分；领一次剩 255 ≥ 241，再领一次剩 240 → 2 次
    assert D.claims_per_window(18, 241) == 2
    # 每日 16 分：240 < 241，一次都领不到
    assert D.claims_per_window(16, 241) == 0
    # 门槛恰好等于总分也能领
    assert D.claims_per_window(16, 240) == 1


def test_volume_for_points_hand():
    assert D.volume_for_points(1) == 2 and D.volume_for_points(5) == 32  # FAQ 原表
    assert D.volume_for_points(13) == 8192
