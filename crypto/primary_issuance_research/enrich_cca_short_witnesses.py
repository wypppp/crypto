#!/usr/bin/env python3
"""Fetch transaction sender and gas for selected CCA 24h capacity witnesses."""

from __future__ import annotations

import argparse
import csv
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
        "--bids",
        type=Path,
        default=base_dir / "output/cca_robinhood_short_execution_bids.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_short_witness_transactions.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    rows = list(csv.DictReader(args.bids.open()))
    tx_hashes = sorted(
        {
            row["witness_tx"].lower()
            for row in rows
            if row.get("capacity_witness_5x_24h") == "True" and row.get("witness_tx")
        }
    )
    if not tx_hashes:
        raise RuntimeError("no selected witness transactions in bid analysis")

    observed_chain_id = int(
        EvmRpc(args.rpc, args.proxy_mode, args.timeout).call("eth_chainId", []), 16
    )
    results: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []

    def fetch(tx_hash: str) -> tuple[str, dict[str, Any]]:
        rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
        transaction = rpc.call("eth_getTransactionByHash", [tx_hash])
        receipt = rpc.call("eth_getTransactionReceipt", [tx_hash])
        if transaction is None or receipt is None:
            raise RuntimeError("missing transaction or receipt")
        gas_used = int(receipt["gasUsed"], 16)
        effective_gas_price = int(receipt["effectiveGasPrice"], 16)
        return tx_hash, {
            "from": transaction["from"].lower(),
            "to": transaction["to"].lower() if transaction.get("to") else None,
            "block_number": int(transaction["blockNumber"], 16),
            "status": int(receipt["status"], 16),
            "gas_used": gas_used,
            "effective_gas_price_raw": effective_gas_price,
            "gas_cost_raw": gas_used * effective_gas_price,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch, tx_hash): tx_hash for tx_hash in tx_hashes}
        for index, future in enumerate(as_completed(futures), 1):
            tx_hash = futures[future]
            try:
                key, value = future.result()
                results[key] = value
            except Exception as exc:
                failures.append({"transaction_hash": tx_hash, "error": str(exc)})
            if index % 25 == 0 or index == len(tx_hashes):
                print(
                    json.dumps(
                        {
                            "processed": index,
                            "total": len(tx_hashes),
                            "failures": len(failures),
                        }
                    ),
                    flush=True,
                )

    payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "transactions": results,
        "failures": failures,
        "complete": not failures and len(results) == len(tx_hashes),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "transactions": len(results),
                "failures": len(failures),
                "complete": payload["complete"],
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
