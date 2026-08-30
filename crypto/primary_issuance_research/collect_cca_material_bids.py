#!/usr/bin/env python3
"""Collect BidSubmitted logs and auction timing for material Robinhood CCAs."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_bid_allocations import decode_log


EVENT_TOPIC = "0x650baad5cd8ca09b8f580be220fa04ce2ba905a041f764b6a3fe2c848eb70540"


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def rpc_batch(url: str, calls: list[dict[str, Any]], timeout: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(calls).encode(),
        headers={
            "content-type": "application/json",
            "user-agent": "primary-issuance-research/0.1",
        },
    )
    errors = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
                return payload if isinstance(payload, list) else [payload]
        except Exception as exc:
            errors.append(str(exc))
            if attempt < 2:
                time.sleep(min(2**attempt, 8))
    raise RuntimeError("; ".join(errors))


def collect_calls(
    url: str,
    calls: list[dict[str, Any]],
    batch_size: int,
    timeout: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    results: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []

    def run_one(call: dict[str, Any]) -> list[dict[str, Any]]:
        return rpc_batch(url, [call], timeout)

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
        pending = {executor.submit(run_one, call): call for call in calls}
        for future in concurrent.futures.as_completed(pending):
            call = pending[future]
            completed += 1
            if completed % 25 == 0 or completed == len(calls):
                print(
                    json.dumps({"rpc_progress": f"{completed}/{len(calls)}"}),
                    flush=True,
                )
            try:
                responses = future.result()
            except Exception as exc:
                responses = []
                failures.append({"id": call["id"], "error": str(exc)})
            for response in responses:
                response_id = str(response.get("id"))
                if "result" in response and response["result"] is not None:
                    results[response_id] = response["result"]
                else:
                    failures.append(
                        {"id": response_id, "error": json.dumps(response.get("error"))}
                    )
    return results, failures


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--created",
        type=Path,
        default=base_dir / "data/cca_robinhood_created_events.json",
    )
    parser.add_argument(
        "--material-onchain",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_onchain.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_bids.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    created = {row["auction"].lower(): row for row in json.loads(args.created.read_text())}
    material = json.loads(args.material_onchain.read_text())["rows"]
    rows = []
    for row in material:
        auction = row["auction"].lower()
        source = created[auction]
        rows.append(
            {
                "auction": auction,
                "token": row["token"].lower(),
                "pool_id": row["pool_id"].lower(),
                "created_block": int(source["block_number"]),
                "start_block": int(source["start_block"]),
                "end_block": int(source["end_block"]),
                "claim_block": int(source["claim_block"]),
                "migration_block": int(row["migration_block"]),
                "tokens_recipient": source["tokens_recipient"].lower(),
                "funds_recipient": source["funds_recipient"].lower(),
                "validation_hook": source["validation_hook"].lower(),
                "currency_raised_raw": int(row["currency_raised_raw"]),
            }
        )

    log_calls = [
        {
            "jsonrpc": "2.0",
            "id": f"logs:{row['auction']}",
            "method": "eth_getLogs",
            "params": [
                {
                    "fromBlock": hex(row["start_block"]),
                    "toBlock": hex(row["end_block"]),
                    "address": row["auction"],
                    "topics": [EVENT_TOPIC],
                }
            ],
        }
        for row in rows
    ]
    block_numbers = sorted(
        {
            row[key]
            for row in rows
            for key in ("created_block", "start_block", "end_block", "migration_block")
        }
    )
    block_calls = [
        {
            "jsonrpc": "2.0",
            "id": f"block:{block}",
            "method": "eth_getBlockByNumber",
            "params": [hex(block), False],
        }
        for block in block_numbers
    ]
    log_results, log_failures = collect_calls(
        args.rpc, log_calls, args.batch_size, args.timeout
    )
    block_results, block_failures = collect_calls(
        args.rpc, block_calls, args.batch_size, args.timeout
    )
    topic_to_name = {EVENT_TOPIC: "bid_submitted"}
    for row in rows:
        raw_logs = log_results.get(f"logs:{row['auction']}", [])
        row["bids"] = sorted(
            (decode_log(log, topic_to_name) for log in raw_logs),
            key=lambda event: (
                event["block_number"],
                event["transaction_index"],
                event["log_index"],
            ),
        )
        row["bid_count"] = len(row["bids"])
        row["unique_bid_owner_count"] = len(
            {event["owner"] for event in row["bids"]}
        )
        for name in ("created", "start", "end", "migration"):
            block = block_results.get(f"block:{row[f'{name}_block']}")
            row[f"{name}_timestamp"] = (
                int(block["timestamp"], 16) if block else None
            )
        if row["start_timestamp"] is not None and row["end_timestamp"] is not None:
            row["auction_duration_seconds"] = (
                row["end_timestamp"] - row["start_timestamp"]
            )
        else:
            row["auction_duration_seconds"] = None
        if row["created_timestamp"] is not None and row["start_timestamp"] is not None:
            row["onchain_notice_seconds"] = (
                row["start_timestamp"] - row["created_timestamp"]
            )
        else:
            row["onchain_notice_seconds"] = None
        if row["bids"]:
            first = block_results.get(f"block:{row['bids'][0]['block_number']}")
            last = block_results.get(f"block:{row['bids'][-1]['block_number']}")
            # Bid block timestamps were not part of the initial block batch.
            row["first_bid_block"] = row["bids"][0]["block_number"]
            row["last_bid_block"] = row["bids"][-1]["block_number"]
            row["first_bid_timestamp"] = int(first["timestamp"], 16) if first else None
            row["last_bid_timestamp"] = int(last["timestamp"], 16) if last else None

    # Fetch first/last bid blocks after discovering them.
    bid_blocks = sorted(
        {
            row[key]
            for row in rows
            for key in ("first_bid_block", "last_bid_block")
            if key in row
        }
        - set(block_numbers)
    )
    bid_block_calls = [
        {
            "jsonrpc": "2.0",
            "id": f"block:{block}",
            "method": "eth_getBlockByNumber",
            "params": [hex(block), False],
        }
        for block in bid_blocks
    ]
    bid_block_results, bid_block_failures = collect_calls(
        args.rpc, bid_block_calls, args.batch_size, args.timeout
    )
    block_results.update(bid_block_results)
    for row in rows:
        if not row["bids"]:
            continue
        first = block_results.get(f"block:{row['first_bid_block']}")
        last = block_results.get(f"block:{row['last_bid_block']}")
        row["first_bid_timestamp"] = int(first["timestamp"], 16) if first else None
        row["last_bid_timestamp"] = int(last["timestamp"], 16) if last else None
        row["first_bid_delay_seconds"] = (
            row["first_bid_timestamp"] - row["start_timestamp"]
            if row["first_bid_timestamp"] is not None
            and row["start_timestamp"] is not None
            else None
        )
        row["last_bid_seconds_before_end"] = (
            row["end_timestamp"] - row["last_bid_timestamp"]
            if row["last_bid_timestamp"] is not None and row["end_timestamp"] is not None
            else None
        )

    failures = log_failures + block_failures + bid_block_failures
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "selection": "successful Migrated native-currency CCAs with currencyRaised >= 1 ETH",
        "bid_event_signature": "BidSubmitted(uint256,address,uint256,uint128)",
        "bid_event_topic": EVENT_TOPIC,
        "rows": rows,
        "audit": {
            "auction_count": len(rows),
            "log_result_count": len(log_results),
            "block_result_count": len(block_results),
            "failures": failures,
            "complete": not failures
            and len(log_results) == len(rows)
            and all(row["auction_duration_seconds"] is not None for row in rows),
        },
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "auction_count": len(rows),
                "bid_count": sum(row["bid_count"] for row in rows),
                "unique_owners": len(
                    {bid["owner"] for row in rows for bid in row["bids"]}
                ),
                "failures": len(failures),
                "complete": output["audit"]["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
