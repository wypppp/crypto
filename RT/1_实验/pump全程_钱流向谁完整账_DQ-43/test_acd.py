"""A、C、D 的合成数据测试（10-13 v2）。必须的反例：循环筛选、结果窗未成熟、自身触发；另加槽内先后、
逐事件排除、同簇合并、不可检验、分辨率不足、无信号场景的误报率、缺片、零费用。不读任何真实数据。"""

import math
import random

import pytest

import a_riskset as A
import c_path as C
import contract_filter as CF
import d_autolabel as D

E9 = 1_000_000_000
FAR = 1e12  # 观察终点很远：成熟


# ---------- A ----------


def B(bid, ent, coin, ts, slot=1, tx=0, state=("s",), obs_end=FAR, txid=None):
    return A.Buy(
        bid, ent, coin, ts, (slot, tx, 0, -1), txid or f"t{bid}", state, obs_end
    )


def Ev(coin, ts, slot, tx, trig, kind="grad", txid=None):
    return A.Event(coin, kind, ts, (slot, tx, 0, -1), txid or f"g{coin}{ts}", trig)


def synth(seed=1, informed=True):
    """40 个币、每币 30 笔填充买入；前 20 个币在 t=5000 毕业。I（知情）在毕业前 600 秒买；N 随机；
    S 在 20..29 号币上买入后由自己触发毕业。"""
    rng = random.Random(seed)
    buys, events, bid = [], [], 0
    for c in range(40):
        coin = f"c{c}"
        for _ in range(30):
            bid += 1
            t = rng.uniform(0, 8000)
            buys.append(B(bid, f"f{rng.randrange(200)}", coin, t, slot=int(t)))
        bid += 1
        t = rng.uniform(0, 8000)
        buys.append(B(bid, "N", coin, t, slot=int(t)))
        if c < 20:
            events.append(Ev(coin, 5000.0, 5000, 9, "other"))
            if informed:
                bid += 1
                buys.append(B(bid, "I", coin, 4400.0, slot=4400))
        elif c < 30:
            bid += 1
            buys.append(B(bid, "S", coin, 3000.0, slot=3000))
            events.append(Ev(coin, 3300.0, 3300, 1, "S"))
    return buys, events


def run(buys, events, n_perm=499, seed=7):
    return A.permutation_p(
        A.collapse(A.label(buys, events, "grad")), n_perm=n_perm, seed=seed
    )


def test_riskset_keeps_every_buy():
    buys, events = synth()
    rows = A.label(buys, events, "grad")
    assert len(rows) == len(buys)  # 零事件的币留在分母
    assert sum(1 for r in rows if r["coin"] == "c35") == 31


def test_expected_hits_hand():
    b = [B(1, "x", "c", 0, slot=0), B(2, "y", "c", 10, slot=10)]
    rows = A.collapse(A.label(b, [Ev("c", 1000, 1000, 0, "o")], "grad", horizon=995))
    assert [r["hit"] for r in rows] == [
        0,
        1,
    ]  # x：0→1000 超出 995 秒；y：10→1000 在窗内
    assert A.expected_hits(rows) == {"x": 0.5, "y": 0.5}


def test_positive_control_and_null():
    res = run(*synth())
    assert res["I"]["obs"] == 20 and res["I"]["p"] < 0.01
    assert res["N"]["p"] > 0.05


def test_counterexample_circular_selection():
    buys, events = synth()
    assert (
        A.v4_circular_rate(buys, events, "grad", "N") == 1.0
    )  # v4 写法：无信息的 N 也是 100%
    assert run(buys, events)["N"]["p"] > 0.05  # 风险集写法：不显著


def test_counterexample_self_trigger_per_event():
    buys, events = synth()
    s = [r for r in A.label(buys, events, "grad") if r["entity"] == "S"]
    assert sum(r["self"] for r in s) == 10 and sum(r["hit"] for r in s) == 0
    # 先有自身事件、后有外部事件：外部事件照样算命中（逐事件排除，GPT 13）
    b = [B(1, "x", "c", 0, slot=0)]
    e = [Ev("c", 10, 10, 0, "x", kind="boost"), Ev("c", 20, 20, 0, "o", kind="boost")]
    r = A.label(b, e, "boost")[0]
    assert (r["hit"], r["self"]) == (1, 1)
    # 同一 slot 内关联体触发也算自身
    e2 = [Ev("c", 0, 0, 5, "x_alt")]
    assert A.label(b, e2, "grad", affiliates={"x": {"x_alt"}})[0]["hit"] == 0
    assert A.label(b, e2, "grad")[0]["hit"] == 1


