#!/usr/bin/env python3
"""Link MetaDAO launch allocations to participant token-sale balance changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
PDA_MARKER = b"ProgramDerivedAddress"
P = 2**255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P
I = pow(2, (P - 1) // 4, P)
SECONDS_180D = 180 * 86400


def b58decode(value: str) -> bytes:
    number = 0
    for char in value:
        number = number * 58 + ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(value) - len(value.lstrip("1"))) + raw


def b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + (encoded or "")


def is_on_curve(raw: bytes) -> bool:
    if len(raw) != 32:
        return False
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= P:
        return False
    y2 = y * y % P
    x2 = (y2 - 1) * pow((D * y2 + 1) % P, P - 2, P) % P
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * I % P
    return (x * x - x2) % P == 0


def find_program_address(seeds: list[bytes], program: str) -> str:
    program_raw = b58decode(program)
    for bump in range(255, -1, -1):
        digest = hashlib.sha256(b"".join(seeds + [bytes([bump]), program_raw, PDA_MARKER])).digest()
        if not is_on_curve(digest):
            return b58encode(digest)
    raise RuntimeError("unable to derive PDA")


def associated_token_address(owner: str, mint: str) -> str:
    return find_program_address(
        [b58decode(owner), b58decode(TOKEN_PROGRAM), b58decode(mint)],
        ASSOCIATED_TOKEN_PROGRAM,
    )


class Rpc:
    def __init__(self, url: str, timeout: int, pause: float):
        self.url = url
        self.timeout = timeout
        self.pause = pause
        self.calls = 0

    def call_many(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        completed = subprocess.run(
            [
                "curl",
                "--max-time",
                str(self.timeout),
                "-sS",
                self.url,
                "-H",
                "content-type: application/json",
                "-d",
                json.dumps(requests, separators=(",", ":")),
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout + 5,
        )
        self.calls += 1
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "curl failed")
        payload = json.loads(completed.stdout)
        if isinstance(payload, dict):
            payload = [payload]
        by_id = {str(row.get("id")): row for row in payload}
        ordered = [by_id.get(str(request["id"]), {"error": "missing batch response"}) for request in requests]
        if self.pause:
            time.sleep(self.pause)
        return ordered

    def call(self, method: str, params: list[Any], request_id: str) -> Any:
        response = self.call_many(
            [{"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}]
        )[0]
        if "error" in response:
            raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
        return response["result"]


def token_amounts(meta: dict[str, Any], field: str, owner: str, mint: str) -> int:
    total = 0
    for row in meta.get(field) or []:
        if row.get("owner") == owner and row.get("mint") == mint:
            total += int(row["uiTokenAmount"]["amount"])
    return total


def transaction_delta(tx: dict[str, Any], owner: str, mint: str) -> dict[str, Any] | None:
    meta = tx.get("meta")
    if not meta or meta.get("err") is not None:
        return None
    token_before = token_amounts(meta, "preTokenBalances", owner, mint)
    token_after = token_amounts(meta, "postTokenBalances", owner, mint)
    usdc_before = token_amounts(meta, "preTokenBalances", owner, USDC_MINT)
    usdc_after = token_amounts(meta, "postTokenBalances", owner, USDC_MINT)
    token_delta = token_after - token_before
    usdc_delta = usdc_after - usdc_before
    if token_delta == 0 and usdc_delta == 0:
        return None
    return {
        "block_time": tx.get("blockTime"),
        "slot": tx.get("slot"),
        "token_delta_raw": token_delta,
        "usdc_delta_raw": usdc_delta,
    }


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
        "--funding-records", type=Path, default=base / "data/metadao_material_funding_records.json"
    )
    parser.add_argument(
        "--launches", type=Path, default=base / "data/metadao_current_launch_accounts.json"
    )
    parser.add_argument(
        "--output", type=Path, default=base / "data/metadao_participant_exit_audit.json"
    )
    parser.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    parser.add_argument("--transaction-batch-size", type=int, default=5)
    parser.add_argument("--candidates-per-token", type=int, default=12)
    parser.add_argument("--minimum-cost", type=float, default=100)
    parser.add_argument("--maximum-cost", type=float, default=250)
    args = parser.parse_args()

    target_mints = {
        "AVICI": "BANKJmvhT8tiJRsBSS1n2HryMBPvT5Ze4HU95DUAmeta",
        "UMBRA": "PRVT6TB7uss3FrUd2D9xs2zqDBsa3GbMJMwCQsgmeta",
    }
    records = json.loads(args.funding_records.read_text())["records"]
    launches = {row["base_mint"]: row for row in json.loads(args.launches.read_text())}
    rpc = Rpc(args.rpc, args.timeout, args.pause_seconds)
    candidates = []
    for symbol, mint in target_mints.items():
        eligible = [
            row
            for row in records
            if row["token_mint"] == mint
            and args.minimum_cost <= row["actual_accepted_usd"] <= args.maximum_cost
            and row["is_tokens_claimed"] is True
        ]
        eligible.sort(key=lambda row: hashlib.sha256(row["funder"].encode()).digest())
        launch = launches[mint]
        total_committed = int(launch["decoded"]["totalCommittedAmount"])
        for row in eligible[: args.candidates_per_token]:
            allocation_raw = int(row["committed_raw"]) * (10_000_000 * 1_000_000) // total_committed
            candidates.append(
                {
                    **row,
                    "symbol": symbol,
                    "ata": associated_token_address(row["funder"], mint),
                    "allocation_token_raw": allocation_raw,
                    "launch_end": launch_end(launch),
                    "issue_price_usd": int(launch["decoded"]["finalRaiseAmount"]) / 1_000_000 / 10_000_000,
                }
            )

    owner_requests = [
        {
            "jsonrpc": "2.0",
            "id": f"owner-{index}",
            "method": "getAccountInfo",
            "params": [row["funder"], {"encoding": "base64", "commitment": "finalized"}],
        }
        for index, row in enumerate(candidates)
    ]
    owner_responses = rpc.call_many(owner_requests)
    for row, response in zip(candidates, owner_responses):
        value = response.get("result", {}).get("value")
        row["funder_current_account_owner"] = value.get("owner") if value else None
        row["funder_eoa_like"] = value is None or value.get("owner") == SYSTEM_PROGRAM

    signature_failures = []
    for index, row in enumerate(candidates, start=1):
        try:
            signatures = rpc.call(
                "getSignaturesForAddress",
                [row["ata"], {"limit": 1000, "commitment": "finalized"}],
                f"sig-{index}",
            )
            row["ata_signatures_total"] = len(signatures)
            row["signatures"] = [
                entry["signature"]
                for entry in signatures
                if entry.get("err") is None
                and entry.get("blockTime") is not None
                and row["launch_end"] - 86400 <= entry["blockTime"] <= row["launch_end"] + SECONDS_180D
            ]
        except Exception as exc:
            row["ata_signatures_total"] = None
            row["signatures"] = []
            signature_failures.append({"funder": row["funder"], "error": str(exc)})
        print(
            json.dumps(
                {
                    "candidate": f"{index}/{len(candidates)}",
                    "symbol": row["symbol"],
                    "signatures": len(row["signatures"]),
                    "failures": len(signature_failures),
                }
            ),
            flush=True,
        )

    unique_signatures = sorted({signature for row in candidates for signature in row["signatures"]})
    transactions: dict[str, Any] = {}
    transaction_failures = []
    batch_size = args.transaction_batch_size
    for start in range(0, len(unique_signatures), batch_size):
        batch = unique_signatures[start : start + batch_size]
        requests = [
            {
                "jsonrpc": "2.0",
                "id": signature,
                "method": "getTransaction",
                "params": [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "commitment": "finalized",
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            }
            for signature in batch
        ]
        responses = rpc.call_many(requests)
        for signature, response in zip(batch, responses):
            if "error" in response or response.get("result") is None:
                transaction_failures.append(
                    {"signature": signature, "error": response.get("error", "null result")}
                )
            else:
                transactions[signature] = response["result"]
        print(
            json.dumps(
                {
                    "transaction_progress": f"{min(start + batch_size, len(unique_signatures))}/{len(unique_signatures)}",
                    "decoded": len(transactions),
                    "failures": len(transaction_failures),
                }
            ),
            flush=True,
        )

    results = []
    for row in candidates:
        deltas = []
        for signature in row["signatures"]:
            tx = transactions.get(signature)
            if not tx:
                continue
            delta = transaction_delta(tx, row["funder"], row["token_mint"])
            if delta:
                deltas.append({"signature": signature, **delta})
        sales = [delta for delta in deltas if delta["token_delta_raw"] < 0 and delta["usdc_delta_raw"] > 0]
        sold_raw = sum(-delta["token_delta_raw"] for delta in sales)
        usdc_received = sum(delta["usdc_delta_raw"] for delta in sales) / 1_000_000
        allocation_tokens = row["allocation_token_raw"] / 1_000_000
        average_sale_price = usdc_received / (sold_raw / 1_000_000) if sold_raw else None
        single_transaction_full_exits = [
            delta
            for delta in sales
            if -delta["token_delta_raw"] >= row["allocation_token_raw"] * 0.99
            and delta["usdc_delta_raw"] / 1_000_000 >= 500
        ]
        result = {key: value for key, value in row.items() if key != "signatures"}
        result.update(
            {
                "allocation_tokens": allocation_tokens,
                "decoded_balance_change_transactions": len(deltas),
                "sale_transactions": len(sales),
                "sold_tokens": sold_raw / 1_000_000,
                "sold_vs_allocation_ratio": sold_raw / row["allocation_token_raw"]
                if row["allocation_token_raw"]
                else None,
                "usdc_received_from_sales": usdc_received,
                "average_sale_price_usd": average_sale_price,
                "average_sale_multiple": average_sale_price / row["issue_price_usd"]
                if average_sale_price is not None
                else None,
                # Strict sufficient evidence.  Cumulative sales can contain
                # tokens bought after launch, so they are not used to prove
                # that the initial allocation itself exited for >=$500.
                "mechanical_full_exit_ge_500": bool(single_transaction_full_exits),
                "single_transaction_full_exits": single_transaction_full_exits,
                "sales": sorted(sales, key=lambda item: item["block_time"] or 0),
            }
        )
        results.append(result)

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "selection": {
            "targets": target_mints,
            "cost_range_usd": [args.minimum_cost, args.maximum_cost],
            "candidates_per_token": args.candidates_per_token,
            "candidate_order": "sha256(funder), deterministic non-outcome selection",
        },
        "rpc_calls": rpc.calls,
        "unique_signatures": len(unique_signatures),
        "transactions_decoded": len(transactions),
        "signature_failures": signature_failures,
        "transaction_failures": transaction_failures,
        "mechanical_successes": sum(row["mechanical_full_exit_ge_500"] for row in results),
        "results": results,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "candidates": len(results),
                "eoa_like": sum(row["funder_eoa_like"] for row in results),
                "mechanical_successes": output["mechanical_successes"],
                "rpc_calls": rpc.calls,
                "transaction_failures": len(transaction_failures),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
