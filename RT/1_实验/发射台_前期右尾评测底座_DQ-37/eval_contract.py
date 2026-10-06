#!/usr/bin/env python3
"""评价契约 v1.1 的项目实现（10-05；总控第十七轮采纳 GPT 批 0 B；总控第十九轮第五节第 2 条“评价器移植”）。

由 3_审计/2026-10-04_总控第十四轮/eval_contract_ref.py（v1 参考实现，供数学核验）移植，按 v1.1 改：
- 账本三种价值（总控第十七轮第三节第 3 条）：
    可执行清算价值 liq＝现金＋可交易仓位按可执行清算价（判定成功、盈利追加）；
    风险估值 v_loss＝liq＋锁定资产按三类计价＋未到账退款按退款额（判定亏完、暂停线、停止线）；
    可用现金 cash（开仓）。
- 锁定资产三类：未上市按成本、自认购截止日起 180 天仍未上市记 0；已上市且在约定归属期内按 min(成本, 合格市价×0.7)，
  没有合格市价按成本；逾期未解锁（过了约定解锁日）记 0。起算日不随项目延期重置；项目取消或失败记 0。
  合格市价＝过去 24 小时成交额 ≥ 我方该资产估值的 10 倍。30% 折扣是政策选择，不是真实价值下界。
- 退款：到账前不计入可执行清算价值，风险估值按退款额计；到账是资产转换（现金增加，累计入金 D 不变）。
- 资金耗尽暂停：v_loss < m_min 且没有下一笔可投 → 暂停，保留真实现金与 N（GPT 尘埃卡死反例）。
- 暂停期间：清掉可交易仓位、禁止开仓；锁定资产照常跟踪；停止线照常有效（GPT“暂停中减记触发停止”反例）。
- 永久停止后：继续记账，不自动恢复。
- resume()：状态机内校验暂停 ≥90 天、确认凭证、36 个月期限（GPT“resume 绕过”反例），并记录暂停起点。
  10-06 第二十二轮（GPT 整改复核 A）：凭证只收可信确认记录（ConfirmationRegistry）的编号，核卡片、通道、通过结论、
  暂停后时段；仓位与认购的编号由账本计数器分配，单调递增、永不复用，资产名只作标签。
- 统计：台阶下界 P4（0≤L_j≤1、同时有效、L_{J+1}＝0、从右往左取累积最大）；P6（台阶证书对任意 f 成立；经验 Bernstein
  的 f 网格须在开发期冻结）；P12 的准确表述（只排除保守分布下 g≤0 的下注，不保证不超过 Kelly，也不控制有限期大亏）。
- 需求曲线：改称“指定二点模型、指定下注规则下的需求曲线”，在网格上计算并检查单调（GPT 批 0 A8）。
时间单位：天（一年 365 天；36 个月按 1,095 天）。金额单位：元。实现之前契约不得用于正式判定（总控第十七轮）；本文件即实现，
交 GPT 批 1b 复核之前仍只作开发用。
"""

import math
from collections import namedtuple

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import beta

WAN = 10_000.0
YEAR = 365
HORIZON = 3 * YEAR
PAUSE_MIN_DAYS = 90
LOCK_UNLISTED_DAYS = 180
HAIRCUT = 0.7
QUALIFIED_VOLUME_MULT = 10.0


# ---------------------------------------------------------------- 1. 对数增长与台阶证书（P4、P6）
def h(f, r):
    """单注对数回报 ln(1+f(r-1))；r 为含全部成本的回收倍数（≥0），0≤f<1。"""
    return math.log1p(f * (r - 1.0))


def clean_lower_bounds(L):
    """P4：台阶尾概率下界的规范化。先夹到 [0,1]；再从右往左取累积最大——
    因为 P(R≥r_j) ≥ P(R≥r_k)（j<k），max_{k≥j} L_k 仍是 P(R≥r_j) 的有效下界，且不比原值保守。"""
    L = [min(1.0, max(0.0, float(x))) for x in L]
    out, cur = [0.0] * len(L), 0.0
    for j in range(len(L) - 1, -1, -1):
        cur = max(cur, L[j])
        out[j] = cur
    return out


