"""Streaming data-quality audit for a raw shadow capture."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .replay import iter_events


GAP_BUCKETS_MS = (
    10,
    25,
    50,
    100,
    250,
    500,
    1_000,
    2_000,
    5_000,
    10_000,
    30_000,
    60_000,
    300_000,
    900_000,
    3_600_000,
)


@dataclass
class GapStats:
    first_ns: Optional[int] = None
    last_ns: Optional[int] = None
    intervals_n: int = 0
    sum_ms: float = 0.0
    max_ms: float = 0.0
    out_of_order_n: int = 0
    buckets: Counter = field(default_factory=Counter)

    def observe(self, timestamp_ns: int) -> None:
        if timestamp_ns <= 0:
            return
        if self.first_ns is None:
            self.first_ns = timestamp_ns
        if self.last_ns is not None:
            if timestamp_ns < self.last_ns:
                self.out_of_order_n += 1
                return
            gap_ms = (timestamp_ns - self.last_ns) / 1_000_000
            self.intervals_n += 1
            self.sum_ms += gap_ms
            self.max_ms = max(self.max_ms, gap_ms)
            bucket = next(
                (bound for bound in GAP_BUCKETS_MS if gap_ms <= bound),
                ">3600000",
            )
            self.buckets[bucket] += 1
        self.last_ns = timestamp_ns

    def quantile_upper_bound_ms(self, probability: float) -> Optional[Any]:
        if self.intervals_n <= 0:
            return None
        target = max(int(self.intervals_n * probability + 0.999999), 1)
        cumulative = 0
        for bound in GAP_BUCKETS_MS:
            cumulative += self.buckets.get(bound, 0)
            if cumulative >= target:
                return bound
        return ">3600000"

    def to_dict(self) -> Dict[str, Any]:
        fresh_at_most_5s_n = sum(
            self.buckets.get(bound, 0)
            for bound in GAP_BUCKETS_MS
            if bound <= 5_000
        )
        return {
            "intervals_n": self.intervals_n,
            "mean_ms": self.sum_ms / self.intervals_n
            if self.intervals_n
            else None,
            "p50_upper_bound_ms": self.quantile_upper_bound_ms(0.50),
            "p95_upper_bound_ms": self.quantile_upper_bound_ms(0.95),
            "p99_upper_bound_ms": self.quantile_upper_bound_ms(0.99),
            "max_ms": self.max_ms if self.intervals_n else None,
            "observed_span_seconds": (self.last_ns - self.first_ns) / 1_000_000_000
            if self.first_ns is not None and self.last_ns is not None
            else None,
            "out_of_order_n": self.out_of_order_n,
            "at_most_5s_n": fresh_at_most_5s_n,
            "at_most_5s_fraction": (
                fresh_at_most_5s_n / self.intervals_n
                if self.intervals_n
                else None
            ),
        }


def _iso_ns(value: Any) -> Optional[int]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return int(parsed.timestamp() * 1_000_000_000)


def _message_groups(event: Dict[str, Any]) -> Set[str]:
    source = str(event.get("source") or "")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return set()
    groups: Set[str] = set()
    if source == "coinbase_ws":
        product = str(payload.get("product_id") or "")
        if product:
            groups.add("coinbase_ws|{}".format(product.split("-")[0].upper()))
    elif source == "kraken_ws":
        for row in payload.get("data", []) or []:
            if isinstance(row, dict) and row.get("symbol"):
                symbol = str(row["symbol"]).split("/")[0].upper()
                groups.add("kraken_ws|{}".format(symbol))
    elif source == "polymarket_rtds":
        body = payload.get("payload")
        if isinstance(body, dict) and body.get("symbol"):
            symbol = str(body["symbol"]).split("/")[0].upper()
            groups.add(
                "polymarket_rtds|{}|{}".format(payload.get("topic") or "", symbol)
            )
    elif source == "clob_ws":
        for ref in event.get("market_refs", []) or []:
            if isinstance(ref, dict) and ref.get("symbol"):
                groups.add(
                    "clob_ws|{}|{}m".format(
                        str(ref["symbol"]).upper(), ref.get("interval_minutes")
                    )
                )
        if event.get("symbol"):
            groups.add(
                "clob_ws|{}|{}m".format(
                    str(event["symbol"]).upper(), event.get("interval_minutes")
                )
            )
    return groups


def _source_timestamp_ns(event: Dict[str, Any]) -> Optional[int]:
    source = str(event.get("source") or "")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    if source == "coinbase_ws":
        return _iso_ns(payload.get("time"))
    if source == "kraken_ws":
        rows = payload.get("data", []) or []
        if rows and isinstance(rows[0], dict):
            return _iso_ns(rows[0].get("timestamp"))
    if source == "polymarket_rtds":
        body = payload.get("payload")
        if isinstance(body, dict) and body.get("timestamp") is not None:
            try:
                return int(body["timestamp"]) * 1_000_000
            except (TypeError, ValueError):
                return None
    if source == "clob_ws" and payload.get("timestamp") is not None:
        try:
            timestamp = int(payload["timestamp"])
            return timestamp * (1_000_000 if timestamp < 10**16 else 1)
        except (TypeError, ValueError):
            return None
    return None


def analyze_capture(path: Path) -> Dict[str, Any]:
    events_n = 0
    source_counts: Counter = Counter()
    event_counts: Counter = Counter()
    errors: Counter = Counter()
    group_counts: Counter = Counter()
    gaps: Dict[str, GapStats] = {}
    age_stats: Dict[str, GapStats] = {}
    age_negative: Counter = Counter()
    run_start: Dict[str, Any] = {}
    run_complete: Dict[str, Any] = {}
    first_ns: Optional[int] = None
    last_ns: Optional[int] = None
    discovery_markets: Set[str] = set()
    market_windows: Dict[str, Tuple[Optional[int], Optional[int]]] = {}
    market_first_seen_ns: Dict[str, int] = {}
    clock_samples = 0

    for event in iter_events(path):
        events_n += 1
        source = str(event.get("source") or "")
        event_type = str(event.get("event_type") or "")
        source_counts[source] += 1
        event_counts["{}|{}".format(source, event_type)] += 1
        received_ns = int(
            event.get("socket_received_at_ns") or event.get("received_at_ns") or 0
        )
        arrival_ns = int(event.get("monotonic_ns") or received_ns)
        if arrival_ns > 0:
            first_ns = arrival_ns if first_ns is None else min(first_ns, arrival_ns)
            last_ns = arrival_ns if last_ns is None else max(last_ns, arrival_ns)
        if event_type in {
            "stream_error",
            "decode_error",
            "server_time_error",
            "stream_close",
        }:
            errors["{}|{}".format(source, event_type)] += 1
        payload = event.get("payload")
        if source == "shadow_ws" and event_type == "run_start" and isinstance(payload, dict):
            run_start = payload
        elif source == "shadow_ws" and event_type == "run_complete" and isinstance(payload, dict):
            run_complete = payload
        elif event_type in {"discovery_update", "discovery_heartbeat"} and isinstance(payload, dict):
            discovery_markets.update(str(item) for item in payload.get("condition_ids", []))
            for row in payload.get("markets", []) or []:
                if not isinstance(row, dict):
                    continue
                condition_id = str(row.get("condition_id") or "")
                if condition_id:
                    market_first_seen_ns.setdefault(condition_id, received_ns)
                    market_windows[condition_id] = (
                        _iso_ns(row.get("window_start")),
                        _iso_ns(row.get("end_time")),
                    )
        elif source == "clob" and event_type == "server_time":
            clock_samples += 1

        groups = _message_groups(event)
        for group in groups:
            group_counts[group] += 1
            gaps.setdefault(group, GapStats()).observe(arrival_ns)
        source_ns = _source_timestamp_ns(event)
        if source_ns is not None and received_ns > 0:
            age_ns = received_ns - source_ns
            if age_ns < 0:
                age_negative[source] += 1
            else:
                # Reuse the fixed histogram by presenting message age as a
                # synthetic interval from zero.
                age_keys = [source, "{}|{}".format(source, event_type)]
                stream_name = str(event.get("stream_name") or "")
                if stream_name:
                    age_keys.extend(
                        [
                            "{}|stream|{}".format(source, stream_name),
                            "{}|stream|{}|{}".format(
                                source, stream_name, event_type
                            ),
                        ]
                    )
                if source == "clob_ws":
                    condition_id = str(
                        event.get("condition_id")
                        or payload.get("market")
                        or payload.get("condition_id")
                        or ""
                    )
                    window = market_windows.get(condition_id)
                    if window is not None:
                        start_ns, end_ns = window
                        if (
                            (start_ns is None or received_ns >= start_ns)
                            and (end_ns is None or received_ns <= end_ns)
                        ):
                            age_keys.append(
                                "{}|active_market|{}".format(source, event_type)
                            )
                            first_seen_ns = market_first_seen_ns.get(condition_id)
                            if (
                                start_ns is not None
                                and first_seen_ns is not None
                                and first_seen_ns <= start_ns
                            ):
                                age_keys.append(
                                    "{}|preobserved_active_market|{}".format(
                                        source, event_type
                                    )
                                )
                for age_key in age_keys:
                    stat = age_stats.setdefault(
                        age_key, GapStats(first_ns=0, last_ns=0)
                    )
                    stat.last_ns = 0
                    stat.observe(age_ns)
                    stat.last_ns = 0

    config = run_start.get("config", {}) if isinstance(run_start, dict) else {}
    symbols = [str(item).upper() for item in config.get("symbols", [])]
    intervals = [int(item) for item in config.get("intervals_minutes", [])]
    expected: Set[str] = set()
    if config.get("enable_coinbase_ws"):
        expected.update("coinbase_ws|{}".format(symbol) for symbol in symbols)
    if config.get("enable_kraken_ws"):
        expected.update("kraken_ws|{}".format(symbol) for symbol in symbols)
    for topic in config.get("rtds_topics", []):
        expected.update(
            "polymarket_rtds|{}|{}".format(topic, symbol) for symbol in symbols
        )
    expected.update(
        "clob_ws|{}|{}m".format(symbol, interval)
        for symbol in symbols
        for interval in intervals
    )
    observed = set(group_counts)
    hard_error_count = sum(
        count
        for key, count in errors.items()
        if key.endswith("|decode_error") or key.endswith("|server_time_error")
    )
    writer_summary = run_complete.get("writer", {}) if run_complete else {}
    checks = {
        "has_run_start": bool(run_start),
        "has_run_complete": bool(run_complete),
        "no_decode_or_clock_errors": hard_error_count == 0,
        "no_threads_left_alive": not run_complete.get("threads_still_alive", ["missing"])
        if run_complete
        else False,
        "market_discovery_succeeded": bool(discovery_markets),
        "server_clock_sampled": clock_samples > 0,
        "all_expected_stream_groups_observed": not (expected - observed),
        "writer_dropped_zero_events": writer_summary.get("events_dropped_n") == 0,
        "writer_worker_healthy": writer_summary.get("worker_error") is None
        if writer_summary
        else False,
    }
    capture_seconds = (
        (last_ns - first_ns) / 1_000_000_000
        if first_ns is not None and last_ns is not None
        else None
    )
    gap_reports: Dict[str, Dict[str, Any]] = {}
    for key in sorted(gaps):
        report = gaps[key].to_dict()
        span = report.get("observed_span_seconds")
        report["observed_span_fraction"] = (
            span / capture_seconds
            if span is not None and capture_seconds and capture_seconds > 0
            else None
        )
        gap_reports[key] = report
    clob_trade_age = age_stats.get(
        "clob_ws|preobserved_active_market|last_trade_price"
    )
    clob_p95 = (
        clob_trade_age.quantile_upper_bound_ms(0.95)
        if clob_trade_age is not None
        else None
    )
    rtds_expected = [
        key for key in expected if key.startswith("polymarket_rtds|")
    ]
    rtds_coverage = [
        gap_reports.get(key, {}).get("observed_span_fraction")
        for key in rtds_expected
    ]
    checks["preobserved_active_clob_last_trade_samples_at_least_30"] = (
        clob_trade_age is not None and clob_trade_age.intervals_n >= 30
    )
    checks["preobserved_active_clob_last_trade_age_p95_at_most_5s"] = (
        isinstance(clob_p95, (int, float)) and clob_p95 <= 5000
    )
    checks["rtds_group_span_at_least_99pct"] = bool(rtds_coverage) and all(
        value is not None and value >= 0.99 for value in rtds_coverage
    )
    return {
        "input": str(path),
        "events_n": events_n,
        "capture_seconds": capture_seconds,
        "markets_observed_n": len(discovery_markets),
        "clock_samples_n": clock_samples,
        "source_counts": dict(sorted(source_counts.items())),
        "source_event_counts": dict(sorted(event_counts.items())),
        "errors": dict(sorted(errors.items())),
        "stream_errors_present": any(
            key.endswith("|stream_error") or key.endswith("|stream_close")
            for key in errors
        ),
        "stream_group_counts": dict(sorted(group_counts.items())),
        "stream_group_gaps": gap_reports,
        "source_message_age": {
            key: {
                **age_stats[key].to_dict(),
                "negative_age_n": age_negative.get(key, 0),
            }
            for key in sorted(set(age_stats) | set(age_negative))
        },
        "missing_expected_stream_groups": sorted(expected - observed),
        "checks": checks,
        "ready_for_pilot_capture": all(checks.values()),
        "run_complete": run_complete,
    }
