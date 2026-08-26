"""Read-only WebSocket collection for the shadow market-making experiment."""

import hashlib
import json
import signal
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .collector import make_event
from .config import CollectorConfig
from .market_filter import ClassifiedMarket, filter_short_crypto_markets
from .models import parse_json_list, parse_optional_bool
from .rest import PublicRestClient, summarize_exception
from .storage import JsonlEventWriter


def websocket_dependency() -> Any:
    try:
        import websocket
    except ImportError as exc:  # pragma: no cover - depends on deployment environment
        raise RuntimeError(
            "websocket-client is required; install requirements-shadow.txt"
        ) from exc
    return websocket


def decode_wire_message(raw: Any) -> Tuple[List[Dict[str, Any]], str]:
    if isinstance(raw, bytes):
        wire_text = raw.decode("utf-8", errors="replace")
    else:
        wire_text = str(raw)
    if wire_text.upper() in ("PING", "PONG", "NO NEW ASSETS"):
        return [{"protocol_message": wire_text.upper()}], wire_text
    parsed = json.loads(wire_text)
    if isinstance(parsed, dict):
        return [parsed], wire_text
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)], wire_text
    return [{"value": parsed}], wire_text


def market_record(item: ClassifiedMarket) -> Dict[str, Any]:
    market = item.market
    raw_fields = (
        "id",
        "conditionId",
        "questionID",
        "question",
        "slug",
        "description",
        "resolutionSource",
        "active",
        "closed",
        "acceptingOrders",
        "startTime",
        "eventStartTime",
        "endDate",
        "endDateIso",
        "clobTokenIds",
        "outcomes",
        "orderPriceMinTickSize",
        "orderMinSize",
        "feesEnabled",
        "feeSchedule",
        "feeType",
        "makerBaseFee",
        "takerBaseFee",
        "makerRebatesFeeShareBps",
        "rewardsMinSize",
        "rewardsMaxSpread",
        "holdingRewardsEnabled",
        "liquidity",
        "liquidityClob",
        "cryptoMarketConfigId",
        "cryptoMarketConfig",
        "version",
        "updatedAt",
    )
    events = market.raw.get("events") or []
    event_metadata: Dict[str, Any] = {}
    if events and isinstance(events, list) and isinstance(events[0], dict):
        candidate = events[0].get("eventMetadata")
        if isinstance(candidate, dict):
            event_metadata = candidate
    return {
        "condition_id": market.condition_id,
        "slug": market.slug,
        "question": market.question,
        "end_time": item.effective_end_time.isoformat()
        if item.effective_end_time
        else None,
        "gamma_end_time": market.end_time.isoformat() if market.end_time else None,
        "window_start": item.window_start.isoformat() if item.window_start else None,
        "symbol": item.symbol,
        "interval_minutes": item.interval_minutes,
        "tokens": [token.__dict__ for token in market.tokens],
        "minimum_tick_size": str(market.minimum_tick_size)
        if market.minimum_tick_size is not None
        else None,
        "minimum_order_size": str(market.minimum_order_size)
        if market.minimum_order_size is not None
        else None,
        "resolution_source": market.raw.get("resolutionSource"),
        "description": market.raw.get("description"),
        "fees_enabled": market.raw.get("feesEnabled"),
        "fee_schedule": market.raw.get("feeSchedule"),
        "rewards": market.raw.get("rewards"),
        "event_metadata": event_metadata,
        "price_to_beat": event_metadata.get("priceToBeat"),
        "raw_market": {key: market.raw.get(key) for key in raw_fields if key in market.raw},
    }


class MarketUniverse:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._markets: List[ClassifiedMarket] = []
        self._registry: Dict[str, ClassifiedMarket] = {}
        self._revision = 0

    def update(self, markets: Sequence[ClassifiedMarket]) -> int:
        with self._lock:
            old_ids = tuple(item.market.condition_id for item in self._markets)
            new_ids = tuple(item.market.condition_id for item in markets)
            self._markets = list(markets)
            for item in markets:
                if item.market.condition_id:
                    self._registry[item.market.condition_id] = item
            if old_ids != new_ids:
                self._revision += 1
            return self._revision

    def snapshot(self) -> Tuple[int, List[ClassifiedMarket]]:
        with self._lock:
            return self._revision, list(self._markets)

    def registry_snapshot(self) -> List[ClassifiedMarket]:
        with self._lock:
            return list(self._registry.values())


