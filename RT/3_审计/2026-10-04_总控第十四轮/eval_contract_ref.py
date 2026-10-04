"""评价契约 v1 的参考实现与测试向量（总控 2026-10-04，供 GPT 数学核验）。

只用于核验契约里的公式与账本规则；不是项目代码，不读任何行情数据。
运行：python3 eval_contract_ref.py  —— 全部断言通过会打印 "ALL TESTS PASSED"。
依赖：numpy、scipy。
"""
import math

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import beta, binom

WAN = 10_000.0  # 1 万元


# ---------------------------------------------------------------- 1. 对数增长
def h(f, r):
    """单注对数回报 ln(1+f(r-1))。r 为含全部成本的回收倍数（>=0），0<=f<1。"""
    return math.log1p(f * (r - 1.0))


def g_empirical(f, R):
    """经验对数增长：同一分数 f 下各注 ln(1+f(R-1)) 的平均。"""
    R = np.asarray(R, dtype=float)
    return float(np.mean(np.log1p(f * (R - 1.0))))


def g_two_point(p, K, f):
    """二点分布（命中得 K 倍，否则归零）的对数增长。"""
    return p * h(f, K) + (1 - p) * h(f, 0.0)


# ---------------------------------------------------------------- 2. 台阶证书
def monotone_nonincreasing(L):
    """尾概率下界须随台阶不增；取从左到右的累积最小值（只会让下界更保守）。"""
    out, cur = [], 1.0
    for x in L:
        cur = min(cur, max(0.0, float(x)))
        out.append(cur)
    return out


def step_certificate(f, steps, L):
    """台阶证书：g(f) >= h(0) + Σ_j [h(r_j) - h(r_{j-1})] * L_j。

    steps: 0 = r_0 < r_1 < ... < r_J；L: 长度 J，L_j 是 P(R >= r_j) 的（同时有效）下界。
    成立条件：R >= 0；h 在 r 上单调增（f>0）；L_j 确为下界。
    """
    assert steps[0] == 0.0 and all(a < b for a, b in zip(steps, steps[1:]))
    assert len(L) == len(steps) - 1
    L = monotone_nonincreasing(L)
    val = h(f, steps[0])
    for j in range(1, len(steps)):
        val += (h(f, steps[j]) - h(f, steps[j - 1])) * L[j - 1]
    return val


def conservative_distribution(steps, L):
    """由台阶下界构造一个被真实分布随机占优的保守分布：P(R=r_j) = L_j - L_{j+1}，P(R=0) = 1 - L_1。"""
    L = monotone_nonincreasing(L) + [0.0]
    probs = [1.0 - L[0]] + [L[j] - L[j + 1] for j in range(len(L) - 1)]
    return list(steps), probs


def kelly_on_distribution(values, probs, f_max=0.999):
    """在离散分布上求使 E ln(1+f(R-1)) 最大的 f（f ∈ [0, f_max]）。返回 (f*, g*)。"""
    values = np.asarray(values, float)
    probs = np.asarray(probs, float)
    rmin = values[probs > 0].min()
    upper = f_max if rmin >= 1 else min(f_max, 0.999999 / (1.0 - rmin))

    def neg(f):
        return -float(np.sum(probs * np.log1p(f * (values - 1.0))))

    res = minimize_scalar(neg, bounds=(0.0, upper), method="bounded", options={"xatol": 1e-12})
    f_star = float(res.x)
    g_star = -neg(f_star)
    if g_star < 0:  # f=0 时 g=0，取最优不为负
        return 0.0, 0.0
    return f_star, g_star


# ---------------------------------------------------------------- 3. 置信下界
def cp_lower(k, n, alpha):
    """Clopper–Pearson 单侧下界（独立同分布伯努利）。"""
    return 0.0 if k == 0 else float(beta.ppf(alpha, k, n - k + 1))