def step_certificate(f, steps, L):
    """台阶证书：g(f) ≥ h(f,0)＋Σ_j [h(f,r_j)−h(f,r_{j−1})]·L_j（对任意 0≤f<1 成立，P6）。
    steps: 0＝r_0＜r_1＜…＜r_J；L：长度 J，L_j 为 P(R≥r_j) 的同时有效下界；L_{J+1}＝0。"""
    assert steps[0] == 0.0 and all(a < b for a, b in zip(steps, steps[1:]))
    assert len(L) == len(steps) - 1
    L = clean_lower_bounds(L)
    val = h(f, steps[0])
    for j in range(1, len(steps)):
        val += (h(f, steps[j]) - h(f, steps[j - 1])) * L[j - 1]
    return val


def conservative_distribution(steps, L):
    """被真实分布一阶随机占优的保守分布：P(R＝r_j)＝L_j−L_{j+1}（L_{J+1}＝0），P(R＝0)＝1−L_1。"""
    L = clean_lower_bounds(L) + [0.0]
    probs = [1.0 - L[0]] + [L[j] - L[j + 1] for j in range(len(L) - 1)]
    return list(steps), probs


def kelly_on_distribution(values, probs, f_max=0.999):
    """离散分布上使 E ln(1+f(R−1)) 最大的 f∈[0,f_max]，返回 (f*, g*)；最优为负时取 f＝0。
    P12：用保守分布的 f_c 及 2f_c 政策上限，只排除“保守分布下 g≤0”的下注，不保证不超过 Kelly，也不控制有限期大亏。"""
    values = np.asarray(values, float)
    probs = np.asarray(probs, float)
    if float(np.sum(probs * values)) <= 1.0 + 1e-12:
        return (
            0.0,
            0.0,
        )  # 期望回收 ≤1（含确定回收 1 倍）时不下注（GPT 批 1b A：原实现确定回收 1 倍时返回约 99.9%）
    rmin = values[probs > 0].min()
    upper = f_max if rmin >= 1 else min(f_max, 0.999999 / (1.0 - rmin))

    def neg(f):
        return -float(np.sum(probs * np.log1p(f * (values - 1.0))))

    res = minimize_scalar(
        neg, bounds=(0.0, upper), method="bounded", options={"xatol": 1e-12}
    )
    f_star, g_star = float(res.x), -neg(float(res.x))
    return (0.0, 0.0) if g_star < 0 else (f_star, g_star)


def cp_lower(k, n, alpha):
    """Clopper–Pearson 单侧下界（独立同分布伯努利）。"""
    return 0.0 if k == 0 else float(beta.ppf(alpha, k, n - k + 1))


def eb_lower(Y, a, u, alpha, M):
    """封顶对数回报的经验 Bernstein 单侧下界（Maurer–Pontil 2009 定理 4）。M＝开发期冻结的 f 网格大小（P6）。"""
    Y = np.asarray(Y, float)
    assert Y.min() >= a - 1e-12 and Y.max() <= u + 1e-12
    n = len(Y)
    lg = math.log(2 * M / alpha)
    s2 = float(np.var(Y, ddof=1))
    return float(
        Y.mean() - math.sqrt(2 * s2 * lg / n) - 7 * (u - a) * lg / (3 * (n - 1))
    )


# ---------------------------------------------------------------- 2. 二点模型首达与需求曲线（A8）
def first_passage_two_point(p, K, N, f, target=101.0, lower=0.1):
    """二点模型（命中得 K 倍，否则归零）、固定分数 f、N 注内首次财富 ≥ target 的概率与跌破 lower 的概率（动态规划）。"""
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


def half_kelly(p, K):
    return max(0.0, (p - (1 - p) / (K - 1)) / 2)


def demand_curve(p_grid, N, target_prob, K_grid, target=101.0):
    """指定二点模型、指定下注规则（半 Kelly）下的需求曲线：对每个命中率 p，在 K 网格上找首达概率 ≥ target_prob 的最小 K。
    返回 [(p, K_min 或 None)]，并检查单调：p 越大，所需 K 不应更大（网格上逐点比较，违反即抛错）。"""
    out = []
    for p in p_grid:
        k_min = None
        for K in K_grid:
            f = half_kelly(p, K)
            if f <= 0:
                continue
            if first_passage_two_point(p, K, N, f, target)[0] >= target_prob:
                k_min = K
                break
        out.append((p, k_min))
    ks = [k for _, k in out if k is not None]
    if any(b > a for a, b in zip(ks, ks[1:])):
        raise ValueError("需求曲线在网格上不单调：%s" % out)
    return out


