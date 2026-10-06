"""screen_gate 的手算预期值测试（10-06）。周别由 weeks.py 的哈希规则决定，这里只用手算核过的日期。"""

import hashlib

import screen_gate as G
import weeks as W


def _first(cls):
    """2025-02-24 起第一个属于 cls 的周一（用 weeks.py 本身的规则找，避免手写哈希）。"""
    import datetime as dt

    d = W.FIRST_MONDAY
    while W.week_class(d) != cls:
        d += dt.timedelta(days=7)
    return d


def test_holdout_symbol_rule_hand():
    for s in ("SYNA", "BTC", "PEPE", "TRUMP"):
        want = hashlib.sha256(s.encode()).digest()[0] % 5 == 0
        assert G.is_holdout_symbol(s.lower()) == want  # 按大写判
    assert not G.is_holdout_symbol("SYNA")  # DQ-23 测试里核过：mod 5 ＝ 3


def test_date_ok_boundaries():
    dev, test = _first("dev"), _first("test")
    assert G.date_ok(dev) and not G.date_ok(test)
    assert not G.date_ok("2026-06-20")  # 封存周
    assert G.date_ok("2024-12-31")  # DQ-37 范围之前
    assert not G.date_ok("2026-10-05")  # 止日之后（也是前向批次）
    assert G.date_ok("2026-10-04") == (W.week_class("2026-10-04") == "dev")


def test_o1_row_rules():
    dev, test = _first("dev"), _first("test")
    assert G.o1_row_ok(dev, dev, listing_venue="OKX")
    assert not G.o1_row_ok(dev, test)  # TGE 日在检验周
    assert not G.o1_row_ok(test, dev)  # 发行日在检验周
    assert not G.o1_row_ok(None, "")  # 两个日期都缺
    assert G.o1_row_ok(dev, "TBD", listing_venue="Bybit")  # 只有一个日期，按它判
    assert not G.o1_row_ok(
        dev, dev, listing_venue="Binance Alpha"
    )  # 无代号又在币安上市
    assert G.o1_row_ok(
        dev, dev, symbol="SYNA", listing_venue="Binance"
    )  # 有代号、不命中留出
    hold = next(
        "T%d" % i for i in range(100) if G.is_holdout_symbol("T%d" % i)
    )  # 约 1/5 的代号命中
    assert not G.o1_row_ok(dev, dev, symbol=hold, listing_venue="OKX")


def test_gate_csv_reads_only_allowed_rows(tmp_path):
    dev, test = _first("dev"), _first("test")
    p = tmp_path / "x.csv"
    p.write_text(
        "platform,sale_date,tge_date,listing_venue,first_price_usd\n"
        "A,%s,%s,OKX,1.5\n"
        "B,%s,%s,OKX,9.9\n"
        "C,%s,%s,Binance,2.0\n" % (dev, dev, test, dev, dev, dev)
    )
    df, n_out = G.gate_csv(p)
    assert (
        n_out == 2
        and list(df["platform"]) == ["A"]
        and list(df["first_price_usd"]) == ["1.5"]
    )
