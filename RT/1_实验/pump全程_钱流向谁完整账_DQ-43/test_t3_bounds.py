"""冻结卡 v4 新规则的手算测试（10-14）：成本上下界下的 §9.1 判定、抽样阶梯。"""

import t3_bounds as TB

POS, NEG, NC = (
    {"result": "positive"},
    {"result": "not_positive"},
    {"result": "not_computable"},
)
OK = {"computable": True, "holds": True}
NO = {"computable": True, "holds": False}
R_NC = {"computable": False, "holds": False}


def test_same_conclusion_under_both_bounds():
    assert TB.decide_with_bounds(POS, NO, NO)["decision"] == "keep"
    assert TB.decide_with_bounds(NEG, OK, OK)["decision"] == "keep"
    assert TB.decide_with_bounds(NEG, NO, NO)["decision"] == "downgrade"


def test_flip_needs_mapping_for_union():
    """COST_lo 下 R2 成立、COST_hi 下不成立：结论翻转，对两种口径下实体集合的并集补映射（R2 是合并比率，共同成员的成本差也起作用）。"""
    d = TB.decide_with_bounds(
        NEG, OK, NO, members_lo={"a", "b", "c"}, members_hi={"b", "c", "d"}
    )
    assert d["decision"] == "needs_mapping"
    assert (d["keep_lo"], d["keep_hi"]) == ("keep", "downgrade")
    assert d["flip_entities"] == ["a", "b", "c", "d"]


def test_s3_positive_makes_bounds_irrelevant():
    assert TB.decide_with_bounds(POS, OK, NO)["decision"] == "keep"


def test_sampling_ladder():
    assert (
        TB.next_sampling_step(0.10, NC, R_NC) == 0.25
    )  # 两项都因人数不足不可计算 → 扩样
    assert TB.next_sampling_step(0.25, NEG, R_NC) == 0.50  # R2 人数不足 → 扩样
    assert TB.next_sampling_step(0.50, NC, NO) == 1.00
    assert TB.next_sampling_step(1.00, NC, R_NC) is None  # 已全量 → 按 §9.1 降级
    assert (
        TB.next_sampling_step(0.10, NEG, NO) is None
    )  # 都可计算、都不阳性 → 直接降级，不扩样
    assert TB.next_sampling_step(0.10, POS, R_NC) is None  # 已保持主线
