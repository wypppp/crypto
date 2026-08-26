import gzip
import json

from shadow_mm.quality import analyze_capture


def test_quality_audit_requires_preobserved_active_trade_sample(tmp_path) -> None:
    path = tmp_path / "capture.jsonl.gz"
    events = [
        {
            "source": "shadow_ws",
            "event_type": "run_start",
            "received_at_ns": 1,
            "payload": {
                "config": {
                    "symbols": ["BTC"],
                    "intervals_minutes": [5],
                    "rtds_topics": ["crypto_prices_twap_sixty"],
                    "enable_coinbase_ws": True,
                    "enable_kraken_ws": True,
                }
            },
        },
        {
            "source": "gamma",
            "event_type": "discovery_update",
            "received_at_ns": 2,
            "payload": {"condition_ids": ["condition"]},
        },
        {
            "source": "clob",
            "event_type": "server_time",
            "received_at_ns": 3,
            "payload": {"server_time": 1},
        },
        {
            "source": "coinbase_ws",
            "event_type": "ticker",
            "received_at_ns": 4,
            "payload": {"product_id": "BTC-USD"},
        },
        {
            "source": "kraken_ws",
            "event_type": "snapshot",
            "received_at_ns": 5,
            "payload": {"data": [{"symbol": "BTC/USD"}]},
        },
        {
            "source": "polymarket_rtds",
            "event_type": "update",
            "received_at_ns": 1,
            "payload": {
                "topic": "crypto_prices_twap_sixty",
                "payload": {"symbol": "btc/usd"},
            },
        },
        {
            "source": "polymarket_rtds",
            "event_type": "update",
            "received_at_ns": 8,
            "payload": {
                "topic": "crypto_prices_twap_sixty",
                "payload": {"symbol": "btc/usd"},
            },
        },
        {
            "source": "clob_ws",
            "event_type": "last_trade_price",
            "received_at_ns": 7,
            "payload": {"timestamp": 0},
            "market_refs": [
                {"symbol": "BTC", "interval_minutes": 5}
            ],
        },
        {
            "source": "shadow_ws",
            "event_type": "run_complete",
            "received_at_ns": 8,
            "payload": {
                "threads_still_alive": [],
                "writer": {"events_dropped_n": 0, "worker_error": None},
            },
        },
    ]
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    result = analyze_capture(path)
    assert result["ready_for_pilot_capture"] is False
    assert (
        result["checks"][
            "preobserved_active_clob_last_trade_samples_at_least_30"
        ]
        is False
    )
    assert result["missing_expected_stream_groups"] == []
    assert result["markets_observed_n"] == 1
