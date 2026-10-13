"""S3 集合检验、R2 三对合并与 §9.1 v3 的测试（10-13，总控第二、三轮；GPT 增量 03～06 的反例）。合成数据，不读真实数据。"""

import random
from collections import defaultdict

import pytest

import a_riskset as A
import t3_persist as P


def row(ent, coin, hit, stratum=None):
    return {"entity": ent, "coin": coin, "hit": hit, "stratum": stratum or (coin,)}


# ---------- 选集 ----------


def test_select_set_hand(monkeypatch):
    monkeypatch.setattr(A, "MIN_ROWS", 2)
    rows = []
    # 4 个币，每币一层：a、b、c 三个实体各买每个币；只有 a 在 3 个币上命中、b 在 1 个币上命中
    for k in range(4):
        rows += [
            row("a", f"k{k}", int(k < 3)),
            row("b", f"k{k}", int(k == 0)),
            row("c", f"k{k}", 0),
        ]
    # 期望：每层命中率＝该层命中数/3 → a 的期望 (2+1+1+0)/3＝4/3，得分 3−4/3＝5/3；b 得分 1−4/3<0
    assert A.expected_hits(rows)["a"] == pytest.approx(4 / 3)
    assert A.select_set(rows) == ["a"]  # 合格 3 个，取 ⌈0.3⌉＝1 个候选


# ---------- 检验 ----------


def test_set_test_hand(monkeypatch):
    monkeypatch.setattr(A, "MIN_ACTIVE", 1)
    rows = [row("x", "c", 1), row("y", "c", 0)]
    r = A.set_test([(rows, ["x"])], n_perm=4000, seed=1)
    assert r["T"] == pytest.approx(0.5)  # 命中 1 − 期望 0.5
    assert r["p"] == pytest.approx(0.5, abs=0.03)  # 零假设下 x 拿到命中的概率是 1/2


def test_hypergeometric_equals_brute_force(monkeypatch):
    """超几何抽样的零分布与逐行打乱一致（同一组数据，p 值相差很小）。"""
    monkeypatch.setattr(A, "MIN_ACTIVE", 1)
    rng = random.Random(3)
    rows = []
    for c in range(30):
        for e in ("m1", "m2", "o1", "o2", "o3", "o4"):
            rows.append(
                row(
                    e, f"c{c}", int(rng.random() < (0.45 if e.startswith("m") else 0.3))
                )
            )
    members = {"m1", "m2"}
    fast = A.set_test([(rows, members)], n_perm=6000, seed=5)["p"]
    t_obs = A.set_statistic(rows, members)
    by = defaultdict(list)
    for i, r in enumerate(rows):
        by[r["stratum"]].append(i)
    ge, n = 0, 6000
    for _ in range(n):
        hits = [r["hit"] for r in rows]
        for idx in by.values():
            v = [hits[i] for i in idx]
            rng.shuffle(v)
            for i, x in zip(idx, v):
                hits[i] = x
        perm = [dict(r, hit=h) for r, h in zip(rows, hits)]
        ge += A.set_statistic(perm, members) >= t_obs - 1e-9
    assert fast == pytest.approx((1 + ge) / (1 + n), abs=0.03)


def test_not_computable():
    rows = [row(f"e{i}", "c", 0) for i in range(10)]
    assert (
        A.set_test([(rows, [f"e{i}" for i in range(10)])])["result"] == "not_computable"
    )  # 活跃 10 <20


# ---------- 校准：三对合并的误报率与功效 ----------


def make_week(rng, week, informed, n_coins=60, n_buys=25, pool=300):
    buys, events, bid = [], [], 0
    for c in range(n_coins):
        coin = f"w{week}c{c}"
        grad = rng.random() < 0.5
        tg = rng.uniform(2000, 8000)
        if grad:
            events.append(
                A.Event(coin, "grad", tg, (int(tg), 9, 0, -1), f"g{coin}", "other")
            )
        for _ in range(n_buys):
            bid += 1
            t = rng.uniform(0, 9000)
            buys.append(
                A.Buy(
                    bid,
                    f"e{rng.randrange(pool)}",
                    coin,
                    t,
                    (int(t), 0, 0, -1),
                    f"t{coin}{bid}",
                    ("s",),
                    1e12,
                )
            )
        if grad:
            for ent in informed:
                bid += 1
                t = tg - 600
                buys.append(
                    A.Buy(
                        bid,
                        ent,
                        coin,
                        t,
                        (int(t), 0, 0, -1),
                        f"t{coin}{bid}",
                        ("s",),
                        1e12,
                    )
                )
    return A.collapse(A.label(buys, events, "grad"))


