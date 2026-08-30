#!/usr/bin/env python3
"""Enrich CCA bid allocations and peak sells with RPC transaction evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_auctions import EvmRpc


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allocations",
        type=Path,
        default=base_dir / "data/cca_robinhood_bid_allocations.json",
    )
    parser.add_argument(
        "--swap-capacity",
        type=Path,
        default=base_dir / "output/cca_robinhood_peak_swap_capacity_summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_bid_execution_enriched.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    allocations = json.loads(args.allocations.read_text())
    capacity = json.loads(args.swap_capacity.read_text())
    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    observed_chain_id = int(rpc.call("eth_chainId", []), 16)

    event_txs = {
        event["transaction_hash"]
        for job in allocations["jobs"]
        for event in job["events"]
    }
    selected_sell_txs = {
        swap["transaction_hash"].lower()
        for pool_id, detail in capacity["details"].items()
        if detail["summary"]["observed_equivalent_0_04_to_0_20_eth_exit"]
        for swap in detail["qualifying_sells"]
        if swap["initial_vwap_notional_eth"] >= 0.04
        and swap["native_amount_eth"] >= 0.20
    }
    tx_hashes = sorted(event_txs | selected_sell_txs)
    transactions: dict[str, Any] = {}
    receipts: dict[str, Any] = {}
    block_numbers: set[int] = set()
    failures: list[dict[str, str]] = []
    for tx_hash in tx_hashes:
        try:
            tx = rpc.call("eth_getTransactionByHash", [tx_hash])
            receipt = rpc.call("eth_getTransactionReceipt", [tx_hash])
            transactions[tx_hash] = {
                "from": tx["from"].lower(),
                "to": tx["to"].lower() if tx.get("to") else None,
                "block_number": int(tx["blockNumber"], 16),
                "value_raw": int(tx["value"], 16),
            }
            receipts[tx_hash] = {
                "status": int(receipt["status"], 16),
                "gas_used": int(receipt["gasUsed"], 16),
                "effective_gas_price_raw": int(receipt["effectiveGasPrice"], 16),
                "gas_cost_raw": int(receipt["gasUsed"], 16)
                * int(receipt["effectiveGasPrice"], 16),
            }
            block_numbers.add(int(tx["blockNumber"], 16))
        except Exception as exc:
            failures.append({"transaction_hash": tx_hash, "error": str(exc)})

    blocks: dict[str, Any] = {}
    for block_number in sorted(block_numbers):
        try:
            block = rpc.call("eth_getBlockByNumber", [hex(block_number), False])
            blocks[str(block_number)] = {
                "timestamp": int(block["timestamp"], 16),
                "hash": block["hash"].lower(),
            }
        except Exception as exc:
            failures.append({"block_number": str(block_number), "error": str(exc)})

    owners = sorted(
        {
            event["owner"]
            for job in allocations["jobs"]
            for event in job["events"]
            if event["event"] == "bid_submitted"
        }
    )
    owner_code: dict[str, Any] = {}
    for owner in owners:
        try:
            code = rpc.call("eth_getCode", [owner, "latest"])
            owner_code[owner] = {
                "latest_code": code,
                "is_eoa_at_latest": code in ("0x", "0x0"),
            }
        except Exception as exc:
            failures.append({"owner": owner, "error": str(exc)})

    bidder_owners = set(owners)
    selected_sells = []
    for pool_id, detail in capacity["details"].items():
        if not detail["summary"]["observed_equivalent_0_04_to_0_20_eth_exit"]:
            continue
        for swap in detail["qualifying_sells"]:
            if not (
                swap["initial_vwap_notional_eth"] >= 0.04
                and swap["native_amount_eth"] >= 0.20
            ):
                continue
            tx_hash = swap["transaction_hash"].lower()
            sender = transactions.get(tx_hash, {}).get("from")
            selected_sells.append(
                {
                    "pool_id": pool_id,
                    "token": detail["candidate"]["token"].lower(),
                    "transaction_hash": tx_hash,
                    "block_number": swap["block_number"],
                    "log_index": swap["log_index"],
                    "sender": sender,
                    "sender_is_any_target_bid_owner": sender in bidder_owners,
                    "native_out_eth": swap["native_amount_eth"],
                    "token_amount": swap["token_amount"],
                    "average_execution_x_auction_vwap": swap["average_execution_x"],
                }
            )

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "transaction_count": len(transactions),
        "receipt_count": len(receipts),
        "block_count": len(blocks),
        "owner_count": len(owner_code),
        "eoa_owner_count": sum(row["is_eoa_at_latest"] for row in owner_code.values()),
        "transactions": transactions,
        "receipts": receipts,
        "blocks": blocks,
        "owner_code": owner_code,
        "selected_sells": selected_sells,
        "failures": failures,
        "complete": not failures
        and len(transactions) == len(tx_hashes)
        and len(receipts) == len(tx_hashes),
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "transaction_count": output["transaction_count"],
                "owner_count": output["owner_count"],
                "eoa_owner_count": output["eoa_owner_count"],
                "selected_sells": selected_sells,
                "failures": len(failures),
                "complete": output["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
