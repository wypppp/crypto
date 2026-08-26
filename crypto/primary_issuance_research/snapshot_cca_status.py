#!/usr/bin/env python3
"""Batch-read current economic state for v2 CCA auction contracts."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_metadao_launches import http_json


FUNCTIONS = {
    "graduated": "isGraduated()",
    "currency_raised_raw": "currencyRaised()",
    "clearing_price_q96": "clearingPrice()",
    "total_cleared_raw": "totalCleared()",
    "remaining_supply_raw": "remainingSupply()",
    "total_supply_raw": "totalSupply()",
}


def decode_word(value: str, kind: str) -> Any:
    if not value or value == "0x":
        return None
    number = int(value, 16)
    return bool(number) if kind == "graduated" else number


def main() -> None:
    parser = argparse.ArgumentParser()
    base_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--events",
        type=Path,
        default=base_dir / "data/cca_robinhood_created_events.json",
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--out-dir", type=Path, default=base_dir / "data")
    parser.add_argument("--output-prefix", default="cca_robinhood_status")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--batch-pause", type=float, default=0.25)
    parser.add_argument(
        "--postprocess-existing",
        action="store_true",
        help="Rebuild CSV/audit from an already written JSON after an export-only failure",
    )
    parser.add_argument(
        "--proxy-mode",
        choices=("auto", "env-proxy", "direct"),
        default="auto",
    )
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.output_prefix}.json"
    csv_path = args.out_dir / f"{args.output_prefix}.csv"
    audit_path = args.out_dir / f"{args.output_prefix}_audit.json"
    if args.postprocess_existing:
        output = json.loads(json_path.read_text())
        columns = list(dict.fromkeys(key for row in output for key in row))
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(
                [dict(row, rpc_errors=json.dumps(row["rpc_errors"], ensure_ascii=False)) for row in output]
            )
        audit = {
            "snapshot_at": output[0]["snapshot_at"] if output else None,
            "rpc": args.rpc,
            "rows": len(output),
            "rows_with_any_rpc_error": sum(bool(row["rpc_errors"]) for row in output),
            "graduated_true": sum(row.get("graduated") is True for row in output),
            "graduated_false": sum(row.get("graduated") is False for row in output),
            "postprocessed_existing_json": True,
        }
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(audit, indent=2))
        return

    rows = json.loads(args.events.read_text())
    rows = [row for row in rows if row["factory_version"].startswith("v2_")]
    request_id = 0

    def single_call(method: str, params: list[Any]) -> Any:
        nonlocal request_id
        request_id += 1
        response = http_json(
            args.rpc,
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            proxy_mode=args.proxy_mode,
            timeout=args.timeout,
        )
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    observed_chain_id = int(single_call("eth_chainId", []), 16)
    latest_block = int(single_call("eth_blockNumber", []), 16)
    selectors = {}
    for name, signature in FUNCTIONS.items():
        digest = single_call("web3_sha3", ["0x" + signature.encode().hex()])
        selectors[name] = digest[:10]

    snapshot_at = datetime.now(timezone.utc).isoformat()
    values = [dict() for _ in rows]
    errors = [dict() for _ in rows]

    def batch_rpc(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(7):
            try:
                response = http_json(
                    args.rpc,
                    payload,
                    proxy_mode=args.proxy_mode,
                    timeout=args.timeout,
                )
                if not isinstance(response, list):
                    raise RuntimeError(f"batch RPC did not return a list: {type(response)}")
                return response
            except Exception as exc:
                last_error = exc
                if attempt == 6:
                    break
                time.sleep(min(30, 2 ** (attempt + 1)))
        raise RuntimeError(f"batch RPC failed after retries: {last_error}")

    # Phase 1 uses one call per auction. This establishes the failure base rate
    # without spending five extra calls on thousands of non-graduated launches.
    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]
        payload = []
        lookup = {}
        for row_index, row in enumerate(batch):
            request_id += 1
            global_index = start + row_index
            lookup[request_id] = global_index
            payload.append(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "eth_call",
                    "params": [
                        {"to": row["auction"], "data": selectors["graduated"]},
                        "latest",
                    ],
                }
            )
        responses = batch_rpc(payload)
        for response in responses:
            global_index = lookup[response["id"]]
            if "error" in response:
                errors[global_index]["graduated"] = response["error"]
            else:
                values[global_index]["graduated"] = decode_word(
                    response.get("result", "0x"), "graduated"
                )
        time.sleep(args.batch_pause)

    # Phase 2 reads economic details only for launches that actually graduated.
    graduated_indices = [
        index for index, value in enumerate(values) if value.get("graduated") is True
    ]
    detail_names = [name for name in FUNCTIONS if name != "graduated"]
    detail_batch_size = max(1, 100 // len(detail_names))
    for start in range(0, len(graduated_indices), detail_batch_size):
        indices = graduated_indices[start : start + detail_batch_size]
        payload = []
        lookup = {}
        for global_index in indices:
            row = rows[global_index]
            for name in detail_names:
                request_id += 1
                lookup[request_id] = (global_index, name)
                payload.append(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "eth_call",
                        "params": [{"to": row["auction"], "data": selectors[name]}, "latest"],
                    }
                )
        responses = batch_rpc(payload)
        for response in responses:
            global_index, name = lookup[response["id"]]
            if "error" in response:
                errors[global_index][name] = response["error"]
            else:
                values[global_index][name] = decode_word(response.get("result", "0x"), name)
        time.sleep(args.batch_pause)

    output = []
    for row, value, error in zip(rows, values, errors):
        required = row.get("required_currency_raised_raw")
        raised = value.get("currency_raised_raw")
        output.append(
            {
                "snapshot_at": snapshot_at,
                "chain": row["chain"],
                "chain_id": row["chain_id"],
                "factory_version": row["factory_version"],
                "auction": row["auction"],
                "token": row["token"],
                "currency": row.get("currency"),
                "created_block": row["block_number"],
                "start_block": row.get("start_block"),
                "end_block": row.get("end_block"),
                "required_currency_raised_raw": required,
                **value,
                "raised_over_required": (
                    float(raised) / float(required)
                    if raised is not None and required not in (None, 0)
                    else None
                ),
                "clearing_price_raw_ratio": (
                    float(value["clearing_price_q96"]) / float(2**96)
                    if value.get("clearing_price_q96") is not None
                    else None
                ),
                "rpc_errors": error,
            }
        )

    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    columns = list(dict.fromkeys(key for row in output for key in row))
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(
            [dict(row, rpc_errors=json.dumps(row["rpc_errors"], ensure_ascii=False)) for row in output]
        )
    audit = {
        "snapshot_at": snapshot_at,
        "rpc": args.rpc,
        "observed_chain_id": observed_chain_id,
        "latest_block": latest_block,
        "selectors": selectors,
        "rows": len(output),
        "rows_with_any_rpc_error": sum(bool(row["rpc_errors"]) for row in output),
        "graduated_true": sum(row.get("graduated") is True for row in output),
        "graduated_false": sum(row.get("graduated") is False for row in output),
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