def test_slot_order_not_timestamp():
    """GPT 12：同一时刻、同一 slot，事件排在买入之后才算“之后”。"""
    b = [B(1, "x", "c", 100, slot=50, tx=3)]
    assert (
        A.label(b, [Ev("c", 100, 50, 7, "o")], "grad")[0]["hit"] == 1
    )  # 同秒，交易序更后
    assert (
        A.label(b, [Ev("c", 100, 50, 1, "o")], "grad")[0]["hit"] == 0
    )  # 同秒，交易序更前


def test_counterexample_immature_excluded():
    """GPT 12：止日前 10 秒买入、无事件，不能记 hit=0 进检验。"""
    b = [B(1, "x", "c", 1000, slot=1000, obs_end=1010)]
    r = A.label(b, [], "grad")[0]
    assert r["mature"] is False and A.collapse([r]) == []


def test_collapse_cluster_and_untestable():
    """GPT 14：同一实体在同一币上的 20 笔合成 1 行；层内没有标签变化的实体记不可检验。"""
    b = [B(i, "p", "c", i, slot=i) for i in range(20)] + [
        B(100 + i, "q", "c", 3000 + i, slot=3000 + i) for i in range(20)
    ]
    rows = A.collapse(A.label(b, [Ev("c", 1000, 1000, 0, "o")], "grad"))
    assert len(rows) == 2 and {r["entity"]: r["hit"] for r in rows} == {"p": 1, "q": 0}
    res = A.permutation_p(rows, n_perm=199)
    assert res["p"]["p"] == pytest.approx(0.5, abs=0.15)  # 两个可交换位置，不再是 0.001
    lone = A.collapse(A.label([B(1, "z", "d", 0, slot=0)], [], "grad"))
    assert A.permutation_p(lone, n_perm=99)["z"]["status"] == "untestable"


def test_holm_resolution_and_classes():
    res = {f"e{i}": {"p": 0.001, "status": "testable"} for i in range(60)}
    res["u"] = {"p": None, "status": "untestable"}
    cls = A.holm_classify(res, alpha=0.05, n_perm=999)  # 最小 p 0.001 > 0.05/60
    assert cls["e0"] == "resolution_insufficient" and cls["u"] == "untestable"
    small = {
        "a": {"p": 0.001, "status": "testable"},
        "b": {"p": 0.04, "status": "testable"},
    }
    assert A.holm_classify(small, 0.05, 999) == {"a": "significant", "b": "significant"}
    assert A.n_perm_for(60, 0.05) == 24000


def test_null_false_positive_rate():
    """无信号场景：所有实体随机买入，p<0.05 的比例应接近 0.05（多次合成，只用固定种子）。"""
    hits = total = 0
    for seed in range(8):
        buys, events = synth(seed=seed, informed=False)
        res = run(buys, events, n_perm=199, seed=seed)
        ps = [v["p"] for v in res.values() if v["status"] == "testable"]
        hits += sum(p < 0.05 for p in ps)
        total += len(ps)
    assert total > 500 and hits / total < 0.08


# ---------- C ----------


def T(ts, sol, tok, slot=0, tx=0, price=None):
    return C.Trade(ts, slot or int(ts * 10), tx, 0, -1, sol, tok, price)


