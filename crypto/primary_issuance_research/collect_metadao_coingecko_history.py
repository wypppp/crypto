#!/usr/bin/env python3
"""Collect contract-matched CoinGecko market history for material MetaDAO launches."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API = "https://api.coingecko.com/api/v3"
SECONDS_180D = 180 * 86400


def curl_json(url: str, timeout: int) -> Any:
    completed = subprocess.run(
        ["curl", "-L", "--max-time", str(timeout), "-sS", url],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "curl failed")
    payload = json.loads(completed.stdout)
    if isinstance(payload, dict) and ("error" in payload or "status" in payload):
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return payload


def accepted_raw(launch: dict[str, Any]) -> int:
    decoded = launch["decoded"]
    for field in ("finalRaiseAmount", "totalApprovedAmount", "totalCommittedAmount"):
        value = decoded.get(field)
        if value is not None:
            return int(value)
    return 0


def launch_end(launch: dict[str, Any]) -> int:
    decoded = launch["decoded"]
    return int(
        launch.get("closed_at")
        or decoded.get("unixTimestampCompleted")
        or decoded.get("unixTimestampClosed")
        or int(launch["started_at"]) + int(decoded.get("secondsForLaunch") or 0)
    )


def main() -> None:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--launches", type=Path, default=base / "data/metadao_current_launch_accounts.json"
    )
    parser.add_argument(
        "--markets", type=Path, default=base / "data/metadao_market_snapshot.json"
    )
    parser.add_argument(
        "--coin-list", type=Path, default=base / "data/coingecko_coin_contracts.json"
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=base / "data/metadao_coingecko_history"
    )
    parser.add_argument(
        "--audit", type=Path, default=base / "data/metadao_coingecko_history_audit.json"
    )
    parser.add_argument("--minimum-raise-usd", type=float, default=10_000)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep-seconds", type=float, default=3.0)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    if args.refresh or not args.coin_list.exists():
        coin_list_url = f"{API}/coins/list?include_platform=true"
        coin_list = curl_json(coin_list_url, args.timeout)
        args.coin_list.parent.mkdir(parents=True, exist_ok=True)
        args.coin_list.write_text(json.dumps(coin_list, ensure_ascii=False) + "\n")
    else:
        coin_list_url = f"{API}/coins/list?include_platform=true"
        coin_list = json.loads(args.coin_list.read_text())

    by_contract = {
        str(contract).lower(): coin
        for coin in coin_list
        for contract in coin.get("platforms", {}).values()
        if contract
    }
    launches = [
        row
        for row in json.loads(args.launches.read_text())
        if row["state"] == "Complete"
        and accepted_raw(row) / 1_000_000 >= args.minimum_raise_usd
    ]
    markets = {row["launch_account"]: row for row in json.loads(args.markets.read_text())}
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    now = int(datetime.now(timezone.utc).timestamp())
    matched: dict[str, str] = {}
    unmatched: list[str] = []
    errors: dict[str, str] = {}
    collected = 0
    for index, launch in enumerate(launches, start=1):
        mint = launch["base_mint"]
        coin = by_contract.get(mint.lower())
        if not coin:
            unmatched.append(mint)
            continue
        coin_id = coin["id"]
        matched[mint] = coin_id
        output_path = args.cache_dir / f"{mint}.json"
        if output_path.exists() and not args.refresh:
            collected += 1
            continue
        start = launch_end(launch)
        end = min(now, start + SECONDS_180D)
        url = (
            f"{API}/coins/{coin_id}/market_chart/range?vs_currency=usd"
            f"&from={start}&to={end}"
        )
        try:
            payload = curl_json(url, args.timeout)
            market = markets.get(launch["launch_account"], {})
            output = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "CoinGecko market_chart/range",
                "source_url": url,
                "coin_id": coin_id,
                "launch_account": launch["launch_account"],
                "token_mint": mint,
                "token_symbol": market.get("token_symbol") or coin.get("symbol", "").upper(),
                "accepted_usd": accepted_raw(launch) / 1_000_000,
                "public_tokens": 10_000_000,
                "issue_price_usd": accepted_raw(launch) / 1_000_000 / 10_000_000,
                "launch_end_timestamp": start,
                "target_end_timestamp": end,
                "prices": payload.get("prices", []),
                "market_caps": payload.get("market_caps", []),
                "total_volumes": payload.get("total_volumes", []),
            }
            output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
            collected += 1
        except Exception as exc:
            errors[mint] = str(exc)
        print(
            json.dumps(
                {
                    "processed": index,
                    "material": len(launches),
                    "matched": len(matched),
                    "collected": collected,
                    "unmatched": len(unmatched),
                    "errors": len(errors),
                }
            ),
            flush=True,
        )
        if index < len(launches):
            time.sleep(args.sleep_seconds)

    audit = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "coin_list_url": coin_list_url,
        "coin_list_sha256": hashlib.sha256(args.coin_list.read_bytes()).hexdigest(),
        "material_launches": len(launches),
        "contract_matched": len(matched),
        "matched_coin_ids": matched,
        "unmatched_mints": unmatched,
        "cached_or_collected": collected,
        "errors": errors,
        "complete_for_contract_matched": collected == len(matched) and not errors,
    }
    args.audit.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
