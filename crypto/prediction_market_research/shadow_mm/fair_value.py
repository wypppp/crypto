"""Pre-registered transparent fair-probability baseline for TWAP markets."""

import math
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Deque, Dict, Optional, Tuple


@dataclass
class RollingSpotVolatility:
    window_seconds: int = 300
    latest: Dict[str, Tuple[float, int]] = field(default_factory=dict)
    samples: Deque[Tuple[int, float]] = field(default_factory=deque)
    squared_rates: Deque[Tuple[int, float]] = field(default_factory=deque)
    last_sample_second: Optional[int] = None

    def update(self, venue: str, price: float, timestamp_ns: int) -> None:
        if price <= 0 or timestamp_ns <= 0:
            return
        self.latest[venue] = (price, timestamp_ns)
        second = timestamp_ns // 1_000_000_000
        if second == self.last_sample_second:
            return
        self.last_sample_second = second
        fresh = [
            value
            for value, observed_ns in self.latest.values()
            if timestamp_ns - observed_ns <= 5_000_000_000
        ]
        if not fresh:
            return
        composite = sum(fresh) / len(fresh)
        log_price = math.log(composite)
        if self.samples:
            prior_second, prior_log = self.samples[-1]
            elapsed = max(second - prior_second, 1)
            squared_rate = ((log_price - prior_log) ** 2) / elapsed
            self.squared_rates.append((second, squared_rate))
        self.samples.append((second, log_price))
        cutoff = second - self.window_seconds
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()
        while self.squared_rates and self.squared_rates[0][0] < cutoff:
            self.squared_rates.popleft()

    def sigma_per_sqrt_second(self, minimum_samples: int = 30) -> Optional[float]:
        if len(self.squared_rates) < minimum_samples:
            return None
        return math.sqrt(
            sum(value for _, value in self.squared_rates)
            / len(self.squared_rates)
        )


def binary_up_probability(
    current_price: float,
    target_price: float,
    sigma_per_sqrt_second: float,
    remaining_seconds: float,
) -> Optional[float]:
    if current_price <= 0 or target_price <= 0 or remaining_seconds <= 0:
        return None
    if sigma_per_sqrt_second <= 0:
        return 1.0 if current_price >= target_price else 0.0
    scale = sigma_per_sqrt_second * math.sqrt(remaining_seconds)
    z = math.log(current_price / target_price) / scale
    probability = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return min(max(probability, 0.001), 0.999)


class FairValueModel:
    def __init__(
        self,
        symbols: Any,
        volatility_window_seconds: int = 300,
        minimum_volatility_samples: int = 30,
        max_twap_staleness_seconds: float = 5.0,
    ) -> None:
        self.volatility = {
            str(symbol).upper(): RollingSpotVolatility(volatility_window_seconds)
            for symbol in symbols
        }
        self.twap: Dict[str, Tuple[float, int]] = {}
        self.minimum_volatility_samples = minimum_volatility_samples
        self.max_twap_staleness_ns = int(max_twap_staleness_seconds * 1_000_000_000)

    def update_event(self, event: Dict[str, Any], timestamp_ns: int) -> Optional[str]:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return None
        source = str(event.get("source") or "")
        if source == "coinbase_ws" and payload.get("product_id"):
            symbol = str(payload["product_id"]).split("-")[0].upper()
            try:
                price = (
                    float(payload["best_bid"]) + float(payload["best_ask"])
                ) / 2
            except (KeyError, TypeError, ValueError):
                try:
                    price = float(payload["price"])
                except (KeyError, TypeError, ValueError):
                    return None
            if symbol in self.volatility:
                self.volatility[symbol].update("coinbase", price, timestamp_ns)
                return symbol
        if source == "kraken_ws":
            rows = payload.get("data", []) or []
            if rows and isinstance(rows[0], dict) and rows[0].get("symbol"):
                row = rows[0]
                symbol = str(row["symbol"]).split("/")[0].upper()
                try:
                    price = (float(row["bid"]) + float(row["ask"])) / 2
                except (KeyError, TypeError, ValueError):
                    return None
                if symbol in self.volatility:
                    self.volatility[symbol].update("kraken", price, timestamp_ns)
                    return symbol
        if (
            source == "polymarket_rtds"
            and payload.get("topic") == "crypto_prices_twap_sixty"
        ):
            body = payload.get("payload")
            if isinstance(body, dict) and body.get("symbol"):
                symbol = str(body["symbol"]).split("/")[0].upper()
                try:
                    price = float(body["value"])
                except (KeyError, TypeError, ValueError):
                    return None
                self.twap[symbol] = (price, timestamp_ns)
                return symbol
        return None

    def probability_up(self, market: Any, timestamp_ns: int) -> Optional[Decimal]:
        if market.price_to_beat is None or market.end_ns is None:
            return None
        reference = self.twap.get(market.symbol.upper())
        volatility = self.volatility.get(market.symbol.upper())
        if reference is None or volatility is None:
            return None
        current, observed_ns = reference
        if timestamp_ns - observed_ns > self.max_twap_staleness_ns:
            return None
        sigma = volatility.sigma_per_sqrt_second(self.minimum_volatility_samples)
        if sigma is None:
            return None
        remaining = (market.end_ns - timestamp_ns) / 1_000_000_000
        probability = binary_up_probability(
            current,
            float(market.price_to_beat),
            sigma,
            remaining,
        )
        return Decimal(str(probability)) if probability is not None else None
