"""共同合同（过滤契约、窗口对、记账）的手算预期值测试（10-13）。不读任何数据。"""

import datetime as dt
from fractions import Fraction

import pytest

import contract_filter as CF
import contract_ledger as L
import contract_pairs as CP

E9 = L.LAMPORTS
D = dt.date


# ---------- 过滤契约 ----------


def test_coin_boundaries_hand():
    ok = "PEPE2X"
    assert CF.symbol_allowed(ok)
    assert CF.coin_allowed("2026-06-01T12:00:00Z", ok)  # 开发周
    assert not CF.coin_allowed("2026-06-08T12:00:00Z", ok)  # 检验周（weeks.py）
    assert not CF.coin_allowed("2026-06-20T12:00:00Z", ok)  # 封存周
    assert not CF.coin_allowed("2026-10-05T00:00:00Z", ok)  # 前向批次
    assert not CF.coin_allowed("2025-02-20T00:00:00Z", ok)  # 范围外


def test_holdout_names():
    assert len(CF.HOLDOUT_NAMES) == 152  # DQ-35 README：152 个基础资产命中留出规则
    s = sorted(CF.HOLDOUT_NAMES)[0]
    assert not CF.symbol_allowed(" $" + s.lower() + " ")  # 规范化：去 $、去空白、大写
    assert not CF.coin_allowed("2026-06-01T12:00:00Z", s)


def test_trade_cutoff_strict():
    c = ("2026-09-21T00:00:00Z", "ABCX")
    assert CF.trade_allowed("2026-10-04T23:59:59Z", *c)
    assert not CF.trade_allowed("2026-10-05T00:00:00Z", *c)


def test_edge_domain():
    assert CF.edge_allowed("2026-09-01T00:00:00Z")
    assert not CF.edge_allowed("2026-10-05T00:00:01Z")
    assert not CF.edge_allowed(
        "2026-06-09T00:00:00Z", ("2026-06-08T01:00:00Z", "ABCX")
    )  # 取自检验周币的成交


def test_entry_then_derive():
    rows = [
        {
            "ts": "2026-10-04T10:00:00Z",
            "created_ts": "2026-09-21T00:00:00Z",
            "symbol": "Q",
            "px": 2,
        },
        {
            "ts": "2026-10-05T01:00:00Z",
            "created_ts": "2026-09-21T00:00:00Z",
            "symbol": "Q",
            "px": 99,
        },
        {
            "ts": "2026-06-09T00:00:00Z",
            "created_ts": "2026-06-08T00:00:00Z",
            "symbol": "Q",
            "px": 50,
        },
    ]
    kept = CF.entry(rows, "trade")
    assert max(r["px"] for r in kept) == 2  # 全窗最高价从过滤后的行重算


def test_first_seen_domain_bias():
    rows = [
        {
            "wallet": "w",
            "ts": "2026-06-09T00:00:00Z",
            "created_ts": "2026-06-08T00:00:00Z",
            "symbol": "Q",
        },
        {
            "wallet": "w",
            "ts": "2026-06-02T00:00:00Z",
            "created_ts": "2026-06-01T00:00:00Z",
            "symbol": "Q",
        },
        {
            "wallet": "w",
            "ts": "2026-06-03T00:00:00Z",
            "created_ts": "2026-06-01T00:00:00Z",
            "symbol": "Q",
        },
    ]
    fs = CF.first_seen(CF.entry(rows, "first_seen"))
    assert fs["w"] == dt.datetime(2026, 6, 2, tzinfo=dt.timezone.utc)


def test_same_name_count():
    coins = [
        {"symbol": "$cat", "created_ts": "2026-06-01T00:00:00Z"},
        {"symbol": "CAT", "created_ts": "2026-06-02T00:00:00Z"},
        {"symbol": "CAT", "created_ts": "2026-06-08T00:00:00Z"},
    ]  # 检验周：入口就被去掉
    kept = CF.entry(coins, "coin")
    assert CF.same_name_count(kept, "symbol", "Cat", "2026-06-02T00:00:00Z") == 1


def test_label_maturity():
    h = dt.timedelta(days=7)
    assert CF.label_status("2026-09-28T00:00:00Z", h) == "mature"
    assert CF.label_status("2026-09-28T00:00:01Z", h) == "immature"
    assert (
        CF.label_status("2026-08-01T00:00:00Z", h, window_end="2026-08-05T00:00:00Z")
        == "immature"
    )


def test_lagged_week():
    assert CF.lagged_week(D(2026, 6, 1)) == D(2026, 5, 25)
    assert CF.lagged_week(D(2026, 6, 15)) is None  # 上一周 06-08 是检验周：缺失，不顶替


# ---------- 窗口对 ----------


def test_pairs_hand():
    assert CP.pair_ok(D(2026, 7, 27))  # 08-03 周的观察窗终点 09-09
    assert not CP.pair_ok(D(2026, 6, 1))  # W+1＝06-08 是检验周
    assert not CP.pair_ok(D(2026, 8, 24))  # 终点 10-07 晚于 10-05
    s = CP.select()
    assert s["ab"] is None and len(s["late"]) == 2
    assert all(w >= CP.LATE_FROM and CP.pair_ok(w) for w in s["late"])
    assert CP.select() == s  # 确定性


# ---------- 记账 ----------


