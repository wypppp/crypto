#!/usr/bin/env python3
"""Append one pre-outcome CCA score with an on-chain deadline check."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_cca_auctions import EvmRpc


DIMENSIONS = (
    "team_identity_verifiability",
    "product_code_usage_evidence",
    "valuation_vs_verifiable_assets_or_revenue",
    "token_rights_team_lockup_and_dilution",
    "fundraise_and_initial_liquidity_structure",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("auction", help="Auction contract address")
    parser.add_argument(
        "--score-json",
        type=Path,
        required=True,
        help="JSON with five integer scores, evidence URLs/snapshots, and notes",
    )
    parser.add_argument(
        "--state-dir", type=Path, default=base_dir / "forward/cca_robinhood"
    )
    parser.add_argument("--rpc", default="https://rpc.mainnet.chain.robinhood.com")
    parser.add_argument("--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    auction = args.auction.lower()
    created = {
        row["auction"].lower(): row
        for row in read_jsonl(args.state_dir / "auction_created.jsonl")
    }
    if auction not in created:
        raise RuntimeError("auction is not in the post-freeze append-only discovery log")
    existing = {
        row["auction"].lower()
        for row in read_jsonl(args.state_dir / "scores.jsonl")
        if row.get("score_status") == "frozen_pre_outcome"
    }
    if auction in existing:
        raise RuntimeError("a frozen score already exists; overwrite is forbidden")

    score = json.loads(args.score_json.read_text(encoding="utf-8"))
    missing = [name for name in DIMENSIONS if name not in score]
    if missing:
        raise ValueError(f"missing score dimensions: {missing}")
    for name in DIMENSIONS:
        value = score[name]
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1, 2):
            raise ValueError(f"{name} must be an integer 0, 1, or 2")
    evidence = score.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a list of URLs, archive references, or hashes")

    rpc = EvmRpc(args.rpc, args.proxy_mode, args.timeout)
    latest = int(rpc.call("eth_blockNumber", []), 16)
    end_block = created[auction].get("end_block")
    if end_block is None:
        raise RuntimeError("auction has no decoded end block")
    if latest >= int(end_block):
        raise RuntimeError(
            f"pre-outcome deadline missed: latest block {latest} >= end block {end_block}"
        )
    block = rpc.call("eth_getBlockByNumber", [hex(latest), False])
    row = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "recorded_block": latest,
        "recorded_block_timestamp": int(block["timestamp"], 16),
        "auction": auction,
        "token": created[auction]["token"],
        "end_block": int(end_block),
        "score_status": "frozen_pre_outcome",
        "scores": {name: score[name] for name in DIMENSIONS},
        "total_score": sum(score[name] for name in DIMENSIONS),
        "evidence": evidence,
        "evidence_capture_sha256": score.get("evidence_capture_sha256"),
        "notes": score.get("notes", ""),
    }
    append_jsonl(args.state_dir / "scores.jsonl", row)
    print(json.dumps(row, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
