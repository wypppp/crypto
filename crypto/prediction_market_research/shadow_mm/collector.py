import hashlib
import json
import signal
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import CollectorConfig
from .market_filter import ClassifiedMarket, filter_short_crypto_markets
from .rest import PublicRestClient, summarize_exception
from .storage import JsonlEventWriter


SCHEMA_VERSION = 1


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def make_event(
    source: str,
    event_type: str,
    payload: Any,
    market: Optional[ClassifiedMarket] = None,
    token_id: str = "",
    include_payload_hash: bool = True,
) -> Dict[str, Any]:
    wall_ns = time.time_ns()
    event: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "received_at": utc_now_text(),
        "received_at_ns": wall_ns,
        "monotonic_ns": time.monotonic_ns(),
        "source": source,
        "event_type": event_type,
        "token_id": token_id,
        "payload": payload,
    }
    if market is not None:
        event.update(
            {
                "condition_id": market.market.condition_id,
                "market_slug": market.market.slug,
                "question": market.market.question,
                "symbol": market.symbol,
                "interval_minutes": market.interval_minutes,
            }
        )
    if include_payload_hash:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        event["payload_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return event


class ShadowCollector:
    """Collect public market data. This class has no authenticated endpoints."""

    def __init__(self, config: CollectorConfig, writer: JsonlEventWriter) -> None:
        self.config = config
        self.writer = writer
        self.client = PublicRestClient(
            gamma_url=config.gamma_url,
            clob_url=config.clob_url,
            coinbase_url=config.coinbase_url,
            timeout_seconds=config.request_timeout_seconds,
        )
        self.markets: List[ClassifiedMarket] = []
        self.stop_requested = False
        self._last_discovery_monotonic = 0.0

    def request_stop(self, *_: Any) -> None:
        self.stop_requested = True

    def discover(self) -> List[ClassifiedMarket]:
        raw = self.client.gamma_markets(
            page_size=self.config.discovery_page_size,
            pages=self.config.discovery_pages,
        )
        selected = filter_short_crypto_markets(
            raw,
            symbols=self.config.symbols,
            intervals=self.config.intervals_minutes,
        )
        selected.sort(
            key=lambda item: (
                item.effective_end_time
                or datetime.max.replace(tzinfo=timezone.utc),
                item.symbol,
                item.interval_minutes,
            )
        )
        self.markets = selected[: self.config.max_markets]
        self._last_discovery_monotonic = time.monotonic()
        self.writer.write(
            make_event(
                "gamma",
                "discovery",
                {
                    "raw_markets_n": len(raw),
                    "selected_markets_n": len(self.markets),
                    "markets": [
                        {
                            "condition_id": item.market.condition_id,
                            "slug": item.market.slug,
                            "question": item.market.question,
                            "end_time": item.effective_end_time.isoformat()
                            if item.effective_end_time
                            else None,
                            "symbol": item.symbol,
                            "interval_minutes": item.interval_minutes,
                            "tokens": [token.__dict__ for token in item.market.tokens],
                            "minimum_tick_size": str(item.market.minimum_tick_size)
                            if item.market.minimum_tick_size is not None
                            else None,
                            "minimum_order_size": str(item.market.minimum_order_size)
                            if item.market.minimum_order_size is not None
                            else None,
                        }
                        for item in self.markets
                    ],
                },
            )
        )
        return self.markets

    def _tasks(self) -> List[Tuple[str, str, Optional[ClassifiedMarket], str]]:
        tasks: List[Tuple[str, str, Optional[ClassifiedMarket], str]] = []
        for symbol in sorted({market.symbol for market in self.markets}):
            tasks.append(("spot", symbol, None, ""))
        for market in self.markets:
            for token in market.market.tokens:
                tasks.append(("book", token.token_id, market, token.token_id))
                tasks.append(("last_trade", token.token_id, market, token.token_id))
        return tasks

    def _execute_task(
        self, task: Tuple[str, str, Optional[ClassifiedMarket], str]
    ) -> Dict[str, Any]:
        kind, argument, market, token_id = task
        started = time.monotonic_ns()
        try:
            if kind == "spot":
                payload = self.client.coinbase_ticker(argument)
                source = "coinbase"
                event_type = "spot_ticker"
            elif kind == "book":
                payload = self.client.book(argument)
                source = "clob"
                event_type = "book_snapshot"
            elif kind == "last_trade":
                payload = self.client.last_trade_price(argument)
                source = "clob"
                event_type = "last_trade_price"
            else:
                raise ValueError("unknown task kind: {}".format(kind))
            event = make_event(source, event_type, payload, market=market, token_id=token_id)
            event["request_elapsed_ns"] = time.monotonic_ns() - started
            return event
        except BaseException as exc:
            event = make_event(
                "collector",
                "request_error",
                {"task": kind, "argument": argument, **summarize_exception(exc)},
                market=market,
                token_id=token_id,
            )
            event["request_elapsed_ns"] = time.monotonic_ns() - started
            return event

    def poll_once(self) -> int:
        try:
            server_time = self.client.server_time()
            self.writer.write(make_event("clob", "server_time", server_time))
        except BaseException as exc:
            self.writer.write(
                make_event("collector", "request_error", {"task": "server_time", **summarize_exception(exc)})
            )
        tasks = self._tasks()
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = [executor.submit(self._execute_task, task) for task in tasks]
            for future in as_completed(futures):
                self.writer.write(future.result())
        self.writer.write(
            make_event(
                "collector",
                "poll_complete",
                {"tasks_n": len(tasks), "markets_n": len(self.markets)},
            )
        )
        return len(tasks)

    def run(self, duration_seconds: float) -> Dict[str, Any]:
        old_int = signal.signal(signal.SIGINT, self.request_stop)
        old_term = signal.signal(signal.SIGTERM, self.request_stop)
        started = time.monotonic()
        polls = 0
        tasks = 0
        try:
            while not self.stop_requested:
                now = time.monotonic()
                if now - started >= duration_seconds:
                    break
                if not self.markets or now - self._last_discovery_monotonic >= self.config.discovery_seconds:
                    try:
                        self.discover()
                    except BaseException as exc:
                        self.writer.write(
                            make_event("collector", "discovery_error", summarize_exception(exc))
                        )
                if self.markets:
                    poll_started = time.monotonic()
                    tasks += self.poll_once()
                    polls += 1
                    elapsed = time.monotonic() - poll_started
                    remaining = self.config.poll_seconds - elapsed
                    if remaining > 0:
                        time.sleep(min(remaining, max(duration_seconds - (time.monotonic() - started), 0)))
                else:
                    time.sleep(min(self.config.poll_seconds, 2.0))
        finally:
            signal.signal(signal.SIGINT, old_int)
            signal.signal(signal.SIGTERM, old_term)
            self.client.close()
        summary = {
            "duration_seconds": time.monotonic() - started,
            "polls_n": polls,
            "tasks_n": tasks,
            "markets_n": len(self.markets),
            "transport": "rest_poll_smoke_only",
            "writer": self.writer.summary(),
        }
        self.writer.write(make_event("collector", "run_complete", summary))
        return summary


def output_path(config: CollectorConfig) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(config.output_dir) / "raw_rest_{}.jsonl".format(stamp)
