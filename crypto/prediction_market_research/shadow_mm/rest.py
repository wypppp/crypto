import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from .models import Market


class PublicRestClient:
    """Public, unauthenticated endpoints only. No order placement methods."""

    def __init__(
        self,
        gamma_url: str,
        clob_url: str,
        coinbase_url: str,
        timeout_seconds: float = 8.0,
        retries: int = 2,
    ) -> None:
        self.gamma_url = gamma_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")
        self.coinbase_url = coinbase_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "polymarket-shadow-mm/0.1 read-only-research"}
        )

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(0.25 * (2 ** attempt), 1.0))
        assert last_error is not None
        raise last_error

    def server_time(self) -> Any:
        return self._get(self.clob_url + "/time")

    def gamma_markets(
        self,
        page_size: int = 500,
        pages: int = 6,
        end_grace_seconds: float = 120.0,
    ) -> List[Market]:
        answer: List[Market] = []
        seen = set()
        # Gamma currently caps this endpoint at 100 rows even when a larger
        # limit is requested. Paging by the requested 500 would silently skip
        # 400 records on every page.
        effective_page_size = max(min(int(page_size), 100), 1)
        end_date_min = (
            datetime.now(timezone.utc) - timedelta(seconds=max(end_grace_seconds, 0.0))
        ).isoformat()
        for page in range(max(pages, 1)):
            payload = self._get(
                self.gamma_url + "/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": effective_page_size,
                    "offset": page * effective_page_size,
                    "end_date_min": end_date_min,
                    "order": "endDate",
                    "ascending": "true",
                },
            )
            rows = payload.get("data", []) if isinstance(payload, dict) else payload
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                market = Market.from_gamma(row)
                key = market.condition_id or market.slug
                if key and key not in seen:
                    seen.add(key)
                    answer.append(market)
            if len(rows) < effective_page_size:
                break
        return answer

    def gamma_markets_by_condition_ids(
        self, condition_ids: Iterable[str]
    ) -> List[Market]:
        identifiers = [str(item) for item in condition_ids if item]
        if not identifiers:
            return []
        payload = self._get(
            self.gamma_url + "/markets",
            params={
                "condition_ids": identifiers,
                "closed": "true",
                "limit": min(len(identifiers), 100),
            },
        )
        rows = payload.get("data", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []
        return [
            Market.from_gamma(row) for row in rows if isinstance(row, dict)
        ]

    def book(self, token_id: str) -> Dict[str, Any]:
        payload = self._get(self.clob_url + "/book", params={"token_id": token_id})
        if not isinstance(payload, dict):
            raise ValueError("CLOB /book returned a non-object payload")
        return payload

    def last_trade_price(self, token_id: str) -> Dict[str, Any]:
        payload = self._get(
            self.clob_url + "/last-trade-price", params={"token_id": token_id}
        )
        if not isinstance(payload, dict):
            return {"value": payload}
        return payload

    def coinbase_ticker(self, symbol: str) -> Dict[str, Any]:
        product = "{}-USD".format(symbol.upper())
        payload = self._get(self.coinbase_url + "/products/{}/ticker".format(product))
        if not isinstance(payload, dict):
            raise ValueError("Coinbase ticker returned a non-object payload")
        return payload

    def close(self) -> None:
        self.session.close()


def summarize_exception(exc: BaseException) -> Dict[str, str]:
    return {"error_type": type(exc).__name__, "message": str(exc)[:500]}
