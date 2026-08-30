#!/usr/bin/env python3
"""Recover timed-out material CCA bid scans by adaptively splitting ranges."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from collect_cca_auctions import EvmRpc
from collect_cca_bid_allocations import decode_log, get_logs_adaptive
from collect_cca_material_bids import EVENT_TOPIC


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_bids.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    payload = json.loads(args.input.read_text())
    failed_auctions = {
        row["id"].split(":", 1)[1]
        for row in payload["audit"]["failures"]
        if row["id"].startswith("logs:")
    }
    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    remaining_failures = [
        row
        for row in payload["audit"]["failures"]
        if not row["id"].startswith("logs:")
    ]
    recovered = []
    for row in payload["rows"]:
        if row["auction"] not in failed_auctions:
            continue
        logs, audit = get_logs_adaptive(
            rpc,
            row["auction"],
            row["start_block"],
            row["end_block"],
            [EVENT_TOPIC],
            1_000,
        )
        if not audit["complete"]:
            remaining_failures.append(
                {
                    "id": f"logs:{row['auction']}",
                    "error": json.dumps(audit, ensure_ascii=False),
                }
            )
            continue
        bids = sorted(
            (decode_log(log, {EVENT_TOPIC: "bid_submitted"}) for log in logs),
            key=lambda event: (
                event["block_number"],
                event["transaction_index"],
                event["log_index"],
            ),
        )
        row["bids"] = bids
        row["bid_count"] = len(bids)
        row["unique_bid_owner_count"] = len({bid["owner"] for bid in bids})
        if bids:
            row["first_bid_block"] = bids[0]["block_number"]
            row["last_bid_block"] = bids[-1]["block_number"]
            first = rpc.call("eth_getBlockByNumber", [hex(row["first_bid_block"]), False])
            last = rpc.call("eth_getBlockByNumber", [hex(row["last_bid_block"]), False])
            row["first_bid_timestamp"] = int(first["timestamp"], 16)
            row["last_bid_timestamp"] = int(last["timestamp"], 16)
            row["first_bid_delay_seconds"] = (
                row["first_bid_timestamp"] - row["start_timestamp"]
            )
            row["last_bid_seconds_before_end"] = (
                row["end_timestamp"] - row["last_bid_timestamp"]
            )
        recovered.append(
            {
                "auction": row["auction"],
                "bid_count": len(bids),
                "rpc_calls": audit["rpc_calls"],
            }
        )

    payload["collected_at"] = datetime.now(timezone.utc).isoformat()
    payload["audit"]["failures"] = remaining_failures
    payload["audit"]["log_result_count"] = len(payload["rows"]) - sum(
        row["id"].startswith("logs:") for row in remaining_failures
    )
    payload["audit"]["recovered_adaptively"] = recovered
    payload["audit"]["complete"] = not remaining_failures and all(
        row["auction_duration_seconds"] is not None for row in payload["rows"]
    )
    args.input.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "recovered": recovered,
                "remaining_failures": len(remaining_failures),
                "total_bids": sum(row["bid_count"] for row in payload["rows"]),
                "complete": payload["audit"]["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
