"""rule_window_infer 的手算预期值测试（10-06）。"""

import itertools
import math

import numpy as np

import rule_window_infer as R


def test_cr1_cr2_hand():
    # y = 1,2,3,10,4，簇 a={1,2}、b={3,10,4}；n=5，均值 4，残差 −3,−2,−1,6,0；簇和 a −5、b +5
    y = [1, 2, 3, 10, 4]
    g = ["a", "a", "b", "b", "b"]
    gi, G = R._groups(g)
    # CR1：G/(G−1)·Σs²/n² = 2·(25+25)/25 = 4 → 2
    assert abs(R.cr1_se(y, gi, G) - 2.0) < 1e-12
    # CR2：a 簇 −5/√(1−2/5)，b 簇 5/√(1−3/5)；(25/0.6 + 25/0.4)/25 = (41.667+62.5)/25 = 4.16667 → 2.041241
    assert abs(R.cr2_se(y, g) - math.sqrt((25 / 0.6 + 25 / 0.4) / 25)) < 1e-12


def test_wcr_pvalue_two_singletons_hand():
    # 两个单元素簇 y=(1,3)、μ0=0：t = (a+b)/|a−b| = 2；自助 t* = (w1·1 + w2·3)/|w1·1 − w2·3|
    # （簇大小为 1 时 CR1 的 se = |y1*−y2*|/2，均值 (y1*+y2*)/2）。穷举 36 种权重，手推闭式计数
    ge = 0
    for w1, w2 in itertools.product(R.WEBB, repeat=2):
        d = abs(w1 - 3 * w2)
        ts = (w1 + 3 * w2) / d if d > 0 else 0.0
        ge += ts >= 2 - 1e-12
    assert abs(R.wcr_pvalue([1, 3], ["a", "b"], 0.0) - (1 + ge) / 37) < 1e-12


def test_lower_bound_monotone_and_conservative():
    rng = np.random.default_rng(1)
    g = np.repeat(np.arange(12), 20)
    y = 0.02 + rng.normal(0, 0.1, 12)[g] + rng.normal(0, 0.2, len(g))
    p_lo = R.wcr_pvalue(y, g, -0.5, B=999)
    p_hi = R.wcr_pvalue(y, g, 0.5, B=999)
    assert p_lo < 0.05 and p_hi > 0.95  # μ0 远低于均值时拒绝，远高于时不拒绝
    lb = R.lower_bound(y, g, level=0.8, B=999)
    assert lb["conservative"] == min(lb["wcr"], lb["cr2"]) < float(np.mean(y))
