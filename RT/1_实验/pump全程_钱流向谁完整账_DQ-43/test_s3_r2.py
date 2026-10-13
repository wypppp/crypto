"""S3 集合检验、R2 三对合并与 §9.1 v2 的测试（10-13，总控第二轮）。合成数据，不读真实数据。"""

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


# ---------- R2 与 §9.1 ----------


def test_top_decile_hand():
    net = {f"e{i}": i for i in range(25)}
    assert P.top_decile(net) == ["e24", "e23", "e22"]  # ⌈2.5⌉＝3


def r2rows(n, ratio, p_class=False, pair="a"):
    return [
        {
            "pair": pair,
            "entity": f"e{i}",
            "in_cost": 100,
            "out_held": int(100 * ratio),
            "active": True,
            "p_class": p_class,
        }
        for i in range(n)
    ]


def test_r2_hand():
    r = P.r2_pooled(r2rows(20, 1.5, p_class=True))
    assert r["mr"] == 1.5 and r["lower"] == 1.5 and r["holds"]
    assert not P.r2_pooled(r2rows(20, 1.5, p_class=False))["holds"]  # P 类不足 20
    assert not P.r2_pooled(r2rows(19, 1.5, p_class=True))["computable"]
    inactive = r2rows(20, 1.5, True) + [
        {
            "pair": "b",
            "entity": "z",
            "in_cost": 0,
            "out_held": 0,
            "active": False,
            "p_class": False,
        }
    ]
    assert P.r2_pooled(inactive)["n_active"] == 20  # 不活跃的单列，不当作 MR＝0


def test_keep_main_line_table():
    pos, neg, nc = (
        {"result": "positive"},
        {"result": "not_positive"},
        {"result": "not_computable"},
    )
    r2_ok, r2_no, r2_nc = (
        {"computable": True, "holds": True},
        {"computable": True, "holds": False},
        {"computable": False, "holds": False},
    )
    assert P.keep_main_line(pos, r2_no) == "keep"
    assert P.keep_main_line(neg, r2_ok) == "keep"
    assert P.keep_main_line(neg, r2_no) == "downgrade"
    assert P.keep_main_line(pos, r2_nc) == "downgrade"  # 两者都须可计算（总控原文）
    assert P.keep_main_line(nc, r2_ok) == "downgrade"
