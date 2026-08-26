import json
import threading
from datetime import datetime, timedelta, timezone

from shadow_mm.config import CollectorConfig
from shadow_mm.market_filter import ClassifiedMarket
from shadow_mm.models import Market
from shadow_mm.storage import JsonlEventWriter
from shadow_mm.ws_collector import (
    BinanceSpotStream,
    ClobMarketStream,
    CoinbaseSpotStream,
    ClockWorker,
    DiscoveryWorker,
    MarketUniverse,
    KrakenSpotStream,
    RtdsPriceStream,
    ResolutionWorker,
    decode_wire_message,
)


class FakeConnection:
    def __init__(self) -> None:
        self.sent = []

    def send(self, value: str) -> None:
        self.sent.append(value)


def classified(
    condition_id: str = "0xabc", token_a: str = "up-token", token_b: str = "down-token"
) -> ClassifiedMarket:
    row = {
        "conditionId": condition_id,
        "question": "Bitcoin Up or Down - 5:00-5:05 PM ET",
        "slug": "bitcoin-up-or-down-5m",
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "endDate": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "clobTokenIds": json.dumps([token_a, token_b]),
        "outcomes": json.dumps(["Up", "Down"]),
    }
    return ClassifiedMarket(Market.from_gamma(row), "BTC", 5)


def test_decode_clob_list_and_heartbeat() -> None:
    messages, raw = decode_wire_message('[{"event_type":"book","asset_id":"1"}]')
    assert raw.startswith("[")
    assert messages[0]["event_type"] == "book"
    assert decode_wire_message("PONG")[0] == [{"protocol_message": "PONG"}]
    assert decode_wire_message("NO NEW ASSETS")[0] == [
        {"protocol_message": "NO NEW ASSETS"}
    ]


def test_clob_subscription_and_market_context(tmp_path) -> None:
    config = CollectorConfig()
    universe = MarketUniverse()
    item = classified()
    universe.update([item])
    connection = FakeConnection()
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        stream = ClobMarketStream(config, writer, universe, threading.Event())
        stream._on_connected(connection)
        initial = json.loads(connection.sent[0])
        assert initial["assets_ids"] == ["down-token", "up-token"]
        assert initial["custom_feature_enabled"] is True
        market, token_id, refs = stream._event_context(
            {
                "event_type": "last_trade_price",
                "asset_id": "up-token",
                "side": "BUY",
                "price": "0.51",
                "size": "7",
            }
        )
        assert market == item
        assert token_id == "up-token"
        assert refs[0]["condition_id"] == "0xabc"


def test_clob_dynamic_subscription_diff(tmp_path) -> None:
    config = CollectorConfig()
    universe = MarketUniverse()
    universe.update([classified()])
    connection = FakeConnection()
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        stream = ClobMarketStream(config, writer, universe, threading.Event())
        stream._on_connected(connection)
        universe.update([classified("0xdef", "new-up", "new-down")])
        stream._on_idle(connection)
    updates = [json.loads(value) for value in connection.sent[1:]]
    by_operation = {item["operation"]: item["assets_ids"] for item in updates}
    assert by_operation["subscribe"] == ["new-down", "new-up"]
    assert by_operation["unsubscribe"] == ["down-token", "up-token"]


def test_clob_shard_only_indexes_selected_series(tmp_path) -> None:
    config = CollectorConfig()
    universe = MarketUniverse()
    btc = classified("btc", "btc-up", "btc-down")
    eth = classified("eth", "eth-up", "eth-down")
    eth = ClassifiedMarket(eth.market, "ETH", 5)
    universe.update([btc, eth])
    connection = FakeConnection()
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        stream = ClobMarketStream(
            config,
            writer,
            universe,
            threading.Event(),
            allowed_symbols=["ETH"],
            allowed_intervals=[5],
            shard_name="ETH-5m",
        )
        stream._on_connected(connection)
    assert json.loads(connection.sent[0])["assets_ids"] == ["eth-down", "eth-up"]


def test_clob_token_subshards_are_disjoint_and_complete(tmp_path) -> None:
    config = CollectorConfig()
    universe = MarketUniverse()
    universe.update([classified("btc", "100", "101")])
    observed = []
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        for index in (0, 1):
            connection = FakeConnection()
            stream = ClobMarketStream(
                config,
                writer,
                universe,
                threading.Event(),
                token_shard_index=index,
                token_shard_count=2,
            )
            stream._on_connected(connection)
            observed.append(set(json.loads(connection.sent[0])["assets_ids"]))
    assert observed[0].isdisjoint(observed[1])
    assert observed[0] | observed[1] == {"100", "101"}


def test_clob_filters_deep_incremental_changes_but_keeps_near_bbo(tmp_path) -> None:
    config = CollectorConfig(clob_price_change_depth_ticks=2)
    universe = MarketUniverse()
    universe.update([classified("btc", "100", "101")])
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        stream = ClobMarketStream(config, writer, universe, threading.Event())
        stream.token_map = stream._index(universe.snapshot()[1])
        payload = {
            "event_type": "price_change",
            "price_changes": [
                {
                    "asset_id": "100",
                    "side": "BUY",
                    "price": "0.48",
                    "best_bid": "0.49",
                },
                {
                    "asset_id": "101",
                    "side": "SELL",
                    "price": "0.80",
                    "best_ask": "0.51",
                },
            ],
        }
        assert stream._accept_payload(payload)
    assert [row["asset_id"] for row in payload["price_changes"]] == ["100"]
    assert stream.filtered_price_changes == 1