def simultaneous_cp_lower(ks, n, alpha):
    """J 个台阶的同时下界（Bonferroni：每个 α/J）。"""
    J = len(ks)
    return [cp_lower(k, n, alpha / J) for k in ks]


def eb_lower(Y, a, u, alpha, M=1):
    """封顶对数回报的经验 Bernstein 单侧下界（Maurer–Pontil 2009 定理 4 应用于 (u-Y)/(u-a)）。

    Y 取值须在 [a, u]；M 为同时保护的固定政策数。成立条件：Y 独立同分布。
    L = mean(Y) - sqrt(2 s² ln(2M/α) / n) - 7 (u-a) ln(2M/α) / (3(n-1))
    """
    Y = np.asarray(Y, float)
    assert Y.min() >= a - 1e-12 and Y.max() <= u + 1e-12
    n = len(Y)
    lg = math.log(2 * M / alpha)
    s2 = float(np.var(Y, ddof=1))
    return float(Y.mean() - math.sqrt(2 * s2 * lg / n) - 7 * (u - a) * lg / (3 * (n - 1)))


def capped_log_returns(f, R, u):
    """Y = min(ln(1+f(R-1)), u)；下侧不截断，a = ln(1-f)。"""
    R = np.asarray(R, float)
    return np.minimum(np.log1p(f * (R - 1.0)), u), math.log1p(-f)


# ---------------------------------------------------------------- 4. 二点模型首达（核验用）
def first_passage_two_point(p, K, N, f, target=101.0, lower=0.1):
    """二点模型、固定分数 f、N 注内首次 W>=target 的概率（动态规划，GPT 附录 A 同法）。"""
    a, b = math.log1p(f * (K - 1)), math.log1p(-f)
    alive = np.ones(1)
    success = failed = 0.0
    for n in range(1, N + 1):
        nxt = np.zeros(n + 1)
        nxt[:-1] += alive * (1 - p)
        nxt[1:] += alive * p
        k = np.arange(n + 1)
        logw = k * a + (n - k) * b
        hi, lo = logw >= math.log(target), logw < math.log(lower)
        success += nxt[hi].sum()
        failed += nxt[lo].sum()
        nxt[hi | lo] = 0
        alive = nxt
    return success, failed


# ---------------------------------------------------------------- 5. 资金账本状态机
class Account:
    """背景.md 第 4、5 条＋总控 10-04 代定细则（契约 §1）的状态机。

    事件按时间顺序调用 mark(t_months, V)：V 为该时刻全部仓位按可执行清算价＋现金的价值（元）。
    规则：
      - 可清算价值低于最小票面 m_min 时按 0 计（尘埃核销）。
      - N = V + W - D（累计净收益）；W（取出）在成功前恒为 0。
      - 阶段 A（暂停前）：N <= -2 万 → 暂停（清仓、停止开仓）；V = 0 且 D = 1 万 → 投入第二笔 1 万。
      - 一年内（t <= 12）、D = 1 万、V >= 10 万 → 追加 2 万（一次）。
      - 累计入金上限 3 万。暂停后经批准恢复（resume）：若 D < 3 万，投入 1 万；进入阶段 B。
      - 任意阶段 N <= -3 万 → 永久停止。阶段 B 不再有暂停线。
      - t <= 36 且 N >= 100 万 → 成功（首次到达，按清算价值）。t > 36 → 期满。
    """

    def __init__(self, m_min=100.0):
        self.m_min = m_min
        self.D, self.W, self.V = 1 * WAN, 0.0, 1 * WAN
        self.phase = "A"
        self.state = "ACTIVE"
        self.bonus_used = False
        self.log = []

    @property
    def N(self):
        return self.V + self.W - self.D

    def _rec(self, t, what):
        self.log.append((t, what, self.D, round(self.V, 2), round(self.N, 2), self.state))

    def mark(self, t, V):
        if self.state in ("STOPPED", "SUCCESS", "EXPIRED"):
            return self.state
        if t > 36:
            self.state = "EXPIRED"
            self._rec(t, "expire")
            return self.state
        self.V = 0.0 if V < self.m_min else float(V)
        if self.state == "PAUSED":  # 暂停期间已清仓，价值不变
            return self.state
        if self.N >= 100 * WAN:
            self.state = "SUCCESS"
            self._rec(t, "success")
            return self.state
        if self.N <= -3 * WAN:
            self.state = "STOPPED"
            self._rec(t, "stop")
            return self.state
        if self.phase == "A" and self.N <= -2 * WAN:
            self.state = "PAUSED"  # 清仓：V 保留为现金
            self._rec(t, "pause")
            return self.state
        if not self.bonus_used and t <= 12 and self.D == 1 * WAN and self.V >= 10 * WAN:
            self.D += 2 * WAN
            self.V += 2 * WAN
            self.bonus_used = True
            self._rec(t, "bonus+2万")
        if self.phase == "A" and self.V == 0.0 and self.D == 1 * WAN:
            self.D += 1 * WAN
            self.V += 1 * WAN
            self._rec(t, "tranche2+1万")
        return self.state

    def resume(self, t):
        """暂停后批准恢复（契约 §1.4：暂停后 >=90 天且冻结策略在新前向模拟盘上通过确认）。"""
        assert self.state == "PAUSED"
        if self.D < 3 * WAN:
            add = min(1 * WAN, 3 * WAN - self.D)
            self.D += add
            self.V += add
        self.phase, self.state = "B", "ACTIVE"
        self._rec(t, "resume")


