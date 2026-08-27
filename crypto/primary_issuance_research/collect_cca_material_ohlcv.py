#!/usr/bin/env python3
"""Collect daily quote-token OHLCV for materially funded Robinhood CCA pools.

The mother universe is defined by on-chain factory events. GeckoTerminal is
used only as an outcome index. Responses are cached per pool so an interrupted
rate-limited run can resume without repeating successful requests.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
GECKO_ROOT = "https://api.geckoterminal.com/api/v2"


def get_json(url: str, timeout: int) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json;version=20230203",
            "user-agent": "primary-issuance-research/0.1",
        },
    )
    failures = []
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            failures.append(f"HTTP {exc.code}: {exc.reason}")
            if exc.code == 429 and attempt < 4:
                retry_after = exc.headers.get("Retry-After")
                wait_seconds = min(max(float(retry_after or 30), 10.0), 30.0)
                print(
                    json.dumps(
                        {"rate_limited": True, "wait_seconds": wait_seconds}
                    ),
                    flush=True,
                )
                time.sleep(wait_seconds)
                continue
            if attempt < 4:
                time.sleep(min(2**attempt, 8))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            failures.append(str(exc))
            if attempt < 4:
                time.sleep(min(2**attempt, 8))
    raise RuntimeError("; ".join(failures))


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--status",
        type=Path,
        default=base_dir / "data/cca_robinhood_status.json",
    )
    parser.add_argument(
        "--migration-events",
        type=Path,
        default=base_dir / "data/cca_robinhood_migrations_events.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_ohlcv_daily",
    )
    parser.add_argument("--minimum-native-wei", type=int, default=10**18)
    parser.add_argument("--sleep-seconds", type=float, default=8.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-pools", type=int)
    args = parser.parse_args()

    status = {
        row["auction"].lower(): row for row in json.loads(args.status.read_text())
    }
    migrations = [
        row
        for row in json.loads(args.migration_events.read_text())
        if row["event"] == "migrated"
    ]
    selected = []
    for migration in migrations:
        row = status.get(migration["auction"].lower())
        if not row:
            continue
        if row["currency"].lower() != ZERO_ADDRESS:
            continue
        if (row.get("currency_raised_raw") or 0) < args.minimum_native_wei:
            continue
        selected.append((migration, row))
    selected.sort(key=lambda item: (item[0]["block_number"], item[0]["auction"]))
    if args.max_pools is not None:
        selected = selected[: args.max_pools]

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    errors: dict[str, str] = {}
    for index, (migration, row) in enumerate(selected, 1):
        pool_id = migration["pool_id"].lower()
        path = args.cache_dir / f"{pool_id}.json"
        if path.exists() and not args.refresh:
            ok += 1
            continue
        query = urllib.parse.urlencode(
            {
                "aggregate": 1,
                "limit": 100,
                "currency": "token",
                "token": "base",
            }
        )
        url = f"{GECKO_ROOT}/networks/robinhood/pools/{pool_id}/ohlcv/day?{query}"
        try:
            payload = get_json(url, args.timeout)
            output = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_url": url,
                "auction": migration["auction"],
                "token": row["token"],
                "pool_id": pool_id,
                "migration_block": migration["block_number"],
                "initial_sqrt_price_x96": migration["initial_sqrt_price_x96"],
                "currency_raised_raw": row.get("currency_raised_raw"),
                "total_cleared_raw": row.get("total_cleared_raw"),
                "payload": payload,
            }
            path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
            ok += 1
        except Exception as exc:
            errors[pool_id] = str(exc)
        if index % 10 == 0 or index == len(selected):
            print(
                json.dumps(
                    {"processed": index, "selected": len(selected), "ok": ok, "errors": len(errors)}
                ),
                flush=True,
            )
        if index < len(selected):
            time.sleep(args.sleep_seconds)

    audit = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "chain": "robinhood",
            "currency": ZERO_ADDRESS,
            "graduation": "successful Migrated event",
            "minimum_currency_raised_raw": args.minimum_native_wei,
        },
        "selected_pools": len(selected),
        "cached_or_collected": ok,
        "complete": ok == len(selected) and not errors,
        "errors": errors,
    }
    (args.cache_dir.parent / "cca_robinhood_ohlcv_daily_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
