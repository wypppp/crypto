#!/usr/bin/env python3
"""Resolve peak-minute UTC boundaries to Robinhood blocks via batched RPC binary search."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def rpc_batch(url: str, calls: list[dict[str, Any]], timeout: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(calls).encode(),
        headers={"content-type": "application/json", "user-agent": "primary-issuance-research/0.1"},
    )
    failures = []
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:
            failures.append(str(exc))
            if attempt < 4:
                time.sleep(
                    10
                    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429
                    else min(2**attempt, 8)
                )
    raise RuntimeError("; ".join(failures))


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def resolve_first_ge(
    url: str,
    targets: list[int],
    low_block: int,
    high_block: int,
    batch_size: int,
    timeout: int,
) -> dict[int, int]:
    bounds = {target: [low_block, high_block] for target in targets}
    iteration = 0
    while any(low < high for low, high in bounds.values()):
        iteration += 1
        mids = sorted({(low + high) // 2 for low, high in bounds.values() if low < high})
        timestamps: dict[int, int] = {}
        for batch in chunks(mids, batch_size):
            calls = [
                {
                    "jsonrpc": "2.0",
                    "id": str(block),
                    "method": "eth_getBlockByNumber",
                    "params": [hex(block), False],
                }
                for block in batch
            ]
            for response in rpc_batch(url, calls, timeout):
                if response.get("result"):
                    timestamps[int(response["id"])] = int(
                        response["result"]["timestamp"], 16
                    )
                else:
                    raise RuntimeError(json.dumps(response, ensure_ascii=False))
        for target, bound in bounds.items():
            low, high = bound
            if low >= high:
                continue
            middle = (low + high) // 2
            if timestamps[middle] < target:
                bound[0] = middle + 1
            else:
                bound[1] = middle
        if iteration % 5 == 0:
            print(
                json.dumps(
                    {
                        "iteration": iteration,
                        "unresolved": sum(low < high for low, high in bounds.values()),
                    }
                ),
                flush=True,
            )
    return {target: low for target, (low, _) in bounds.items()}


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--persistence-csv",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_persistence.csv",
    )
    parser.add_argument(
        "--minute-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_ohlcv/minute",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_minute_blocks.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    candidates = [
        row
        for row in csv.DictReader(args.persistence_csv.open())
        if row["triage_persistent_5x"] == "True"
    ]
    jobs = []
    for candidate in candidates:
        payload = json.loads(
            (args.minute_dir / f"{candidate['pool_id']}.json").read_text()
        )
        issue = float(candidate["issue_vwap_eth_per_token"])
        peak_hour = int(candidate["peak_hour_timestamp"])
        candles = [
            candle
            for candle in payload["payload"]["data"]["attributes"]["ohlcv_list"]
            if peak_hour <= int(candle[0]) < peak_hour + 3600
            and float(candle[4]) >= 5 * issue
        ]
        selected = max(candles, key=lambda candle: float(candle[5]))
        jobs.append(
            {
                "pool_id": candidate["pool_id"],
                "token": candidate["token"],
                "migration_timestamp": int(float(candidate["peak_hour_timestamp"])),
                "minute_timestamp": int(selected[0]),
                "selected_minute_candle": selected,
            }
        )

    head = rpc_batch(
        args.rpc,
        [{"jsonrpc": "2.0", "id": "head", "method": "eth_blockNumber", "params": []}],
        args.timeout,
    )[0]
    latest_block = int(head["result"], 16)
    targets = sorted(
        {timestamp for job in jobs for timestamp in (job["minute_timestamp"], job["minute_timestamp"] + 60)}
    )
    resolved = resolve_first_ge(
        args.rpc,
        targets,
        0,
        latest_block,
        args.batch_size,
        args.timeout,
    )
    for job in jobs:
        job["from_block"] = resolved[job["minute_timestamp"]]
        job["to_block"] = resolved[job["minute_timestamp"] + 60] - 1
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "latest_block": latest_block,
        "jobs": jobs,
        "complete": all(job["from_block"] <= job["to_block"] for job in jobs),
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "jobs": len(jobs),
                "unique_boundaries": len(targets),
                "complete": output["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