def test_rtds_subscribes_once_per_topic_and_filters_locally(tmp_path) -> None:
    config = CollectorConfig(symbols=["BTC"], rtds_topics=["crypto_prices_chainlink"])
    connection = FakeConnection()
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        stream = RtdsPriceStream(config, writer, threading.Event())
        stream._on_connected(connection)
    payload = json.loads(connection.sent[0])
    subscription = payload["subscriptions"][0]
    assert subscription == {"topic": "crypto_prices_chainlink", "type": "*"}
    assert stream._accept_payload(
        {"payload": {"symbol": "btc/usd", "value": 100}}
    )
    assert not stream._accept_payload(
        {"payload": {"symbol": "zec/usd", "value": 10}}
    )


def test_public_spot_subscriptions_require_no_auth(tmp_path) -> None:
    config = CollectorConfig(symbols=["BTC", "ETH"])
    coinbase_connection = FakeConnection()
    kraken_connection = FakeConnection()
    binance_connection = FakeConnection()
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        coinbase = CoinbaseSpotStream(config, writer, threading.Event())
        kraken = KrakenSpotStream(config, writer, threading.Event())
        binance = BinanceSpotStream(config, writer, threading.Event())
        coinbase._on_connected(coinbase_connection)
        kraken._on_connected(kraken_connection)
        binance._on_connected(binance_connection)
    coinbase_payload = json.loads(coinbase_connection.sent[0])
    kraken_payload = json.loads(kraken_connection.sent[0])
    binance_payload = json.loads(binance_connection.sent[0])
    assert coinbase_payload == {
        "type": "subscribe",
        "product_ids": ["BTC-USD", "ETH-USD"],
        "channels": ["ticker", "heartbeat"],
    }
    assert "auth" not in coinbase_payload
    assert kraken_payload == {
        "method": "subscribe",
        "params": {
            "channel": "ticker",
            "symbol": ["BTC/USD", "ETH/USD"],
            "event_trigger": "bbo",
            "snapshot": True,
        },
        "req_id": 1,
    }
    assert binance_payload["params"] == [
        "btcusdt@bookTicker",
        "btcusdt@aggTrade",
        "ethusdt@bookTicker",
        "ethusdt@aggTrade",
    ]
    assert set(binance_payload) == {"method", "params", "id"}


def test_discovery_refresh_records_full_market_metadata(tmp_path) -> None:
    item = classified()

    class FakeClient:
        def gamma_markets(self, **kwargs):
            assert kwargs["end_grace_seconds"] == 120.0
            return [item.market]

    config = CollectorConfig(symbols=["BTC"], intervals_minutes=[5])
    universe = MarketUniverse()
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        worker = DiscoveryWorker(config, writer, universe, threading.Event())
        selected = worker.refresh(FakeClient())
    assert selected == [item]
    assert universe.snapshot()[0] == 1
    event = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
    assert event["payload"]["markets"][0]["raw_market"]["conditionId"] == "0xabc"
    assert event["event_type"] == "discovery_update"


def test_discovery_server_clock_records_round_trip_bounds(tmp_path) -> None:
    class FakeClient:
        def server_time(self):
            return 1234567890

    config = CollectorConfig()
    universe = MarketUniverse()
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        worker = ClockWorker(config, writer, threading.Event())
        worker.sample_server_clock(FakeClient())
    event = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
    payload = event["payload"]
    assert event["event_type"] == "server_time"
    assert payload["server_time"] == 1234567890
    assert payload["request_started_at_ns"] <= payload["request_midpoint_at_ns"]
    assert payload["request_midpoint_at_ns"] <= payload["response_received_at_ns"]
    assert worker.samples == 1
    assert worker.errors == 0


def test_resolution_requires_closed_binary_one_zero_prices() -> None:
    observed = classified()
    resolved = Market.from_gamma(
        {
            "conditionId": observed.market.condition_id,
            "closed": True,
            "outcomes": '["Up","Down"]',
            "clobTokenIds": '["up-token","down-token"]',
            "outcomePrices": '["1","0"]',
            "closedTime": "2026-08-25T00:00:00Z",
            "events": [
                {
                    "eventMetadata": {
                        "priceToBeat": 100,
                        "finalPrice": 101,
                    }
                }
            ],
        }
    )
    payload = ResolutionWorker.resolution_payload(observed, resolved)
    assert payload["winning_asset_id"] == "up-token"
    assert payload["resolution_source"] == "gamma_closed_outcome_prices"
    assert payload["price_to_beat"] == 100
    assert payload["final_price"] == 101

    unresolved = Market.from_gamma(
        {
            "conditionId": observed.market.condition_id,
            "closed": False,
            "outcomePrices": '["1","0"]',
        }
    )
    assert ResolutionWorker.resolution_payload(observed, unresolved) is None


def test_discovery_bounds_each_series_to_recent_current_and_next(tmp_path) -> None:
    now = int(datetime.now(timezone.utc).timestamp())

    def timed(start_delta: int) -> Market:
        start = now + start_delta
        payload = {
            "conditionId": "condition-{}".format(start),
            "question": "Bitcoin Up or Down - 5 minutes",
            "slug": "btc-updown-5m-{}".format(start),
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "clobTokenIds": json.dumps(["up-{}".format(start), "down-{}".format(start)]),
            "outcomes": json.dumps(["Up", "Down"]),
        }
        return Market.from_gamma(payload)

    raw = [timed(delta) for delta in (-600, -300, 0, 300, 600)]
    config = CollectorConfig(
        symbols=["BTC"],
        intervals_minutes=[5],
        market_end_grace_seconds=120,
        past_markets_per_series=1,
        future_markets_per_series=1,
    )
    with JsonlEventWriter(tmp_path / "events.jsonl", fsync_every=0) as writer:
        worker = DiscoveryWorker(config, writer, MarketUniverse(), threading.Event())
        selected = worker._select(raw)
    assert [item.window_start.timestamp() for item in selected] == [
        now - 300,
        now,
        now + 300,
    ]