# ---------------------------------------------------------------- 6. 测试向量
def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def run_tests():
    out = {}

    # T1 二点分布对数增长（GPT 复算值 0.0026552903）
    t1 = g_two_point(0.10, 13.0, 0.0125)
    assert close(t1, 0.1 * math.log(1.15) + 0.9 * math.log(0.9875))
    assert abs(t1 - 0.0026552903) < 1e-9
    out["T1 g(p=0.1,K=13,f=0.0125)"] = t1

    # T2 Jensen：E[R] <= 1 时任意 0<f<1 都有 g <= 0
    rng = np.random.default_rng(7)
    for _ in range(200):
        R = rng.exponential(1.0, 50)
        R = R / R.mean() * rng.uniform(0.3, 1.0)  # 平均 <= 1
        f = rng.uniform(0.01, 0.9)
        assert g_empirical(f, R) <= 1e-12
    out["T2 Jensen 200 次随机反例检查"] = "通过"

    # T3 E[R]>1 但给定 f 时 g<0：p=0.01, K=150（E[R]=1.5），f=0.05
    t3 = g_two_point(0.01, 150.0, 0.05)
    assert t3 < 0
    out["T3 g(p=0.01,K=150,f=0.05)"] = t3

    # T4 有限期限反例（全仓）：p=1%,K=130 一中即达 101 倍 → 1%；p=30%,K=13/3 需连赢 4 注 → 0.3^4
    k30 = 1.3 / 0.30
    need = math.ceil(math.log(101) / math.log(k30))
    assert need == 4
    out["T4 全仓：p=1%,K=130 成功率"] = 0.01
    out["T4 全仓：p=30%,K=4.333 成功率"] = 0.30 ** need

    # T5 半 Kelly 二点首达（GPT 精确值：p=0.3、156 注 0.2868%；p=0.1、1092 注 16.2443%）
    def half_kelly(p, K):
        return (p - (1 - p) / (K - 1)) / 2

    s1, _ = first_passage_two_point(0.30, 1.3 / 0.30, 156, half_kelly(0.30, 1.3 / 0.30))
    s2, _ = first_passage_two_point(0.10, 13.0, 1092, half_kelly(0.10, 13.0))
    assert abs(s1 - 0.002868) < 5e-6 and abs(s2 - 0.162443) < 5e-6
    out["T5 首达 p=0.3,156 注"] = s1
    out["T5 首达 p=0.1,1092 注"] = s2
    # 半 Kelly、固定 pK 时每次命中账户增长 (pK-1)/2
    for p in (0.003, 0.02, 0.1, 0.3):
        K = 1.3 / p
        assert close(half_kelly(p, K) * (K - 1), 0.15)
    out["T5b 半Kelly且pK=1.3时每次命中增长"] = 0.15

    # T6 台阶证书
    steps = [0.0, 0.5, 1.0, 2.0, 4.0, 10.0, 100.0]
    L = [0.40, 0.25, 0.12, 0.05, 0.015, 0.002]
    f = 0.02
    cert = step_certificate(f, steps, L)
    vals, probs = conservative_distribution(steps, L)
    assert close(sum(probs), 1.0)
    direct = sum(pr * h(f, v) for v, pr in zip(vals, probs))
    assert close(cert, direct)  # 证书 = 保守分布下的精确对数增长
    out["T6 台阶证书 g_L(f=0.02)"] = cert
    # 证书是下界：任何满足 P(R>=r_j)>=L_j 的分布，其 g 都不小于证书
    for _ in range(500):
        extra = rng.uniform(0, 1, len(L))
        trueL = monotone_nonincreasing([min(1.0, l + e * (1 - l) * 0.3) for l, e in zip(L, extra)])
        v2, p2 = conservative_distribution(steps, trueL)
        # 在每个台阶区间内把质量放到区间内任意位置（不低于台阶左端）
        g_true = 0.0
        bounds = steps + [1000.0]
        for j, (v, pr) in enumerate(zip(v2, p2)):
            r = rng.uniform(bounds[j], bounds[j + 1])
            g_true += pr * h(f, r)
        assert g_true >= cert - 1e-12
    out["T6b 证书下界性 500 次随机检查"] = "通过"
    # 不单调的 L 会被改为累积最小值
    assert monotone_nonincreasing([0.3, 0.4, 0.1]) == [0.3, 0.3, 0.1]

    out["T6c 上例保守分布的期望回收"] = sum(v * pr for v, pr in zip(vals, probs))  # 0.815 <1，证书必为负

    # T7 保守 Kelly：负例（上面的 L）应得 f_c=0；正例尾部更厚
    f_c, g_c = kelly_on_distribution(vals, probs)
    assert f_c == 0.0 and g_c == 0.0
    L_pos = [0.40, 0.25, 0.12, 0.05, 0.02, 0.006]
    vals_p, probs_p = conservative_distribution(steps, L_pos)
    ER_p = sum(v * pr for v, pr in zip(vals_p, probs_p))
    f_c, g_c = kelly_on_distribution(vals_p, probs_p)
    assert f_c > 0 and g_c > 0
    assert close(step_certificate(f_c, steps, L_pos), g_c, 1e-7)
    g2 = sum(pr * h(2 * f_c, v) for v, pr in zip(vals_p, probs_p))
    out["T7 正例保守分布期望回收"] = ER_p
    out["T7 正例保守 Kelly f_c"] = f_c
    out["T7 正例 g*(f_c)"] = g_c
    out["T7 正例 g(0.5 f_c)"] = sum(pr * h(0.5 * f_c, v) for v, pr in zip(vals_p, probs_p))
    out["T7 正例 g(2 f_c)"] = g2

    # T8 Clopper–Pearson 与样本量（GPT：n=301, c=7, 一类 3.325%, 功效 80.009%）
    n, c = 301, 7
    size = binom.sf(c - 1, n, 0.01)
    power = binom.sf(c - 1, n, 0.03)
    assert abs(size - 0.03325) < 5e-5 and abs(power - 0.80009) < 5e-5
    out["T8 n=301,c=7 一类错误"] = size
    out["T8 n=301,c=7 功效"] = power
    out["T8 CP 下界 k=7,n=301,α=5%"] = cp_lower(7, 301, 0.05)
    out["T8 同时 CP 下界 ks=[120,36,9,2],n=301,α=5%"] = simultaneous_cp_lower([120, 36, 9, 2], 301, 0.05)

    # T9 经验 Bernstein：手算构造
    f = 0.02
    R = np.array([0.0] * 700 + [0.5] * 150 + [1.5] * 100 + [5.0] * 40 + [30.0] * 9 + [500.0] * 1)
    u = math.log1p(f * (20 - 1))  # 封顶在 R=20 对应的对数回报
    Y, a = capped_log_returns(f, R, u)
    lb = eb_lower(Y, a, u, alpha=0.05, M=3)
    assert lb <= Y.mean() <= g_empirical(f, R) + 1e-12
    out["T9 平均封顶对数回报"] = float(Y.mean())
    out["T9 未封顶经验 g"] = g_empirical(f, R)
    out["T9 经验 Bernstein 下界（M=3）"] = lb
    out["T9 该样本 E[R]（>1，但 f=0.02 时 g<0）"] = float(R.mean())
    # T9b 正例：较厚尾部、较小 f
    R2 = np.array([0.0] * 600 + [0.5] * 150 + [1.5] * 100 + [5.0] * 100 + [30.0] * 40 + [500.0] * 10)
    f2 = 0.01
    u2 = math.log1p(f2 * (50 - 1))
    Y2, a2 = capped_log_returns(f2, R2, u2)
    lb2 = eb_lower(Y2, a2, u2, alpha=0.05, M=3)
    assert lb2 <= Y2.mean() <= g_empirical(f2, R2) + 1e-12
    out["T9b 平均封顶对数回报"] = float(Y2.mean())
    out["T9b 经验 Bernstein 下界（M=3）"] = lb2

    # T10 资金账本状态机
    # S1 两笔亏完 → 暂停
    A = Account()
    A.mark(1, 3000)
    A.mark(2, 50)          # 低于最小票面 → 0 → 投第二笔
    assert A.D == 2 * WAN and A.V == 1 * WAN
    A.mark(4, 0)
    assert A.state == "PAUSED" and close(A.N, -2 * WAN)
    # S4 暂停后恢复 → 第三笔 → 亏完 → 永久停止
    A.resume(8)
    assert A.D == 3 * WAN and A.phase == "B"
    A.mark(9, 15_000)      # 阶段 B：N=-1.5 万，无暂停线
    assert A.state == "ACTIVE"
    A.mark(10, 0)
    assert A.state == "STOPPED" and close(A.N, -3 * WAN)
    out["T10 S1+S4 日志"] = A.log

    # S2 一年内到 10 万 → 追加 2 万；随后归零 → N=-3 万 → 永久停止
    B = Account()
    B.mark(6, 100_000)
    assert B.D == 3 * WAN and B.V == 120_000 and close(B.N, 9 * WAN)
    B.mark(9, 0)
    assert B.state == "STOPPED"
    # S3 第 13 个月才到 10 万 → 不追加
    C = Account()
    C.mark(13, 100_000)
    assert C.D == 1 * WAN and not C.bonus_used
    # S5 追加后回落到 N<=-2 万（V=1 万）→ 暂停；恢复时入金已达 3 万，不再投
    E = Account()
    E.mark(5, 100_000)
    E.mark(7, 10_000)
    assert E.state == "PAUSED" and close(E.N, -2 * WAN)
    E.resume(11)
    assert E.D == 3 * WAN and E.V == 10_000
    # S6 成功按清算价值首达；期满后不再判成功
    F = Account()
    F.mark(30, 1_010_000)
    assert F.state == "SUCCESS"
    G = Account()
    G.mark(37, 5_000_000)
    assert G.state == "EXPIRED"
    out["T10 账本六个情景"] = "通过"

    return out


if __name__ == "__main__":
    res = run_tests()
    for k, v in res.items():
        if isinstance(v, float):
            print(f"{k}: {v:.10g}")
        else:
            print(f"{k}: {v}")
    print("ALL TESTS PASSED")
