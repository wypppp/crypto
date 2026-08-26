from datetime import datetime, timedelta, timezone
from decimal import Decimal

from shadow_mm.replay import MakerReplayConfig, ShadowReplay


def event(event_type, payload, timestamp_ns, source="clob_ws"):
    return {
        "event_type": event_type,
        "source": source,
        "payload": payload,
        "received_at_ns": timestamp_ns,
        "socket_received_at_ns": timestamp_ns,
    }


def test_replay_submits_fills_merges_and_settles() -> None:
    base = datetime.now(timezone.utc)
    base_ns = int(base.timestamp() * 1_000_000_000)
    config = MakerReplayConfig(
        name="test",
        latency_seconds=5,
        quote_size=Decimal("2"),
        max_shares_per_token=Decimal("2"),
        stop_before_end_seconds=0,
    )
    replay = ShadowReplay([config])
    replay.process_event(
        event(
            "discovery_update",
            {
                "markets": [
                    {
                        "condition_id": "condition",
                        "symbol": "BTC",
                        "interval_minutes": 5,
                        "window_start": (base - timedelta(seconds=1)).isoformat(),
                        "end_time": (base + timedelta(minutes=5)).isoformat(),
                        "minimum_tick_size": "0.01",
                        "minimum_order_size": "1",
                        "fees_enabled": True,
                        "fee_schedule": {
                            "rate": 0.07,
                            "exponent": 1,
                            "rebateRate": 0.2,
                        },
                        "tokens": [
                            {"token_id": "up", "outcome": "Up"},
                            {"token_id": "down", "outcome": "Down"},
                        ],
                    }
                ]
            },
            base_ns,
            source="gamma",
        )
    )
    replay.process_event(
        event(
            "book",
            {
                "asset_id": "up",
                "bids": [{"price": "0.48", "size": "0.1"}],
                "asks": [{"price": "0.52", "size": "10"}],
            },
            base_ns,
        )
    )
    replay.process_event(
        event(
            "last_trade_price",
            {
                "asset_id": "up",
                "price": "0.47",
                "size": "1",
                "side": "SELL",
            },
            base_ns + 6_000_000_000,
        )
    )
    replay.process_event(
        event(
            "market_resolved",
            {
                "market": "condition",
                "assets_ids": ["up", "down"],
                "winning_asset_id": "up",
            },
            base_ns + 7_000_000_000,
        )
    )
    summary = replay.summary()["strategies"][0]
    assert summary["fills_n"] == 1
    assert summary["resolved_markets_n"] == 1
    assert summary["resolved_matched_notional"] == Decimal("0.96")
    assert summary["resolved_pnl"] == Decimal("1.04")
    assert summary["resolved_estimated_maker_rebate"] == Decimal("0.0069888")
    assert summary["resolved_pnl_with_estimated_maker_rebate"] == Decimal(
        "1.0469888"
    )
    assert summary["peak_external_capital"] == Decimal("0.96")


def test_replay_post_only_rejects_quote_that_crosses_during_latency() -> None:
    base = datetime.now(timezone.utc)
    base_ns = int(base.timestamp() * 1_000_000_000)
    config = MakerReplayConfig(
        name="test", latency_seconds=5, quote_size=Decimal("2"), stop_before_end_seconds=0
    )
    replay = ShadowReplay([config])
    replay.process_event(
        event(
            "discovery_update",
            {
                "markets": [
                    {
                        "condition_id": "condition",
                        "symbol": "BTC",
                        "interval_minutes": 5,
                        "window_start": (base - timedelta(seconds=1)).isoformat(),
                        "end_time": (base + timedelta(minutes=5)).isoformat(),
                        "minimum_tick_size": "0.01",
                        "minimum_order_size": "1",
                        "tokens": [
                            {"token_id": "up", "outcome": "Up"},
                            {"token_id": "down", "outcome": "Down"},
                        ],
                    }
                ]
            },
            base_ns,
            source="gamma",
        )
    )
    replay.process_event(
        event(
            "book",
            {
                "asset_id": "up",
                "bids": [{"price": "0.48", "size": "5"}],
                "asks": [{"price": "0.52", "size": "5"}],
            },
            base_ns,
        )
    )
    replay.process_event(
        event(
            "price_change",
            {
                "price_changes": [
                    {"asset_id": "up", "price": "0.48", "size": "5", "side": "SELL"}
                ]
            },
            base_ns + 4_000_000_000,
        )
    )
    replay.process_event(
        event(
            "last_trade_price",
            {"asset_id": "up", "price": "0.47", "size": "10", "side": "SELL"},
            base_ns + 6_000_000_000,
        )
    )
    summary = replay.summary()["strategies"][0]
    assert summary["post_only_rejections_n"] == 1
    assert summary["fills_n"] == 0


def test_replay_deduplicates_last_trade_transaction_hash() -> None:
    replay = ShadowReplay([])
    payload = {
        "transaction_hash": "0xtrade",
        "asset_id": "up",
        "timestamp": "1000",
        "price": "0.5",
        "size": "1",
        "side": "SELL",
    }
    replay.process_event(event("last_trade_price", payload, 2_000_000_000))
    replay.process_event(event("last_trade_price", payload, 2_100_000_000))
    assert replay.summary()["duplicate_trades_skipped_n"] == 1


def test_replay_ignores_stale_incremental_trade() -> None:
    replay = ShadowReplay([], max_clob_incremental_age_seconds=5)
    replay.process_event(
        event(
            "last_trade_price",
            {
                "transaction_hash": "0xstale",
                "asset_id": "up",
                "timestamp": "1000",
                "price": "0.5",
                "size": "1",
                "side": "SELL",
            },
            7_000_000_000,
        )
    )
    assert replay.summary()["stale_clob_incrementals_skipped"] == {
        "last_trade_price": 1
    }
