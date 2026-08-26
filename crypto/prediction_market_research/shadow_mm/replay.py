"""Deterministic replay of public market data into conservative shadow orders."""

import gzip
import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .models import parse_timestamp
from .fair_value import FairValueModel
from .simulator import ConservativeFillEngine, Portfolio, ShadowQuote, TradeTick


ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass
class TokenBook:
    bids: Dict[Decimal, Decimal] = field(default_factory=dict)
    asks: Dict[Decimal, Decimal] = field(default_factory=dict)

    @staticmethod
    def _levels(values: Any) -> Dict[Decimal, Decimal]:
        answer: Dict[Decimal, Decimal] = {}
        for row in values or []:
            if not isinstance(row, dict):
                continue
            try:
                price = Decimal(str(row["price"]))
                size = Decimal(str(row["size"]))
            except (KeyError, TypeError, ValueError):
                continue
            if size > 0:
                answer[price] = size
        return answer

    def replace(self, payload: Dict[str, Any]) -> None:
        self.bids = self._levels(payload.get("bids"))
        self.asks = self._levels(payload.get("asks"))

    def change(self, side: str, price: Decimal, size: Decimal) -> None:
        levels = self.bids if side.upper() == "BUY" else self.asks
        if size <= 0:
            levels.pop(price, None)
        else:
            levels[price] = size

    @property
    def best_bid(self) -> Optional[Decimal]:
        return max(self.bids, default=None)

    @property
    def best_ask(self) -> Optional[Decimal]:
        return min(self.asks, default=None)


@dataclass(frozen=True)
class ReplayMarket:
    condition_id: str
    token_ids: Tuple[str, ...]
    outcomes: Dict[str, str]
    window_start_ns: Optional[int]
    end_ns: Optional[int]
    tick_size: Decimal
    minimum_order_size: Decimal
    symbol: str
    interval_minutes: int
    fees_enabled: bool
    fee_rate: Decimal
    fee_exponent: int
    maker_rebate_rate: Decimal
    price_to_beat: Optional[Decimal]

    @classmethod
    def from_record(cls, row: Dict[str, Any]) -> "ReplayMarket":
        tokens = row.get("tokens") or []
        token_ids = tuple(str(token.get("token_id")) for token in tokens if token.get("token_id"))
        outcomes = {
            str(token.get("token_id")): str(token.get("outcome") or "")
            for token in tokens
            if token.get("token_id")
        }
        start = parse_timestamp(row.get("window_start"))
        end = parse_timestamp(row.get("end_time"))
        fee_schedule = row.get("fee_schedule") or {}
        if not isinstance(fee_schedule, dict):
            fee_schedule = {}
        price_to_beat = row.get("price_to_beat")
        return cls(
            condition_id=str(row.get("condition_id") or ""),
            token_ids=token_ids,
            outcomes=outcomes,
            window_start_ns=int(start.timestamp() * 1_000_000_000) if start else None,
            end_ns=int(end.timestamp() * 1_000_000_000) if end else None,
            tick_size=Decimal(str(row.get("minimum_tick_size") or "0.01")),
            minimum_order_size=Decimal(str(row.get("minimum_order_size") or "1")),
            symbol=str(row.get("symbol") or ""),
            interval_minutes=int(row.get("interval_minutes") or 0),
            fees_enabled=bool(row.get("fees_enabled")),
            fee_rate=Decimal(str(fee_schedule.get("rate") or "0")),
            fee_exponent=int(fee_schedule.get("exponent") or 1),
            maker_rebate_rate=Decimal(
                str(fee_schedule.get("rebateRate") or "0")
            ),
            price_to_beat=Decimal(str(price_to_beat))
            if price_to_beat not in (None, "")
            else None,
        )

    def maker_rebate(self, price: Decimal, shares: Decimal) -> Decimal:
        if (
            not self.fees_enabled
            or self.fee_rate <= 0
            or self.maker_rebate_rate <= 0
        ):
            return ZERO
        curve = price * (ONE - price)
        return (
            shares
            * self.fee_rate
            * (curve ** max(self.fee_exponent, 1))
            * self.maker_rebate_rate
        )


