"""exit_pair_d 的手算预期值测试（10-06）。"""

from datetime import datetime

import exit_pair_d as E


def _r(**kw):
    r = dict(
        entry_x=100.0,
        entry_y=1e6,
        entry_fee=0.01,
        entry_sol_usd=100.0,
        entry_marg_cap=1e7,
    )
    r.update(kw)
    return r


def test_proxy_mult_hand():
    # 买入 1,000 美元＝10 SOL，扣 1% 费后 9.9 SOL 入池：得币 1e6 − 100·1e6/109.9 = 90,081.8926
    # 市值 4 倍（4e7）：x' = 100·√4 = 200 SOL，y' = 200 / (4e7/1e9/100) = 500,000
    # 卖出：(200 − 200·500,000/590,081.8926)·0.99 = 30.22668 SOL → 3,022.668 美元；减两笔链上成本 2·0.005·100 = 1 美元
    m = E.proxy_mult(_r(), 4e7, 1000.0)
    assert abs(m - 3.021668) < 1e-6
    # 市值不变：代理池回到入场深度，卖出 90,081.8926 枚得 100 − 100·1e6/1,090,081.8926 = 8.26381 SOL，
    # 扣 1% 费 8.18113 SOL → 818.113 美元，减 1 美元链上成本 → 0.817114（1,000 美元占池深 10%，两边都计冲击）
    m1 = E.proxy_mult(_r(), 1e7, 1000.0)
    assert abs(m1 - 0.8171135) < 1e-6
    assert E.proxy_mult(_r(), None, 1000.0) is None


def test_weighted_stats_hand():
    xs = [(1.0, 1.0), (3.0, 3.0)]
    assert E.wmean(xs) == 2.5  # (1·1 + 3·3)/4
    assert E.wmedian(xs) == 3.0  # 累计权重 1 < 2，到 3.0 时 4 ≥ 2


def test_drop_top2_flags_undetermined_hand():
    t = datetime(2025, 3, 3)
    # 币 a、b 各 +10，其余 8 个币各 −1：均值 (20 − 8)/10 = +1.2；去掉 a、b 后为 −1 → 变号，记“未判定”
    pairs = [("a", t, 11.0, 1.0, 1.0), ("b", t, 11.0, 1.0, 1.0)]
    pairs += [("c%d" % i, t, 0.0, 1.0, 1.0) for i in range(8)]
    s = E.summarize(pairs)
    assert abs(s["diff_mean"] - 1.2) < 1e-12
    assert s["diff_mean_drop_top2"] == -1.0
    assert s["undetermined_top2"] is True
    assert [x["mint"] for x in s["top5"][:2]] == ["a", "b"]
