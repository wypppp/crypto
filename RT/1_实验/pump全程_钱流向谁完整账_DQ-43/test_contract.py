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


def test_missing_metadata_not_passed():
    """GPT 11：缺代号不放行；取自成交的边缺所在币报错；边缺来源类型报错。"""
    assert not CF.coin_allowed("2026-06-01T12:00:00Z", None)
    with pytest.raises(ValueError):
        CF.coin_allowed(None, "ABCX")
    with pytest.raises(ValueError):
        CF.entry([{"ts": "2026-09-01T00:00:00Z", "source": "trade"}], "edge")
    with pytest.raises(ValueError):
        CF.entry([{"ts": "2026-09-01T00:00:00Z"}], "edge")
    rows = [
        {"ts": "2026-09-01T00:00:00Z", "source": "transfer"},
        {
            "ts": "2026-06-09T00:00:00Z",
            "source": "trade",
            "via_created": "2026-06-08T00:00:00Z",
            "via_symbol": "ABCX",
        },
    ]
    assert CF.entry(rows, "edge") == rows[:1]
    assert CF.entry(
        [{"ts": "2026-10-05T00:00:00Z"}, {"ts": "2026-10-04T00:00:00Z"}], "fx"
    ) == [{"ts": "2026-10-04T00:00:00Z"}]


def test_mixed_tx_cost_keeps_only_allowed_legs():
    c = L.TxCost("t", "E", (("A", "curve"), ("P", "curve"), ("B", "amm")), 9, 0, 0)
    a = L.allocate_tx_costs([c], keep_coin=lambda coin: coin != "P")  # P 是保护币
    assert a == {
        ("E", "A", "curve"): 3,
        ("E", "B", "amm"): 3,
    }  # 按 3 条腿均摊，P 的份额不输出


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
    assert CF.label_status("2026-09-27T23:59:59Z", h) == "mature"
    assert (
        CF.label_status("2026-09-28T00:00:00Z", h) == "immature"
    )  # 终点恰在止日：看不到
    assert (
        CF.label_status("2026-08-01T00:00:00Z", h, window_end="2026-08-05T00:00:00Z")
        == "immature"
    )


@pytest.mark.parametrize("blank", ["", "   ", "$", " $ "])
def test_blank_symbol_excluded_on_every_branch(blank):
    """GPT 增量 01：规范化后为空的代号与缺失同样排除，币、成交、成本、奖励、取自成交的边都挡住。"""
    c, t = "2026-06-01T12:00:00Z", "2026-06-02T00:00:00Z"
    assert not CF.coin_allowed(c, blank)
    assert not CF.trade_allowed(t, c, blank)
    row = {"ts": t, "created_ts": c, "symbol": blank}
    for branch in ("coin", "trade", "raw_event", "cost", "reward", "behavior"):
        assert CF.entry([row], branch) == []
    edge = {"ts": t, "source": "trade", "via_created": c, "via_symbol": blank}
    assert CF.entry([edge], "edge") == []
    assert CF.entry([dict(row, symbol="ABCX")], "cost") != []  # 对照：正常代号放行


def test_boundary_exit_maturity():
    """GPT 增量 02：B 的固定退出按桶边界收盘，单设成熟判定。"""
    pool = dt.datetime(2026, 6, 2, tzinfo=dt.timezone.utc)
    entry = pool + dt.timedelta(seconds=300)
    exit7 = pool + dt.timedelta(days=7)
    # A 的严格规则下，退出＝观察终点会被判未成熟（GPT 的反例）
    assert CF.label_status(entry, exit7 - entry, window_end=exit7) == "immature"
    # 正常 7 天退出：远早于止日、数据覆盖到边界
    assert CF.boundary_exit_status(exit7, covered_until=exit7) == "mature"
    # 恰到全局止日：未成熟；早 1 秒：成熟
    assert CF.boundary_exit_status(CF.CUTOFF, covered_until=CF.CUTOFF) == "immature"
    b = CF.CUTOFF - dt.timedelta(seconds=1)
    assert CF.boundary_exit_status(b, covered_until=b) == "mature"
    # 桶缺片或覆盖不到边界：单列缺片
    assert CF.boundary_exit_status(exit7, covered_until=exit7, gap=True) == "gap"
    early = exit7 - dt.timedelta(hours=1)
    assert CF.boundary_exit_status(exit7, covered_until=early) == "gap"


def test_lagged_week():
    assert CF.lagged_week(D(2026, 6, 1)) == D(2026, 5, 25)
    assert CF.lagged_week(D(2026, 6, 15)) is None  # 上一周 06-08 是检验周：缺失，不顶替


# ---------- 窗口对 ----------


