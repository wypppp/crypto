import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from .models import Market


SYMBOL_PATTERNS = {
    "BTC": r"\b(?:btc|bitcoin)\b",
    "ETH": r"\b(?:eth|ethereum)\b",
    "SOL": r"\b(?:sol|solana)\b",
    "XRP": r"\b(?:xrp|ripple)\b",
    "HYPE": r"\b(?:hype|hyperliquid)\b",
    "BNB": r"\b(?:bnb|binance coin)\b",
    "DOGE": r"\b(?:doge|dogecoin)\b",
}


INTERVAL_PATTERNS = {
    5: r"(?:\b5\s*(?:m|min|mins|minute|minutes)\b|5-minute)",
    15: r"(?:\b15\s*(?:m|min|mins|minute|minutes)\b|15-minute)",
}


TIME_RANGE_PATTERN = re.compile(
    r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\s*[-\u2013\u2014]\s*"
    r"(\d{1,2}):(\d{2})\s*(am|pm)?\b",
    flags=re.IGNORECASE,
)

SLUG_EPOCH_PATTERN = re.compile(r"(?:^|-)(\d{10})(?:$|-)")


@dataclass(frozen=True)
class ClassifiedMarket:
    market: Market
    symbol: str
    interval_minutes: int

    @property
    def window_start(self) -> Optional[datetime]:
        matches = SLUG_EPOCH_PATTERN.findall(self.market.slug)
        if not matches:
            return None
        try:
            return datetime.fromtimestamp(int(matches[-1]), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    @property
    def effective_end_time(self) -> Optional[datetime]:
        if self.window_start is not None:
            return self.window_start + timedelta(minutes=self.interval_minutes)
        return self.market.end_time


def _haystack(market: Market) -> str:
    return " ".join((market.question, market.slug, *market.tags)).lower()


def detect_symbol(text: str, allowed: Sequence[str]) -> Optional[str]:
    for symbol in allowed:
        pattern = SYMBOL_PATTERNS.get(symbol.upper())
        if pattern and re.search(pattern, text, flags=re.IGNORECASE):
            return symbol.upper()
    return None


def detect_interval(text: str, allowed: Sequence[int]) -> Optional[int]:
    for minutes in allowed:
        pattern = INTERVAL_PATTERNS.get(int(minutes))
        if pattern and re.search(pattern, text, flags=re.IGNORECASE):
            return int(minutes)

    # Gamma questions often encode the horizon only as a clock range, for
    # example "5:00-5:05 ET". Infer that range without interpreting its date.
    match = TIME_RANGE_PATTERN.search(text)
    if match is not None:
        start_hour, start_minute, start_meridiem = match.group(1, 2, 3)
        end_hour, end_minute, end_meridiem = match.group(4, 5, 6)

        # A single trailing meridiem normally scopes the whole range
        # ("5:55-6:00 PM"). Preserve explicit mixed ranges such as
        # "11:45 PM-12:00 AM".
        if start_meridiem is None and end_meridiem is not None:
            start_meridiem = end_meridiem
        elif end_meridiem is None and start_meridiem is not None:
            end_meridiem = start_meridiem
        start = _clock_minutes(int(start_hour), int(start_minute), start_meridiem)
        end = _clock_minutes(int(end_hour), int(end_minute), end_meridiem)
        clock_size = 24 * 60 if start_meridiem or end_meridiem else 12 * 60
        elapsed = (end - start) % clock_size
        if elapsed in {int(value) for value in allowed}:
            return elapsed
    return None


def _clock_minutes(hour: int, minute: int, meridiem: Optional[str]) -> int:
    if not 0 <= minute < 60:
        return -10_000
    if meridiem:
        if not 1 <= hour <= 12:
            return -10_000
        hour = hour % 12
        if meridiem.lower() == "pm":
            hour += 12
    elif not 0 <= hour <= 23:
        return -10_000
    return hour * 60 + minute


def classify_short_crypto_market(
    market: Market,
    symbols: Sequence[str],
    intervals: Sequence[int],
) -> Optional[ClassifiedMarket]:
    if not market.active or market.closed or len(market.tokens) != 2:
        return None
    if market.accepting_orders is False:
        return None
    text = _haystack(market)
    symbol = detect_symbol(text, symbols)
    interval = detect_interval(text, intervals)
    directional = (
        "up or down" in text
        or "crypto prices" in text
        or "twap" in text
        or "higher or lower" in text
    )
    if symbol is None or interval is None or not directional:
        return None
    return ClassifiedMarket(market=market, symbol=symbol, interval_minutes=interval)


def filter_short_crypto_markets(
    markets: Iterable[Market],
    symbols: Sequence[str],
    intervals: Sequence[int],
) -> list:
    answer = []
    for market in markets:
        classified = classify_short_crypto_market(market, symbols, intervals)
        if classified is not None:
            answer.append(classified)
    return answer
