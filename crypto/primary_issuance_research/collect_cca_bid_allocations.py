#!/usr/bin/env python3
"""Collect actual bid, exit, and claim events for executable CCA tail cases.

The scan stops at the already-selected peak minute.  This is intentional: a
position exited or claimed after the observed exit window was not executable
inside that window.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_auctions import EvmRpc


EVENT_SIGNATURES = {
    "bid_submitted": "BidSubmitted(uint256,address,uint256,uint128)",
    "bid_exited": "BidExited(uint256,address,uint256,uint256)",
    "tokens_claimed": "TokensClaimed(uint256,address,uint256)",
}


def uint_word(data: bytes, index: int) -> int:
    start = 32 * index
    return int.from_bytes(data[start : start + 32], "big")


def topic_uint(topic: str) -> int:
    return int(topic, 16)


def topic_address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def get_logs_adaptive(
    rpc: EvmRpc,
    address: str,
    start_block: int,
    end_block: int,
    topics: list[str],
    max_queries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pending = [(start_block, end_block)]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    calls = 0
    while pending and calls < max_queries:
        start, end = pending.pop()
        calls += 1
        try:
            results.extend(
                rpc.call(
                    "eth_getLogs",
                    [
                        {
                            "fromBlock": hex(start),
                            "toBlock": hex(end),
                            "address": address,
                            "topics": [topics],
                        }
                    ],
                )
            )
        except Exception as exc:
            if start == end:
                failures.append(
                    {"from_block": start, "to_block": end, "error": str(exc)}
                )
                continue
            middle = (start + end) // 2
            pending.append((middle + 1, end))
            pending.append((start, middle))
    return results, {
        "rpc_calls": calls,
        "complete": not pending and not failures,
        "unqueried_ranges": pending,
        "single_block_failures": failures,
    }


def decode_log(log: dict[str, Any], topic_to_name: dict[str, str]) -> dict[str, Any]:
    topics = log["topics"]
    name = topic_to_name[topics[0].lower()]
    data = bytes.fromhex(log["data"][2:])
    row: dict[str, Any] = {
        "event": name,
        "bid_id": topic_uint(topics[1]),
        "owner": topic_address(topics[2]),
        "block_number": int(log["blockNumber"], 16),
        "transaction_hash": log["transactionHash"].lower(),
        "transaction_index": int(log["transactionIndex"], 16),
        "log_index": int(log["logIndex"], 16),
    }
    if name == "bid_submitted":
        row.update({"price_q96": uint_word(data, 0), "amount_raw": uint_word(data, 1)})
    elif name == "bid_exited":
        row.update(
            {
                "tokens_filled_raw": uint_word(data, 0),
                "currency_refunded_raw": uint_word(data, 1),
            }
        )
    elif name == "tokens_claimed":
        row["tokens_claimed_raw"] = uint_word(data, 0)
    return row


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
        "--minute-blocks",
        type=Path,
        default=base_dir / "data/cca_robinhood_peak_minute_blocks.json",
    )
    parser.add_argument(
        "--swap-capacity",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_swap_capacity_summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_bid_allocations.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-log-queries", type=int, default=1_000)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    created = {row["auction"].lower(): row for row in json.loads(args.created.read_text())}
    material = {
        row["token"].lower(): row
        for row in json.loads(args.material_onchain.read_text())["rows"]
    }
    minute_jobs = {
        row["pool_id"].lower(): row
        for row in json.loads(args.minute_blocks.read_text())["jobs"]
    }
    capacity = json.loads(args.swap_capacity.read_text())
    target_pools = [
        pool_id.lower()
        for pool_id, detail in capacity["details"].items()
        if detail["summary"]["observed_equivalent_0_04_to_0_20_eth_exit"]
    ]

    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    observed_chain_id = int(rpc.call("eth_chainId", []), 16)
    latest_block = int(rpc.call("eth_blockNumber", []), 16)
    event_topics = {
        name: rpc.call("web3_sha3", ["0x" + signature.encode().hex()])
        for name, signature in EVENT_SIGNATURES.items()
    }
    topic_to_name = {value.lower(): name for name, value in event_topics.items()}

    jobs = []
    for pool_id in target_pools:
        detail = capacity["details"][pool_id]
        token = detail["candidate"]["token"].lower()
        onchain = material[token]
        auction = onchain["auction"].lower()
        auction_row = created[auction]
        minute = minute_jobs[pool_id]
        logs, audit = get_logs_adaptive(
            rpc,
            auction,
            int(auction_row["start_block"]),
            int(minute["to_block"]),
            list(event_topics.values()),
            args.max_log_queries,
        )
        decoded = sorted(
            (decode_log(log, topic_to_name) for log in logs),
            key=lambda row: (
                row["block_number"],
                row["transaction_index"],
                row["log_index"],
            ),
        )
        jobs.append(
            {
                "auction": auction,
                "token": token,
                "pool_id": pool_id,
                "tokens_recipient": auction_row["tokens_recipient"].lower(),
                "funds_recipient": auction_row["funds_recipient"].lower(),
                "validation_hook": auction_row["validation_hook"].lower(),
                "start_block": int(auction_row["start_block"]),
                "end_block": int(auction_row["end_block"]),
                "claim_block": int(auction_row["claim_block"]),
                "selected_minute_from_block": int(minute["from_block"]),
                "selected_minute_to_block": int(minute["to_block"]),
                "events": decoded,
                "event_counts": {
                    name: sum(row["event"] == name for row in decoded)
                    for name in EVENT_SIGNATURES
                },
                "audit": audit,
            }
        )

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "latest_block": latest_block,
        "official_contract_source": {
            "repository": "Uniswap/continuous-clearing-auction",
            "tag": "v2.1.0",
            "resolved_commit": "a56d42231e7bf048136d9d88fa61e8518c10c5ff",
            "event_interface": "src/interfaces/IContinuousClearingAuction.sol",
        },
        "event_signatures": EVENT_SIGNATURES,
        "event_topics": event_topics,
        "target_selection": (
            "the two persistent 5x cases whose selected peak minute contained "
            "an observed >=0.04 ETH issue-notional sell receiving >=0.20 ETH"
        ),
        "jobs": jobs,
        "complete": all(job["audit"]["complete"] for job in jobs),
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "target_pools": len(target_pools),
                "complete": output["complete"],
                "jobs": [
                    {
                        "auction": job["auction"],
                        "event_counts": job["event_counts"],
                        "rpc_calls": job["audit"]["rpc_calls"],
                    }
                    for job in jobs
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
