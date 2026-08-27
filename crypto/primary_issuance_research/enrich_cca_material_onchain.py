#!/usr/bin/env python3
"""Add on-chain migration timestamps and token decimals to material CCA pools."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DECIMALS_SELECTOR = "0x313ce567"


def rpc_batch(url: str, calls: list[dict[str, Any]], timeout: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(calls).encode(),
        headers={"content-type": "application/json", "user-agent": "primary-issuance-research/0.1"},
    )
    failures = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:
            failures.append(str(exc))
            if attempt < 2:
                time.sleep(10 if isinstance(exc, urllib.error.HTTPError) and exc.code == 429 else 2**attempt)
    raise RuntimeError("; ".join(failures))


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=base_dir / "data/cca_robinhood_ohlcv_daily",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/cca_robinhood_material_onchain.json",
    )
    args = parser.parse_args()

    source_rows = [json.loads(path.read_text()) for path in sorted(args.cache_dir.glob("0x*.json"))]
    blocks = sorted({int(row["migration_block"]) for row in source_rows})
    tokens = sorted({row["token"].lower() for row in source_rows})
    calls = [
        {
            "jsonrpc": "2.0",
            "id": f"block:{block}",
            "method": "eth_getBlockByNumber",
            "params": [hex(block), False],
        }
        for block in blocks
    ] + [
        {
            "jsonrpc": "2.0",
            "id": f"decimals:{token}",
            "method": "eth_call",
            "params": [{"to": token, "data": DECIMALS_SELECTOR}, "latest"],
        }
        for token in tokens
    ]

    responses: dict[str, dict[str, Any]] = {}
    batches = chunks(calls, args.batch_size)
    for batch_index, batch in enumerate(batches):
        for response in rpc_batch(args.rpc, batch, args.timeout):
            responses[str(response["id"])] = response
        if batch_index + 1 < len(batches):
            time.sleep(args.sleep_seconds)

    errors: dict[str, Any] = {}
    block_timestamps: dict[int, int] = {}
    token_decimals: dict[str, int] = {}
    for block in blocks:
        key = f"block:{block}"
        response = responses.get(key, {})
        result = response.get("result")
        if not result:
            errors[key] = response.get("error", "missing response")
        else:
            block_timestamps[block] = int(result["timestamp"], 16)
    for token in tokens:
        key = f"decimals:{token}"
        response = responses.get(key, {})
        result = response.get("result")
        if not result or result == "0x":
            errors[key] = response.get("error", "missing response")
        else:
            token_decimals[token] = int(result, 16)

    rows = []
    for source in source_rows:
        meta = source.get("payload", {}).get("meta", {})
        base_address = (
            meta.get("base", {}).get("address", "").lower()
        )
        quote_address = meta.get("quote", {}).get("address", "").lower()
        token = source["token"].lower()
        token_side = "base" if base_address == token else "quote" if quote_address == token else None
        if token_side is None:
            errors[f"token_orientation:{source['pool_id']}"] = {
                "expected_token": token,
                "observed_base": base_address,
                "observed_quote": quote_address,
            }
        rows.append(
            {
                "auction": source["auction"],
                "token": token,
                "pool_id": source["pool_id"],
                "migration_block": source["migration_block"],
                "migration_timestamp": block_timestamps.get(source["migration_block"]),
                "token_decimals": token_decimals.get(token),
                "currency_decimals": 18,
                "gecko_token_side": token_side,
                "gecko_base_address": base_address,
                "gecko_quote_address": quote_address,
                "currency_raised_raw": source["currency_raised_raw"],
                "total_cleared_raw": source["total_cleared_raw"],
            }
        )

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "rows": rows,
        "complete": not errors and all(
            row["migration_timestamp"] is not None and row["token_decimals"] is not None
            for row in rows
        ),
        "errors": errors,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "rows": len(rows),
                "complete": output["complete"],
                "errors": len(errors),
                "token_decimals": {
                    str(value): sum(1 for row in rows if row["token_decimals"] == value)
                    for value in sorted(set(token_decimals.values()))
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