def test_buckets_hand():
    tr = [T(1, E9, 100), T(3, E9 // 2, 100), T(2, 5_000_000, 1), T(11, 2 * E9, 100)]
    s = C.buckets(tr, 0, 15)
    # 按代币量加权：(1e9＋0.5e9)/200＝7.5e6；尘埃成交（0.005 SOL）不进
    assert s[0] == (0, 5, 1.5 * E9 / 200, "trade")
    assert s[1] == (1, 10, 1.5 * E9 / 200, "filled")
    assert s[2] == (2, 15, 2 * E9 / 100, "trade")
    assert len(C.buckets(tr, 0, 14)) == 2  # 不完整的桶不出现


def test_price_override_and_gap():
    tr = [T(1, E9, 100, price=1.0e7), T(2, E9, 300, price=2.0e7), T(11, E9, 100)]
    s = C.buckets(tr, 0, 15, gaps=[(5, 10)])
    assert s[0][2] == pytest.approx(
        (1e7 * 100 + 2e7 * 300) / 400
    )  # 单独传入的价格，权重是代币量
    assert s[1] == (1, 10, None, "missing")  # 缺片：不沿用
    assert s[2][3] == "trade"


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
    assert C.pullback_trigger(C.buckets(tr, 0, 23), 0.5) is None  # 桶 [20,25) 还没走完
    assert C.pullback_trigger(C.buckets(tr, 0, 25), 0.5) == (4, 25)


def test_counterexample_immature_and_incomplete():
    s = C.buckets([T(1, E9, 100), T(6, 3 * E9, 100)], 0, 10)
    st = CF.label_status(
        "2026-10-01T00:00:00Z", __import__("datetime").timedelta(days=7)
    )
    assert st == "immature" and C.exceed_label(s, 0, 1.0, 1, st) == "immature"
    # GPT 17：只有 1 个未来桶却要观察 100 桶，传入 mature 也不能返回 0
    assert C.exceed_label(s, 0, 1.0, 100, "mature") == "incomplete"
    assert C.exceed_label(s, 0, 1.0, 1, "mature") == 1
    g = C.buckets([T(1, E9, 100), T(11, 3 * E9, 100)], 0, 15, gaps=[(5, 10)])
    assert C.exceed_label(g, 0, 1.0, 2, "mature") == "incomplete"  # 结果窗里有缺片


# ---------- D ----------


def acts_buy(ent, n, ts=0.0, fee=1, slot=10):
    return [D.Act(ent, f"k{i}", ts + i, "buy", slot, fee) for i in range(n)]


def test_c1_threshold_and_as_of():
    lab = D.labels(acts_buy("p", 50) + acts_buy("q", 49), as_of=1e6)
    assert lab["p"]["c1"] and not lab["q"]["c1"]
    late = [D.Act("r", f"k{i}", 2e6 + i, "buy", 10, 1) for i in range(60)]
    assert "r" not in D.labels(late, as_of=1e6)  # 之后的行为不影响 as_of 的标签


def test_formation_window():
    a = acts_buy("p", 50, ts=0) + acts_buy("p", 50, ts=500_000)
    assert D.labels(a, as_of=1e6, form_start=400_000)["p"]["c1"]  # 只看形成期内的那天
    assert "p" not in D.labels(acts_buy("p", 50, ts=0), as_of=1e6, form_start=400_000)


def test_c2_needs_completed_round_trips():
    a = []
    for i in range(20):
        a += [
            D.Act("h", f"k{i}", 1000 * i, "buy", 10, 1),
            D.Act("h", f"k{i}", 1000 * i + 30, "sell", 10, 1),
        ]
    assert D.labels(a, as_of=1e6)["h"]["c2"]
    assert not D.labels(a, as_of=19000 + 10)["h"]["c2"]  # 第 20 个首卖还没发生


def test_c3_strict_majority():
    a = [D.Act("e", f"k{i}", i, "buy", 1 if i < 3 else 9, 1) for i in range(5)]
    assert D.labels(a, 1e6)["e"]["c3"]
    b = [D.Act("e", f"k{i}", i, "buy", 1 if i < 2 else 9, 1) for i in range(4)]
    assert not D.labels(b, 1e6)["e"]["c3"]  # 恰好一半不算


def test_c4_p90_hand_and_zero_fees():
    a = [
        D.Act(f"u{f}", "k", f, "buy", 10, f) for f in range(1, 11)
    ]  # 费用中位 1..10，p90＝9.1
    lab = D.labels(a, 1e6)
    assert lab["u10"]["c4"] and not lab["u9"]["c4"]
    z = [
        D.Act(f"z{i}", "k", i, "buy", 10, 0) for i in range(10)
    ]  # 全体为 0：没有人算高费（GPT 19）
    assert not any(v["c4"] for v in D.labels(z, 1e6).values())