def scenario():
    f = [
        L.Fill("E", "X", 1, 0, 0, -1, "curve", "buy", sol=E9, tok=1000),
        L.Fill("E", "X", 2, 0, 0, -1, "curve", "buy", sol=E9 // 2, tok=400),
        L.Fill("E", "X", 3, 0, 0, -1, "curve", "sell", sol=9 * E9 // 10, tok=700),
        L.Fill(
            "E",
            "X",
            9,
            4,
            1,
            0,
            "amm",
            "sell",
            sol=4 * E9 // 10,
            tok=200,
            cashback=E9 // 100,
        ),
    ]
    costs = [
        L.TxCost("E", "t1", ("X",), 5000, 10000, 0),
        L.TxCost("E", "t2", ("X",), 5000, 0, 0, failed=True),
        L.TxCost("E", "t3", ("Y", "X"), 3, 0, 0),
    ]
    rewards = [L.Reward("E", "X", 2 * E9 // 100)]
    return f, costs, rewards


def test_tx_cost_allocation_hand():
    _, costs, _ = scenario()
    a = L.allocate_tx_costs(costs)
    assert (
        a[("E", "X")] == 15000 + 5000 + 2 and a[("E", "Y")] == 1
    )  # 3 拆成 2＋1，余数给排序第一的 X
    b = L.allocate_tx_costs(costs, split=False)
    assert b[("E", "X")] == 20003 and b[("E", "Y")] == 0
    assert sum(a.values()) == sum(b.values()) == 20003  # 不重复分摊：15000＋5000＋3


def test_cycle_hand():
    f, costs, rewards = scenario()
    val = lambda q: L.sell_out(q, 10 * E9, 10_000, cap=3 * E9 // 10)  # noqa: E731
    c = L.cycle(f, L.allocate_tx_costs(costs), rewards, val)
    assert c.IN == 1_500_000_000
    assert c.OUT == 900_000_000 + 400_000_000 + 10_000_000 + 20_000_000
    assert c.COST == 20002 and c.q_end == 500
    assert c.HELD == 300_000_000  # 10e9·500/10500≈4.76e8，被真实储备 3e8 封顶
    assert c.NET == 129_979_998
    assert c.RR == Fraction(1_330_000_000, 1_500_020_002)
    assert c.MR == Fraction(1_630_000_000, 1_500_020_002)
    # 阶段分解：曲线 0.15e9 − 20002；两段之和等于整段
    assert c.stage_net["curve"] == 150_000_000 - 20002
    assert sum(c.stage_net.values()) == c.NET
    assert not c.cost_unknown


def test_cycle_uncapped_and_mark():
    f, costs, rewards = scenario()
    c = L.cycle(
        f,
        L.allocate_tx_costs(costs),
        rewards,
        lambda q: L.sell_out(q, 10 * E9, 10_000),
        lambda q: L.mark_value(q, 10 * E9, 10_000),
    )
    assert c.HELD == Fraction(10 * E9 * 500, 10_500)
    assert c.HELD_mark == 500_000_000  # 标价：500·10e9/10000
    assert sum(c.stage_net.values()) == c.NET


def test_cost_unknown_flags():
    f = [
        L.Fill("E", "X", 1, 0, 0, -1, "curve", "xfer_in", tok=100),
        L.Fill("E", "X", 2, 0, 0, -1, "curve", "sell", sol=E9, tok=100),
    ]
    assert L.cycle(f, {}, [], lambda q: 0).cost_unknown
    g = [
        L.Fill("E", "X", 1, 0, 0, -1, "curve", "buy", sol=E9, tok=50),
        L.Fill("E", "X", 2, 0, 0, -1, "curve", "sell", sol=E9, tok=100),
    ]
    assert L.cycle(g, {}, [], lambda q: 0).cost_unknown


def test_sell_out_fee_hand():
    # 1% 费率：q'＝99，x·q'/(y+q')＝1000·99/1099
    assert L.sell_out(100, 1000, 1000, fee_bps=100) == Fraction(1000 * 99, 1099)


def test_order_key_unique():
    f, _, _ = scenario()
    assert L.order_key_unique(f)
    assert not L.order_key_unique(
        f + [L.Fill("Z", "X", 9, 4, 1, 0, "amm", "buy", sol=1, tok=1)]
    )


def test_t2a_hand_and_double_counts():
    rec = L.net_receipts(
        {"protocol": 3, "creator": 4, "validator_jito": 5},
        {"creator": 2, "protocol": 1},
    )
    assert rec == {"protocol": 2, "creator": 2, "validator_jito": 5}
    # 买入 100、交易成本 5；卖出 60、返现 1、持有人奖励 2；池子真实储备 +33（含留在池里的 LP 费 1）
    assert L.t2a_residual(100, 5, 63, rec, 33) == 0
    with pytest.raises(ValueError):  # LP 费重复记
        L.t2a_residual(100, 5, 63, {**rec, "lp": 1}, 33)
    gross = {
        "protocol": 2,
        "creator": 4,
        "validator_jito": 5,
    }  # 忘了扣掉已分给持有人的 2
    assert L.t2a_residual(100, 5, 63, gross, 33) == -2
    with pytest.raises(KeyError):
        L.net_receipts({"protocol": 3}, {"creator": 1})
