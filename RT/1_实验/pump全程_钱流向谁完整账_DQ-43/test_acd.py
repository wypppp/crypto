"""A、C、D 的合成数据测试（10-13）。三个必须的反例：循环筛选、结果窗未成熟、自身触发。不读任何真实数据。"""

import math
import random

import pytest

import a_riskset as A
import c_path as C
import contract_filter as CF
import d_autolabel as D

E9 = 1_000_000_000


# ---------- A ----------


def synth(seed=1):
    """40 个币、每币 30 笔随机买入（填充层）；前 20 个币在 t=5000 毕业。
    I：每个毕业币上，毕业前 600 秒买入（知情）；N：每个币随机时刻买入（无信息）；
    S：在 20..29 号币上买入后 300 秒由自己的交易触发毕业。"""
    rng = random.Random(seed)
    buys, events, bid = [], [], 0
    st = ("curve", 5)
    for c in range(40):
        coin = f"c{c}"
        for _ in range(30):
            bid += 1
            buys.append(
                A.Buy(
                    bid,
                    f"f{rng.randrange(200)}",
                    coin,
                    rng.uniform(0, 8000),
                    1,
                    f"t{bid}",
                    st,
                )
            )
        bid += 1
        buys.append(A.Buy(bid, "N", coin, rng.uniform(0, 8000), 1, f"t{bid}", st))
        if c < 20:
            events.append(A.Event(coin, "grad", 5000.0, 999, f"g{c}", "other"))
            bid += 1
            buys.append(A.Buy(bid, "I", coin, 4400.0, 1, f"t{bid}", st))
        elif c < 30:
            bid += 1
            buys.append(A.Buy(bid, "S", coin, 3000.0, 1, f"t{bid}", st))
            events.append(A.Event(coin, "grad", 3300.0, 999, f"g{c}", "S"))
    return buys, events


def test_riskset_keeps_every_buy():
    buys, events = synth()
    rows = A.label(buys, events, "grad")
    assert len(rows) == len(buys)  # 零事件的币留在分母
    assert sum(1 for r in rows if r["stratum"][0] == "c35") == 31


def test_expected_hits_hand():
    b = [A.Buy(1, "x", "c", 0, 1, "a", ()), A.Buy(2, "y", "c", 10, 1, "b", ())]
    e = [A.Event("c", "grad", 1000, 5, "z", "o")]
    rows = A.label(
        b, e, "grad", horizon=995
    )  # 只有 x（0→1000）在 995 秒窗外；y（10→1000）在窗内
    assert [r["hit"] for r in rows] == [0, 1]
    assert A.expected_hits(rows) == {"x": 0.5, "y": 0.5}


def test_positive_control_and_null():
    buys, events = synth()
    res = A.permutation_p(A.label(buys, events, "grad"), n_perm=499, seed=7)
    assert res["I"][0] == 20 and res["I"][2] < 0.01
    assert res["N"][2] > 0.05


def test_counterexample_circular_selection():
    buys, events = synth()
    assert (
        A.v4_circular_rate(buys, events, "grad", "N") == 1.0
    )  # v4 写法：无信息的 N 也是 100%
    res = A.permutation_p(A.label(buys, events, "grad"), n_perm=499, seed=7)
    assert res["N"][2] > 0.05  # 风险集写法：不显著


def test_counterexample_self_trigger():
    buys, events = synth()
    rows = A.label(buys, events, "grad")
    s = [r for r in rows if r["entity"] == "S"]
    assert sum(r["self"] for r in s) == 10 and sum(r["hit"] for r in s) == 0
    # 同一 slot 内关联体触发也算自身触发
    b = [A.Buy(1, "x", "c", 0, 7, "a", ())]
    e = [A.Event("c", "grad", 10, 7, "q", "x_alt")]
    assert A.label(b, e, "grad", affiliates={"x": {"x_alt"}})[0]["hit"] == 0
    assert A.label(b, e, "grad")[0]["hit"] == 1


# ---------- C ----------


def T(ts, sol, tok, slot=0, tx=0):
    return C.Trade(ts, slot or int(ts * 10), tx, 0, -1, sol, tok)


