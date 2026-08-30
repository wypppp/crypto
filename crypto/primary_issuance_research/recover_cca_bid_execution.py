#!/usr/bin/env python3
"""Retry isolated RPC failures in the CCA bid execution enrichment artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from collect_cca_auctions import EvmRpc


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=base_dir / "data/cca_robinhood_bid_execution_enriched.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    payload = json.loads(args.input.read_text())
    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    remaining = []
    recovered = []
    for failure in payload["failures"]:
        try:
            if "transaction_hash" in failure:
                tx_hash = failure["transaction_hash"]
                tx = rpc.call("eth_getTransactionByHash", [tx_hash])
                receipt = rpc.call("eth_getTransactionReceipt", [tx_hash])
                payload["transactions"][tx_hash] = {
                    "from": tx["from"].lower(),
                    "to": tx["to"].lower() if tx.get("to") else None,
                    "block_number": int(tx["blockNumber"], 16),
                    "value_raw": int(tx["value"], 16),
                }
                payload["receipts"][tx_hash] = {
                    "status": int(receipt["status"], 16),
                    "gas_used": int(receipt["gasUsed"], 16),
                    "effective_gas_price_raw": int(receipt["effectiveGasPrice"], 16),
                    "gas_cost_raw": int(receipt["gasUsed"], 16)
                    * int(receipt["effectiveGasPrice"], 16),
                }
                block_number = int(tx["blockNumber"], 16)
                if str(block_number) not in payload["blocks"]:
                    block = rpc.call("eth_getBlockByNumber", [hex(block_number), False])
                    payload["blocks"][str(block_number)] = {
                        "timestamp": int(block["timestamp"], 16),
                        "hash": block["hash"].lower(),
                    }
                recovered.append({"transaction_hash": tx_hash})
            elif "block_number" in failure:
                block_number = int(failure["block_number"])
                block = rpc.call("eth_getBlockByNumber", [hex(block_number), False])
                payload["blocks"][str(block_number)] = {
                    "timestamp": int(block["timestamp"], 16),
                    "hash": block["hash"].lower(),
                }
                recovered.append({"block_number": block_number})
            else:
                remaining.append(failure)
        except Exception as exc:
            remaining.append({**failure, "retry_error": str(exc)})

    payload["collected_at"] = datetime.now(timezone.utc).isoformat()
    payload["transaction_count"] = len(payload["transactions"])
    payload["receipt_count"] = len(payload["receipts"])
    payload["block_count"] = len(payload["blocks"])
    payload["failures"] = remaining
    payload["recovered"] = recovered
    payload["complete"] = not remaining
    args.input.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "recovered": recovered,
                "remaining_failures": len(remaining),
                "complete": payload["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
