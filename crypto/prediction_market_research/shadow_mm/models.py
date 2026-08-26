from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def parse_json_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [value]
        return list(parsed) if isinstance(parsed, list) else [parsed]
    return [value]


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_optional_bool(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no", ""):
        return False
    return default


@dataclass(frozen=True)
class Token:
    token_id: str
    outcome: str


@dataclass(frozen=True)
class Market:
    condition_id: str
    question: str
    slug: str
    end_time: Optional[datetime]
    tokens: Tuple[Token, ...]
    tags: Tuple[str, ...] = field(default_factory=tuple)
    active: bool = True
    closed: bool = False
    accepting_orders: Optional[bool] = None
    minimum_tick_size: Optional[Decimal] = None
    minimum_order_size: Optional[Decimal] = None
    raw: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_gamma(cls, row: Dict[str, Any]) -> "Market":
        token_ids = [str(x) for x in parse_json_list(row.get("clobTokenIds"))]
        outcomes = [str(x) for x in parse_json_list(row.get("outcomes"))]
        tokens = tuple(
            Token(token_id=token_id, outcome=outcomes[i] if i < len(outcomes) else str(i))
            for i, token_id in enumerate(token_ids)
        )
        raw_tags = row.get("tags") or []
        tags: List[str] = []
        for tag in raw_tags if isinstance(raw_tags, list) else parse_json_list(raw_tags):
            if isinstance(tag, dict):
                tags.append(str(tag.get("label") or tag.get("name") or tag.get("slug") or ""))
            else:
                tags.append(str(tag))
        tick = row.get("orderPriceMinTickSize")
        min_order = row.get("orderMinSize")
        return cls(
            condition_id=str(row.get("conditionId") or row.get("condition_id") or ""),
            question=str(row.get("question") or row.get("title") or ""),
            slug=str(row.get("slug") or ""),
            # Gamma's endDateIso can be date-only while endDate carries the
            # actual intraday close for 5m/15m markets.
            end_time=parse_timestamp(row.get("endDate") or row.get("endDateIso")),
            tokens=tokens,
            tags=tuple(tag for tag in tags if tag),
            active=bool(parse_optional_bool(row.get("active"), True)),
            closed=bool(parse_optional_bool(row.get("closed"), False)),
            accepting_orders=parse_optional_bool(row.get("acceptingOrders")),
            minimum_tick_size=Decimal(str(tick)) if tick not in (None, "") else None,
            minimum_order_size=Decimal(str(min_order)) if min_order not in (None, "") else None,
            raw=row,
        )


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class BookSnapshot:
    token_id: str
    timestamp_ns: int
    bids: Tuple[BookLevel, ...]
    asks: Tuple[BookLevel, ...]
    market: str = ""
    source_timestamp: Optional[str] = None

    @property
    def best_bid(self) -> Optional[Decimal]:
        return max((level.price for level in self.bids), default=None)

    @property
    def best_ask(self) -> Optional[Decimal]:
        return min((level.price for level in self.asks), default=None)

    @property
    def midpoint(self) -> Optional[Decimal]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / Decimal("2")

    @classmethod
    def from_clob(cls, token_id: str, timestamp_ns: int, row: Dict[str, Any]) -> "BookSnapshot":
        def levels(key: str) -> Tuple[BookLevel, ...]:
            answer = []
            for level in row.get(key, []) or []:
                try:
                    answer.append(BookLevel(Decimal(str(level["price"])), Decimal(str(level["size"]))))
                except (KeyError, TypeError, ValueError):
                    continue
            return tuple(answer)

        return cls(
            token_id=token_id,
            timestamp_ns=timestamp_ns,
            bids=levels("bids"),
            asks=levels("asks"),
            market=str(row.get("market") or ""),
            source_timestamp=str(row.get("timestamp")) if row.get("timestamp") is not None else None,
        )