def test_buckets_hand():
    tr = [T(1, E9, 100), T(3, E9 // 2, 100), T(2, 5_000_000, 1), T(11, 2 * E9, 100)]
    s = C.buckets(tr, 0, 15)
    assert s[0] == (0, 5, 1.5 * E9 / 200, False)  # 尘埃成交（0.005 SOL）不进
    assert s[1] == (1, 10, 1.5 * E9 / 200, True)  # 空桶沿用前值并标记
    assert s[2] == (2, 15, 2 * E9 / 100, False)
    assert len(C.buckets(tr, 0, 14)) == 2  # 不完整的桶不出现


def test_order_key_must_be_unique():
    with pytest.raises(ValueError):
        C.ordered([C.Trade(1, 5, 0, 0, -1, E9, 1), C.Trade(2, 5, 0, 0, -1, E9, 1)])


def test_zigzag_hand():
    pv = C.zigzag([1, 2.5, 4, 1.9, 1.8, 4, 8], 0.5)
    assert [(a, b, c) for a, b, c, _ in pv] == [
        (1, "trough", 0),
        (3, "peak", 2),
        (5, "trough", 4),
    ]
    assert math.isclose(pv[1][3], 4) and math.isclose(pv[2][3], 1.8)
    assert C.prior_wave_high(pv, 2) is None  # 顶在序号 3 才确认
    assert math.isclose(C.prior_wave_high(pv, 3), 4)


def test_trigger_waits_for_complete_bucket():
    tr = [T(1, E9, 100), T(6, 3 * E9, 100), T(11, 2 * E9, 100), T(22, E9, 100)]
    # 桶 [20,25) 在 t=23 还没走完：不能触发
    assert C.pullback_trigger(C.buckets(tr, 0, 23), 0.5) is None
    assert C.pullback_trigger(C.buckets(tr, 0, 25), 0.5) == (
        4,
        25,
    )  # 桶走完，25 秒之后才能下单


def test_counterexample_immature_window():
    s = C.buckets([T(1, E9, 100), T(6, 3 * E9, 100)], 0, 10)
    st = CF.label_status(
        "2026-10-01T00:00:00Z", __import__("datetime").timedelta(days=7)
    )
    assert st == "immature"
    assert C.exceed_label(s, 0, 1.0, 10, st) == "immature"  # 不当作“没涨”（0）
    assert C.exceed_label(s, 0, 1.0, 10, "mature") == 1


# ---------- D ----------


def acts_buy(ent, n, ts=0.0, fee=1, slot=10):
    return [D.Act(ent, f"k{i}", ts + i, "buy", slot, fee) for i in range(n)]


def test_c1_threshold_and_as_of():
    a = acts_buy("p", 50) + acts_buy("q", 49)
    lab = D.labels(a, as_of=1e6)
    assert lab["p"]["c1"] and not lab["q"]["c1"]
    late = [D.Act("r", f"k{i}", 2e6 + i, "buy", 10, 1) for i in range(60)]
    assert "r" not in D.labels(late, as_of=1e6)  # 之后的行为不影响 as_of 的标签


def test_c2_needs_completed_round_trips():
    a = []
    for i in range(20):
        a += [
            D.Act("h", f"k{i}", 1000 * i, "buy", 10, 1),
            D.Act("h", f"k{i}", 1000 * i + 30, "sell", 10, 1),
        ]
    assert D.labels(a, as_of=1e6)["h"]["c2"]
    assert not D.labels(a, as_of=19000 + 10)["h"]["c2"]  # 第 20 个往返的卖出还没发生


def test_c3_strict_majority():
    a = [D.Act("e", f"k{i}", i, "buy", 1 if i < 3 else 9, 1) for i in range(5)]
    assert D.labels(a, 1e6)["e"]["c3"]
    b = [D.Act("e", f"k{i}", i, "buy", 1 if i < 2 else 9, 1) for i in range(4)]
    assert not D.labels(b, 1e6)["e"]["c3"]  # 恰好一半不算


def test_c4_p90_hand():
    a = [
        D.Act(f"u{f}", "k", f, "buy", 10, f) for f in range(1, 11)
    ]  # 费用中位 1..10，p90＝9.1
    lab = D.labels(a, 1e6)
    assert lab["u10"]["c4"] and not lab["u9"]["c4"]