def pooled(seed, informed=(), n_perm=199):
    rng = random.Random(seed)
    pairs = []
    for p in range(3):
        w = make_week(rng, 2 * p, informed)
        w1 = make_week(rng, 2 * p + 1, informed)
        pairs.append((w1, A.select_set(w)))
    return A.set_test(pairs, n_perm=n_perm, seed=seed)


def test_calibration_null_rate():
    res = [pooled(s) for s in range(80)]
    assert all(r["result"] != "not_computable" for r in res)
    rate = sum(r["result"] == "positive" for r in res) / len(res)
    assert rate <= 0.10  # 名义 0.05；80 次合成


def test_power_with_persistent_informed():
    informed = tuple(f"i{k}" for k in range(8))
    res = [pooled(s, informed) for s in range(10)]
    assert sum(r["result"] == "positive" for r in res) >= 9


def test_active_entities_deduplicated_across_pairs(monkeypatch):
    """GPT 增量 04：同样 7 个实体出现在三对里，是 7 个实体、21 个“实体 × 窗口对”，不能冒充 21 个实体。"""
    ents = [f"e{i}" for i in range(7)]
    pairs = [([row(e, f"p{k}c", 0) for e in ents], ents) for k in range(3)]
    r = A.set_test(pairs)
    assert r["active"] == 7 and r["active_pairs"] == 21
    assert r["result"] == "not_computable"
    members = [
        {"pair": k, "entity": e, "active": True, "p_class": True}
        for k in range(3)
        for e in ents
    ]
    flows = [
        {"pair": k, "entity": e, "day": 7 * k + d, "in_cost": 100, "out_held": 150}
        for k in range(3)
        for e in ents
        for d in range(7)
    ]
    r2 = P.r2_pooled(members, flows)
    assert (r2["n_active"], r2["n_active_pairs"], r2["n_p"]) == (7, 21, 7)
    assert not r2["computable"] and not r2["holds"]


def _collapse_any(rows):
    """被取代的合并写法（状态取首笔、命中取任一笔），只为复现 GPT 增量 05 的反例。"""
    groups = {}
    for r in sorted((r for r in rows if r["mature"]), key=lambda r: r["key"]):
        k = (r["entity"], r["coin"])
        if k not in groups:
            groups[k] = dict(r)
        else:
            groups[k]["hit"] = max(groups[k]["hit"], r["hit"])
            groups[k]["self"] = max(groups[k]["self"], r["self"])
    for g in groups.values():
        g["stratum"] = (g["coin"], g["day"], g["state"], g["self"])
    return list(groups.values())


def test_fixed_frequency_counterexample():
    """GPT 增量 05：20 个实体每币按固定时间表买 5 次，其余只买一次，没有任何事件信息。
    旧写法（命中取任一笔）几乎每次都“显著”；每个实体 × 币只留首笔成熟买入后不再显著。"""
    import calib_joint as C

    old = new = 0
    for seed in range(5):
        rng = random.Random(seed)
        shock = defaultdict(lambda: 1.0)
        po, pn = [], []
        for k in range(3):
            bw, ew, _ = C.make_week(rng, 2 * k, "freq", shock)
            bw1, ew1, _ = C.make_week(rng, 2 * k + 1, "freq", shock)
            lw, lw1 = A.label(bw, ew, "grad"), A.label(bw1, ew1, "grad")
            po.append((_collapse_any(lw1), A.select_set(_collapse_any(lw))))
            pn.append((A.collapse(lw1), A.select_set(A.collapse(lw))))
        old += A.set_test(po, n_perm=999, seed=seed)["result"] == "positive"
        new += A.set_test(pn, n_perm=999, seed=seed)["result"] == "positive"
    assert old == 5 and new <= 1