class DiscoveryWorker:
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        universe: MarketUniverse,
        stop_event: threading.Event,
        client_factory: Callable[..., PublicRestClient] = PublicRestClient,
    ) -> None:
        self.config = config
        self.writer = writer
        self.universe = universe
        self.stop_event = stop_event
        self.client_factory = client_factory
        self.refreshes = 0
        self.errors = 0

    def _select(self, raw: Sequence[Any]) -> List[ClassifiedMarket]:
        selected = filter_short_crypto_markets(
            raw, self.config.symbols, self.config.intervals_minutes
        )
        cutoff = datetime.now(timezone.utc).timestamp() - self.config.market_end_grace_seconds
        selected = [
            item
            for item in selected
            if item.effective_end_time is None
            or item.effective_end_time.timestamp() >= cutoff
        ]
        now = datetime.now(timezone.utc)
        grouped: Dict[Tuple[str, int], List[ClassifiedMarket]] = {}
        for item in selected:
            grouped.setdefault((item.symbol, item.interval_minutes), []).append(item)

        bounded: List[ClassifiedMarket] = []
        for key in sorted(grouped):
            rows = sorted(
                grouped[key],
                key=lambda item: item.effective_end_time
                or datetime.max.replace(tzinfo=timezone.utc),
            )
            started = [
                item
                for item in rows
                if item.window_start is None or item.window_start <= now
            ]
            future = [
                item
                for item in rows
                if item.window_start is not None and item.window_start > now
            ]
            keep_started = 1 + max(int(self.config.past_markets_per_series), 0)
            bounded.extend(started[-keep_started:])
            bounded.extend(
                future[: max(int(self.config.future_markets_per_series), 0)]
            )

        bounded.sort(
            key=lambda item: (
                item.effective_end_time or datetime.max.replace(tzinfo=timezone.utc),
                item.symbol,
                item.interval_minutes,
            )
        )
        return bounded[: self.config.max_markets]

    def refresh(self, client: PublicRestClient) -> List[ClassifiedMarket]:
        raw = client.gamma_markets(
            page_size=self.config.discovery_page_size,
            pages=self.config.discovery_pages,
            end_grace_seconds=self.config.market_end_grace_seconds,
        )
        selected = self._select(raw)
        prior_revision, _ = self.universe.snapshot()
        revision = self.universe.update(selected)
        changed = revision != prior_revision
        self.refreshes += 1
        self.writer.write(
            make_event(
                "gamma",
                "discovery_update" if changed else "discovery_heartbeat",
                {
                    "raw_markets_n": len(raw),
                    "selected_markets_n": len(selected),
                    "revision": revision,
                    # Essential metadata such as eventMetadata.priceToBeat can
                    # appear after a future market becomes current even when
                    # the condition-ID set is unchanged.
                    "markets": [market_record(item) for item in selected],
                    "condition_ids": [item.market.condition_id for item in selected],
                },
            )
        )
        return selected

    def run(self) -> None:
        client = self.client_factory(
            gamma_url=self.config.gamma_url,
            clob_url=self.config.clob_url,
            coinbase_url=self.config.coinbase_url,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        try:
            while not self.stop_event.is_set():
                refresh_ok = False
                try:
                    self.refresh(client)
                    refresh_ok = True
                except BaseException as exc:
                    self.errors += 1
                    self.writer.write(
                        make_event("discovery", "stream_error", summarize_exception(exc))
                    )
                wait_seconds = (
                    self.config.discovery_seconds
                    if refresh_ok
                    else min(self.config.discovery_seconds, 5.0)
                )
                self.stop_event.wait(max(wait_seconds, 0.25))
        finally:
            client.close()

class ClockWorker:
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        stop_event: threading.Event,
        client_factory: Callable[..., PublicRestClient] = PublicRestClient,
    ) -> None:
        self.config = config
        self.writer = writer
        self.stop_event = stop_event
        self.client_factory = client_factory
        self.samples = 0
        self.errors = 0

    def sample_server_clock(self, client: PublicRestClient) -> None:
        started_at_ns = time.time_ns()
        started_monotonic_ns = time.monotonic_ns()
        try:
            server_time = client.server_time()
            received_at_ns = time.time_ns()
            self.samples += 1
            self.writer.write(
                make_event(
                    "clob",
                    "server_time",
                    {
                        "server_time": server_time,
                        "request_started_at_ns": started_at_ns,
                        "response_received_at_ns": received_at_ns,
                        "request_midpoint_at_ns": (started_at_ns + received_at_ns) // 2,
                        "request_elapsed_ns": time.monotonic_ns()
                        - started_monotonic_ns,
                    },
                )
            )
        except BaseException as exc:
            self.errors += 1
            self.writer.write(
                make_event(
                    "clob",
                    "server_time_error",
                    summarize_exception(exc),
                )
            )

    def run(self) -> None:
        client = self.client_factory(
            gamma_url=self.config.gamma_url,
            clob_url=self.config.clob_url,
            coinbase_url=self.config.coinbase_url,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        try:
            while not self.stop_event.is_set():
                self.sample_server_clock(client)
                self.stop_event.wait(max(self.config.clock_poll_seconds, 0.25))
        finally:
            client.close()


class ResolutionWorker:
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        universe: MarketUniverse,
        stop_event: threading.Event,
        client_factory: Callable[..., PublicRestClient] = PublicRestClient,
    ) -> None:
        self.config = config
        self.writer = writer
        self.universe = universe
        self.stop_event = stop_event
        self.client_factory = client_factory
        self.resolved: set = set()
        self.polls = 0
        self.errors = 0

    @staticmethod
    def resolution_payload(
        observed: ClassifiedMarket, resolved_market: Any
    ) -> Optional[Dict[str, Any]]:
        raw = resolved_market.raw
        if not bool(parse_optional_bool(raw.get("closed"), False)):
            return None
        prices = parse_json_list(raw.get("outcomePrices"))
        if len(prices) != len(observed.market.tokens) or len(prices) != 2:
            return None
        try:
            numeric = [float(value) for value in prices]
        except (TypeError, ValueError):
            return None
        winners = [index for index, value in enumerate(numeric) if value >= 0.999]
        losers = [index for index, value in enumerate(numeric) if value <= 0.001]
        if len(winners) != 1 or len(losers) != 1:
            return None
        winner = observed.market.tokens[winners[0]]
        events = raw.get("events") or []
        event_metadata: Dict[str, Any] = {}
        if events and isinstance(events, list) and isinstance(events[0], dict):
            candidate = events[0].get("eventMetadata")
            if isinstance(candidate, dict):
                event_metadata = candidate
        return {
            "market": observed.market.condition_id,
            "condition_id": observed.market.condition_id,
            "market_slug": observed.market.slug,
            "winning_asset_id": winner.token_id,
            "winning_outcome": winner.outcome,
            "outcome_prices": numeric,
            "closed_time": raw.get("closedTime"),
            "resolution_status": raw.get("umaResolutionStatus"),
            "price_to_beat": event_metadata.get("priceToBeat"),
            "final_price": event_metadata.get("finalPrice"),
            "resolution_source": "gamma_closed_outcome_prices",
        }

    def poll_once(self, client: PublicRestClient) -> int:
        now = datetime.now(timezone.utc).timestamp()
        candidates = [
            item
            for item in self.universe.registry_snapshot()
            if item.market.condition_id not in self.resolved
            and item.effective_end_time is not None
            and item.effective_end_time.timestamp()
            + self.config.resolution_start_grace_seconds
            <= now
        ]
        resolved_n = 0
        for offset in range(0, len(candidates), 100):
            batch = candidates[offset : offset + 100]
            by_id = {item.market.condition_id: item for item in batch}
            rows = client.gamma_markets_by_condition_ids(by_id)
            for row in rows:
                observed = by_id.get(row.condition_id)
                if observed is None:
                    continue
                payload = self.resolution_payload(observed, row)
                if payload is None:
                    continue
                self.writer.write(
                    make_event("gamma_resolution", "market_resolved", payload)
                )
                self.resolved.add(row.condition_id)
                resolved_n += 1
        self.polls += 1
        return resolved_n

    def run(self) -> None:
        client = self.client_factory(
            gamma_url=self.config.gamma_url,
            clob_url=self.config.clob_url,
            coinbase_url=self.config.coinbase_url,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        try:
            while not self.stop_event.is_set():
                try:
                    self.poll_once(client)
                except BaseException as exc:
                    self.errors += 1
                    self.writer.write(
                        make_event(
                            "gamma_resolution",
                            "stream_error",
                            summarize_exception(exc),
                        )
                    )
                self.stop_event.wait(max(self.config.resolution_poll_seconds, 1.0))
        finally:
            client.close()


class BaseSocketStream:
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        stop_event: threading.Event,
        source: str,
        url: str,
        heartbeat_seconds: float,
        websocket_module: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.writer = writer
        self.stop_event = stop_event
        self.source = source
        self.url = url
        self.heartbeat_seconds = heartbeat_seconds
        self.websocket = websocket_module
        self.connections = 0
        self.reconnects = 0
        self.errors = 0
        self.messages = 0
        self.skipped_messages = 0
        self.event_counts: Counter = Counter()

    def _module(self) -> Any:
        if self.websocket is None:
            self.websocket = websocket_dependency()
        return self.websocket

    def _connect(self) -> Any:
        module = self._module()
        connection = module.create_connection(
            self.url,
            timeout=self.config.ws_connect_timeout_seconds,
            enable_multithread=True,
        )
        connection.settimeout(self.config.ws_read_timeout_seconds)
        return connection

    def _send_heartbeat(self, connection: Any) -> None:
        connection.send("PING")

    def _on_connected(self, connection: Any) -> None:
        raise NotImplementedError

    def _on_idle(self, connection: Any) -> None:
        return None

    def _event_context(
        self, payload: Dict[str, Any]
    ) -> Tuple[Optional[ClassifiedMarket], str, List[Dict[str, Any]]]:
        return None, str(payload.get("asset_id") or ""), []

    def _accept_payload(self, payload: Dict[str, Any]) -> bool:
        return True

    def _stream_context(self) -> Dict[str, Any]:
        return {}

    def _record_wire(self, raw: Any) -> None:
        received_at_ns = time.time_ns()
        try:
            messages, wire_text = decode_wire_message(raw)
        except (UnicodeError, ValueError, TypeError) as exc:
            self.errors += 1
            self.writer.write(
                make_event(
                    self.source,
                    "decode_error",
                    {"wire_preview": str(raw)[:500], **summarize_exception(exc)},
                )
            )
            return
        wire_hash = (
            hashlib.sha256(wire_text.encode("utf-8")).hexdigest()
            if self.config.enable_message_hashes
            else None
        )
        for payload in messages:
            if not self._accept_payload(payload):
                self.skipped_messages += 1
                continue
            market, token_id, refs = self._event_context(payload)
            event_type = str(
                payload.get("event_type")
                or payload.get("type")
                or payload.get("topic")
                or payload.get("e")
                or "protocol_message"
            )
            event = make_event(
                self.source,
                event_type,
                payload,
                market=market,
                token_id=token_id,
                include_payload_hash=self.config.enable_message_hashes,
            )
            event["socket_received_at_ns"] = received_at_ns
            event.update(self._stream_context())
            if wire_hash is not None:
                event["wire_sha256"] = wire_hash
            if refs:
                event["market_refs"] = refs
            self.writer.write(event)
            self.messages += 1
            self.event_counts[event_type] += 1

    def _receive(self, connection: Any) -> Optional[Any]:
        module = self._module()
        if not hasattr(connection, "recv_data"):
            return connection.recv()
        opcode, data = connection.recv_data(control_frame=True)
        if opcode == module.ABNF.OPCODE_CLOSE:
            status = getattr(connection, "status", None)
            if status is None and hasattr(connection, "getstatus"):
                status = connection.getstatus()
            reason = ""
            if isinstance(data, bytes) and len(data) > 2:
                reason = data[2:].decode("utf-8", errors="replace")
            self.writer.write(
                make_event(
                    self.source,
                    "stream_close",
                    {"close_status": status, "close_reason": reason},
                )
            )
            raise ConnectionError(
                "websocket closed status={} reason={}".format(status, reason)
            )
        if opcode in (module.ABNF.OPCODE_PING, module.ABNF.OPCODE_PONG):
            self.writer.write(
                make_event(
                    self.source,
                    "protocol_control",
                    {
                        "opcode": "ping"
                        if opcode == module.ABNF.OPCODE_PING
                        else "pong"
                    },
                )
            )
            return None
        return data

    def _session(self) -> None:
        module = self._module()
        connection = self._connect()
        self.connections += 1
        try:
            self._on_connected(connection)
            self.writer.write(
                {
                    **make_event(
                    self.source,
                    "stream_connected",
                    {"url": self.url, "connection_n": self.connections},
                    ),
                    **self._stream_context(),
                }
            )
            next_heartbeat = time.monotonic() + self.heartbeat_seconds
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now >= next_heartbeat:
                    self._send_heartbeat(connection)
                    next_heartbeat = now + self.heartbeat_seconds
                self._on_idle(connection)
                try:
                    raw = self._receive(connection)
                except module.WebSocketTimeoutException:
                    continue
                if raw is None:
                    continue
                if raw == "" or raw == b"":
                    # RTDS emits an empty text frame immediately after a valid
                    # subscription. It is not a close frame; close opcodes are
                    # handled explicitly in _receive.
                    self.writer.write(
                        make_event(self.source, "protocol_empty", {"ignored": True})
                    )
                    continue
                self._record_wire(raw)
        finally:
            try:
                connection.close()
            except BaseException:
                pass

    def run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            try:
                self._session()
                backoff = 1.0
            except BaseException as exc:
                if self.stop_event.is_set():
                    break
                self.errors += 1
                self.reconnects += 1
                self.writer.write(
                    {
                        **make_event(
                            self.source,
                            "stream_error",
                            {"retry_seconds": backoff, **summarize_exception(exc)},
                        ),
                        **self._stream_context(),
                    }
                )
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, self.config.reconnect_max_seconds)

    def summary(self) -> Dict[str, Any]:
        return {
            "connections_n": self.connections,
            "reconnects_n": self.reconnects,
            "errors_n": self.errors,
            "messages_n": self.messages,
            "skipped_messages_n": self.skipped_messages,
            "event_counts": dict(self.event_counts),
        }


