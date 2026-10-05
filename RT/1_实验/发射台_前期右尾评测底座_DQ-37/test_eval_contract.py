"""eval_contract（契约 v1.1）的手算预期值测试（10-05）。
统计部分沿用 v1 参考实现的测试向量（GPT 批 0 复算值）；账本部分加入 GPT 批 0 的五个状态机反例。"""

import math

import numpy as np
import pytest
from scipy.stats import binom

import eval_contract as E

W = E.WAN


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# ---------- 统计（沿用 v1 测试向量）
def test_two_point_growth_hand():
    g = 0.1 * E.h(0.0125, 13.0) + 0.9 * E.h(0.0125, 0.0)
    assert abs(g - 0.0026552903) < 1e-9  # GPT 复算值


def test_first_passage_gpt_values():
    s1, _ = E.first_passage_two_point(
        0.30, 1.3 / 0.30, 156, E.half_kelly(0.30, 1.3 / 0.30)
    )
    s2, _ = E.first_passage_two_point(0.10, 13.0, 1092, E.half_kelly(0.10, 13.0))
    assert abs(s1 - 0.002868) < 5e-6 and abs(s2 - 0.162443) < 5e-6


def test_p4_clean_lower_bounds_hand():
    # 夹到 [0,1]，再从右往左取累积最大：[0.3, 0.1, 0.25, -0.1] → [0.3, 0.25, 0.25, 0.0]
    assert E.clean_lower_bounds([0.3, 0.1, 0.25, -0.1]) == [0.3, 0.25, 0.25, 0.0]
    assert E.clean_lower_bounds([1.2, 0.4]) == [1.0, 0.4]


def test_step_certificate_equals_conservative_and_is_lower_bound():
    steps = [0.0, 0.5, 1.0, 2.0, 4.0, 10.0, 100.0]
    L = [0.40, 0.25, 0.12, 0.05, 0.015, 0.002]
    f = 0.02
    cert = E.step_certificate(f, steps, L)
    vals, probs = E.conservative_distribution(steps, L)
    assert close(sum(probs), 1.0)
    assert close(cert, sum(pr * E.h(f, v) for v, pr in zip(vals, probs)))
    rng = np.random.default_rng(7)
    for _ in range(300):
        trueL = E.clean_lower_bounds(
            [
                min(1.0, lb + e * (1 - lb) * 0.3)
                for lb, e in zip(L, rng.uniform(0, 1, len(L)))
            ]
        )
        v2, p2 = E.conservative_distribution(steps, trueL)
        bounds = steps + [1000.0]
        g_true = sum(
            pr * E.h(f, rng.uniform(bounds[j], bounds[j + 1]))
            for j, (v, pr) in enumerate(zip(v2, p2))
        )
        assert g_true >= cert - 1e-12


def test_p12_two_fc_can_exceed_kelly_hand():
    # GPT 批 0 B.2：保守分布 20% 回收 6、80% 回收 0；Kelly 最优 f_c＝0.04，2f_c＝0.08 仍 g>0——政策上限不等于不过度下注
    f_c, g_c = E.kelly_on_distribution([0.0, 6.0], [0.8, 0.2])
    assert abs(f_c - 0.04) < 1e-6
    g2 = 0.2 * math.log(1.4) + 0.8 * math.log(0.92)
    assert g2 > 0 and close(0.2 * E.h(0.08, 6.0) + 0.8 * E.h(0.08, 0.0), g2)


def test_cp_and_power_gpt_values():
    assert (
        abs(binom.sf(6, 301, 0.01) - 0.03325) < 5e-5
        and abs(binom.sf(6, 301, 0.03) - 0.80009) < 5e-5
    )
    assert E.cp_lower(0, 10, 0.05) == 0.0


def test_demand_curve_monotone_and_raises():
    out = E.demand_curve(
        [0.1, 0.2, 0.3], N=200, target_prob=0.01, K_grid=[3, 5, 8, 13, 20, 40]
    )
    ks = [k for _, k in out if k is not None]
    assert all(b <= a for a, b in zip(ks, ks[1:]))


# ---------- 账本（契约 v1.1；GPT 批 0 五个反例）
def test_dust_lock_triggers_funds_exhausted_pause():
    # GPT 批 0 反例，m_min＝100：首笔剩 50 → 投第二笔；第二笔又亏到总共只剩 50：
    # D＝2 万、N＝−19,950，过不了 −2 万的暂停线，但已不能下注 → 须“资金耗尽暂停”，保留真实现金与 N
    A = E.Ledger(m_min=100)
    A.open("x", W)
    A.set_value("x", 50)
    A.mark(10)
    assert A.D == 2 * W and A.state == "ACTIVE"
    A.close("x")  # 现金 10,050
    A.open("y", W)
    A.set_value("y", 0)
    A.mark(20)
    assert A.state == "PAUSED" and close(A.n_loss(20), -19_950) and A.cash == 50
    assert A.log[-1][1] == "pause:funds_exhausted"


