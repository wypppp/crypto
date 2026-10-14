"""run_dune.budget_gate 的手算测试（10-14，总控第五轮第三节：上限 22,000，硬停 24,000；额度更低时以额度为准）。"""

import run_dune as R

PAID = 25_000.0


def test_gate_hand():
    assert R.budget_gate(None, 10) != ""  # 读不到即停
    assert R.budget_gate((21_999.0, PAID), 100) == ""
    assert R.budget_gate((22_000.0, PAID), 1) != ""  # 到上限先报
    assert R.budget_gate((21_950.0, PAID), 2_100) != ""  # 21,950＋2,100＞24,000
    assert R.budget_gate((21_900.0, PAID), 2_100) == ""  # 恰好 24,000 不超


def test_gate_uses_lower_included_credits_hand():
    """接口显示本期额度 2,500（10-14 实读）：上限与硬停都按 2,500。"""
    assert R.budget_gate((2_400.0, 2_500.0), 100) == ""  # 恰好 2,500
    assert R.budget_gate((2_401.0, 2_500.0), 100) != ""
    assert R.budget_gate((2_500.0, 2_500.0), 0) != ""