# ---------------------------------------------------------------- 3. 资金账本（契约 v1.1）
class LockedAsset:
    """锁定资产：认购后不能卖。sub_deadline＝认购截止日（起算日，不随项目延期重置）；
    listed_day＝上市日（None＝未上市）；vest_end＝我方额度约定解锁日；状态 cancelled／failed 记 0；
    refund＝退款请求额（到账前风险估值按此计）。"""

    def __init__(self, cost, sub_deadline, vest_end=None):
        self.cost, self.sub_deadline, self.vest_end = (
            float(cost),
            sub_deadline,
            vest_end,
        )
        self.listed_day = None
        self.price_value = None  # 我方额度按市价的价值
        self.volume_24h = 0.0
        self.dead = False
        self.refund = None

    def qualified(self):
        return (
            self.price_value is not None
            and self.volume_24h >= QUALIFIED_VOLUME_MULT * self.price_value
        )

    def value_loss(self, t):
        if self.refund is not None:
            return self.refund
        if self.dead:
            return 0.0
        if self.listed_day is None:
            return 0.0 if t - self.sub_deadline > LOCK_UNLISTED_DAYS else self.cost
        if self.vest_end is not None and t > self.vest_end:
            return 0.0  # 逾期未解锁
        return (
            min(self.cost, HAIRCUT * self.price_value)
            if self.qualified()
            else self.cost
        )


CHANNELS = ("C2", "C3")
ConfirmationRecord = namedtuple(
    "ConfirmationRecord", "card_sha channel passed data_start data_end"
)


class ConfirmationRegistry:
    """可信的确认结果记录（10-06 第二十二轮，GPT 整改复核 A）。由确认评分流程写入，账本只按编号读取。
    每条记录绑定冻结卡片的哈希、通道（C2 或 C3）、通过结论、确认所用数据的时段。账本不重算统计检验。"""

    def __init__(self):
        self._recs = {}
        self._seq = 0

    def record(self, card_sha, channel, passed, data_start, data_end):
        """写入一条确认结果，返回编号。字段不合规即拒绝。"""
        if channel not in CHANNELS:
            raise ValueError("确认通道只能是 C2 或 C3：%r" % (channel,))
        if not isinstance(passed, bool):
            raise ValueError("通过结论必须是布尔值：%r" % (passed,))
        if not data_start < data_end:
            raise ValueError("确认数据时段为空")
        self._seq += 1
        self._recs[self._seq] = ConfirmationRecord(
            card_sha, channel, passed, data_start, data_end
        )
        return self._seq

    def get(self, rid):
        if rid not in self._recs:
            raise KeyError("未知确认记录 %r" % (rid,))
        return self._recs[rid]


