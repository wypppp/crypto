"""十进制MB预算、取整假设及完整分页的手算预期。"""

from decimal import Decimal
from itertools import pairwise

import pytest

import a11_small_page_plan as P


def test_budget_keeps_fractional_cost_even_when_floor_hypothesis_is_zero():
    assert P.fee_budget(236422) == Decimal("0.472844")
    assert P.floor_hypothesis(236422) == 0
    assert P.fee_budget(500000) == 1
    assert P.floor_hypothesis(500000) == 1
    assert P.floor_hypothesis(499999) == 0


def test_four_existing_page_sizes_match_billing_multiset_only_under_hypothesis():
    sizes = [1016581, 944577, 975208, 236422]
    assert [P.floor_hypothesis(n) for n in sizes] == [2, 1, 1, 0]
    assert sum(P.fee_budget(n) for n in sizes) == Decimal("6.345576")


def test_all_rows_covered_once_and_final_short_page_kept():
    plan = P.offsets(16145)
    assert len(plan) == 17 and plan[-1] == {"offset": 16000, "limit": 145}
    assert sum(p["limit"] for p in plan) == 16145
    for a, b in pairwise(plan):
        assert a["offset"] + a["limit"] == b["offset"]
    assert P.offsets(0) == []


@pytest.mark.parametrize("value", [-1, 1.5, "1000"])
def test_unknown_or_invalid_size_does_not_become_zero_budget(value):
    with pytest.raises(ValueError):
        P.fee_budget(value)
    with pytest.raises(ValueError):
        P.offsets(value)