def test_pairs_hand():
    assert CP.pair_ok(D(2026, 7, 27))  # 08-03 周的观察窗终点 09-09
    assert not CP.pair_ok(D(2026, 6, 1))  # W+1＝06-08 是检验周
    assert not CP.pair_ok(D(2026, 8, 24))  # 终点 10-07 晚于 10-05
    s = CP.select()
    assert s["ab"] is None and s["old"] == D(2026, 5, 25)
    # 哈希顺序 07-27、08-03（共用 08-03 周，跳过）、07-20（共用 07-27 周，跳过）、08-10；GPT 独立复算同为 07-27、08-10
    assert s["late"] == [D(2026, 7, 27), D(2026, 8, 10)]
    weeks = [
        w + dt.timedelta(days=7 * k) for w in [s["old"]] + s["late"] for k in (0, 1)
    ]
    assert len(set(weeks)) == 6  # 三对不共用创建周


# ---------- 记账（10-13 v2，按 GPT 门 1 第 03～08 条） ----------


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
        L.TxCost("t1", "E", (("X", "curve"),), 5000, 10000, 0),
        L.TxCost("t2", "E", (("X", "curve"),), 5000, 0, 0, failed=True),
        L.TxCost("t3", "E", (("Y", "curve"), ("X", "amm")), 3, 0, 0),
    ]
    rewards = [L.Reward("E", "X", 2 * E9 // 100, "amm")]
    return f, costs, rewards


def test_tx_cost_allocation_hand():
    _, costs, _ = scenario()
    a = L.allocate_tx_costs(costs)
    # t3 的两条腿排序为 (X, amm)、(Y, curve)：3 拆成 2＋1，余数给第一腿
    assert a == {
        ("E", "X", "curve"): 20000,
        ("E", "X", "amm"): 2,
        ("E", "Y", "curve"): 1,
    }
    b = L.allocate_tx_costs(costs, split=False)
    assert b[("E", "X", "amm")] == 3 and b[("E", "Y", "curve")] == 0
    assert sum(a.values()) == sum(b.values()) == 20003  # 15000＋5000＋3，不重复分摊


def test_tx_cost_dedupe_and_conflict():
    c = L.TxCost("t", "E", (("X", "amm"), ("X", "amm")), 10, 0, 0)  # 重复腿按集合
    assert L.allocate_tx_costs([c, c]) == {("E", "X", "amm"): 10}  # 同一 tx_id 只记一次
    with pytest.raises(ValueError):
        L.allocate_tx_costs([c, L.TxCost("t", "E", (("X", "amm"),), 11, 0, 0)])


def test_cycle_hand():
    f, costs, rewards = scenario()
    val = lambda q: L.liquidation(q, 10 * E9, 10_000, cap=3 * E9 // 10, fee_bps=0)  # noqa: E731
    c = L.cycle("E", "X", f, L.allocate_tx_costs(costs), rewards, val, "amm")
    assert c.IN == 1_500_000_000
    assert c.OUT == 900_000_000 + 400_000_000 + 10_000_000 + 20_000_000
    assert c.COST == 20002 and c.q_end == 500
    assert c.HELD == 300_000_000  # 定价毛额 10e9·500/10500≈4.76e8，被真实储备 3e8 封顶
    assert c.NET == 129_979_998
    assert c.RR == Fraction(1_330_000_000, 1_500_020_002)
    assert c.MR == Fraction(1_630_000_000, 1_500_020_002)
    # 实现阶段账：曲线 0.9e9＋结转 0.75e9−1.5e9−20000；毕业后 0.43e9＋0.3e9−0.75e9−2
    assert c.stage_net("curve") == 149_980_000
    assert c.stage_net("amm") == -20_000_002
    assert c.stage_net("curve") + c.stage_net("amm") == c.NET
    assert c.stage_mr("amm") == Fraction(730_000_000, 750_000_002)
    assert not c.cost_unknown


def test_stage_costs_follow_stage():
    """GPT 05 反例：毕业后买 100、卖 110、费用 5 → 曲线 0，毕业后 +5。"""
    f = [
        L.Fill("E", "X", 1, 0, 0, -1, "amm", "buy", sol=100, tok=10),
        L.Fill("E", "X", 2, 0, 0, -1, "amm", "sell", sol=110, tok=10),
    ]
    a = L.allocate_tx_costs([L.TxCost("t", "E", (("X", "amm"),), 5, 0, 0)])
    c = L.cycle("E", "X", f, a, [], lambda q: 0, "amm")
    assert (c.stage_net("curve"), c.stage_net("amm"), c.NET) == (0, 5, 5)


def test_realized_stage_attribution():
    """GPT 08 例子：曲线买入成本 1、毕业后立即卖 10 → +9 全记在毕业后（按实现阶段归属）。"""
    f = [
        L.Fill("E", "X", 1, 0, 0, -1, "curve", "buy", sol=1, tok=10),
        L.Fill("E", "X", 2, 0, 0, -1, "amm", "sell", sol=10, tok=10),
    ]
    c = L.cycle("E", "X", f, {}, [], lambda q: 0, "amm")
    assert (c.stage_net("curve"), c.stage_net("amm")) == (0, 9)


def test_held_from_curve_into_amm_carried():
    f = [L.Fill("E", "X", 1, 0, 0, -1, "curve", "buy", sol=100, tok=10)]
    c = L.cycle("E", "X", f, {}, [], lambda q: 150, "amm")
    assert (c.stage_net("curve"), c.stage_net("amm"), c.NET) == (0, 50, 50)
    with pytest.raises(ValueError):
        L.cycle("E", "X", f, {}, [], lambda q: 150, "")  # 期末阶段必须显式给出


def test_cost_only_and_reward_only_cycles():
    """GPT 06：只有失败交易费用、第三方代付、只有奖励，也要有周期。"""
    a = L.allocate_tx_costs(
        [L.TxCost("t", "P", (("X", "curve"),), 5000, 0, 0, failed=True)]
    )
    rw = [L.Reward("Q", "X", 7, "amm")]
    assert L.cycle_keys([], a, rw) == {("P", "X"), ("Q", "X")}
    cp = L.cycle("P", "X", [], a, rw, lambda q: 0, "curve")
    cq = L.cycle("Q", "X", [], a, rw, lambda q: 0, "amm")
    assert (cp.NET, cp.RR) == (-5000, 0) and (cq.NET, cq.RR) == (7, None)


def test_cost_unknown_flags():
    f = [
        L.Fill("E", "X", 1, 0, 0, -1, "curve", "xfer_in", tok=100),
        L.Fill("E", "X", 2, 0, 0, -1, "curve", "sell", sol=E9, tok=100),
    ]
    assert L.cycle("E", "X", f, {}, [], lambda q: 0, "curve").cost_unknown
    g = [
        L.Fill("E", "X", 1, 0, 0, -1, "curve", "buy", sol=E9, tok=50),
        L.Fill("E", "X", 2, 0, 0, -1, "curve", "sell", sol=E9, tok=100),
    ]
    assert L.cycle("E", "X", g, {}, [], lambda q: 0, "curve").cost_unknown
    h = [
        L.Fill("E", "X", 1, 0, 0, -1, "curve", "buy", sol=100, tok=10),
        L.Fill("E", "X", 2, 0, 0, -1, "curve", "xfer_out", tok=4),
    ]
    c = L.cycle("E", "X", h, {}, [], lambda q: 0, "curve")
    assert (
        c.cost_unknown
        and c.xfer_out_basis == 40
        and c.stage_net("curve") == c.NET == -100
    )


def test_liquidation_hand():
    # 毛额 1000·100/1100＝1000/11；扣 1% 后 990/11＝90
    assert L.liquidation(100, 1000, 1000, cap=10**9, fee_bps=100) == 90
    # 封顶 50，再扣 1%：49.5 向下取整 49
    assert L.liquidation(100, 1000, 1000, cap=50, fee_bps=100) == 49
    assert L.mark_value(500, 10 * E9, 10_000) == 500_000_000


def test_order_key_unique():
    f, _, _ = scenario()
    assert L.order_key_unique(f)
    assert not L.order_key_unique(
        f + [L.Fill("Z", "X", 9, 4, 1, 0, "amm", "buy", sol=1, tok=1)]
    )


def test_t2a_flows_buyback_and_rewards():
    """GPT 07 反例：交易者投入 100（回购费 10、进池 90），回购金库再花 6 买入。按账户类对账，不会重复记。"""
    flows = [("trader", "pool", 90), ("trader", "buyback", 10), ("buyback", "pool", 6)]
    net = L.class_nets(flows)
    assert (net["trader"], net["pool"], net["buyback"]) == (-100, 96, 4) and sum(
        net.values()
    ) == 0
    assert L.t2a_residual(100, 0, 0, flows) == 0
    # 持有人奖励：创建者 → 奖励金库 → 交易者；事件口径 OUT 含奖励 2
    flows2 = flows + [("creator", "holder_vault", 2), ("holder_vault", "trader", 2)]
    assert L.t2a_residual(100, 0, 2, flows2) == 0
    assert L.t2a_residual(100, 0, 0, flows2) == 2  # 事件口径漏记奖励：残差暴露出来
    with pytest.raises(ValueError):
        L.class_nets([("trader", "nowhere", 1)])
    with pytest.raises(ValueError):
        L.class_nets([("trader", "pool", -1)])