@dataclass(frozen=True)
class MakerReplayConfig:
    name: str
    latency_seconds: float
    quote_size: Decimal
    policy: str = "join_bbo"
    stop_before_end_seconds: float = 15.0
    max_shares_per_token: Decimal = Decimal("50")
    max_unpaired_shares_per_market: Decimal = Decimal("15")
    half_spread: Decimal = Decimal("0.01")
    start_before_end_seconds: Optional[float] = None

    @property
    def latency_ns(self) -> int:
        return int(self.latency_seconds * 1_000_000_000)


class MakerReplayStrategy:
    """BUY both outcomes; complete sets are merged instead of naked shorting."""

    def __init__(
        self,
        config: MakerReplayConfig,
        books: Dict[str, TokenBook],
        markets: Dict[str, ReplayMarket],
        token_market: Dict[str, str],
        fair_values: Optional[Dict[str, Decimal]] = None,
    ) -> None:
        self.config = config
        self.books = books
        self.markets = markets
        self.token_market = token_market
        self.fair_values = fair_values if fair_values is not None else {}
        self.engine = ConservativeFillEngine()
        self.portfolio = Portfolio()
        self.current_quote: Dict[str, str] = {}
        self.activated: Set[str] = set()
        self.quote_condition: Dict[str, str] = {}
        self.sequence = 0
        self.quotes_submitted = 0
        self.post_only_rejections = 0
        self.fills_n = 0
        self.filled_shares = ZERO
        self.matched_notional = ZERO
        self.merges = ZERO
        self.market_cash: Dict[str, Decimal] = {}
        self.market_notional: Dict[str, Decimal] = {}
        self.market_estimated_rebate: Dict[str, Decimal] = {}
        self.resolved_results: Dict[str, Dict[str, Any]] = {}
        self.fill_reasons: Dict[str, int] = {}
        self.fill_diagnostics: List[Dict[str, Any]] = []

    def _market_for(self, token_id: str) -> Optional[ReplayMarket]:
        condition_id = self.token_market.get(token_id)
        return self.markets.get(condition_id) if condition_id else None

    def _cutoff_ns(self, market: ReplayMarket) -> Optional[int]:
        if market.end_ns is None:
            return None
        return market.end_ns - int(self.config.stop_before_end_seconds * 1_000_000_000)

    def _quote_start_ns(self, market: ReplayMarket) -> Optional[int]:
        if market.end_ns is None or self.config.start_before_end_seconds is None:
            return market.window_start_ns
        return market.end_ns - int(
            self.config.start_before_end_seconds * 1_000_000_000
        )

    def _cancel_current(self, token_id: str, timestamp_ns: int) -> None:
        quote_id = self.current_quote.get(token_id)
        quote = self.engine.quotes.get(quote_id) if quote_id else None
        if quote is not None and quote.cancel_effective_ns is None:
            self.engine.cancel(quote.quote_id, timestamp_ns, self.config.latency_ns)
        self.current_quote.pop(token_id, None)

    def _desired_bid(
        self, token_id: str, book: TokenBook, tick: Decimal
    ) -> Optional[Decimal]:
        ask = book.best_ask
        bid = book.best_bid
        if ask is None:
            return None
        ceiling = ask - tick
        if ceiling < tick:
            return None
        if bid is None and self.config.policy == "fair_join":
            return None
        if bid is None and self.config.policy != "fair_value":
            return ceiling
        if self.config.policy == "join_bbo":
            desired = bid
        elif self.config.policy == "midpoint":
            midpoint = (bid + ask) / Decimal("2")
            desired = (midpoint / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
            desired = max(desired, bid)
        elif self.config.policy == "fair_value":
            fair_value = self.fair_values.get(token_id)
            if fair_value is None:
                return None
            raw = fair_value - self.config.half_spread
            if raw < tick:
                return None
            desired = (raw / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
        elif self.config.policy == "fair_join":
            fair_value = self.fair_values.get(token_id)
            if fair_value is None or bid is None:
                return None
            # Keep queue priority at the visible BBO, but only when the model's
            # contemporaneous probability leaves the frozen safety margin.
            # Unlike fair_value this policy never improves or undercuts BBO.
            if bid > fair_value - self.config.half_spread:
                return None
            desired = bid
        else:
            raise ValueError("unknown maker replay policy: {}".format(self.config.policy))
        return min(max(desired, tick), ceiling)

    def advance(
        self, timestamp_ns: int, token_ids: Optional[Set[str]] = None
    ) -> None:
        candidates = (
            list(self.engine.quotes.values())
            if token_ids is None
            else [
                quote
                for token_id in token_ids
                for quote in self.engine.quotes_by_token.get(token_id, {}).values()
            ]
        )
        for quote in candidates:
            market = self._market_for(quote.token_id)
            cutoff = self._cutoff_ns(market) if market else None
            if cutoff is not None and timestamp_ns >= cutoff and quote.cancel_effective_ns is None:
                self.engine.cancel(quote.quote_id, timestamp_ns, self.config.latency_ns)
            if quote.quote_id in self.activated or quote.active_ns > timestamp_ns:
                continue
            book = self.books.get(quote.token_id, TokenBook())
            if book.best_ask is not None and quote.price >= book.best_ask:
                quote.expires_ns = quote.active_ns
                self.post_only_rejections += 1
            else:
                self.activated.add(quote.quote_id)
        self.engine.prune(timestamp_ns, token_ids)
        current_items = (
            list(self.current_quote.items())
            if token_ids is None
            else [
                (token_id, self.current_quote[token_id])
                for token_id in token_ids
                if token_id in self.current_quote
            ]
        )
        for token_id, quote_id in current_items:
            if quote_id not in self.engine.quotes:
                self.current_quote.pop(token_id, None)

    def observe_book(self, token_id: str, timestamp_ns: int) -> None:
        book = self.books[token_id]
        for quote in self.engine.quotes_by_token.get(token_id, {}).values():
            if (
                quote.token_id == token_id
                and quote.quote_id not in self.activated
                and timestamp_ns < quote.active_ns
            ):
                quote.queue_ahead = max(
                    quote.queue_ahead, book.bids.get(quote.price, ZERO)
                )

        market = self._market_for(token_id)
        if market is None:
            return
        cutoff = self._cutoff_ns(market)
        quote_start = self._quote_start_ns(market)
        if (
            quote_start is not None
            and timestamp_ns < quote_start
        ) or (cutoff is not None and timestamp_ns >= cutoff):
            self._cancel_current(token_id, timestamp_ns)
            return
        desired = self._desired_bid(token_id, book, market.tick_size)
        if desired is None:
            self._cancel_current(token_id, timestamp_ns)
            return

        quote_id = self.current_quote.get(token_id)
        current = self.engine.quotes.get(quote_id) if quote_id else None
        if current is not None and current.price == desired and current.remaining > 0:
            return

        position = max(self.portfolio.positions.get(token_id, ZERO), ZERO)
        outstanding = sum(
            quote.remaining
            for quote in self.engine.quotes_by_token.get(token_id, {}).values()
            if quote.remaining > 0
            and (quote.expires_ns is None or timestamp_ns < quote.expires_ns)
            and (
                quote.cancel_effective_ns is None
                or timestamp_ns < quote.cancel_effective_ns
            )
        )
        capacity = self.config.max_shares_per_token - position - outstanding
        if len(market.token_ids) == 2:
            other_token = next(
                item for item in market.token_ids if item != token_id
            )
            other_position = max(
                self.portfolio.positions.get(other_token, ZERO), ZERO
            )
            unpaired_on_this_side = max(position - other_position, ZERO)
            capacity = min(
                capacity,
                self.config.max_unpaired_shares_per_market
                - unpaired_on_this_side
                - outstanding,
            )
        if capacity <= 0:
            self._cancel_current(token_id, timestamp_ns)
            return
        if current is not None:
            self._cancel_current(token_id, timestamp_ns)

        size = min(
            max(self.config.quote_size, market.minimum_order_size), capacity
        )
        if size < market.minimum_order_size:
            return
        self.sequence += 1
        new_id = "{}-{}".format(self.config.name, self.sequence)
        quote = ShadowQuote(
            quote_id=new_id,
            token_id=token_id,
            side="BUY",
            price=desired,
            size=size,
            submitted_ns=timestamp_ns,
            active_ns=timestamp_ns + self.config.latency_ns,
            expires_ns=market.end_ns,
            queue_ahead=book.bids.get(desired, ZERO),
        )
        self.engine.submit(quote)
        self.current_quote[token_id] = new_id
        self.quote_condition[new_id] = market.condition_id
        self.quotes_submitted += 1

    def on_trade(self, trade: TradeTick) -> None:
        fills = self.engine.on_trade(trade)
        for fill in fills:
            condition_id = self.quote_condition[fill.quote_id]
            notional = fill.price * fill.size
            self.portfolio.apply_fill(fill)
            self.market_cash[condition_id] = self.market_cash.get(condition_id, ZERO) - notional
            self.market_notional[condition_id] = (
                self.market_notional.get(condition_id, ZERO) + notional
            )
            self.fills_n += 1
            self.filled_shares += fill.size
            self.matched_notional += notional
            self.fill_reasons[fill.reason] = self.fill_reasons.get(fill.reason, 0) + 1
            market = self.markets.get(condition_id)
            fair_value = self.fair_values.get(fill.token_id)
            self.fill_diagnostics.append(
                {
                    "condition_id": condition_id,
                    "token_id": fill.token_id,
                    "timestamp_ns": fill.timestamp_ns,
                    "price": fill.price,
                    "size": fill.size,
                    "fair_value": fair_value,
                    "model_edge_per_share": fair_value - fill.price
                    if fair_value is not None
                    else None,
                    "reason": fill.reason,
                }
            )
            if market is not None:
                self.market_estimated_rebate[condition_id] = (
                    self.market_estimated_rebate.get(condition_id, ZERO)
                    + market.maker_rebate(fill.price, fill.size)
                )
            if market is not None and len(market.token_ids) == 2:
                merged = self.portfolio.merge_complete_set(*market.token_ids)
                if merged > 0:
                    self.market_cash[condition_id] += merged
                    self.merges += merged

    def settle_market(
        self, condition_id: str, winning_token_id: str, timestamp_ns: int
    ) -> None:
        if condition_id in self.resolved_results:
            return
        market = self.markets.get(condition_id)
        if market is None:
            return
        for token_id in market.token_ids:
            self._cancel_current(token_id, timestamp_ns)
            payout = self.portfolio.settle(
                token_id, ONE if token_id == winning_token_id else ZERO
            )
            self.market_cash[condition_id] = self.market_cash.get(condition_id, ZERO) + payout
        pnl = self.market_cash.get(condition_id, ZERO)
        notional = self.market_notional.get(condition_id, ZERO)
        estimated_rebate = self.market_estimated_rebate.get(condition_id, ZERO)
        diagnostics = [
            row
            for row in self.fill_diagnostics
            if row["condition_id"] == condition_id
        ]
        forecast_rows = [row for row in diagnostics if row["fair_value"] is not None]
        forecast_shares = sum((row["size"] for row in forecast_rows), ZERO)
        model_expected_pnl = sum(
            (row["model_edge_per_share"] * row["size"] for row in forecast_rows),
            ZERO,
        )
        winning_value = lambda row: ONE if row["token_id"] == winning_token_id else ZERO
        forecast_brier = (
            sum(
                (
                    ((row["fair_value"] - winning_value(row)) ** 2) * row["size"]
                    for row in forecast_rows
                ),
                ZERO,
            )
            / forecast_shares
            if forecast_shares > 0
            else None
        )
        self.resolved_results[condition_id] = {
            "condition_id": condition_id,
            "symbol": market.symbol,
            "interval_minutes": market.interval_minutes,
            "winning_token_id": winning_token_id,
            "pnl": pnl,
            "estimated_maker_rebate": estimated_rebate,
            "pnl_with_estimated_maker_rebate": pnl + estimated_rebate,
            "matched_notional": notional,
            "edge": pnl / notional if notional > 0 else None,
            "forecast_fills_n": len(forecast_rows),
            "forecast_shares": forecast_shares,
            "model_expected_pnl": model_expected_pnl,
            "model_expected_edge": model_expected_pnl / notional
            if notional > 0
            else None,
            "fill_weighted_brier": forecast_brier,
        }

    def summary(self) -> Dict[str, Any]:
        executable_bids = {
            token_id: book.best_bid or ZERO for token_id, book in self.books.items()
        }
        resolved_notional = sum(
            (row["matched_notional"] for row in self.resolved_results.values()), ZERO
        )
        resolved_pnl = sum(
            (row["pnl"] for row in self.resolved_results.values()), ZERO
        )
        resolved_rebate = sum(
            (
                row["estimated_maker_rebate"]
                for row in self.resolved_results.values()
            ),
            ZERO,
        )
        estimated_rebate = sum(self.market_estimated_rebate.values(), ZERO)
        resolved_ids = set(self.resolved_results)
        resolved_fill_diagnostics = [
            row
            for row in self.fill_diagnostics
            if row["condition_id"] in resolved_ids
        ]
        model_expected_pnl = sum(
            (
                row["model_edge_per_share"] * row["size"]
                for row in resolved_fill_diagnostics
                if row["model_edge_per_share"] is not None
            ),
            ZERO,
        )
        return {
            "name": self.config.name,
            "policy": self.config.policy,
            "latency_seconds": self.config.latency_seconds,
            "quote_size": self.config.quote_size,
            "max_unpaired_shares_per_market": self.config.max_unpaired_shares_per_market,
            "start_before_end_seconds": self.config.start_before_end_seconds,
            "quotes_submitted_n": self.quotes_submitted,
            "post_only_rejections_n": self.post_only_rejections,
            "fills_n": self.fills_n,
            "filled_shares": self.filled_shares,
            "matched_notional": self.matched_notional,
            "resolved_markets_n": len(self.resolved_results),
            "resolved_matched_notional": resolved_notional,
            "resolved_pnl": resolved_pnl,
            "estimated_maker_rebate": estimated_rebate,
            "resolved_estimated_maker_rebate": resolved_rebate,
            "resolved_pnl_with_estimated_maker_rebate": resolved_pnl
            + resolved_rebate,
            "resolved_edge": resolved_pnl / resolved_notional
            if resolved_notional > 0
            else None,
            "resolved_edge_with_estimated_maker_rebate": (
                (resolved_pnl + resolved_rebate) / resolved_notional
                if resolved_notional > 0
                else None
            ),
            "cash": self.portfolio.cash,
            "liquidation_value": self.portfolio.liquidation_value(executable_bids),
            "peak_external_capital": self.portfolio.peak_external_capital,
            "merged_complete_sets": self.merges,
            "fill_reasons": dict(self.fill_reasons),
            "resolved_model_expected_pnl": model_expected_pnl,
            "resolved_model_expected_edge": model_expected_pnl / resolved_notional
            if resolved_notional > 0
            else None,
            "fill_diagnostics": resolved_fill_diagnostics,
            "open_positions": {
                token_id: size
                for token_id, size in self.portfolio.positions.items()
                if size != 0
            },
        }


class ShadowReplay:
    def __init__(
        self,
        configs: Sequence[MakerReplayConfig],
        max_clob_incremental_age_seconds: float = 5.0,
        price_to_beat_overrides: Optional[Dict[str, Decimal]] = None,
    ) -> None:
        self.books: Dict[str, TokenBook] = {}
        self.markets: Dict[str, ReplayMarket] = {}
        self.token_market: Dict[str, str] = {}
        self.fair_values: Dict[str, Decimal] = {}
        self.price_to_beat_overrides = price_to_beat_overrides or {}
        self.fair_model = FairValueModel(["BTC", "ETH", "SOL"])
        self.strategies = [
            MakerReplayStrategy(
                config,
                self.books,
                self.markets,
                self.token_market,
                self.fair_values,
            )
            for config in configs
        ]
        self.seen_trade_keys: OrderedDict = OrderedDict()
        self.duplicate_trades_skipped = 0
        self.max_clob_incremental_age_ns = int(
            max(max_clob_incremental_age_seconds, 0.0) * 1_000_000_000
        )
        self.stale_clob_incrementals_skipped: Dict[str, int] = {}

    @staticmethod
    def _timestamp_ns(event: Dict[str, Any]) -> int:
        return int(event.get("socket_received_at_ns") or event.get("received_at_ns") or 0)

    def _load_discovery(self, payload: Dict[str, Any]) -> None:
        for row in payload.get("markets", []) or []:
            if not isinstance(row, dict):
                continue
            market = ReplayMarket.from_record(row)
            if not market.condition_id or len(market.token_ids) != 2:
                continue
            if market.price_to_beat is None:
                target = self.price_to_beat_overrides.get(market.condition_id)
                if target is not None:
                    # Historical Gamma backfills expose the opening reference
                    # that was fixed before trading.  Only this fixed input is
                    # preloaded; finalPrice and the winning token remain unseen
                    # until the resolution event is processed in event order.
                    market = replace(market, price_to_beat=target)
            self.markets[market.condition_id] = market
            for token_id in market.token_ids:
                self.token_market[token_id] = market.condition_id
                self.books.setdefault(token_id, TokenBook())

    def _refresh_fair_values(self, timestamp_ns: int) -> None:
        for market in self.markets.values():
            probability_up = self.fair_model.probability_up(market, timestamp_ns)
            for token_id in market.token_ids:
                outcome = market.outcomes.get(token_id, "").lower()
                if probability_up is None:
                    self.fair_values.pop(token_id, None)
                elif outcome == "up":
                    self.fair_values[token_id] = probability_up
                elif outcome == "down":
                    self.fair_values[token_id] = ONE - probability_up

    def _new_trade(self, payload: Dict[str, Any]) -> bool:
        transaction_hash = str(payload.get("transaction_hash") or "")
        if transaction_hash:
            key = "{}|{}".format(transaction_hash, payload.get("asset_id") or "")
        else:
            canonical = json.dumps(
                {
                    name: payload.get(name)
                    for name in ("asset_id", "timestamp", "price", "size", "side")
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if key in self.seen_trade_keys:
            self.seen_trade_keys.move_to_end(key)
            self.duplicate_trades_skipped += 1
            return False
        self.seen_trade_keys[key] = None
        if len(self.seen_trade_keys) > 100000:
            self.seen_trade_keys.popitem(last=False)
        return True

    @staticmethod
    def _exchange_timestamp_ns(payload: Dict[str, Any], fallback_ns: int) -> int:
        try:
            value = int(payload.get("timestamp"))
        except (TypeError, ValueError):
            return fallback_ns
        return value * (1_000_000 if value < 10**16 else 1)

    def process_event(self, event: Dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        timestamp_ns = self._timestamp_ns(event)
        if event_type in ("discovery_update", "discovery_heartbeat"):
            self._load_discovery(payload)
            return
        if event_type == "market_resolved":
            condition_id = str(
                payload.get("market") or payload.get("condition_id") or ""
            )
            winning = str(payload.get("winning_asset_id") or "")
            market = self.markets.get(condition_id)
            affected = set(market.token_ids) if market is not None else None
            for strategy in self.strategies:
                strategy.advance(timestamp_ns, affected)
                strategy.settle_market(condition_id, winning, timestamp_ns)
            return
        reference_symbol = self.fair_model.update_event(event, timestamp_ns)
        if reference_symbol is not None:
            self._refresh_fair_values(timestamp_ns)
            affected_tokens: Set[str] = set()
            for market in self.markets.values():
                if market.symbol.upper() == reference_symbol:
                    affected_tokens.update(market.token_ids)
            fair_strategies = [
                strategy
                for strategy in self.strategies
                if strategy.config.policy == "fair_value"
            ]
            for strategy in fair_strategies:
                strategy.advance(timestamp_ns, affected_tokens)
            for market in self.markets.values():
                if market.symbol.upper() != reference_symbol:
                    continue
                for token_id in market.token_ids:
                    if token_id in self.books:
                        for strategy in fair_strategies:
                            strategy.observe_book(token_id, timestamp_ns)
            return
        if event.get("source") != "clob_ws":
            return
        if event_type in {"price_change", "last_trade_price"}:
            source_timestamp_ns = self._exchange_timestamp_ns(payload, timestamp_ns)
            if (
                self.max_clob_incremental_age_ns > 0
                and timestamp_ns - source_timestamp_ns
                > self.max_clob_incremental_age_ns
            ):
                self.stale_clob_incrementals_skipped[event_type] = (
                    self.stale_clob_incrementals_skipped.get(event_type, 0) + 1
                )
                return
        self._refresh_fair_values(timestamp_ns)
        changed_tokens: Set[str] = set()
        if event_type == "book":
            token_id = str(payload.get("asset_id") or "")
            if token_id:
                self.books.setdefault(token_id, TokenBook()).replace(payload)
                changed_tokens.add(token_id)
        elif event_type == "price_change":
            for change in payload.get("price_changes", []) or []:
                if not isinstance(change, dict):
                    continue
                try:
                    token_id = str(change["asset_id"])
                    price = Decimal(str(change["price"]))
                    size = Decimal(str(change["size"]))
                    side = str(change["side"])
                except (KeyError, TypeError, ValueError):
                    continue
                self.books.setdefault(token_id, TokenBook()).change(side, price, size)
                changed_tokens.add(token_id)
        elif event_type == "last_trade_price":
            if not self._new_trade(payload):
                return
            try:
                trade = TradeTick(
                    timestamp_ns=self._exchange_timestamp_ns(payload, timestamp_ns),
                    token_id=str(payload["asset_id"]),
                    price=Decimal(str(payload["price"])),
                    size=Decimal(str(payload["size"])),
                    aggressor_side=str(payload["side"]).upper(),
                )
            except (KeyError, TypeError, ValueError):
                return
            for strategy in self.strategies:
                strategy.advance(timestamp_ns, {trade.token_id})
                strategy.on_trade(trade)
        if changed_tokens:
            for strategy in self.strategies:
                strategy.advance(timestamp_ns, changed_tokens)
        for token_id in changed_tokens:
            for strategy in self.strategies:
                strategy.observe_book(token_id, timestamp_ns)

    def summary(self) -> Dict[str, Any]:
        return {
            "markets_seen_n": len(self.markets),
            "duplicate_trades_skipped_n": self.duplicate_trades_skipped,
            "stale_clob_incrementals_skipped": dict(
                self.stale_clob_incrementals_skipped
            ),
            "strategies": [strategy.summary() for strategy in self.strategies],
            "market_results": {
                strategy.config.name: list(strategy.resolved_results.values())
                for strategy in self.strategies
            },
        }


def iter_events(path: Path) -> Iterator[Dict[str, Any]]:
    opener = gzip.open if Path(path).suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(event, dict):
                yield event


def default_replay_configs() -> List[MakerReplayConfig]:
    answer = []
    for policy in ("join_bbo", "midpoint", "fair_value", "fair_join"):
        for latency in (5.0, 15.0, 30.0):
            name = "{}_{}s".format(policy, int(latency))
            answer.append(
                MakerReplayConfig(
                    name=name,
                    latency_seconds=latency,
                    quote_size=Decimal("5"),
                    policy=policy,
                )
            )
    return answer


def replay_path(path: Path, configs: Optional[Sequence[MakerReplayConfig]] = None) -> Dict[str, Any]:
    return replay_paths([path], configs)


def replay_paths(
    paths: Sequence[Path],
    configs: Optional[Sequence[MakerReplayConfig]] = None,
) -> Dict[str, Any]:
    # Resolution sidecars are conventionally appended after the raw capture.
    # Preload only their fixed opening target so captures made before Gamma
    # exposed eventMetadata can still exercise a causal fair-value model.
    targets: Dict[str, Decimal] = {}
    for path in paths[1:]:
        for event in iter_events(path):
            payload = event.get("payload")
            if event.get("event_type") != "market_resolved" or not isinstance(payload, dict):
                continue
            condition_id = str(payload.get("market") or payload.get("condition_id") or "")
            value = payload.get("price_to_beat")
            if condition_id and value not in (None, ""):
                try:
                    targets[condition_id] = Decimal(str(value))
                except (TypeError, ValueError):
                    continue
    replay = ShadowReplay(
        configs or default_replay_configs(),
        price_to_beat_overrides=targets,
    )
    events_n = 0
    for path in paths:
        for event in iter_events(path):
            replay.process_event(event)
            events_n += 1
    answer = replay.summary()
    answer["events_read_n"] = events_n
    answer["inputs"] = [str(path) for path in paths]
    answer["input"] = str(paths[0]) if len(paths) == 1 else None
    answer["price_to_beat_overrides_n"] = len(targets)
    return answer
