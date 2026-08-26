#!/usr/bin/env python3
"""Audit Pump.fun -> PumpSwap migrations through a Solana RPC endpoint.

The script first walks signatures touching the live Pump Global.withdraw_authority,
then fetches transactions and requires both Pump `migrate` and the matching canonical
PumpSwap `create_pool`. It records raw JSONL alongside a compact CSV.

This is an audit/fallback tool, not the recommended 85-day bulk collector: public RPC
history is rate-limited and the withdraw authority attracts many failed transactions.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RPC_DEFAULT = "https://api.mainnet-beta.solana.com"
WITHDRAW_AUTHORITY = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_AMM_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL_MINT = "So11111111111111111111111111111111111111112"
MIGRATE_DISCRIMINATOR = bytes([155, 234, 231, 146, 236, 158, 162, 30])
CREATE_POOL_DISCRIMINATOR = bytes([233, 146, 209, 142, 207, 104, 64, 188])
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode(value: str) -> bytes:
    number = 0
    for char in value:
        number = number * 58 + ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(value) - len(value.lstrip("1"))) + raw


def iso_to_ts(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def ts_to_iso(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class Rpc:
    def __init__(self, url: str, min_interval: float = 0.15) -> None:
        self.url = url
        self.min_interval = min_interval
        self.last_call = 0.0
        self.request_id = 0

    def call(self, method: str, params: list[Any], retries: int = 10) -> Any:
        self.request_id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
        ).encode()
        for attempt in range(retries):
            delay = self.min_interval - (time.monotonic() - self.last_call)
            if delay > 0:
                time.sleep(delay)
            request = urllib.request.Request(
                self.url, data=body, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.load(response)
                self.last_call = time.monotonic()
                if "error" in payload:
                    raise RuntimeError(f"RPC {method}: {payload['error']}")
                return payload["result"]
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                if attempt + 1 == retries:
                    raise
                wait = min(60.0, 1.4**attempt + random.random())
                print(f"retry {method} after {exc!r}; sleeping {wait:.1f}s", flush=True)
                time.sleep(wait)
        raise AssertionError("unreachable")

    def batch(self, calls: list[tuple[str, list[Any]]], retries: int = 10) -> list[Any]:
        """Execute JSON-RPC calls in one HTTP request and preserve input order."""
        if not calls:
            return []
        requests = []
        ids = []
        for method, params in calls:
            self.request_id += 1
            ids.append(self.request_id)
            requests.append(
                {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
            )
        body = json.dumps(requests).encode()
        for attempt in range(retries):
            delay = self.min_interval - (time.monotonic() - self.last_call)
            if delay > 0:
                time.sleep(delay)
            request = urllib.request.Request(
                self.url, data=body, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.load(response)
                self.last_call = time.monotonic()
                by_id = {item["id"]: item for item in payload}
                results = []
                for request_id in ids:
                    item = by_id[request_id]
                    if "error" in item:
                        raise RuntimeError(f"RPC batch item: {item['error']}")
                    results.append(item["result"])
                return results
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                if attempt + 1 == retries:
                    raise
                wait = min(60.0, 1.4**attempt + random.random())
                print(f"retry batch after {exc!r}; sleeping {wait:.1f}s", flush=True)
                time.sleep(wait)
        raise AssertionError("unreachable")


def collect_signatures(rpc: Rpc, start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    before = None
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    page_number = 0
    while True:
        options: dict[str, Any] = {"limit": 1000, "commitment": "finalized"}
        if before:
            options["before"] = before
        page = rpc.call("getSignaturesForAddress", [WITHDRAW_AUTHORITY, options])
        page_number += 1
        if not page:
            break
        oldest = page[-1].get("blockTime")
        newest = page[0].get("blockTime")
        print(
            f"signature page {page_number}: {len(page)} rows, "
            f"{ts_to_iso(oldest) if oldest else '?'} .. {ts_to_iso(newest) if newest else '?'}",
            flush=True,
        )
        for row in page:
            block_time = row.get("blockTime")
            signature = row["signature"]
            if (
                block_time is not None
                and start_ts <= block_time < end_ts
                and signature not in seen
            ):
                kept.append(row)
                seen.add(signature)
        if oldest is not None and oldest < start_ts:
            break
        before = page[-1]["signature"]
    return sorted(kept, key=lambda row: (row["blockTime"], row["signature"]))


def account_keys(message: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    keys = [item["pubkey"] if isinstance(item, dict) else item for item in message["accountKeys"]]
    loaded = meta.get("loadedAddresses") or {}
    return keys + loaded.get("writable", []) + loaded.get("readonly", [])


def migrate_rows(signature: str, tx: dict[str, Any]) -> list[dict[str, Any]]:
    if not tx or tx.get("meta", {}).get("err") is not None:
        return []
    transaction = tx["transaction"]
    message = transaction["message"]
    meta = tx["meta"]
    keys = account_keys(message, meta)
    instructions: list[dict[str, Any]] = list(message.get("instructions", []))
    for group in meta.get("innerInstructions") or []:
        instructions.extend(group.get("instructions", []))
    rows = []
    for instruction in instructions:
        program = instruction.get("programId")
        if program is None and "programIdIndex" in instruction:
            program = keys[instruction["programIdIndex"]]
        data = instruction.get("data")
        if program != PUMP_PROGRAM or not data:
            continue
        try:
            decoded = b58decode(data)
        except ValueError:
            continue
        if not decoded.startswith(MIGRATE_DISCRIMINATOR):
            continue
        indexes = instruction.get("accounts", [])
        accounts = [keys[index] if isinstance(index, int) else index for index in indexes]
        if len(accounts) < 21:
            raise RuntimeError(f"migrate account list too short in {signature}: {len(accounts)}")
        # IDL order: mint=2, pool=9, pool authority=10, pool vaults=17/18.
        rows.append(
            {
                "signature": signature,
                "slot": tx["slot"],
                "graduated_at": ts_to_iso(tx["blockTime"]),
                "mint": accounts[2],
                "pool": accounts[9],
                "pool_authority": accounts[10],
                "pool_base_token_account": accounts[17],
                "pool_quote_token_account": accounts[18],
                "pump_amm_program": accounts[8],
                "quote_mint": accounts[14],
            }
        )
    return rows


def create_pool_rows(tx: dict[str, Any]) -> list[dict[str, Any]]:
    """Decode PumpSwap create_pool calls, including exact initial reserve inputs."""
    if not tx or tx.get("meta", {}).get("err") is not None:
        return []
    message = tx["transaction"]["message"]
    meta = tx["meta"]
    keys = account_keys(message, meta)
    instructions: list[dict[str, Any]] = list(message.get("instructions", []))
    for group in meta.get("innerInstructions") or []:
        instructions.extend(group.get("instructions", []))
    rows = []
    for instruction in instructions:
        program = instruction.get("programId")
        if program is None and "programIdIndex" in instruction:
            program = keys[instruction["programIdIndex"]]
        data = instruction.get("data")
        if program != PUMP_AMM_PROGRAM or not data:
            continue
        try:
            decoded = b58decode(data)
        except ValueError:
            continue
        if not decoded.startswith(CREATE_POOL_DISCRIMINATOR) or len(decoded) < 26:
            continue
        indexes = instruction.get("accounts", [])
        accounts = [keys[index] if isinstance(index, int) else index for index in indexes]
        rows.append(
            {
                "pool": accounts[0],
                "creator": accounts[2],
                "base_mint": accounts[3],
                "quote_mint": accounts[4],
                "pool_base_token_account": accounts[9],
                "pool_quote_token_account": accounts[10],
                "index": int.from_bytes(decoded[8:10], "little"),
                "base_amount_in_raw": int.from_bytes(decoded[10:18], "little"),
                "quote_amount_in_raw": int.from_bytes(decoded[18:26], "little"),
                "is_mayhem_mode": bool(decoded[58]) if len(decoded) > 58 else None,
            }
        )
    return rows


def decode_transactions(
    rpc: Rpc, signatures: list[dict[str, Any]], raw_path: Path
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for index, item in enumerate(signatures, start=1):
            signature = item["signature"]
            tx = rpc.call(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "commitment": "finalized",
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            )
            raw_file.write(json.dumps({"signature": signature, "tx": tx}) + "\n")
            migrations = migrate_rows(signature, tx)
            creations = create_pool_rows(tx)
            for migration in migrations:
                matches = [
                    creation
                    for creation in creations
                    if creation["index"] == 0
                    and creation["pool"] == migration["pool"]
                    and creation["base_mint"] == migration["mint"]
                    and creation["quote_mint"] == migration["quote_mint"]
                    and creation["pool_base_token_account"]
                    == migration["pool_base_token_account"]
                    and creation["pool_quote_token_account"]
                    == migration["pool_quote_token_account"]
                ]
                if len(matches) > 1:
                    raise RuntimeError(
                        f"multiple matching create_pool calls in {signature}: {len(matches)}"
                    )
                if matches:
                    creation = matches[0]
                    rows.append(
                        migration
                        | {
                            "base_amount_in_raw": creation["base_amount_in_raw"],
                            "quote_amount_in_raw": creation["quote_amount_in_raw"],
                            "is_mayhem_mode": creation["is_mayhem_mode"],
                        }
                    )
            if index % 100 == 0 or index == len(signatures):
                print(
                    f"decoded {index}/{len(signatures)} signatures; "
                    f"matched pool creations={len(rows)}",
                    flush=True,
                )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError("No decoded migrations")
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default=RPC_DEFAULT)
    parser.add_argument("--start", default="2026-05-01T00:00:00Z")
    parser.add_argument("--end", default="2026-07-25T00:00:00Z")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument("--signatures-only", action="store_true")
    args = parser.parse_args()
    rpc = Rpc(args.rpc)
    signatures = collect_signatures(rpc, iso_to_ts(args.start), iso_to_ts(args.end))
    args.out.mkdir(parents=True, exist_ok=True)
    signatures_path = args.out / "migration_candidate_signatures.json"
    signatures_path.write_text(json.dumps(signatures, indent=2), encoding="utf-8")
    print(f"kept {len(signatures)} candidate signatures -> {signatures_path}", flush=True)
    if args.signatures_only:
        return
    rows = decode_transactions(rpc, signatures, args.out / "migration_transactions.jsonl")
    invalid_program = [row for row in rows if row["pump_amm_program"] != PUMP_AMM_PROGRAM]
    if invalid_program:
        raise RuntimeError(
            f"IDL-account validation failed: amm={len(invalid_program)}"
        )
    deduped = list({(row["signature"], row["mint"]): row for row in rows}.values())
    write_csv(args.out / "migrations.csv", deduped)
    print(f"decoded {len(deduped)} unique actual pool creations", flush=True)


if __name__ == "__main__":
    main()
