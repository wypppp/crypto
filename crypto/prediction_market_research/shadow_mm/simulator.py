from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
class TradeTick:
    timestamp_ns: int
    token_id: str
    price: Decimal
    size: Decimal
    aggressor_side: str  # BUY means taker bought; SELL means taker sold.


@dataclass
class ShadowQuote:
    quote_id: str
    token_id: str
    side: str
    price: Decimal
    size: Decimal
    submitted_ns: int
    active_ns: int
    expires_ns: Optional[int] = None
    cancel_effective_ns: Optional[int] = None
    queue_ahead: Decimal = Decimal("0")
    filled: Decimal = Decimal("0")

    @property
    def remaining(self) -> Decimal:
        return max(self.size - self.filled, Decimal("0"))

    def is_active(self, timestamp_ns: int) -> bool:
        if timestamp_ns < self.active_ns or self.remaining <= 0:
            return False
        if self.expires_ns is not None and timestamp_ns >= self.expires_ns:
            return False
        if self.cancel_effective_ns is not None and timestamp_ns >= self.cancel_effective_ns:
            return False
        return True


@dataclass(frozen=True)
class Fill:
    quote_id: str
    token_id: str
    side: str
    price: Decimal
    size: Decimal
    timestamp_ns: int
    reason: str


class ConservativeFillEngine:
    """Trade-through fill model with explicit latency and queue ahead."""

    def __init__(self, retired_retention_ns: int = 60_000_000_000) -> None:
        self.quotes: Dict[str, ShadowQuote] = {}
        self.quotes_by_token: Dict[str, Dict[str, ShadowQuote]] = {}
        self.retired_quotes: Dict[str, ShadowQuote] = {}
        self.retired_by_token: Dict[str, Dict[str, ShadowQuote]] = {}
        self.retired_queue: Deque[Tuple[int, str]] = deque()
        self.retired_retention_ns = max(int(retired_retention_ns), 0)

    def submit(self, quote: ShadowQuote) -> None:
        if quote.quote_id in self.quotes or quote.quote_id in self.retired_quotes:
            raise ValueError("duplicate quote_id")
        if quote.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if quote.price <= 0 or quote.price >= 1 or quote.size <= 0:
            raise ValueError("invalid binary quote price/size")
        self.quotes[quote.quote_id] = quote
        self.quotes_by_token.setdefault(quote.token_id, {})[quote.quote_id] = quote

    def cancel(self, quote_id: str, request_ns: int, latency_ns: int) -> None:
        quote = self.quotes[quote_id]
        effective = request_ns + max(latency_ns, 0)
        if quote.cancel_effective_ns is None or effective < quote.cancel_effective_ns:
            quote.cancel_effective_ns = effective

    def prune(
        self, timestamp_ns: int, token_ids: Optional[set] = None
    ) -> int:
        candidates = (
            list(self.quotes.values())
            if token_ids is None
            else [
                quote
                for token_id in token_ids
                for quote in self.quotes_by_token.get(token_id, {}).values()
            ]
        )
        removable = [
            quote.quote_id
            for quote in candidates
            if quote.remaining <= 0
            or (quote.expires_ns is not None and timestamp_ns >= quote.expires_ns)
            or (
                quote.cancel_effective_ns is not None
                and timestamp_ns >= quote.cancel_effective_ns
            )
        ]
        for quote_id in removable:
            quote = self.quotes.pop(quote_id)
            self.quotes_by_token.get(quote.token_id, {}).pop(quote_id, None)
            self.retired_quotes[quote_id] = quote
            self.retired_by_token.setdefault(quote.token_id, {})[quote_id] = quote
            self.retired_queue.append((timestamp_ns, quote_id))
        while (
            self.retired_queue
            and timestamp_ns - self.retired_queue[0][0]
            > self.retired_retention_ns
        ):
            _, quote_id = self.retired_queue.popleft()
            quote = self.retired_quotes.pop(quote_id, None)
            if quote is not None:
                self.retired_by_token.get(quote.token_id, {}).pop(quote_id, None)
        return len(removable)

    def on_trade(self, trade: TradeTick) -> List[Fill]:
        fills: List[Fill] = []
        candidates = list(self.quotes_by_token.get(trade.token_id, {}).values())
        candidates.extend(self.retired_by_token.get(trade.token_id, {}).values())
        for quote in candidates:
            if quote.token_id != trade.token_id or not quote.is_active(trade.timestamp_ns):
                continue
            matching_flow = (
                quote.side == "BUY" and trade.aggressor_side == "SELL"
            ) or (quote.side == "SELL" and trade.aggressor_side == "BUY")
            if not matching_flow:
                continue
            through = (
                quote.side == "BUY" and trade.price < quote.price
            ) or (quote.side == "SELL" and trade.price > quote.price)
            at_price = trade.price == quote.price
            if not through and not at_price:
                continue
            if through:
                fill_size = quote.remaining
                reason = "strict_trade_through"
            else:
                queue_consumed = min(quote.queue_ahead, trade.size)
                quote.queue_ahead -= queue_consumed
                available = max(trade.size - queue_consumed, Decimal("0"))
                fill_size = min(quote.remaining, available)
                reason = "queue_exhausted_at_price"
            if fill_size <= 0:
                continue
            quote.filled += fill_size
            fills.append(
                Fill(
                    quote_id=quote.quote_id,
                    token_id=quote.token_id,
                    side=quote.side,
                    price=quote.price,
                    size=fill_size,
                    timestamp_ns=trade.timestamp_ns,
                    reason=reason,
                )
            )
        return fills


