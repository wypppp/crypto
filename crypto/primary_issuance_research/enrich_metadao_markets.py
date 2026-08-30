#!/usr/bin/env python3
"""Attach a reproducible current market/liquidity snapshot to MetaDAO launches.

DexScreener is used only as a market-data source, never to define the launch
denominator.  The on-chain Launch-account snapshot remains the left table.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from collect_metadao_launches import http_json


USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def token_mint(row: dict[str, Any]) -> str:
    decoded = row["decoded"]
    return str(row.get("base_mint") or decoded.get("baseMint") or decoded.get("tokenMint") or "")


def accepted_raw(row: dict[str, Any]) -> int:
    decoded = row["decoded"]
    for field in ("finalRaiseAmount", "totalApprovedAmount", "totalCommittedAmount"):
        value = decoded.get(field)
        if value is not None:
            return int(value)
    return 0


def choose_pair(pairs: list[dict[str, Any]], mint: str) -> dict[str, Any] | None:
    eligible = [
        pair
        for pair in pairs
        if pair.get("chainId") == "solana"
        and pair.get("baseToken", {}).get("address") == mint
        and pair.get("quoteToken", {}).get("address") == USDC
    ]
    if not eligible:
        eligible = [
            pair
            for pair in pairs
            if pair.get("chainId") == "solana"
            and pair.get("baseToken", {}).get("address") == mint
        ]
    if not eligible:
        return None
    return max(eligible, key=lambda pair: float(pair.get("liquidity", {}).get("usd") or 0))


def main() -> None:
    parser = argparse.ArgumentParser()
    base_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--launches",
        type=Path,
        default=base_dir / "data/metadao_current_launch_accounts.json",
    )
    parser.add_argument("--out-dir", type=Path, default=base_dir / "data")
    parser.add_argument(
        "--proxy-mode",
        choices=("auto", "env-proxy", "direct"),
        default="auto",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--min-accepted-usd", type=float, default=10_000)
    parser.add_argument("--transport", choices=("urllib", "curl"), default="curl")
    args = parser.parse_args()

    launches = json.loads(args.launches.read_text())
    completed = [
        row
        for row in launches
        if row["state"] == "Complete"
        and token_mint(row)
        and accepted_raw(row) / 1_000_000 >= args.min_accepted_usd
    ]
    mints = [token_mint(row) for row in completed]
    pairs_by_mint: dict[str, list[dict[str, Any]]] = {}
    query_failures: dict[str, str] = {}
    raw_pairs: list[dict[str, Any]] = []
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")

    def query_mint(mint: str) -> list[dict[str, Any]]:
        url = "https://api.dexscreener.com/tokens/v1/solana/" + quote(mint)
        if args.transport == "curl":
            completed_process = subprocess.run(
                ["curl", "--max-time", str(args.timeout), "-sS", url],
                capture_output=True,
                text=True,
                timeout=args.timeout + 5,
            )
            if completed_process.returncode != 0:
                raise RuntimeError(completed_process.stderr.strip() or "curl failed")
            response = json.loads(completed_process.stdout)
        else:
            response = http_json(url, proxy_mode=args.proxy_mode, timeout=args.timeout)
        if not isinstance(response, list):
            raise RuntimeError(f"unexpected DexScreener response: {type(response)}")
        return response

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending = {executor.submit(query_mint, mint): mint for mint in mints}
        for index, future in enumerate(concurrent.futures.as_completed(pending), start=1):
            mint = pending[future]
            try:
                response = future.result()
                pairs_by_mint[mint] = response
                raw_pairs.extend(response)
            except Exception as exc:
                query_failures[mint] = str(exc)
            if index % 10 == 0 or index == len(mints):
                print(json.dumps({"market_query_progress": f"{index}/{len(mints)}"}), flush=True)

    snapshot_at = datetime.now(timezone.utc).isoformat()
    output = []
    for launch in completed:
        mint = token_mint(launch)
        pair = choose_pair(pairs_by_mint.get(mint, []), mint)
        accepted_usd = accepted_raw(launch) / 1_000_000
        result = {
            "snapshot_at": snapshot_at,
            "version": launch["version"],
            "launch_account": launch["launch_account"],
            "token_mint": mint,
            "started_at": launch.get("started_at"),
            "closed_at": launch.get("closed_at"),
            "accepted_usd": accepted_usd,
            "market_query_ok": mint not in query_failures,
            "market_query_error": query_failures.get(mint, ""),
            "has_market_pair": pair is not None,
            "dex_id": "",
            "pair_address": "",
            "token_name": "",
            "token_symbol": "",
            "price_usd": None,
            "liquidity_usd": None,
            "quote_reserve_usd": None,
            "capacity_5pct_quote_approx_usd": None,
            "volume_h24_usd": None,
            "pair_created_at_ms": None,
            "screen_issue_price_if_10m_public_tokens": accepted_usd / 10_000_000,
            "screen_spot_multiple_if_10m_public_tokens": None,
            "screening_warning": (
                "The 10m-token multiple is a triage assumption, not an audited issue price. "
                "It must not enter final ROI statistics until project terms confirm public tokens."
            ),
        }
        if pair:
            price_usd = float(pair["priceUsd"]) if pair.get("priceUsd") else None
            liquidity = pair.get("liquidity", {})
            quote_reserve = liquidity.get("quote")
            result.update(
                {
                    "dex_id": pair.get("dexId", ""),
                    "pair_address": pair.get("pairAddress", ""),
                    "token_name": pair.get("baseToken", {}).get("name", ""),
                    "token_symbol": pair.get("baseToken", {}).get("symbol", ""),
                    "price_usd": price_usd,
                    "liquidity_usd": liquidity.get("usd"),
                    "quote_reserve_usd": quote_reserve,
                    "capacity_5pct_quote_approx_usd": (
                        0.05 * float(quote_reserve) if quote_reserve is not None else None
                    ),
                    "volume_h24_usd": pair.get("volume", {}).get("h24"),
                    "pair_created_at_ms": pair.get("pairCreatedAt"),
                    "screen_spot_multiple_if_10m_public_tokens": (
                        price_usd / result["screen_issue_price_if_10m_public_tokens"]
                        if price_usd is not None and accepted_usd > 0
                        else None
                    ),
                }
            )
        output.append(result)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "metadao_market_snapshot.json"
    csv_path = args.out_dir / "metadao_market_snapshot.csv"
    raw_path = args.out_dir / "metadao_dexscreener_raw_pairs.json"
    audit_path = args.out_dir / "metadao_market_snapshot_audit.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    raw_path.write_text(json.dumps(raw_pairs, indent=2, ensure_ascii=False) + "\n")
    audit_path.write_text(
        json.dumps(
            {
                "snapshot_at": snapshot_at,
                "complete_launches": len(completed),
                "min_accepted_usd": args.min_accepted_usd,
                "successful_market_queries": len(completed) - len(query_failures),
                "failed_market_queries": query_failures,
                "complete": not query_failures,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)

    print(
        json.dumps(
            {
                "complete_launches": len(completed),
                "launches_with_pair": sum(row["has_market_pair"] for row in output),
                "raw_pairs": len(raw_pairs),
                "failed_market_queries": len(query_failures),
                "complete": not query_failures,
                "snapshot": str(csv_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