def test_lock_writedown_classes():
    # 正常 12 个月归属：上市后 200 天仍在归属期内，不能被记 0；按 min(成本, 合格市价×0.7)
    A = E.Ledger()
    A.subscribe("tge", 5_000, sub_deadline=0, vest_end=400)
    A.list_asset(
        "tge", day=30, price_value=6_000, volume_24h=60_000
    )  # 成交额 ≥ 10×估值，合格
    assert A.locked["tge"].value_loss(230) == 4_200  # min(5000, 0.7×6000)
    A.locked["tge"].volume_24h = 59_999  # 不合格 → 视为没有市价 → 按成本
    assert A.locked["tge"].value_loss(230) == 5_000
    assert A.locked["tge"].value_loss(401) == 0.0  # 逾期未解锁
    B = E.Ledger()
    B.subscribe("pre", 3_000, sub_deadline=10)
    assert (
        B.locked["pre"].value_loss(190) == 3_000
        and B.locked["pre"].value_loss(191) == 0.0
    )  # 未上市：截止日起 180 天


def test_writedown_during_pause_triggers_stop():
    # 一年内到 10 万 → 追加 2 万（D＝3 万）；随后可交易部分归零、剩 1 万锁定 → N＝−2 万暂停；锁定项目失败 → N＝−3 万停止
    A = E.Ledger()
    A.open("x", W)
    A.set_value("x", 100_000)
    A.mark(100)
    assert A.D == 3 * W and A.bonus_used
    A.close("x")
    A.subscribe("lk", 10_000, sub_deadline=110, vest_end=500)
    A.open("z", A.cash)
    A.set_value("z", 0)
    A.mark(120)
    assert A.state == "PAUSED" and close(A.n_loss(120), -2 * W)
    A.fail_asset("lk")
    A.mark(130)
    assert A.state == "STOPPED" and close(A.n_loss(130), -3 * W)
    A.mark(140)  # 停止后继续记账、不恢复
    assert A.state == "STOPPED" and A.log[-1][1] == "book"


def test_refund_is_conversion_not_deposit():
    A = E.Ledger()
    A.subscribe("r", 4_000, sub_deadline=0)
    A.request_refund("r", 3_500)
    assert (
        A.liq() == 6_000 and A.v_loss(10) == 9_500
    )  # 到账前：不计入清算价值，风险估值按退款额
    d0 = A.D
    A.refund_arrives("r")
    assert (
        A.cash == 9_500 and A.D == d0 and "r" not in A.locked
    )  # 到账：资产转换，D 不变，不重复计


def test_resume_checks_inside_state_machine():
    A = E.Ledger()
    A.open("x", W)
    A.set_value("x", 0)
    A.mark(5)  # 第二笔
    A.open("y", W)
    A.set_value("y", 0)
    A.mark(10)
    assert A.state == "PAUSED" and A.pause_start == 10
    with pytest.raises(RuntimeError):
        A.resume(50, certificate=True)  # 不足 90 天
    with pytest.raises(RuntimeError):
        A.resume(120, certificate=None)  # 缺确认凭证
    A.resume(120, certificate="cert-001")
    assert A.state == "ACTIVE" and A.phase == "B" and A.D == 3 * W
    B = E.Ledger()
    B.open("x", W)
    B.set_value("x", 0)
    B.mark(5)
    B.open("y", W)
    B.set_value("y", 0)
    B.mark(1_000)
    with pytest.raises(RuntimeError):
        B.resume(1_100, certificate="c")  # 过了 36 个月期限
    with pytest.raises(RuntimeError):
        B.open("z", 1)  # 暂停中禁止开仓


def test_success_by_liquidation_value_only():
    A = E.Ledger()
    A.subscribe("lk", 5_000, sub_deadline=0, vest_end=300)
    A.list_asset(
        "lk", 10, price_value=5_000_000, volume_24h=1e9
    )  # 锁定资产账面很高也不触发成功
    A.mark(20)
    assert A.state == "ACTIVE"
    A.unlock("lk", 1_200_000)
    A.mark(310)
    assert A.state == "SUCCESS"


def test_min_ticket_hand():
    assert E.min_ticket_ok(
        40,
        100,
        cash=500,
        single_cap=200,
        cluster_used=50,
        cluster_cap=200,
        total_used=300,
        total_cap=500,
    )
    assert not E.min_ticket_ok(
        40,
        100,
        cash=500,
        single_cap=200,
        cluster_used=150,
        cluster_cap=200,
        total_used=0,
        total_cap=500,
    )
