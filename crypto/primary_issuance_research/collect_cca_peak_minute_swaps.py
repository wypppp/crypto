#!/usr/bin/env python3
"""Collect direction-level swaps for one liquid >=5x minute per persistent CCA candidate."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from collect_cca_auctions import EvmRpc
from collect_cca_migrations import get_event_logs_adaptive


POOL_MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
SWAP_SIGNATURE = "Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)"
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/api"


def get_json(url: str, timeout: int) -> dict:
    request = urllib.request.Request(
        url, headers={"user-agent": "primary-issuance-research/0.1"}
    )
    failures = []
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:
            failures.append(str(exc))
            if attempt < 3:
                time.sleep(
                    15
                    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429
                    else min(2**attempt, 8)
                )
    raise RuntimeError("; ".join(failures))


def block_by_time(timestamp: int, closest: str, timeout: int) -> int:
    query = urllib.parse.urlencode(
        {
            "module": "block",
            "action": "getblocknobytime",
            "timestamp": timestamp,
            "closest": closest,
        }
    )
    payload = get_json(f"{BLOCKSCOUT}?{query}", timeout)
    if payload.get("status") != "1":
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return int(payload["result"]["blockNumber"])


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
        "--output-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_swaps",
    )
    parser.add_argument(
        "--block-map",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_minute_blocks.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-log-queries", type=int, default=200)
    parser.add_argument("--sleep-seconds", type=float, default=15)
    parser.add_argument("--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    candidates = [
        row
        for row in csv.DictReader(args.persistence_csv.open())
        if row["triage_persistent_5x"] == "True"
    ]
    candidates.sort(key=lambda row: row["pool_id"])
    block_map_payload = json.loads(args.block_map.read_text())
    if not block_map_payload.get("complete"):
        raise RuntimeError("peak minute block map is incomplete")
    block_map = {job["pool_id"].lower(): job for job in block_map_payload["jobs"]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    topic0 = rpc.call("web3_sha3", ["0x" + SWAP_SIGNATURE.encode().hex()])
    errors = {}
    collected = 0

    for index, candidate in enumerate(candidates, 1):
        path = args.output_dir / f"{candidate['pool_id']}.json"
        if path.exists() and not args.refresh:
            collected += 1
            continue
        try:
            minute_payload = json.loads(
                (args.minute_dir / f"{candidate['pool_id']}.json").read_text()
            )
            issue = float(candidate["issue_vwap_eth_per_token"])
            peak_hour = int(candidate["peak_hour_timestamp"])
            candles = [
                candle
                for candle in minute_payload["payload"]["data"]["attributes"]["ohlcv_list"]
                if peak_hour <= int(candle[0]) < peak_hour + 3600
                and float(candle[4]) >= 5 * issue
            ]
            if not candles:
                raise RuntimeError("no minute close >=5x in selected peak hour")
            selected = max(candles, key=lambda candle: float(candle[5]))
            minute_timestamp = int(selected[0])
            mapped = block_map[candidate["pool_id"].lower()]
            if mapped["minute_timestamp"] != minute_timestamp:
                raise RuntimeError("selected minute differs from frozen block map")
            from_block = int(mapped["from_block"])
            to_block = int(mapped["to_block"])
            logs, log_audit = get_event_logs_adaptive(
                rpc,
                POOL_MANAGER,
                from_block,
                to_block,
                [topic0],
                args.max_log_queries,
                indexed_topic1=candidate["pool_id"],
            )
            pool_logs = [
                log
                for log in logs
                if len(log.get("topics", [])) >= 2
                and log["topics"][0].lower() == topic0.lower()
                and log["topics"][1].lower() == candidate["pool_id"].lower()
            ]
            output = {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "candidate": candidate,
                "selected_minute_candle": selected,
                "minute_timestamp": minute_timestamp,
                "from_block": from_block,
                "to_block": to_block,
                "swap_topic0": topic0,
                "log_audit": log_audit,
                "raw_logs": pool_logs,
            }
            path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
            if not log_audit["complete"]:
                errors[candidate["pool_id"]] = "incomplete log query"
            else:
                collected += 1
        except Exception as exc:
            errors[candidate["pool_id"]] = str(exc)
        print(
            json.dumps(
                {
                    "processed": index,
                    "total": len(candidates),
                    "collected": collected,
                    "errors": len(errors),
                }
            ),
            flush=True,
        )
        if index < len(candidates):
            time.sleep(args.sleep_seconds)

    audit = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "collected": collected,
        "complete": collected == len(candidates) and not errors,
        "errors": errors,
    }
    (args.output_dir / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