def test_collapse_keeps_first_buy_only():
    b = [
        A.Buy(1, "x", "c", 0, (0, 0, 0, -1), "t1", ("s",), 1e12),
        A.Buy(2, "x", "c", 5000, (5000, 0, 0, -1), "t2", ("s2",), 1e12),
    ]
    ev = [A.Event("c", "grad", 6000, (6000, 0, 0, -1), "g", "o")]
    rows = A.collapse(A.label(b, ev, "grad"))
    assert len(rows) == 1 and rows[0]["hit"] == 0 and rows[0]["state"] == ("s",)


# ---------- R2 与 §9.1 ----------


def test_top_decile_hand():
    net = {f"e{i}": i for i in range(25)}
    assert P.top_decile(net) == ["e24", "e23", "e22"]  # ⌈2.5⌉＝3


def r2data(n, ratio, p_class=True, n_pairs=1, days=10):
    members = [
        {"pair": k, "entity": f"e{i}", "active": True, "p_class": p_class}
        for k in range(n_pairs)
        for i in range(n)
    ]
    flows = [
        {
            "pair": k,
            "entity": f"e{i}",
            "day": 100 * k + d,
            "in_cost": 100,
            "out_held": int(100 * ratio),
        }
        for k in range(n_pairs)
        for i in range(n)
        for d in range(days)
    ]
    return members, flows


def test_r2_hand():
    r = P.r2_pooled(*r2data(20, 1.5))
    assert r["mr"] == 1.5 and r["lower"] == 1.5 and r["holds"] and r["n_days"] == 10
    assert not P.r2_pooled(*r2data(20, 1.5, p_class=False))["holds"]  # P 类不足 20
    assert not P.r2_pooled(*r2data(19, 1.5))["computable"]  # 活跃实体不足 20
    assert not P.r2_pooled(*r2data(20, 1.5, days=9))["computable"]  # 创建日不足 10
    m, f = r2data(20, 1.5)
    m.append({"pair": 1, "entity": "z", "active": False, "p_class": False})
    assert P.r2_pooled(m, f)["n_active"] == 20  # 不活跃的单列，不当作 MR＝0


def test_r2_common_shock_counterexample(monkeypatch):
    """GPT 增量 06：三对各有一个公平冲击，20 个实体每对同买一个币，投入 100，等概率收回 50 或 150。
    事前平均回收恰为 1。旧写法（只按实体重抽）8 种组合里 4 种“成立”。
    新写法：只有 3 个创建日，独立信息不足，8 种都不可计算；即使放开天数门槛，双向重抽也只在三对全涨时成立。"""
    import itertools

    def data(outcomes):
        members = [
            {"pair": k, "entity": f"e{i}", "active": True, "p_class": True}
            for k in range(3)
            for i in range(20)
        ]
        flows = [
            {"pair": k, "entity": f"e{i}", "day": k, "in_cost": 100, "out_held": o}
            for k, o in enumerate(outcomes)
            for i in range(20)
        ]
        return members, flows

    combos = list(itertools.product((50, 150), repeat=3))
    assert all(not P.r2_pooled(*data(c))["computable"] for c in combos)
    monkeypatch.setattr(P, "MIN_DAYS", 1)
    held = [c for c in combos if P.r2_pooled(*data(c))["holds"]]
    assert held == [
        (150, 150, 150)
    ]  # 两涨一跌（旧写法 MR＝7/6、下界 7/6 成立）不再成立


def test_keep_main_line_table():
    """§9.1 v3 完整 3×3（GPT 增量 03、总控第三轮）：S3 为正，或 R2 可计算且成立，任一满足即保持主线。"""
    s3 = {
        "pos": {"result": "positive"},
        "neg": {"result": "not_positive"},
        "nc": {"result": "not_computable"},
    }
    r2 = {
        "ok": {"computable": True, "holds": True},
        "no": {"computable": True, "holds": False},
        "nc": {"computable": False, "holds": False},
    }
    expect = {
        ("pos", "ok"): "keep",
        ("pos", "no"): "keep",
        ("pos", "nc"): "keep",  # 另一项不可计算不否决有效阳性
        ("neg", "ok"): "keep",
        ("neg", "no"): "downgrade",
        ("neg", "nc"): "downgrade",
        ("nc", "ok"): "keep",
        ("nc", "no"): "downgrade",
        ("nc", "nc"): "downgrade",
    }
    for (a, b), want in expect.items():
        assert P.keep_main_line(s3[a], r2[b]) == want, (a, b)
