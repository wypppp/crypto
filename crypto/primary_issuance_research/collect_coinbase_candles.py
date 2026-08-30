#!/usr/bin/env python3
"""Collect an audited Coinbase Exchange candle range in bounded chunks."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from collect_metadao_launches import http_json


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", default="ETH-USD")
    parser.add_argument("--granularity", type=int, default=3600)
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument(
        "--short-allocations",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_allocations.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/coinbase_ethusd_cca_short_hourly.json",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep-seconds", type=float, default=0.4)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    if args.start is None or args.end is None:
        source = json.loads(args.short_allocations.read_text())
        timestamps = [
            int(job["created_timestamp"]) for job in source["jobs"]
        ] + [int(job["migration_timestamp"]) + 24 * 3600 for job in source["jobs"]]
        start = min(timestamps) - args.granularity
        end = max(timestamps) + args.granularity
    else:
        start, end = args.start, args.end
    if end <= start:
        raise ValueError("end must be after start")

    # Coinbase documents a maximum of 300 candles per request.  Use 250 to
    # leave headroom at inclusive boundaries.
    chunk_seconds = 250 * args.granularity
    by_timestamp: dict[int, list] = {}
    requests = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + chunk_seconds, end)
        query = urllib.parse.urlencode(
            {
                "start": datetime.fromtimestamp(cursor, timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(chunk_end, timezone.utc).isoformat(),
                "granularity": args.granularity,
            }
        )
        url = f"https://api.exchange.coinbase.com/products/{args.product}/candles?{query}"
        payload = http_json(url, proxy_mode=args.proxy_mode, timeout=args.timeout)
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected Coinbase payload: {payload}")
        for candle in payload:
            by_timestamp[int(candle[0])] = candle
        requests.append(
            {
                "start": cursor,
                "end": chunk_end,
                "rows": len(payload),
                "url": url,
            }
        )
        print(
            json.dumps(
                {
                    "request": len(requests),
                    "through": chunk_end,
                    "unique_candles": len(by_timestamp),
                }
            ),
            flush=True,
        )
        cursor = chunk_end
        if cursor < end:
            time.sleep(args.sleep_seconds)

    candles = [by_timestamp[key] for key in sorted(by_timestamp)]
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "Coinbase Exchange public candles API",
        "product": args.product,
        "granularity": args.granularity,
        "requested_start": start,
        "requested_end": end,
        "requests": requests,
        "candles": candles,
        "complete": bool(candles)
        and min(int(row[0]) for row in candles) <= start + args.granularity
        and max(int(row[0]) for row in candles) >= end - 2 * args.granularity,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "candles": len(candles),
                "first": candles[0][0] if candles else None,
                "last": candles[-1][0] if candles else None,
                "complete": output["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
