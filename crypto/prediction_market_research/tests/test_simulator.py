from decimal import Decimal

from shadow_mm.simulator import (
    ConservativeFillEngine,
    Portfolio,
    ShadowQuote,
    TradeTick,
    rounded_quote_prices,
)


def quote(**changes) -> ShadowQuote:
    values = {
        "quote_id": "q1",
        "token_id": "yes",
        "side": "BUY",
        "price": Decimal("0.48"),
        "size": Decimal("10"),
        "submitted_ns": 0,
        "active_ns": 5,
        "queue_ahead": Decimal("6"),
    }
    values.update(changes)
    return ShadowQuote(**values)


def test_latency_prevents_early_fill() -> None:
    engine = ConservativeFillEngine()
    engine.submit(quote())
    fills = engine.on_trade(TradeTick(4, "yes", Decimal("0.47"), Decimal("100"), "SELL"))
    assert fills == []


def test_strict_trade_through_fills_remaining_quote() -> None:
    engine = ConservativeFillEngine()
    engine.submit(quote())
    fills = engine.on_trade(TradeTick(6, "yes", Decimal("0.47"), Decimal("1"), "SELL"))
    assert len(fills) == 1
    assert fills[0].size == Decimal("10")
    assert fills[0].reason == "strict_trade_through"


def test_at_price_requires_queue_exhaustion() -> None:
    engine = ConservativeFillEngine()
    engine.submit(quote())
    assert engine.on_trade(TradeTick(6, "yes", Decimal("0.48"), Decimal("4"), "SELL")) == []
    fills = engine.on_trade(TradeTick(7, "yes", Decimal("0.48"), Decimal("5"), "SELL"))
    assert fills[0].size == Decimal("3")


def test_cancel_has_latency_and_can_be_picked_off() -> None:
    engine = ConservativeFillEngine()
    engine.submit(quote(queue_ahead=Decimal("0")))
    engine.cancel("q1", request_ns=6, latency_ns=5)
    fills = engine.on_trade(TradeTick(10, "yes", Decimal("0.47"), Decimal("1"), "SELL"))
    assert len(fills) == 1


def test_portfolio_tracks_external_capital_and_settlement() -> None:
    engine = ConservativeFillEngine()
    engine.submit(quote(size=Decimal("2"), queue_ahead=Decimal("0")))
    fill = engine.on_trade(TradeTick(6, "yes", Decimal("0.47"), Decimal("1"), "SELL"))[0]
    portfolio = Portfolio()
    portfolio.apply_fill(fill)
    assert portfolio.cash == Decimal("-0.96")
    assert portfolio.peak_external_capital == Decimal("0.96")
    portfolio.settle("yes", Decimal("1"))
    assert portfolio.cash == Decimal("1.04")


def test_quote_rounding_is_post_only_conservative() -> None:
    prices = rounded_quote_prices(
        fair_value=Decimal("0.503"),
        half_spread=Decimal("0.012"),
        tick_size=Decimal("0.01"),
    )
    assert prices == {"bid": Decimal("0.49"), "ask": Decimal("0.52")}


def test_complete_set_merge_releases_one_dollar_per_pair() -> None:
    portfolio = Portfolio(
        cash=Decimal("-1.2"),
        min_cash=Decimal("-1.2"),
        positions={"up": Decimal("2"), "down": Decimal("1.5")},
    )
    merged = portfolio.merge_complete_set("up", "down")
    assert merged == Decimal("1.5")
    assert portfolio.cash == Decimal("0.3")
    assert portfolio.positions == {"up": Decimal("0.5"), "down": Decimal("0.0")}


def test_liquidation_value_uses_executable_bid() -> None:
    portfolio = Portfolio(
        cash=Decimal("-0.4"), positions={"up": Decimal("1")}
    )
    assert portfolio.liquidation_value({"up": Decimal("0.35")}) == Decimal("-0.05")


def test_prune_removes_cancelled_quote_after_effective_time() -> None:
    engine = ConservativeFillEngine()
    engine.submit(quote())
    engine.cancel("q1", request_ns=6, latency_ns=5)
    assert engine.prune(10) == 0
    assert engine.prune(11) == 1


def test_late_trade_can_fill_quote_retired_after_trade_occurred() -> None:
    engine = ConservativeFillEngine(retired_retention_ns=100)
    engine.submit(quote(active_ns=5, queue_ahead=Decimal("0")))
    engine.cancel("q1", request_ns=8, latency_ns=5)
    assert engine.prune(20) == 1
    fills = engine.on_trade(
        TradeTick(10, "yes", Decimal("0.47"), Decimal("1"), "SELL")
    )
    assert len(fills) == 1


def test_late_trade_cannot_fill_quote_created_after_trade_occurred() -> None:
    engine = ConservativeFillEngine()
    engine.submit(quote(active_ns=15, queue_ahead=Decimal("0")))
    fills = engine.on_trade(
        TradeTick(10, "yes", Decimal("0.47"), Decimal("1"), "SELL")
    )
    assert fills == []