@dataclass
class Portfolio:
    cash: Decimal = Decimal("0")
    min_cash: Decimal = Decimal("0")
    positions: Dict[str, Decimal] = field(default_factory=dict)

    def apply_fill(self, fill: Fill) -> None:
        signed = fill.size if fill.side == "BUY" else -fill.size
        cash_delta = -fill.price * fill.size if fill.side == "BUY" else fill.price * fill.size
        self.positions[fill.token_id] = self.positions.get(fill.token_id, Decimal("0")) + signed
        self.cash += cash_delta
        self.min_cash = min(self.min_cash, self.cash)

    def settle(self, token_id: str, settlement_value: Decimal) -> Decimal:
        position = self.positions.pop(token_id, Decimal("0"))
        cash_delta = position * settlement_value
        self.cash += cash_delta
        self.min_cash = min(self.min_cash, self.cash)
        return cash_delta

    def merge_complete_set(self, token_a: str, token_b: str) -> Decimal:
        amount = min(
            max(self.positions.get(token_a, Decimal("0")), Decimal("0")),
            max(self.positions.get(token_b, Decimal("0")), Decimal("0")),
        )
        if amount <= 0:
            return Decimal("0")
        self.positions[token_a] -= amount
        self.positions[token_b] -= amount
        self.cash += amount
        return amount

    def liquidation_value(self, executable_bids: Dict[str, Decimal]) -> Decimal:
        value = self.cash
        for token_id, position in self.positions.items():
            if position > 0:
                value += position * executable_bids.get(token_id, Decimal("0"))
            elif position < 0:
                # Current shadow policies never create shorts. Keeping this
                # branch makes any future misuse visibly conservative.
                value += position
        return value

    @property
    def peak_external_capital(self) -> Decimal:
        return max(-self.min_cash, Decimal("0"))


def rounded_quote_prices(
    fair_value: Decimal,
    half_spread: Decimal,
    tick_size: Decimal,
    inventory_skew: Decimal = Decimal("0"),
) -> Dict[str, Decimal]:
    center = fair_value - inventory_skew
    raw_bid = center - half_spread
    raw_ask = center + half_spread
    bid = (raw_bid / tick_size).to_integral_value(rounding=ROUND_FLOOR) * tick_size
    ask = (raw_ask / tick_size).to_integral_value(rounding=ROUND_CEILING) * tick_size
    return {
        "bid": min(max(bid, tick_size), Decimal("1") - tick_size),
        "ask": min(max(ask, tick_size), Decimal("1") - tick_size),
    }
