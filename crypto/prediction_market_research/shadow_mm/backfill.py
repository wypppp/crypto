"""Read-only Gamma resolution backfill for completed pilot captures."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from .collector import make_event
from .config import CollectorConfig
from .market_filter import ClassifiedMarket
from .models import Market
from .replay import iter_events
from .rest import PublicRestClient
from .storage import JsonlEventWriter
from .ws_collector import ResolutionWorker


def backfill_resolutions(
    input_path: Path, output_path: Path, config: CollectorConfig
) -> Dict[str, int]:
    observed: Dict[str, ClassifiedMarket] = {}
    for event in iter_events(input_path):
        if event.get("event_type") not in (
            "discovery_update",
            "discovery_heartbeat",
        ):
            continue
        payload = event.get("payload") or {}
        for row in payload.get("markets", []) or []:
            raw = dict(row.get("raw_market") or {})
            raw.setdefault("conditionId", row.get("condition_id"))
            raw.setdefault("slug", row.get("slug"))
            raw.setdefault("question", row.get("question"))
            raw.setdefault("endDate", row.get("end_time"))
            raw.setdefault(
                "clobTokenIds",
                [token.get("token_id") for token in row.get("tokens", [])],
            )
            raw.setdefault(
                "outcomes",
                [token.get("outcome") for token in row.get("tokens", [])],
            )
            market = Market.from_gamma(raw)
            if market.condition_id:
                observed[market.condition_id] = ClassifiedMarket(
                    market,
                    str(row.get("symbol") or ""),
                    int(row.get("interval_minutes") or 0),
                )

    client = PublicRestClient(
        gamma_url=config.gamma_url,
        clob_url=config.clob_url,
        coinbase_url=config.coinbase_url,
        timeout_seconds=config.request_timeout_seconds,
    )
    resolved_n = 0
    queried_n = 0
    with JsonlEventWriter(
        output_path,
        fsync_every=100,
        queue_max_events=10000,
        gzip_compresslevel=config.gzip_compresslevel,
    ) as writer:
        try:
            identifiers = sorted(observed)
            for offset in range(0, len(identifiers), 100):
                batch_ids = identifiers[offset : offset + 100]
                rows = client.gamma_markets_by_condition_ids(batch_ids)
                queried_n += len(batch_ids)
                for row in rows:
                    item = observed.get(row.condition_id)
                    if item is None:
                        continue
                    payload = ResolutionWorker.resolution_payload(item, row)
                    if payload is None:
                        continue
                    payload["backfilled_at"] = datetime.now(timezone.utc).isoformat()
                    writer.write(
                        make_event(
                            "gamma_resolution_backfill",
                            "market_resolved",
                            payload,
                        )
                    )
                    resolved_n += 1
        finally:
            client.close()
    return {
        "markets_observed_n": len(observed),
        "markets_queried_n": queried_n,
        "markets_resolved_n": resolved_n,
    }