class ClobMarketStream(BaseSocketStream):
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        universe: MarketUniverse,
        stop_event: threading.Event,
        websocket_module: Optional[Any] = None,
        allowed_symbols: Optional[Sequence[str]] = None,
        allowed_intervals: Optional[Sequence[int]] = None,
        shard_name: str = "all",
        token_shard_index: int = 0,
        token_shard_count: int = 1,
    ) -> None:
        super().__init__(
            config,
            writer,
            stop_event,
            source="clob_ws",
            url=config.clob_ws_url,
            heartbeat_seconds=config.clob_heartbeat_seconds,
            websocket_module=websocket_module,
        )
        self.universe = universe
        self.allowed_symbols = {
            str(symbol).upper() for symbol in (allowed_symbols or [])
        }
        self.allowed_intervals = {
            int(interval) for interval in (allowed_intervals or [])
        }
        self.shard_name = shard_name
        self.token_shard_count = max(int(token_shard_count), 1)
        self.token_shard_index = int(token_shard_index) % self.token_shard_count
        self.revision = -1
        self.subscribed = set()
        self.token_map: Dict[str, ClassifiedMarket] = {}
        self.filtered_price_changes = 0

    def _stream_context(self) -> Dict[str, Any]:
        return {"stream_name": self.shard_name}

    def _accept_payload(self, payload: Dict[str, Any]) -> bool:
        if payload.get("event_type") != "price_change":
            return True
        changes = payload.get("price_changes") or []
        if not isinstance(changes, list):
            return True
        depth_ticks = max(int(self.config.clob_price_change_depth_ticks), 0)
        kept: List[Dict[str, Any]] = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            item = self.token_map.get(str(change.get("asset_id") or ""))
            if item is None:
                continue
            side = str(change.get("side") or "").upper()
            anchor_key = "best_bid" if side == "BUY" else "best_ask"
            try:
                price = float(change["price"])
                anchor = float(change[anchor_key])
                tick = float(item.market.minimum_tick_size or 0.01)
            except (KeyError, TypeError, ValueError):
                # Preserve malformed/unfamiliar updates for auditability.
                kept.append(change)
                continue
            if abs(price - anchor) <= depth_ticks * tick + 1e-12:
                kept.append(change)
        self.filtered_price_changes += max(len(changes) - len(kept), 0)
        if not kept:
            return False
        payload["price_changes"] = kept
        return True

    def summary(self) -> Dict[str, Any]:
        answer = super().summary()
        answer["filtered_price_changes_n"] = self.filtered_price_changes
        return answer

    def _index(self, markets: Sequence[ClassifiedMarket]) -> Dict[str, ClassifiedMarket]:
        answer: Dict[str, ClassifiedMarket] = {}
        for item in markets:
            if self.allowed_symbols and item.symbol.upper() not in self.allowed_symbols:
                continue
            if (
                self.allowed_intervals
                and item.interval_minutes not in self.allowed_intervals
            ):
                continue
            for token_index, token in enumerate(item.market.tokens):
                if not token.token_id:
                    continue
                shard = token_index % self.token_shard_count
                if shard == self.token_shard_index:
                    answer[token.token_id] = item
        return answer

    def _on_connected(self, connection: Any) -> None:
        deadline = (
            time.monotonic()
            + self.config.market_discovery_startup_timeout_seconds
        )
        markets: List[ClassifiedMarket] = []
        token_map: Dict[str, ClassifiedMarket] = {}
        revision = -1
        while not token_map and not self.stop_event.is_set() and time.monotonic() < deadline:
            revision, markets = self.universe.snapshot()
            token_map = self._index(markets)
            if not token_map:
                self.stop_event.wait(0.1)
        if not token_map:
            raise RuntimeError(
                "no target markets discovered before subscription deadline for shard {}".format(
                    self.shard_name
                )
            )
        self.token_map = token_map
        self.subscribed = set(self.token_map)
        self.revision = revision
        connection.send(
            json.dumps(
                {
                    "assets_ids": sorted(self.subscribed),
                    "type": "market",
                    "custom_feature_enabled": True,
                },
                separators=(",", ":"),
            )
        )

    def _on_idle(self, connection: Any) -> None:
        revision, markets = self.universe.snapshot()
        if revision != self.revision:
            token_map = self._index(markets)
            desired = set(token_map)
            additions = sorted(desired - self.subscribed)
            removals = sorted(self.subscribed - desired)
            for operation, token_ids in (("subscribe", additions), ("unsubscribe", removals)):
                if token_ids:
                    connection.send(
                        json.dumps(
                            {"operation": operation, "assets_ids": token_ids},
                            separators=(",", ":"),
                        )
                    )
            self.writer.write(
                make_event(
                    self.source,
                    "subscription_update",
                    {
                        "revision": revision,
                        "shard_name": self.shard_name,
                        "subscribed": additions,
                        "unsubscribed": removals,
                        "active_token_ids_n": len(desired),
                    },
                )
            )
            self.token_map = token_map
            self.subscribed = desired
            self.revision = revision

    def _event_context(
        self, payload: Dict[str, Any]
    ) -> Tuple[Optional[ClassifiedMarket], str, List[Dict[str, Any]]]:
        token_ids = []
        if payload.get("asset_id") is not None:
            token_ids.append(str(payload["asset_id"]))
        for change in payload.get("price_changes", []) or []:
            if isinstance(change, dict) and change.get("asset_id") is not None:
                token_ids.append(str(change["asset_id"]))
        token_ids = list(dict.fromkeys(token_ids))
        refs = []
        for token_id in token_ids:
            item = self.token_map.get(token_id)
            if item is not None:
                refs.append(
                    {
                        "token_id": token_id,
                        "condition_id": item.market.condition_id,
                        "market_slug": item.market.slug,
                        "symbol": item.symbol,
                        "interval_minutes": item.interval_minutes,
                    }
                )
        single = self.token_map.get(token_ids[0]) if len(token_ids) == 1 else None
        return single, token_ids[0] if len(token_ids) == 1 else "", refs


