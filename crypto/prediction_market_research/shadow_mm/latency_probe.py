"""Minimal single-market CLOB latency probe: no event writer, no orders."""

import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .config import CollectorConfig
from .market_filter import filter_short_crypto_markets
from .rest import PublicRestClient
from .ws_collector import decode_wire_message, websocket_dependency


def _upper_quantile(values: List[float], probability: float) -> Any:
    if not values:
        return None
    ordered = sorted(values)
    index = max(math.ceil(len(ordered) * probability) - 1, 0)
    return ordered[index]


def run_probe(duration_seconds: float = 120.0) -> Dict[str, Any]:
    config = CollectorConfig(symbols=["BTC"], intervals_minutes=[5])
    client = PublicRestClient(
        gamma_url=config.gamma_url,
        clob_url=config.clob_url,
        coinbase_url=config.coinbase_url,
        timeout_seconds=config.request_timeout_seconds,
    )
    try:
        raw = client.gamma_markets(
            page_size=config.discovery_page_size,
            pages=config.discovery_pages,
            end_grace_seconds=config.market_end_grace_seconds,
        )
    finally:
        client.close()
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(seconds=max(duration_seconds, 0.0))
    candidates = [
        item
        for item in filter_short_crypto_markets(raw, ["BTC"], [5])
        if item.window_start is not None
        and item.window_start <= horizon
        and item.effective_end_time is not None
        and item.effective_end_time > now
    ]
    if not candidates:
        raise RuntimeError("no BTC-5m market overlapping probe horizon found")
    markets = sorted(candidates, key=lambda item: item.window_start)
    token_to_slug = {
        token.token_id: item.market.slug
        for item in markets
        for token in item.market.tokens
        if token.token_id
    }
    token_ids = sorted(token_to_slug)
    websocket = websocket_dependency()
    connection = websocket.create_connection(
        config.clob_ws_url,
        timeout=config.ws_connect_timeout_seconds,
        enable_multithread=True,
    )
    connection.settimeout(1.0)
    connection.send(
        json.dumps(
            {
                "assets_ids": token_ids,
                "type": "market",
                "custom_feature_enabled": True,
            },
            separators=(",", ":"),
        )
    )
    deadline = time.monotonic() + max(duration_seconds, 0.0)
    next_heartbeat = time.monotonic() + config.clob_heartbeat_seconds
    frames = 0
    messages = 0
    event_counts: Dict[str, int] = {}
    trade_ages_by_market: Dict[str, List[float]] = {
        item.market.slug: [] for item in markets
    }
    all_ages_ms: List[float] = []
    trade_ages_ms: List[float] = []
    started = time.monotonic()
    try:
        while time.monotonic() < deadline:
            if time.monotonic() >= next_heartbeat:
                connection.send("PING")
                next_heartbeat = time.monotonic() + config.clob_heartbeat_seconds
            try:
                raw_message = connection.recv()
            except websocket.WebSocketTimeoutException:
                continue
            received_ns = time.time_ns()
            frames += 1
            for payload in decode_wire_message(raw_message)[0]:
                messages += 1
                event_type = str(payload.get("event_type") or "protocol_message")
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
                try:
                    source_ms = int(payload["timestamp"])
                except (KeyError, TypeError, ValueError):
                    continue
                age_ms = received_ns / 1_000_000 - source_ms
                if age_ms >= 0:
                    all_ages_ms.append(age_ms)
                    if event_type == "last_trade_price":
                        trade_ages_ms.append(age_ms)
                        slug = token_to_slug.get(str(payload.get("asset_id") or ""))
                        if slug:
                            trade_ages_by_market[slug].append(age_ms)
    finally:
        connection.close()
    return {
        "duration_seconds": time.monotonic() - started,
        "market_slugs": [item.market.slug for item in markets],
        "condition_ids": [item.market.condition_id for item in markets],
        "tokens_n": len(token_ids),
        "frames_n": frames,
        "messages_n": messages,
        "event_counts": event_counts,
        "all_timestamped_age_ms": {
            "n": len(all_ages_ms),
            "p50": _upper_quantile(all_ages_ms, 0.50),
            "p95": _upper_quantile(all_ages_ms, 0.95),
            "p99": _upper_quantile(all_ages_ms, 0.99),
            "max": max(all_ages_ms) if all_ages_ms else None,
        },
        "last_trade_age_ms": {
            "n": len(trade_ages_ms),
            "p50": _upper_quantile(trade_ages_ms, 0.50),
            "p95": _upper_quantile(trade_ages_ms, 0.95),
            "p99": _upper_quantile(trade_ages_ms, 0.99),
            "max": max(trade_ages_ms) if trade_ages_ms else None,
        },
        "last_trade_by_market": {
            slug: {
                "n": len(values),
                "p50": _upper_quantile(values, 0.50),
                "p95": _upper_quantile(values, 0.95),
                "max": max(values) if values else None,
            }
            for slug, values in trade_ages_by_market.items()
        },
    }
