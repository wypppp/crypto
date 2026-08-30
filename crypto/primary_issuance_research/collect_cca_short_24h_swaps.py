#!/usr/bin/env python3
"""Collect every Uniswap v4 swap in the first 24h for material <=10m CCAs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_auctions import EvmRpc
from collect_cca_migrations import get_event_logs_adaptive


POOL_MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
SWAP_SIGNATURE = "Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)"


def block_timestamp(rpc: EvmRpc, block_number: int, cache: dict[int, int]) -> int:
    if block_number not in cache:
        block = rpc.call("eth_getBlockByNumber", [hex(block_number), False])
        if block is None:
            raise RuntimeError(f"missing block {block_number}")
        cache[block_number] = int(block["timestamp"], 16)
    return cache[block_number]


def find_block_at_or_before(
    rpc: EvmRpc,
    target_timestamp: int,
    low: int,
    high: int,
    cache: dict[int, int],
) -> int:
    """Return the greatest block whose timestamp is <= target."""
    if block_timestamp(rpc, low, cache) > target_timestamp:
        raise ValueError("low block is already after target")
    while low < high:
        middle = (low + high + 1) // 2
        if block_timestamp(rpc, middle, cache) <= target_timestamp:
            low = middle
        else:
            high = middle - 1
    return low


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allocations",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_allocations.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_24h_swaps",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-log-queries", type=int, default=500)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    source = json.loads(args.allocations.read_text())
    if not source.get("complete") or len(source.get("jobs", [])) != 29:
        raise RuntimeError("short-allocation source is incomplete or not the frozen 29")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    observed_chain_id = int(rpc.call("eth_chainId", []), 16)
    latest_block = int(rpc.call("eth_blockNumber", []), 16)
    topic0 = rpc.call("web3_sha3", ["0x" + SWAP_SIGNATURE.encode().hex()])
    timestamp_cache: dict[int, int] = {}
    jobs: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for index, allocation_job in enumerate(
        sorted(source["jobs"], key=lambda item: item["pool_id"]), 1
    ):
        pool_id = allocation_job["pool_id"].lower()
        path = args.output_dir / f"{pool_id}.json"
        if path.exists() and not args.refresh:
            cached = json.loads(path.read_text())
            if cached.get("log_audit", {}).get("complete"):
                jobs.append(
                    {
                        "pool_id": pool_id,
                        "from_block": cached["from_block"],
                        "to_block": cached["to_block"],
                        "raw_log_count": len(cached["raw_logs"]),
                        "cached": True,
                    }
                )
                continue
        try:
            start_block = int(allocation_job["migration_block"])
            end_timestamp = int(allocation_job["migration_timestamp"]) + 24 * 3600
            end_block = find_block_at_or_before(
                rpc,
                end_timestamp,
                start_block,
                latest_block,
                timestamp_cache,
            )
            logs, log_audit = get_event_logs_adaptive(
                rpc,
                POOL_MANAGER,
                start_block,
                end_block,
                [topic0],
                args.max_log_queries,
                indexed_topic1=pool_id,
            )
            pool_logs = [
                log
                for log in logs
                if len(log.get("topics", [])) >= 2
                and log["topics"][0].lower() == topic0.lower()
                and log["topics"][1].lower() == pool_id
            ]
            output = {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "auction": allocation_job["auction"],
                "token": allocation_job["token"],
                "pool_id": pool_id,
                "migration_timestamp": int(allocation_job["migration_timestamp"]),
                "window_end_timestamp": end_timestamp,
                "from_block": start_block,
                "to_block": end_block,
                "to_block_timestamp": block_timestamp(rpc, end_block, timestamp_cache),
                "swap_topic0": topic0,
                "log_audit": log_audit,
                "raw_logs": pool_logs,
            }
            path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
            if not log_audit["complete"]:
                errors[pool_id] = "incomplete log query"
            jobs.append(
                {
                    "pool_id": pool_id,
                    "from_block": start_block,
                    "to_block": end_block,
                    "raw_log_count": len(pool_logs),
                    "cached": False,
                }
            )
        except Exception as exc:
            errors[pool_id] = str(exc)
        print(
            json.dumps(
                {
                    "processed": index,
                    "total": len(source["jobs"]),
                    "pool_id": pool_id,
                    "errors": len(errors),
                    "logs": jobs[-1]["raw_log_count"] if jobs and jobs[-1]["pool_id"] == pool_id else None,
                }
            ),
            flush=True,
        )

    audit = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "latest_block": latest_block,
        "pool_manager": POOL_MANAGER,
        "swap_signature": SWAP_SIGNATURE,
        "swap_topic0": topic0,
        "selection": source["selection"] + "; swaps in [migration,migration+24h]",
        "jobs": jobs,
        "errors": errors,
        "complete": len(jobs) == 29 and not errors,
    }
    (args.output_dir / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )
    print(
        json.dumps(
            {
                "pools": len(jobs),
                "swaps": sum(job["raw_log_count"] for job in jobs),
                "errors": errors,
                "complete": audit["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