class RtdsPriceStream(BaseSocketStream):
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        stop_event: threading.Event,
        websocket_module: Optional[Any] = None,
    ) -> None:
        super().__init__(
            config,
            writer,
            stop_event,
            source="polymarket_rtds",
            url=config.rtds_ws_url,
            heartbeat_seconds=config.rtds_heartbeat_seconds,
            websocket_module=websocket_module,
        )

    def _on_connected(self, connection: Any) -> None:
        # RTDS currently de-duplicates subscriptions by topic/type and can
        # silently retain only the first symbol filter. Subscribe once per
        # topic, then filter symbols locally to avoid a BTC-only dataset.
        subscriptions = [
            {"topic": topic, "type": "*"} for topic in self.config.rtds_topics
        ]
        connection.send(
            json.dumps(
                {"action": "subscribe", "subscriptions": subscriptions},
                separators=(",", ":"),
            )
        )

    def _accept_payload(self, payload: Dict[str, Any]) -> bool:
        body = payload.get("payload")
        if not isinstance(body, dict) or not body.get("symbol"):
            return True
        allowed = {"{}/usd".format(symbol.lower()) for symbol in self.config.symbols}
        return str(body["symbol"]).lower() in allowed


class CoinbaseSpotStream(BaseSocketStream):
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        stop_event: threading.Event,
        websocket_module: Optional[Any] = None,
    ) -> None:
        super().__init__(
            config,
            writer,
            stop_event,
            source="coinbase_ws",
            url=config.coinbase_ws_url,
            heartbeat_seconds=config.spot_heartbeat_seconds,
            websocket_module=websocket_module,
        )

    def _on_connected(self, connection: Any) -> None:
        products = ["{}-USD".format(symbol.upper()) for symbol in self.config.symbols]
        connection.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "product_ids": products,
                    "channels": ["ticker", "heartbeat"],
                },
                separators=(",", ":"),
            )
        )

    def _send_heartbeat(self, connection: Any) -> None:
        connection.ping()


