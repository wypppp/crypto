#!/usr/bin/env python3
"""DQ-37 规则窗口的推断方法：参考实现（10-06；总控第十八轮第二节与 C4、第十九轮第四节；随批 1b 交 GPT）。

对象：每笔的结果 y_i（例如冻结 f 下的每注对数增长），按周聚类 g(i)。单侧检验 H0: μ ≤ μ0。
- 主方法：施加零假设的 wild cluster bootstrap-t（WCR），Webb 六点权重，t 统计量用 CR1 方差；
  6^G 不超过 B 时穷举全部权重组合，否则固定种子抽 B 次（默认 9,999）。下界由检验反演求得（对 μ0 二分）。
- 交叉核对：CR2（Bell–McCaffrey）方差，临界值取 t(G−1)。
- 报两者，取较保守（较低）的下界。只对均值（只有截距的回归）实现；有协变量时另写。
"""

import itertools
import math

import numpy as np
from scipy import stats

WEBB = np.array(
    [-math.sqrt(1.5), -1.0, -math.sqrt(0.5), math.sqrt(0.5), 1.0, math.sqrt(1.5)]
)


def _groups(groups):
    labels = sorted(set(groups))
    idx = {g: k for k, g in enumerate(labels)}
    return np.array([idx[g] for g in groups]), len(labels)


def cr1_se(y, gi, G):
    y = np.asarray(y, float)
    n = len(y)
    s = np.bincount(gi, weights=y - y.mean(), minlength=G)
    return math.sqrt(G / (G - 1) * float((s**2).sum()) / n**2)


def cr2_se(y, groups):
    """只有截距时的 CR2：每簇残差和除以 sqrt(1 − n_g/n)。"""
    y = np.asarray(y, float)
    gi, G = _groups(groups)
    n = len(y)
    s = np.bincount(gi, weights=y - y.mean(), minlength=G)
    ng = np.bincount(gi, minlength=G)
    return math.sqrt(float(((s / np.sqrt(1 - ng / n)) ** 2).sum()) / n**2)


def wcr_pvalue(y, groups, mu0, B=9999, seed=20261006):
    """单侧 p 值：H0 μ ≤ μ0 对 H1 μ > μ0。p = (1 + #{t* ≥ t}) / (1 + 次数)。"""
    y = np.asarray(y, float)
    gi, G = _groups(groups)
    if G < 2:
        raise ValueError("至少要 2 个簇")
    t = (y.mean() - mu0) / cr1_se(y, gi, G)
    u = y - mu0
    if 6**G <= B:
        ws = (np.array(w) for w in itertools.product(WEBB, repeat=G))
        total = 6**G
    else:
        rng = np.random.default_rng(seed)
        ws = (WEBB[rng.integers(0, 6, G)] for _ in range(B))
        total = B
    ge = 0
    for w in ws:
        ys = mu0 + w[gi] * u
        se = cr1_se(ys, gi, G)
        ts = (ys.mean() - mu0) / se if se > 0 else 0.0
        ge += ts >= t - 1e-12
    return (1 + ge) / (1 + total)


def wcr_lower(y, groups, level=0.8, B=9999, seed=20261006, tol=1e-6):
    """检验反演的单侧下界：p(μ0) 随 μ0 增大而增大，求 p(μ0) = 1 − level 的 μ0（二分）。"""
    y = np.asarray(y, float)
    alpha = 1 - level
    span = (y.max() - y.min()) or 1.0
    lo, hi = y.min() - span, y.mean()
    for _ in range(200):
        if hi - lo < tol:
            break
        mid = (lo + hi) / 2
        if wcr_pvalue(y, groups, mid, B, seed) <= alpha:
            lo = mid
        else:
            hi = mid
    return lo


def cr2_lower(y, groups, level=0.8):
    _, G = _groups(groups)
    return float(np.mean(y)) - stats.t.ppf(level, G - 1) * cr2_se(y, groups)


def lower_bound(y, groups, level=0.8, B=9999, seed=20261006):
    a = wcr_lower(y, groups, level, B, seed)
    b = cr2_lower(y, groups, level)
    return {"wcr": a, "cr2": b, "conservative": min(a, b)}
