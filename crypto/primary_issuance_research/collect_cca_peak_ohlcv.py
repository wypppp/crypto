#!/usr/bin/env python3
"""Collect hourly and peak-hour minute candles for mature CCA 5x candidates."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = "https://api.geckoterminal.com/api/v2"


def get_json(url: str, timeout: int) -> dict:
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
            if attempt < 4:
                time.sleep(10 if exc.code == 429 else min(2**attempt, 8))
        except Exception as exc:
            failures.append(str(exc))
            if attempt < 4:
                time.sleep(min(2**attempt, 8))
    raise RuntimeError("; ".join(failures))


def request_ohlcv(
    pool_id: str,
    timeframe: str,
    token_side: str,
    limit: int,
    timeout: int,
    before_timestamp: int | None = None,
) -> tuple[str, dict]:
    params: dict[str, object] = {
        "aggregate": 1,
        "limit": limit,
        "currency": "token",
        "token": token_side,
    }
    if before_timestamp is not None:
        params["before_timestamp"] = before_timestamp
    query = urllib.parse.urlencode(params)
    url = f"{ROOT}/networks/robinhood/pools/{pool_id}/ohlcv/{timeframe}?{query}"
    return url, get_json(url, timeout)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--daily-csv",
        type=Path,
        default=base_dir / "output/cca_robinhood_material_daily.csv",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_ohlcv",
    )
    parser.add_argument("--sleep-seconds", type=float, default=8)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    candidates = [
        row
        for row in csv.DictReader(args.daily_csv.open())
        if row["mature_30d"] == "True" and float(row["max_spot_30d_x"] or 0) >= 5
    ]
    candidates.sort(key=lambda row: row["pool_id"])
    hour_dir = args.cache_dir / "hour"
    minute_dir = args.cache_dir / "minute"
    hour_dir.mkdir(parents=True, exist_ok=True)
    minute_dir.mkdir(parents=True, exist_ok=True)
    errors = {}

    for index, row in enumerate(candidates, 1):
        path = hour_dir / f"{row['pool_id']}.json"
        if not path.exists() or args.refresh:
            try:
                url, payload = request_ohlcv(
                    row["pool_id"], "hour", row["token_side"], 1000, args.timeout
                )
                path.write_text(
                    json.dumps(
                        {"candidate": row, "source_url": url, "payload": payload},
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            except Exception as exc:
                errors[f"hour:{row['pool_id']}"] = str(exc)
        print(json.dumps({"stage": "hour", "processed": index, "total": len(candidates)}), flush=True)
        if index < len(candidates):
            time.sleep(args.sleep_seconds)

    minute_jobs = []
    for row in candidates:
        path = hour_dir / f"{row['pool_id']}.json"
        if not path.exists():
            continue
        hour = json.loads(path.read_text())
        candles = hour["payload"]["data"]["attributes"]["ohlcv_list"]
        migration_timestamp = int(float(row["migration_timestamp"]))
        candles = [
            candle
            for candle in candles
            if int(candle[0]) + 3600 > migration_timestamp
            and int(candle[0]) < migration_timestamp + 30 * 86_400
        ]
        if not candles:
            errors[f"hour-empty:{row['pool_id']}"] = "no hourly candles"
            continue
        peak = max(candles, key=lambda candle: float(candle[2]))
        minute_jobs.append((row, int(peak[0])))

    for index, (row, peak_hour) in enumerate(minute_jobs, 1):
        path = minute_dir / f"{row['pool_id']}.json"
        if not path.exists() or args.refresh:
            try:
                url, payload = request_ohlcv(
                    row["pool_id"],
                    "minute",
                    row["token_side"],
                    180,
                    args.timeout,
                    before_timestamp=peak_hour + 3600,
                )
                path.write_text(
                    json.dumps(
                        {
                            "candidate": row,
                            "peak_hour_timestamp": peak_hour,
                            "source_url": url,
                            "payload": payload,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            except Exception as exc:
                errors[f"minute:{row['pool_id']}"] = str(exc)
        print(
            json.dumps({"stage": "minute", "processed": index, "total": len(minute_jobs)}),
            flush=True,
        )
        if index < len(minute_jobs):
            time.sleep(args.sleep_seconds)

    audit = {
        "candidate_count": len(candidates),
        "hour_files": len(list(hour_dir.glob("0x*.json"))),
        "minute_files": len(list(minute_dir.glob("0x*.json"))),
        "complete": (
            len(list(hour_dir.glob("0x*.json"))) == len(candidates)
            and len(list(minute_dir.glob("0x*.json"))) == len(candidates)
            and not errors
        ),
        "errors": errors,
    }
    (args.cache_dir / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