class BinanceSpotStream(BaseSocketStream):
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        stop_event: threading.Event,
        websocket_module: Optional[Any] = None,
    ) -> None:
        super().__init__(
            config,
            writer,
            stop_event,
            source="binance_ws",
            url=config.binance_ws_url,
            heartbeat_seconds=config.spot_heartbeat_seconds,
            websocket_module=websocket_module,
        )

    def _on_connected(self, connection: Any) -> None:
        streams = []
        for symbol in self.config.symbols:
            pair = "{}usdt".format(symbol.lower())
            streams.extend((pair + "@bookTicker", pair + "@aggTrade"))
        connection.send(
            json.dumps(
                {"method": "SUBSCRIBE", "params": streams, "id": 1},
                separators=(",", ":"),
            )
        )

    def _send_heartbeat(self, connection: Any) -> None:
        connection.ping()


class KrakenSpotStream(BaseSocketStream):
    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        stop_event: threading.Event,
        websocket_module: Optional[Any] = None,
    ) -> None:
        super().__init__(
            config,
            writer,
            stop_event,
            source="kraken_ws",
            url=config.kraken_ws_url,
            heartbeat_seconds=config.spot_heartbeat_seconds,
            websocket_module=websocket_module,
        )

    def _on_connected(self, connection: Any) -> None:
        connection.send(
            json.dumps(
                {
                    "method": "subscribe",
                    "params": {
                        "channel": "ticker",
                        "symbol": [
                            "{}/USD".format(symbol.upper())
                            for symbol in self.config.symbols
                        ],
                        "event_trigger": "bbo",
                        "snapshot": True,
                    },
                    "req_id": 1,
                },
                separators=(",", ":"),
            )
        )

    def _send_heartbeat(self, connection: Any) -> None:
        connection.ping()


