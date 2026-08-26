import json
from datetime import datetime, timezone

from shadow_mm.market_filter import classify_short_crypto_market
from shadow_mm.models import Market


def row(question: str, slug: str = "") -> dict:
    return {
        "conditionId": "0xabc",
        "question": question,
        "slug": slug,
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "clobTokenIds": json.dumps(["yes-token", "no-token"]),
        "outcomes": json.dumps(["Up", "Down"]),
        "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5,
    }


def test_classifies_5m_bitcoin_up_down() -> None:
    market = Market.from_gamma(row("Bitcoin Up or Down - August 25, 5:00-5:05 ET"))
    answer = classify_short_crypto_market(market, ["BTC", "ETH"], [5, 15])
    assert answer is not None
    assert answer.symbol == "BTC"
    assert answer.interval_minutes == 5


def test_classifies_15_minute_slug() -> None:
    market = Market.from_gamma(
        row("Ethereum Up or Down", "ethereum-up-or-down-15-minute-1787000000")
    )
    answer = classify_short_crypto_market(market, ["ETH"], [15])
    assert answer is not None
    assert answer.symbol == "ETH"
    assert answer.interval_minutes == 15
    assert answer.window_start == datetime.fromtimestamp(1787000000, tz=timezone.utc)
    assert answer.effective_end_time == datetime.fromtimestamp(
        1787000900, tz=timezone.utc
    )


def test_classifies_cross_hour_clock_range() -> None:
    market = Market.from_gamma(
        row("Bitcoin Up or Down - August 25, 5:55-6:00 PM ET")
    )
    answer = classify_short_crypto_market(market, ["BTC"], [5, 15])
    assert answer is not None
    assert answer.interval_minutes == 5


def test_classifies_15_minute_clock_range() -> None:
    market = Market.from_gamma(
        row("Ethereum Up or Down - August 25, 11:45 PM-12:00 AM ET")
    )
    answer = classify_short_crypto_market(market, ["ETH"], [5, 15])
    assert answer is not None
    assert answer.interval_minutes == 15


def test_rejects_long_horizon_price_market() -> None:
    market = Market.from_gamma(row("Will Bitcoin be above $150,000 by December?"))
    assert classify_short_crypto_market(market, ["BTC"], [5, 15]) is None


def test_rejects_closed_market() -> None:
    payload = row("Solana Up or Down - 5 minutes")
    payload["closed"] = True
    market = Market.from_gamma(payload)
    assert classify_short_crypto_market(market, ["SOL"], [5]) is None


def test_string_booleans_are_not_treated_as_truthy() -> None:
    payload = row("Bitcoin Up or Down - 5 minutes")
    payload.update({"active": "false", "closed": "false", "acceptingOrders": "false"})
    market = Market.from_gamma(payload)
    assert market.active is False
    assert market.closed is False
    assert market.accepting_orders is False
    assert classify_short_crypto_market(market, ["BTC"], [5]) is None


def test_gamma_full_end_date_wins_over_date_only_iso() -> None:
    payload = row("Bitcoin Up or Down - 5 minutes")
    payload["endDateIso"] = "2026-08-25"
    payload["endDate"] = "2026-08-25T07:50:00Z"
    market = Market.from_gamma(payload)
    assert market.end_time == datetime(2026, 8, 25, 7, 50, tzinfo=timezone.utc)
