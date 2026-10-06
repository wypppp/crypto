#!/usr/bin/env python3
"""DQ-37 规则窗口的推断方法：参考实现（10-06 v2；按 GPT 批 1b B 与总控第二十一轮第四节 B 修改）。

对象：每个事件的结果 y＝log(1＋f(R−1))（f 在开发期冻结；用 R，不用 Z）；同起同止的并发仓位合并成
log(1＋Σf_j(R_j−1))（concurrent_log_growth）。簇＝多周块（block_ids；块长在开发期按自相关长度定，choose_block_len）。
单侧检验 H0: μ ≤ μ0。
- 主方法：施加零假设的 wild cluster bootstrap-t（WCR），Webb 六点权重，t 统计量用 CR1 方差。
  6^G 不超过 B 时穷举全部权重组合，否则固定种子抽 B 次。只有截距时统计量只依赖各簇残差和，按簇向量化计算。
- 下界用网格反演：在网格上逐点算 p(μ0)，接受集合＝{μ0: p > α}，下界取接受集合的最小网格点。
  p 不保证单调（GPT 三簇反例：穷举时 p 离散，在 α 附近来回跳），所以不用二分。
  检查三件事：零方差、网格下端仍被接受（端点）、接受集合不连续（非单调，只标记）。前两种记“未判定”。
- 交叉核对：CR2（Bell–McCaffrey）方差，临界值取 t(df_BM)，df_BM 为 Satterthwaite 型自由度；另报有效簇数。
- 两者都报；任何一个未判定，结论未判定；否则取较低的下界。
"""

import itertools
import math

import numpy as np
from scipy import stats

WEBB = np.array(
    [-math.sqrt(1.5), -1.0, -math.sqrt(0.5), math.sqrt(0.5), 1.0, math.sqrt(1.5)]
)


# ---------------------------------------------------------------- 统计量与簇
def concurrent_log_growth(events, f):
    """events: [(start, end, R)]。同起同止的仓位合成一个观测 log(1＋Σ f(R_j−1))；返回 [(start, end, y)]（按起止排序）。"""
    acc = {}
    for s, e, r in events:
        acc[(s, e)] = acc.get((s, e), 0.0) + f * (float(r) - 1.0)
    out = []
    for (s, e), x in sorted(acc.items()):
        if 1.0 + x <= 0:
            raise ValueError("并发仓位合计亏损超过本金：%s～%s" % (s, e))
        out.append((s, e, math.log1p(x)))
    return out


