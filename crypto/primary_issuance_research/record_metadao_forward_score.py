#!/usr/bin/env python3
"""Append one MetaDAO score after proving the on-chain deadline is still open."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_metadao_launches import http_json


DIMENSIONS = (
    "product_usage_revenue",
    "team_delivery",
    "valuation",
    "token_rights",
    "float_lockup_dilution",
    "ordinary_allocation_capacity",
    "liquidity_and_backstop",
    "code_security_governance",
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


def rpc_call(
    rpc_url: str,
    method: str,
    params: list[Any],
    proxy_mode: str,
    timeout: int,
) -> Any:
    response = http_json(
        rpc_url,
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        proxy_mode=proxy_mode,
        timeout=timeout,
    )
    if "error" in response:
        raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
    return response["result"]


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("launch_account")
    parser.add_argument("--score-json", type=Path, required=True)
    parser.add_argument(
        "--state-dir", type=Path, default=base_dir / "forward/metadao"
    )
    parser.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    parser.add_argument("--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    launch = args.launch_account
    queue = {
        row["launch_account"]: row
        for row in read_jsonl(args.state_dir / "scoring_queue.jsonl")
    }
    if launch not in queue:
        raise RuntimeError("launch is not in the post-freeze material scoring queue")
    scores_path = args.state_dir / "scores.jsonl"
    if any(row["launch_account"] == launch for row in read_jsonl(scores_path)):
        raise RuntimeError("a frozen score already exists; overwrite is forbidden")
    if any(
        row["launch_account"] == launch
        for row in read_jsonl(args.state_dir / "score_deadline_missed.jsonl")
    ):
        raise RuntimeError("the observer already froze this launch as deadline-missed")
    observer_state = json.loads((args.state_dir / "state.json").read_text(encoding="utf-8"))
    current = observer_state.get("accounts", {}).get(launch)
    if not current or not current.get("forward") or not current.get("queued"):
        raise RuntimeError("launch is not a current forward material account")

    payload = json.loads(args.score_json.read_text(encoding="utf-8"))
    missing = [name for name in DIMENSIONS if name not in payload]
    if missing:
        raise ValueError(f"missing score dimensions: {missing}")
    for name in DIMENSIONS:
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1, 2):
            raise ValueError(f"{name} must be an integer 0, 1, or 2")
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a list")

    slot = int(
        rpc_call(args.rpc, "getSlot", [{"commitment": "finalized"}], args.proxy_mode, args.timeout)
    )
    block_time = int(
        rpc_call(args.rpc, "getBlockTime", [slot], args.proxy_mode, args.timeout)
    )
    closed_at = int(current.get("closed_at") or queue[launch].get("closed_at") or 0)
    if not closed_at:
        raise RuntimeError("launch close time is not fixed on chain yet; observe again before scoring")
    if block_time >= closed_at:
        raise RuntimeError(
            f"pre-outcome deadline missed: finalized time {block_time} >= close {closed_at}"
        )

    row = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "recorded_slot": slot,
        "recorded_block_time": block_time,
        "launch_account": launch,
        "base_mint": current.get("base_mint") or queue[launch]["base_mint"],
        "closed_at": closed_at,
        "score_status": "frozen_pre_outcome",
        "scores": {name: payload[name] for name in DIMENSIONS},
        "total_score": sum(payload[name] for name in DIMENSIONS),
        "strategy_eligible": sum(payload[name] for name in DIMENSIONS) >= 10,
        "evidence": evidence,
        "evidence_capture_sha256": payload.get("evidence_capture_sha256"),
        "notes": payload.get("notes", ""),
    }
    append_jsonl(scores_path, row)
    print(json.dumps(row, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
