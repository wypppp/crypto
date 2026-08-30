#!/usr/bin/env python3
"""Append-only discovery observer for post-freeze Robinhood CCA launches.

The first normal run fixes a chain height and deliberately does not backfill
older launches.  Later runs scan only confirmed blocks after that height and
append newly created auctions to immutable JSONL logs.  No transaction is
signed or submitted by this program.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_auctions import (
    EvmRpc,
    FACTORIES,
    address_from_topic,
    decode_event_data,
)


CHAIN_ID = 4663
EVENT_SIGNATURE = "AuctionCreated(address,address,uint256,bytes)"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_jsonl_keys(path: Path, fields: tuple[str, ...]) -> set[tuple[Any, ...]]:
    if not path.exists():
        return set()
    keys: set[tuple[Any, ...]] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                keys.add(tuple(row.get(field) for field in fields))
    return keys


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def block_timestamp(rpc: EvmRpc, number: int, cache: dict[int, int]) -> int:
    if number not in cache:
        block = rpc.call("eth_getBlockByNumber", [hex(number), False])
        if block is None:
            raise RuntimeError(f"missing block {number}")
        cache[number] = int(block["timestamp"], 16)
    return cache[number]


def scan_factory(
    rpc: EvmRpc,
    address: str,
    topic0: str,
    start: int,
    end: int,
    chunk_size: int,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + chunk_size - 1)
        result = rpc.call(
            "eth_getLogs",
            [
                {
                    "fromBlock": hex(cursor),
                    "toBlock": hex(chunk_end),
                    "address": address,
                    "topics": [topic0],
                }
            ],
        )
        logs.extend(result)
        cursor = chunk_end + 1
    return logs


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-dir", type=Path, default=base_dir / "forward/cca_robinhood"
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--confirmations", type=int, default=3)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    parser.add_argument(
        "--from-block",
        type=int,
        help="Explicit retrospective start for testing only; normal deployment omits this.",
    )
    args = parser.parse_args()

    if args.confirmations < 0 or args.chunk_size < 1:
        raise ValueError("confirmations must be nonnegative and chunk-size positive")

    args.state_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.state_dir / "state.json"
    manifest_path = args.state_dir / "manifest.json"
    created_path = args.state_dir / "auction_created.jsonl"
    queue_path = args.state_dir / "scoring_queue.jsonl"
    runs_path = args.state_dir / "runs.jsonl"
    protocol_path = base_dir / "CCA_SHORT_EXECUTION_FORWARD_2026-08-28.md"

    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    observed_chain_id = int(rpc.call("eth_chainId", []), 16)
    if observed_chain_id != CHAIN_ID:
        raise RuntimeError(f"chain-id mismatch: expected {CHAIN_ID}, got {observed_chain_id}")
    latest = int(rpc.call("eth_blockNumber", []), 16)
    safe_head = latest - args.confirmations
    if safe_head < 0:
        raise RuntimeError("safe head below zero")
    topic0 = rpc.call("web3_sha3", ["0x" + EVENT_SIGNATURE.encode().hex()])
    timestamp_cache: dict[int, int] = {}

    if not state_path.exists():
        retrospective = args.from_block is not None
        first_scanned = args.from_block if retrospective else safe_head + 1
        freeze_block = (args.from_block - 1) if retrospective else safe_head
        manifest = {
            "created_at": utc_now(),
            "purpose": "CCA <=10m forward paper observer; read-only, no bids",
            "chain": "robinhood",
            "chain_id": CHAIN_ID,
            "rpc_at_initialization": args.rpc,
            "confirmations": args.confirmations,
            "freeze_block": freeze_block,
            "freeze_block_timestamp": block_timestamp(rpc, freeze_block, timestamp_cache),
            "retrospective_test_mode": retrospective,
            "protocol_path": str(protocol_path.relative_to(base_dir.parent.parent)),
            "protocol_sha256": sha256_file(protocol_path),
            "event_signature": EVENT_SIGNATURE,
            "event_topic0": topic0,
            "factories": FACTORIES,
            "score_schema": {
                "range_each": [0, 2],
                "missing_information_score": 0,
                "dimensions": [
                    "team_identity_verifiability",
                    "product_code_usage_evidence",
                    "valuation_vs_verifiable_assets_or_revenue",
                    "token_rights_team_lockup_and_dilution",
                    "fundraise_and_initial_liquidity_structure",
                ],
                "must_be_recorded_before_outcome": True,
            },
        }
        if manifest_path.exists():
            raise RuntimeError("manifest exists without state; refusing ambiguous reinitialization")
        atomic_json(manifest_path, manifest)
        state = {
            "initialized_at": manifest["created_at"],
            "freeze_block": freeze_block,
            "last_scanned_block": first_scanned - 1,
            "runs": 0,
        }
        atomic_json(state_path, state)
        if not retrospective:
            append_jsonl(
                runs_path,
                [
                    {
                        "run_at": utc_now(),
                        "mode": "initialize_forward_boundary",
                        "safe_head": safe_head,
                        "new_auctions": 0,
                    }
                ],
            )
            print(
                json.dumps(
                    {
                        "initialized": True,
                        "freeze_block": freeze_block,
                        "safe_head": safe_head,
                        "new_auctions": 0,
                        "state_dir": str(args.state_dir),
                    },
                    indent=2,
                )
            )
            return
    else:
        if args.from_block is not None:
            raise RuntimeError("--from-block is allowed only when initializing a new state directory")
        state = json.loads(state_path.read_text(encoding="utf-8"))

    start = int(state["last_scanned_block"]) + 1
    run_at = utc_now()
    if start > safe_head:
        state["runs"] = int(state.get("runs", 0)) + 1
        state["last_run_at"] = run_at
        state["last_safe_head"] = safe_head
        atomic_json(state_path, state)
        append_jsonl(
            runs_path,
            [{"run_at": run_at, "from_block": start, "to_block": safe_head, "new_auctions": 0}],
        )
        print(json.dumps({"initialized": False, "scanned": 0, "new_auctions": 0}, indent=2))
        return

    raw: list[tuple[str, str, dict[str, Any]]] = []
    errors: dict[str, str] = {}
    for factory_name, factory_address in FACTORIES.items():
        try:
            for log in scan_factory(
                rpc, factory_address, topic0, start, safe_head, args.chunk_size
            ):
                raw.append((factory_name, factory_address, log))
        except Exception as exc:
            errors[factory_name] = str(exc)
    if errors:
        append_jsonl(
            runs_path,
            [
                {
                    "run_at": run_at,
                    "from_block": start,
                    "to_block": safe_head,
                    "errors": errors,
                    "state_advanced": False,
                }
            ],
        )
        raise RuntimeError(f"factory scans incomplete; state not advanced: {errors}")

    existing = load_jsonl_keys(created_path, ("transaction_hash", "log_index"))
    rows: list[dict[str, Any]] = []
    for factory_name, factory_address, log in raw:
        topics = log.get("topics", [])
        if len(topics) < 3 or topics[0].lower() != topic0.lower():
            continue
        key = (log["transactionHash"], int(log["logIndex"], 16))
        if key in existing:
            continue
        block_number = int(log["blockNumber"], 16)
        decoded = decode_event_data(log.get("data", "0x"), factory_name)
        rows.append(
            {
                "observed_at": run_at,
                "chain": "robinhood",
                "chain_id": CHAIN_ID,
                "factory_version": factory_name,
                "factory": factory_address.lower(),
                "auction": address_from_topic(topics[1]).lower(),
                "token": address_from_topic(topics[2]).lower(),
                "created_block": block_number,
                "created_timestamp": block_timestamp(rpc, block_number, timestamp_cache),
                "transaction_hash": log["transactionHash"].lower(),
                "transaction_index": int(log["transactionIndex"], 16),
                "log_index": int(log["logIndex"], 16),
                **decoded,
            }
        )
    rows.sort(key=lambda row: (row["created_block"], row["transaction_index"], row["log_index"]))
    append_jsonl(created_path, rows)
    append_jsonl(
        queue_path,
        [
            {
                "queued_at": run_at,
                "auction": row["auction"],
                "token": row["token"],
                "created_block": row["created_block"],
                "start_block": row.get("start_block"),
                "end_block": row.get("end_block"),
                "validation_hook": row.get("validation_hook", ZERO_ADDRESS),
                "eligibility": "pending_exact_timing_and_migration",
                "score_status": "pending_pre_outcome_evidence_capture",
            }
            for row in rows
            if row["factory_version"].startswith("v2_")
        ],
    )

    state["last_scanned_block"] = safe_head
    state["last_run_at"] = run_at
    state["last_safe_head"] = safe_head
    state["runs"] = int(state.get("runs", 0)) + 1
    state["auction_count"] = len(load_jsonl_keys(created_path, ("transaction_hash", "log_index")))
    atomic_json(state_path, state)
    append_jsonl(
        runs_path,
        [
            {
                "run_at": run_at,
                "from_block": start,
                "to_block": safe_head,
                "new_auctions": len(rows),
                "state_advanced": True,
            }
        ],
    )
    print(
        json.dumps(
            {
                "initialized": False,
                "from_block": start,
                "to_block": safe_head,
                "new_auctions": len(rows),
                "total_auctions": state["auction_count"],
                "state_dir": str(args.state_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