def block_ids(week_index, L):
    """周序号（0 起的整数）→ 块号＝⌊周序号/L⌋。"""
    if L < 1:
        raise ValueError("块长至少 1 周")
    return [int(w) // int(L) for w in week_index]


def choose_block_len(weekly_values, max_len=8):
    """开发期用：周均值序列的自相关，在 1～max_len 阶里，|ρ_k| ≥ 2/√n 的最大阶 k，块长取 k＋1（没有就取 1）。"""
    x = np.asarray(weekly_values, float)
    n = len(x)
    x = x - x.mean()
    d = float((x * x).sum())
    if n < 3 or d == 0:
        return 1
    band = 2.0 / math.sqrt(n)
    last = 0
    for k in range(1, min(max_len, n - 1) + 1):
        if abs(float((x[:-k] * x[k:]).sum()) / d) >= band:
            last = k
    return last + 1


# ---------------------------------------------------------------- 方差
def _groups(groups):
    labels = sorted(set(groups))
    idx = {g: k for k, g in enumerate(labels)}
    return np.array([idx[g] for g in groups]), len(labels)


def _cluster_sums(y, gi, G):
    y = np.asarray(y, float)
    return np.bincount(gi, weights=y, minlength=G), np.bincount(gi, minlength=G).astype(
        float
    )


def cr1_se(y, gi, G):
    y = np.asarray(y, float)
    n = len(y)
    s = np.bincount(gi, weights=y - y.mean(), minlength=G)
    return math.sqrt(G / (G - 1) * float((s**2).sum()) / n**2)


def cr2_se(y, groups):
    """只有截距时的 CR2：每簇残差和除以 √(1 − n_g/n)。"""
    y = np.asarray(y, float)
    gi, G = _groups(groups)
    n = len(y)
    s = np.bincount(gi, weights=y - y.mean(), minlength=G)
    ng = np.bincount(gi, minlength=G)
    return math.sqrt(float(((s / np.sqrt(1 - ng / n)) ** 2).sum()) / n**2)


def bm_df(groups):
    """Bell–McCaffrey（Imbens–Kolesár 2016）自由度，只有截距、同方差工作模型：
    G 矩阵第 g 列＝c_g·(1_g − (n_g/n)·1)，c_g＝1/(n√(1−n_g/n))；df＝(tr G'G)² / tr((G'G)²)。等大的簇时 df＝G−1。"""
    gi, G = _groups(groups)
    ng = np.bincount(gi, minlength=G).astype(float)
    n = ng.sum()
    c = 1.0 / (n * np.sqrt(1 - ng / n))
    M = np.outer(c, c) * (np.diag(ng) - np.outer(ng, ng) / n)
    return float(np.trace(M) ** 2 / np.trace(M @ M))


def effective_clusters(groups):
    """规模异质下的有效簇数（Carter–Schnepel–Steigerwald 2017，取簇内相关 ρ＝1 的保守情形）：G /(1＋CV²(n_g))。"""
    gi, G = _groups(groups)
    ng = np.bincount(gi, minlength=G).astype(float)
    return float(G / (1.0 + ng.var() / ng.mean() ** 2))


# ---------------------------------------------------------------- WCR
def _zero_var(se, mean):
    """零方差：标准误小于均值量级的 1e-12（残差只有浮点噪声）。"""
    return se <= 1e-12 * (1.0 + abs(mean))


def _weights(G, B, seed):
    if 6**G <= B:
        return np.array(list(itertools.product(WEBB, repeat=G)))
    rng = np.random.default_rng(seed)
    return WEBB[rng.integers(0, 6, (B, G))]


def _p_values(A, ng, mus, W):
    """按簇向量化：A＝各簇 y 之和，ng＝各簇大小；对每个 μ0 返回单侧 p＝(1＋#{t*≥t})/(1＋次数)。"""
    G, n = len(A), ng.sum()
    mean = A.sum() / n
    s_obs = A - ng * mean
    se_obs = math.sqrt(G / (G - 1) * float((s_obs**2).sum())) / n
    if _zero_var(se_obs, mean):
        return np.full(len(mus), np.nan)  # 零方差：p 值无定义
    out = []
    for mu in mus:
        S = A - ng * mu  # 施加零假设后的各簇残差和
        t = (mean - mu) / se_obs
        sums = W @ S
        m = sums / n
        c = W * S[None, :] - m[:, None] * ng[None, :]
        se = np.sqrt(G / (G - 1) * (c * c).sum(1)) / n
        ts = np.divide(m, se, out=np.zeros_like(m), where=se > 0)
        out.append((1 + int((ts >= t - 1e-12).sum())) / (1 + len(W)))
    return np.array(out)


def wcr_pvalue(y, groups, mu0, B=9999, seed=20261006):
    """单侧 p 值：H0 μ ≤ μ0 对 H1 μ > μ0。"""
    gi, G = _groups(groups)
    if G < 2:
        raise ValueError("至少要 2 个簇")
    A, ng = _cluster_sums(y, gi, G)
    return float(_p_values(A, ng, [mu0], _weights(G, B, seed))[0])


def wcr_lower(y, groups, level=0.8, B=9999, seed=20261006, n_grid=801, span_se=20.0):
    """网格反演的单侧下界。返回 dict：lower（未判定时为 None）、status（ok／undetermined）、reasons、nonmonotone、
    grid＝(起点, 终点, 点数)。网格从 ȳ − span_se·se_CR1 到 ȳ，等距 n_grid 点；下界取接受集合的最小网格点。"""
    y = np.asarray(y, float)
    gi, G = _groups(groups)
    if G < 2:
        raise ValueError("至少要 2 个簇")
    A, ng = _cluster_sums(y, gi, G)
    mean = float(y.mean())
    se = cr1_se(y, gi, G)
    res = {"lower": None, "status": "undetermined", "reasons": [], "nonmonotone": False}
    if _zero_var(se, mean):
        res["reasons"].append("零方差")
        return res
    mus = np.linspace(mean - span_se * se, mean, n_grid)
    res["grid"] = (float(mus[0]), float(mus[-1]), int(n_grid))
    p = _p_values(A, ng, mus, _weights(G, B, seed))
    acc = p > 1 - level
    if not acc.any():
        res["reasons"].append("网格上没有被接受的点")
        return res
    if acc[0]:
        res["reasons"].append("网格下端仍被接受（端点）")
        return res
    first = int(np.argmax(acc))
    res["nonmonotone"] = bool((~acc[first:]).any())
    res["lower"] = float(mus[first])
    res["status"] = "ok"
    return res


def cr2_lower(y, groups, level=0.8):
    """CR2 方差、t(df_BM) 临界值的单侧下界；另返回 df_BM 与有效簇数。"""
    y = np.asarray(y, float)
    se = cr2_se(y, groups)
    df = bm_df(groups)
    out = {
        "df_bm": df,
        "g_eff": effective_clusters(groups),
        "lower": None,
        "status": "undetermined",
    }
    if _zero_var(se, float(y.mean())):
        out["reasons"] = ["零方差"]
        return out
    out["lower"] = float(y.mean()) - float(stats.t.ppf(level, df)) * se
    out["status"] = "ok"
    return out


def lower_bound(y, groups, level=0.8, B=9999, seed=20261006):
    a = wcr_lower(y, groups, level, B, seed)
    b = cr2_lower(y, groups, level)
    ok = a["status"] == "ok" and b["status"] == "ok"
    return {
        "wcr": a,
        "cr2": b,
        "status": "ok" if ok else "undetermined",
        "conservative": min(a["lower"], b["lower"]) if ok else None,
    }