class WebSocketShadowCollector:
    """Orchestrate public WebSockets and discovery; contains no order methods."""

    def __init__(
        self,
        config: CollectorConfig,
        writer: JsonlEventWriter,
        websocket_module: Optional[Any] = None,
        discovery_client_factory: Callable[..., PublicRestClient] = PublicRestClient,
    ) -> None:
        self.config = config
        self.writer = writer
        self.stop_event = threading.Event()
        self.universe = MarketUniverse()
        self.discovery = DiscoveryWorker(
            config,
            writer,
            self.universe,
            self.stop_event,
            client_factory=discovery_client_factory,
        )
        self.clock = ClockWorker(
            config,
            writer,
            self.stop_event,
            client_factory=discovery_client_factory,
        )
        self.resolution = ResolutionWorker(
            config,
            writer,
            self.universe,
            self.stop_event,
            client_factory=discovery_client_factory,
        )
        if config.clob_shard_by_series:
            shard_specs = [
                (symbol, interval, shard_index)
                for symbol in config.symbols
                for interval in config.intervals_minutes
                for shard_index in range(
                    max(int(config.clob_token_shards_per_series), 1)
                )
            ]
        else:
            shard_specs = [("", 0, 0)]
        self.clob_streams: Dict[str, ClobMarketStream] = {}
        for symbol, interval, shard_index in shard_specs:
            shard_count = (
                max(int(config.clob_token_shards_per_series), 1)
                if config.clob_shard_by_series
                else 1
            )
            shard_name = (
                "{}-{}m-{}/{}".format(
                    symbol.upper(), interval, shard_index + 1, shard_count
                )
                if symbol and interval
                else "all"
            )
            self.clob_streams[shard_name] = ClobMarketStream(
                config,
                writer,
                self.universe,
                self.stop_event,
                websocket_module,
                allowed_symbols=[symbol] if symbol else None,
                allowed_intervals=[interval] if interval else None,
                shard_name=shard_name,
                token_shard_index=shard_index,
                token_shard_count=shard_count,
            )
        # Backward-compatible handle for callers that only inspect one stream.
        self.clob = next(iter(self.clob_streams.values()))
        self.rtds = RtdsPriceStream(config, writer, self.stop_event, websocket_module)
        self.coinbase = CoinbaseSpotStream(
            config, writer, self.stop_event, websocket_module
        )
        self.kraken = KrakenSpotStream(
            config, writer, self.stop_event, websocket_module
        )
        self.binance = BinanceSpotStream(
            config, writer, self.stop_event, websocket_module
        )

    def request_stop(self, *_: Any) -> None:
        self.stop_event.set()

    def run(self, duration_seconds: float) -> Dict[str, Any]:
        duration_seconds = max(duration_seconds, 0.0)
        old_int = signal.signal(signal.SIGINT, self.request_stop)
        old_term = signal.signal(signal.SIGTERM, self.request_stop)
        started = time.monotonic()
        self.writer.write(
            make_event(
                "shadow_ws",
                "run_start",
                {
                    "duration_seconds": duration_seconds,
                    "config": self.config.to_dict(),
                    "safety": "public_read_only_no_auth_no_order_methods",
                },
            )
        )
        threads: List[threading.Thread] = []
        try:
            if duration_seconds > 0:
                threads = [
                    threading.Thread(target=self.discovery.run, name="discovery", daemon=True),
                    threading.Thread(target=self.clock.run, name="clock", daemon=True),
                    threading.Thread(
                        target=self.resolution.run, name="resolution", daemon=True
                    ),
                    threading.Thread(target=self.rtds.run, name="rtds-ws", daemon=True),
                ]
                threads.extend(
                    threading.Thread(
                        target=stream.run,
                        name="clob-ws-{}".format(shard_name.lower()),
                        daemon=True,
                    )
                    for shard_name, stream in self.clob_streams.items()
                )
                if self.config.enable_coinbase_ws:
                    threads.append(
                        threading.Thread(
                            target=self.coinbase.run, name="coinbase-ws", daemon=True
                        )
                    )
                if self.config.enable_kraken_ws:
                    threads.append(
                        threading.Thread(
                            target=self.kraken.run, name="kraken-ws", daemon=True
                        )
                    )
                if self.config.enable_binance_ws:
                    threads.append(
                        threading.Thread(
                            target=self.binance.run, name="binance-ws", daemon=True
                        )
                    )
                for thread in threads:
                    thread.start()
                self.stop_event.wait(duration_seconds)
        finally:
            self.stop_event.set()
            for thread in threads:
                thread.join(timeout=self.config.ws_connect_timeout_seconds + 2)
            signal.signal(signal.SIGINT, old_int)
            signal.signal(signal.SIGTERM, old_term)
        revision, markets = self.universe.snapshot()
        self.writer.drain()
        clob_shard_summaries = {
            name: stream.summary() for name, stream in self.clob_streams.items()
        }
        clob_event_counts: Counter = Counter()
        for item in clob_shard_summaries.values():
            clob_event_counts.update(item["event_counts"])
        clob_summary = {
            "connections_n": sum(
                item["connections_n"] for item in clob_shard_summaries.values()
            ),
            "reconnects_n": sum(
                item["reconnects_n"] for item in clob_shard_summaries.values()
            ),
            "errors_n": sum(
                item["errors_n"] for item in clob_shard_summaries.values()
            ),
            "messages_n": sum(
                item["messages_n"] for item in clob_shard_summaries.values()
            ),
            "skipped_messages_n": sum(
                item["skipped_messages_n"] for item in clob_shard_summaries.values()
            ),
            "event_counts": dict(clob_event_counts),
            "shards": clob_shard_summaries,
        }
        summary = {
            "duration_seconds": time.monotonic() - started,
            "transport": "public_websocket_shadow_only",
            "market_revision": revision,
            "markets_n": len(markets),
            "discovery_refreshes_n": self.discovery.refreshes,
            "discovery_errors_n": self.discovery.errors,
            "clock_samples_n": self.clock.samples,
            "clock_errors_n": self.clock.errors,
            "resolution_polls_n": self.resolution.polls,
            "resolution_errors_n": self.resolution.errors,
            "resolved_markets_n": len(self.resolution.resolved),
            "clob": clob_summary,
            "rtds": self.rtds.summary(),
            "coinbase": self.coinbase.summary(),
            "kraken": self.kraken.summary(),
            "binance": self.binance.summary(),
            "writer": self.writer.summary(),
            "threads_still_alive": [thread.name for thread in threads if thread.is_alive()],
        }
        self.writer.write(make_event("shadow_ws", "run_complete", summary))
        return summary
