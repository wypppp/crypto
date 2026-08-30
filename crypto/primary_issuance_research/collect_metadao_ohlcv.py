#!/usr/bin/env python3
"""Collect first-180-day daily OHLCV for material completed MetaDAO launches."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from collect_cca_material_ohlcv import GECKO_ROOT, get_json


SECONDS_180D = 180 * 86400


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=base_dir / "data/metadao_market_snapshot.csv",
    )
    parser.add_argument(
        "--launches",
        type=Path,
        default=base_dir / "data/metadao_current_launch_accounts.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=base_dir / "data/metadao_ohlcv_daily",
    )
    parser.add_argument("--sleep-seconds", type=float, default=3.5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    launches = {
        row["launch_account"]: row for row in json.loads(args.launches.read_text())
    }
    rows = list(csv.DictReader(args.snapshot.open()))
    selected = [row for row in rows if row["has_market_pair"] == "True"]
    now = int(datetime.now(timezone.utc).timestamp())
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    errors: dict[str, str] = {}
    ok = 0
    request_count = 0
    for index, row in enumerate(selected, start=1):
        pool = row["pair_address"]
        output_path = args.cache_dir / f"{pool}.json"
        if output_path.exists() and not args.refresh:
            ok += 1
            continue
        launch = launches[row["launch_account"]]
        decoded = launch["decoded"]
        launch_end = int(
            row["closed_at"]
            or decoded.get("unixTimestampCompleted")
            or decoded.get("unixTimestampClosed")
            or int(row["started_at"]) + int(decoded.get("secondsForLaunch") or 0)
        )
        target_end = min(now, launch_end + SECONDS_180D)
        before = target_end + 86400
        candles_by_time: dict[int, list[float]] = {}
        source_urls = []
        try:
            for _ in range(3):
                query = urllib.parse.urlencode(
                    {
                        "aggregate": 1,
                        "limit": 100,
                        "before_timestamp": before,
                        "currency": "token",
                        "token": "base",
                    }
                )
                url = f"{GECKO_ROOT}/networks/solana/pools/{pool}/ohlcv/day?{query}"
                payload = get_json(url, args.timeout)
                request_count += 1
                source_urls.append(url)
                candles = payload.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
                for candle in candles:
                    timestamp = int(candle[0])
                    if launch_end - 86400 <= timestamp <= target_end + 86400:
                        candles_by_time[timestamp] = candle
                if not candles:
                    break
                earliest = min(int(candle[0]) for candle in candles)
                if earliest <= launch_end:
                    break
                before = earliest
                time.sleep(args.sleep_seconds)
            output = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "launch_account": row["launch_account"],
                "token_mint": row["token_mint"],
                "token_symbol": row["token_symbol"],
                "pool_address": pool,
                "accepted_usd": float(row["accepted_usd"]),
                "public_tokens": 10_000_000,
                "issue_price_usd": float(row["accepted_usd"]) / 10_000_000,
                "launch_end_timestamp": launch_end,
                "target_end_timestamp": target_end,
                "source_urls": source_urls,
                "candles": [candles_by_time[key] for key in sorted(candles_by_time)],
            }
            output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
            ok += 1
        except Exception as exc:
            errors[pool] = str(exc)
        if index % 5 == 0 or index == len(selected):
            print(
                json.dumps(
                    {
                        "processed": index,
                        "selected": len(selected),
                        "ok": ok,
                        "errors": len(errors),
                        "requests": request_count,
                    }
                ),
                flush=True,
            )
        if index < len(selected):
            time.sleep(args.sleep_seconds)

    audit = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "selection": "completed MetaDAO launch, accepted >= $10k, DexScreener market matched",
        "selected_pools": len(selected),
        "material_completed_without_matched_pair": sum(
            row["has_market_pair"] != "True" for row in rows
        ),
        "cached_or_collected": ok,
        "request_count_this_run": request_count,
        "errors": errors,
        "complete": ok == len(selected) and not errors,
    }
    (args.cache_dir.parent / "metadao_ohlcv_daily_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
