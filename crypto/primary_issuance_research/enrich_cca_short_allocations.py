#!/usr/bin/env python3
"""Enrich short-CCA events with block time, tx/receipt, and owner code evidence."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        default=base_dir / "data/cca_robinhood_short_allocations.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_allocations_enriched.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    source = json.loads(args.allocations.read_text())
    if not source.get("complete"):
        raise RuntimeError("short-allocation source is incomplete")

    events = [event for job in source["jobs"] for event in job["events"]]
    tx_hashes = sorted({event["transaction_hash"].lower() for event in events})
    block_numbers = sorted({int(event["block_number"]) for event in events})
    owners = sorted(
        {
            event["owner"].lower()
            for event in events
            if event["event"] == "bid_submitted"
        }
    )

    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    observed_chain_id = int(rpc.call("eth_chainId", []), 16)
    failures: list[dict[str, Any]] = []
    transactions: dict[str, Any] = {}
    receipts: dict[str, Any] = {}
    blocks: dict[str, Any] = {}
    owner_code: dict[str, Any] = {}

    def rpc_client() -> EvmRpc:
        return EvmRpc(args.rpc, args.proxy_mode, args.timeout)

    def fetch_transaction(tx_hash: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
        client = rpc_client()
        tx = client.call("eth_getTransactionByHash", [tx_hash])
        receipt = client.call("eth_getTransactionReceipt", [tx_hash])
        if tx is None or receipt is None:
            raise RuntimeError("missing transaction or receipt")
        return (
            tx_hash,
            {
                "from": tx["from"].lower(),
                "to": tx["to"].lower() if tx.get("to") else None,
                "block_number": int(tx["blockNumber"], 16),
                "value_raw": int(tx["value"], 16),
            },
            {
                "status": int(receipt["status"], 16),
                "gas_used": int(receipt["gasUsed"], 16),
                "effective_gas_price_raw": int(receipt["effectiveGasPrice"], 16),
                "gas_cost_raw": int(receipt["gasUsed"], 16)
                * int(receipt["effectiveGasPrice"], 16),
            },
        )

    def fetch_block(block_number: int) -> tuple[int, dict[str, Any]]:
        block = rpc_client().call("eth_getBlockByNumber", [hex(block_number), False])
        if block is None:
            raise RuntimeError("missing block")
        return block_number, {
            "timestamp": int(block["timestamp"], 16),
            "hash": block["hash"].lower(),
        }

    def fetch_owner(owner: str) -> tuple[str, dict[str, Any]]:
        code = rpc_client().call("eth_getCode", [owner, "latest"])
        return owner, {
            "latest_code": code,
            "is_eoa_at_latest": code in ("0x", "0x0"),
        }

    processed = 0
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(fetch_transaction, tx_hash): tx_hash for tx_hash in tx_hashes}
        for future in as_completed(futures):
            tx_hash = futures[future]
            processed += 1
            try:
                key, tx_row, receipt_row = future.result()
                transactions[key] = tx_row
                receipts[key] = receipt_row
            except Exception as exc:
                failures.append({"transaction_hash": tx_hash, "error": str(exc)})
            if processed % 50 == 0 or processed == len(tx_hashes):
                print(
                    json.dumps(
                        {
                            "stage": "transactions",
                            "processed": processed,
                            "total": len(tx_hashes),
                            "failures": len(failures),
                        }
                    ),
                    flush=True,
                )

    processed = 0
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(fetch_block, block_number): block_number for block_number in block_numbers}
        for future in as_completed(futures):
            block_number = futures[future]
            processed += 1
            try:
                key, block_row = future.result()
                blocks[str(key)] = block_row
            except Exception as exc:
                failures.append({"block_number": block_number, "error": str(exc)})
            if processed % 100 == 0 or processed == len(block_numbers):
                print(
                    json.dumps(
                        {
                            "stage": "blocks",
                            "processed": processed,
                            "total": len(block_numbers),
                            "failures": len(failures),
                        }
                    ),
                    flush=True,
                )

    processed = 0
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(fetch_owner, owner): owner for owner in owners}
        for future in as_completed(futures):
            owner = futures[future]
            processed += 1
            try:
                key, owner_row = future.result()
                owner_code[key] = owner_row
            except Exception as exc:
                failures.append({"owner": owner, "error": str(exc)})
            if processed % 100 == 0 or processed == len(owners):
                print(
                    json.dumps(
                        {
                            "stage": "owners",
                            "processed": processed,
                            "total": len(owners),
                            "failures": len(failures),
                        }
                    ),
                    flush=True,
                )

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "source_collected_at": source["collected_at"],
        "transactions": transactions,
        "receipts": receipts,
        "blocks": blocks,
        "owner_code": owner_code,
        "counts": {
            "event_transactions": len(tx_hashes),
            "event_blocks": len(block_numbers),
            "bid_owners": len(owners),
        },
        "failures": failures,
        "complete": not failures
        and len(transactions) == len(tx_hashes)
        and len(receipts) == len(tx_hashes)
        and len(blocks) == len(block_numbers)
        and len(owner_code) == len(owners),
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "counts": output["counts"],
                "failures": len(failures),
                "complete": output["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
