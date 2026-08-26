#!/usr/bin/env python3
"""Classify CCA graduates by subsequent LBP migration/recovery events."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_auctions import EvmRpc, get_logs_adaptive


EVENT_SIGNATURES = {
    "migrated": "Migrated(address,(address,address,uint24,int24,address),uint160,bytes)",
    "migration_failed": "MigrationFailed(address,bytes)",
    "funds_recovered": "FundsRecovered(address,address,uint256)",
}


def topic_address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    base_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--events",
        type=Path,
        default=base_dir / "data/cca_robinhood_created_events.json",
    )
    parser.add_argument("--rpc", default="https://robinhood-rpc.publicnode.com")
    parser.add_argument("--out-dir", type=Path, default=base_dir / "data")
    parser.add_argument("--output-prefix", default="cca_robinhood_migrations")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-log-queries", type=int, default=2_000)
    parser.add_argument(
        "--proxy-mode",
        choices=("auto", "env-proxy", "direct"),
        default="auto",
    )
    args = parser.parse_args()

    auctions = json.loads(args.events.read_text())
    v2 = [row for row in auctions if row["factory_version"].startswith("v2_")]
    strategies = sorted(
        {
            row.get("funds_recipient", "").lower()
            for row in v2
            if row.get("funds_recipient")
            and row.get("funds_recipient") != "0x0000000000000000000000000000000000000000"
        }
    )
    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    observed_chain_id = int(rpc.call("eth_chainId", []), 16)
    latest_block = int(rpc.call("eth_blockNumber", []), 16)
    topics = {
        name: rpc.call("web3_sha3", ["0x" + signature.encode().hex()])
        for name, signature in EVENT_SIGNATURES.items()
    }
    topic_to_name = {topic.lower(): name for name, topic in topics.items()}

    event_rows = []
    audit_strategies: dict[str, Any] = {}
    for strategy in strategies:
        try:
            code = rpc.call("eth_getCode", [strategy, "latest"])
            if code in ("0x", "0x0"):
                audit_strategies[strategy] = {"is_contract": False, "log_count": 0}
                continue
            logs, log_audit = get_logs_adaptive(
                rpc, strategy, 0, latest_block, args.max_log_queries
            )
            counts: dict[str, int] = {}
            for log in logs:
                log_topics = log.get("topics", [])
                name = topic_to_name.get(log_topics[0].lower() if log_topics else "")
                if not name or len(log_topics) < 2:
                    continue
                counts[name] = counts.get(name, 0) + 1
                data = bytes.fromhex(log.get("data", "0x")[2:])
                event_rows.append(
                    {
                        "event": name,
                        "strategy": strategy,
                        "auction": topic_address(log_topics[1]),
                        "pool_id": log_topics[2].lower() if name == "migrated" and len(log_topics) > 2 else "",
                        "recipient": (
                            topic_address(log_topics[2])
                            if name == "funds_recovered" and len(log_topics) > 2
                            else ""
                        ),
                        "amount_raw": (
                            int.from_bytes(data[:32], "big")
                            if name == "funds_recovered" and len(data) >= 32
                            else None
                        ),
                        "initial_sqrt_price_x96": (
                            int.from_bytes(data[:32], "big")
                            if name == "migrated" and len(data) >= 32
                            else None
                        ),
                        "block_number": int(log["blockNumber"], 16),
                        "transaction_hash": log["transactionHash"],
                        "log_index": int(log["logIndex"], 16),
                    }
                )
            audit_strategies[strategy] = {
                "is_contract": True,
                "raw_log_count": len(logs),
                "classified_counts": counts,
                **log_audit,
            }
        except Exception as exc:
            audit_strategies[strategy] = {"error": str(exc)}

    by_auction: dict[str, dict[str, Any]] = {}
    for row in event_rows:
        state = by_auction.setdefault(
            row["auction"],
            {
                "migrated": False,
                "migration_failed": False,
                "funds_recovered": False,
                "pool_id": "",
                "migration_block": None,
                "migration_tx": "",
            },
        )
        state[row["event"]] = True
        if row["event"] == "migrated":
            state["pool_id"] = row["pool_id"]
            state["migration_block"] = row["block_number"]
            state["migration_tx"] = row["transaction_hash"]

    joined = []
    for row in v2:
        state = by_auction.get(row["auction"].lower(), {})
        joined.append(
            {
                "auction": row["auction"],
                "token": row["token"],
                "factory_version": row["factory_version"],
                "funds_recipient": row.get("funds_recipient"),
                "created_block": row["block_number"],
                "end_block": row.get("end_block"),
                "migrated": bool(state.get("migrated", False)),
                "migration_failed": bool(state.get("migration_failed", False)),
                "funds_recovered": bool(state.get("funds_recovered", False)),
                "pool_id": state.get("pool_id", ""),
                "migration_block": state.get("migration_block"),
                "migration_tx": state.get("migration_tx", ""),
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    events_path = args.out_dir / f"{args.output_prefix}_events.json"
    joined_path = args.out_dir / f"{args.output_prefix}.csv"
    audit_path = args.out_dir / f"{args.output_prefix}_audit.json"
    events_path.write_text(json.dumps(event_rows, indent=2, ensure_ascii=False) + "\n")
    with joined_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(joined[0]))
        writer.writeheader()
        writer.writerows(joined)
    audit = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "latest_block": latest_block,
        "topics": topics,
        "auction_rows": len(joined),
        "strategy_addresses": len(strategies),
        "migrated_auctions": sum(row["migrated"] for row in joined),
        "migration_failed_auctions": sum(row["migration_failed"] for row in joined),
        "funds_recovered_auctions": sum(row["funds_recovered"] for row in joined),
        "strategies": audit_strategies,
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: audit[key] for key in audit if key != "strategies"}, indent=2))


if __name__ == "__main__":
    main()
