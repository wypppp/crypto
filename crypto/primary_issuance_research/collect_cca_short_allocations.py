#!/usr/bin/env python3
"""Collect complete bid/exit/claim event histories for material <=10m CCAs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_auctions import EvmRpc
from collect_cca_bid_allocations import decode_log, get_logs_adaptive


EVENT_SIGNATURES = {
    "bid_submitted": "BidSubmitted(uint256,address,uint256,uint128)",
    "bid_exited": "BidExited(uint256,address,uint256,uint256)",
    "tokens_claimed": "TokensClaimed(uint256,address,uint256)",
}


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--material-bids",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_bids.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_allocations.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-log-queries", type=int, default=500)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    payload = json.loads(args.material_bids.read_text())
    if not payload.get("audit", {}).get("complete"):
        raise RuntimeError("material bid collection is incomplete")
    targets = [
        row for row in payload["rows"] if int(row["auction_duration_seconds"]) <= 600
    ]
    if len(targets) != 29:
        raise RuntimeError(f"frozen short-auction universe changed: {len(targets)} != 29")

    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    observed_chain_id = int(rpc.call("eth_chainId", []), 16)
    latest_block = int(rpc.call("eth_blockNumber", []), 16)
    event_topics = {
        name: rpc.call("web3_sha3", ["0x" + signature.encode().hex()])
        for name, signature in EVENT_SIGNATURES.items()
    }
    topic_to_name = {value.lower(): name for name, value in event_topics.items()}

    jobs: list[dict[str, Any]] = []
    for index, row in enumerate(sorted(targets, key=lambda item: item["auction"]), 1):
        logs, audit = get_logs_adaptive(
            rpc,
            row["auction"],
            int(row["start_block"]),
            latest_block,
            list(event_topics.values()),
            args.max_log_queries,
        )
        decoded = sorted(
            (decode_log(log, topic_to_name) for log in logs),
            key=lambda event: (
                event["block_number"],
                event["transaction_index"],
                event["log_index"],
            ),
        )
        jobs.append(
            {
                "auction": row["auction"].lower(),
                "token": row["token"].lower(),
                "pool_id": row["pool_id"].lower(),
                "tokens_recipient": row["tokens_recipient"].lower(),
                "funds_recipient": row["funds_recipient"].lower(),
                "validation_hook": row["validation_hook"].lower(),
                "created_block": int(row["created_block"]),
                "start_block": int(row["start_block"]),
                "end_block": int(row["end_block"]),
                "claim_block": int(row["claim_block"]),
                "migration_block": int(row["migration_block"]),
                "created_timestamp": int(row["created_timestamp"]),
                "start_timestamp": int(row["start_timestamp"]),
                "end_timestamp": int(row["end_timestamp"]),
                "migration_timestamp": int(row["migration_timestamp"]),
                "currency_raised_raw": int(row["currency_raised_raw"]),
                "events": decoded,
                "event_counts": {
                    name: sum(event["event"] == name for event in decoded)
                    for name in EVENT_SIGNATURES
                },
                "audit": audit,
            }
        )
        print(
            json.dumps(
                {
                    "processed": index,
                    "total": len(targets),
                    "auction": row["auction"],
                    "events": len(decoded),
                    "complete": audit["complete"],
                }
            ),
            flush=True,
        )

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "latest_block": latest_block,
        "selection": (
            "successful migrated Robinhood native-currency CCAs with "
            "currencyRaised >= 1 ETH and auction_duration_seconds <= 600"
        ),
        "event_signatures": EVENT_SIGNATURES,
        "event_topics": event_topics,
        "jobs": jobs,
        "complete": all(job["audit"]["complete"] for job in jobs),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "auction_count": len(jobs),
                "submitted": sum(job["event_counts"]["bid_submitted"] for job in jobs),
                "exited": sum(job["event_counts"]["bid_exited"] for job in jobs),
                "claimed": sum(job["event_counts"]["tokens_claimed"] for job in jobs),
                "complete": output["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