class Ledger:
    """背景.md 第 4、5 条＋契约 v1.1 的状态机。事件按时间顺序调用；mark(t) 在每次估值后判定状态。
    card_sha：本账本所跑政策的冻结卡片哈希；channel：该卡预先写定的确认通道；
    confirmations：可信确认结果记录（恢复时只从这里按编号读取）。"""

    def __init__(self, m_min=100.0, card_sha="dev", channel="C2", confirmations=None):
        if channel not in CHANNELS:
            raise ValueError("确认通道只能是 C2 或 C3：%r" % (channel,))
        self.m_min = m_min
        self.card_sha, self.channel = card_sha, channel
        self.confirmations = confirmations
        self._seq = 0  # 编号计数器：单调递增、永不复用，与资产名无关（第二十二轮）
        self.labels = {}  # 编号 → 资产名（只作标签）
        self.D, self.W, self.cash = WAN, 0.0, WAN
        self.pos = {}  # 可交易仓位：编号 → 可执行清算价值
        self.locked = {}  # 编号 → LockedAsset
        self.phase, self.state = "A", "ACTIVE"
        self.bonus_used = False
        self.pause_start = None
        self.log = []

    # 三种价值
    def liq(self):
        return self.cash + sum(self.pos.values())

    def v_loss(self, t):
        return self.liq() + sum(a.value_loss(t) for a in self.locked.values())

    def n_liq(self):
        return self.liq() + self.W - self.D

    def n_loss(self, t):
        return self.v_loss(t) + self.W - self.D

    def _rec(self, t, what):
        self.log.append(
            (t, what, self.D, round(self.cash, 2), round(self.v_loss(t), 2), self.state)
        )

    # 交易与资产事件（10-06 按 GPT 批 1b A 改：唯一编号；先校验、后改账，任何一步失败都不留下半截状态）
    def _new_id(self, name):
        """账本计数器分配编号：整数，单调递增，永不复用。资产名只记作标签，可以重复
        （第二十二轮：按名字加 #k 的旧做法会被 x、x#2、x 的顺序撞号）。"""
        self._seq += 1
        self.labels[self._seq] = name
        return self._seq

    @staticmethod
    def _amount(x, what):
        x = float(x)
        if not math.isfinite(x) or x < 0:
            raise ValueError("%s 必须是非负有限数：%r" % (what, x))
        return x

    def _pos_id(self, pid):
        if pid not in self.pos:
            raise KeyError("未知仓位 %r" % pid)
        return pid

    def _lock_id(self, lid):
        if lid not in self.locked:
            raise KeyError("未知锁定资产 %r" % lid)
        return lid

    def open(self, name, amount):
        """开仓，返回仓位编号。"""
        amount = self._amount(amount, "开仓金额")
        if self.state != "ACTIVE":
            raise RuntimeError("非活跃状态禁止开仓（%s）" % self.state)
        if amount > self.cash + 1e-9:
            raise RuntimeError("现金不足")
        pid = self._new_id(name)
        self.cash -= amount
        self.pos[pid] = amount
        return pid

    def set_value(self, pid, value):
        value = self._amount(value, "仓位估值")
        self.pos[self._pos_id(pid)] = value

    def close(self, pid):
        self.cash += self.pos.pop(self._pos_id(pid))

    def subscribe(self, name, cost, sub_deadline, vest_end=None):
        """认购锁定资产，返回编号。"""
        cost = self._amount(cost, "认购额")
        if self.state != "ACTIVE":
            raise RuntimeError("非活跃状态禁止认购（%s）" % self.state)
        if cost > self.cash + 1e-9:
            raise RuntimeError("现金不足")
        lid = self._new_id(name)
        self.cash -= cost
        self.locked[lid] = LockedAsset(cost, sub_deadline, vest_end)
        return lid

    def list_asset(self, lid, day, price_value, volume_24h):
        a = self.locked[self._lock_id(lid)]
        pv = self._amount(price_value, "市价估值")
        vol = self._amount(volume_24h, "24 小时成交额")
        a.listed_day, a.price_value, a.volume_24h = day, pv, vol

    def fail_asset(self, lid):
        self.locked[self._lock_id(lid)].dead = True

    def unlock(self, lid, liq_value):
        """解锁：按当时的可执行清算价值计，从锁定里删除，不重复计。
        活跃时转为可交易仓位；暂停或停止时直接转为现金（暂停期间不持有可交易仓位，GPT 批 1b A）。"""
        self._lock_id(lid)
        v = self._amount(liq_value, "解锁清算价值")
        del self.locked[lid]
        if self.state == "ACTIVE":
            self.pos[lid] = v
        else:
            self.cash += v
        return lid

    def request_refund(self, lid, amount):
        amount = self._amount(amount, "退款额")
        self.locked[self._lock_id(lid)].refund = amount

    def refund_arrives(self, lid):
        """退款到账：资产转换，现金增加，D 不变。必须先有退款申请；校验通过后才改账。"""
        a = self.locked[self._lock_id(lid)]
        if a.refund is None:
            raise RuntimeError("没有退款申请，不能到账：%r" % lid)
        del self.locked[lid]
        self.cash += a.refund

    # 状态判定
    def mark(self, t):
        if self.state in ("SUCCESS", "EXPIRED"):
            return self.state
        if (
            self.state == "STOPPED"
        ):  # 永久停止：继续记账，不自动恢复，也不被期限检查改成期满（GPT 批 1b A）
            self._rec(t, "book")
            return self.state
        if t > HORIZON:
            self.state = "EXPIRED"
            self._rec(t, "expire")
            return self.state
        if (
            self.n_liq() >= 100 * WAN
        ):  # 成功按可执行清算价值；暂停中锁定资产解锁升值也算
            self.state = "SUCCESS"
            self._rec(t, "success")
            return self.state
        if self.n_loss(t) <= -3 * WAN:  # 停止线：任何阶段、包括暂停中
            self.state = "STOPPED"
            self._rec(t, "stop")
            return self.state
        if self.state == "PAUSED":
            return self.state
        if self.phase == "A" and self.n_loss(t) <= -2 * WAN:
            self._pause(t, "pause_line")
            return self.state
        if (
            not self.bonus_used
            and t <= YEAR
            and self.D == WAN
            and self.liq() >= 10 * WAN
        ):
            self.D += 2 * WAN
            self.cash += 2 * WAN
            self.bonus_used = True
            self._rec(t, "bonus+2万")
        if self.v_loss(t) < self.m_min:
            if self.phase == "A" and self.D == WAN:
                self.D += WAN
                self.cash += WAN
                self._rec(t, "tranche2+1万")
            else:
                self._pause(t, "funds_exhausted")
        return self.state

    def _pause(self, t, why):
        for k in list(self.pos):
            self.close(k)  # 清掉可交易仓位；锁定资产照常跟踪
        self.state, self.pause_start = "PAUSED", t
        self._rec(t, "pause:" + why)

    def resume(self, t, record_id):
        """暂停后恢复：先按 t 重估（mark），触及停止线即永久停止、不能恢复；再在状态机内校验，任一不满足就拒绝。
        record_id 是可信确认结果记录的编号（第二十二轮：调用方临时构造的凭证一律不收）。记录须满足：
        卡片哈希＝本账本的卡片；通道＝该卡写定的通道；结论为通过；数据时段在暂停之后、恢复之前。"""
        if self.state != "PAUSED":
            raise RuntimeError("只有暂停状态可以恢复（%s）" % self.state)
        self.mark(t)  # 重估：锁定资产逾期归零等会在这里触发停止线
        if self.state != "PAUSED":
            raise RuntimeError("重估后状态为 %s，不能恢复" % self.state)
        if t - self.pause_start < PAUSE_MIN_DAYS:
            raise RuntimeError("暂停不足 %d 天" % PAUSE_MIN_DAYS)
        if self.confirmations is None or isinstance(record_id, bool):
            raise RuntimeError("缺可信确认记录")
        try:
            rec = self.confirmations.get(record_id)
        except (KeyError, TypeError):
            raise RuntimeError("确认记录 %r 不在可信记录里" % (record_id,))
        if rec.card_sha != self.card_sha:
            raise RuntimeError("确认记录的卡片与账本不一致")
        if rec.channel != self.channel:
            raise RuntimeError("确认记录的通道与卡片写定的通道不一致")
        if rec.passed is not True:
            raise RuntimeError("确认结论不是通过")
        if not (self.pause_start <= rec.data_start < rec.data_end <= t):
            raise RuntimeError("确认数据时段须在暂停之后、恢复之前")
        if t > HORIZON:
            raise RuntimeError("已过 36 个月期限")
        if self.D < 3 * WAN:
            add = min(WAN, 3 * WAN - self.D)
            self.D += add
            self.cash += add
        self.phase, self.state = "B", "ACTIVE"
        self._rec(t, "resume")


def min_ticket_ok(
    stake, m_min, cash, single_cap, cluster_used, cluster_cap, total_used, total_cap
):
    """最小票面：把下注额升到 m_min 后，须同时满足现金、单仓、同簇、总敞口的上限；升票后按实际 R(q) 重新评价（调用方负责）。"""
    q = max(stake, m_min)
    return (
        q <= cash
        and q <= single_cap
        and cluster_used + q <= cluster_cap
        and total_used + q <= total_cap
    )
