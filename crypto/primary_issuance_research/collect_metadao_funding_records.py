#!/usr/bin/env python3
"""Enumerate actual MetaDAO FundingRecord allocations for material launches."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_metadao_launches import (
    BorshReader,
    DEPLOYMENTS,
    IdlDecoder,
    REPO,
    b58encode,
    http_json,
    http_text,
    typescript_idl_to_json,
)


FUNDING_RECORD_DISCRIMINATOR = hashlib.sha256(b"account:FundingRecord").digest()[:8]


def accepted_raw(launch: dict[str, Any]) -> int:
    decoded = launch["decoded"]
    for field in ("finalRaiseAmount", "totalApprovedAmount", "totalCommittedAmount"):
        value = decoded.get(field)
        if value is not None:
            return int(value)
    return 0


def decode_funding_record(
    decoder: IdlDecoder, idl: dict[str, Any], raw: bytes
) -> tuple[dict[str, Any], int]:
    if raw[:8] != FUNDING_RECORD_DISCRIMINATOR:
        raise ValueError("account discriminator is not FundingRecord")
    account = next(
        entry for entry in idl["accounts"] if entry["name"].lower() == "fundingrecord"
    )
    reader = BorshReader(raw, 8)
    result = {
        field["name"]: decoder.decode_spec(reader, field["type"])
        for field in account["type"]["fields"]
    }
    return result, len(raw) - reader.offset


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--launches",
        type=Path,
        default=base_dir / "data/metadao_current_launch_accounts.json",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=base_dir / "data/metadao_current_launch_audit.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base_dir / "data/metadao_material_funding_records.json",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=base_dir / "data/metadao_material_funding_records.csv",
    )
    parser.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    parser.add_argument("--minimum-accepted-usd", type=float, default=10_000)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--source-transport", choices=("urllib", "curl"), default="curl")
    parser.add_argument("--rpc-transport", choices=("urllib", "curl"), default="curl")
    parser.add_argument(
        "--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto"
    )
    args = parser.parse_args()

    def rpc_request(payload: dict[str, Any]) -> dict[str, Any]:
        if args.rpc_transport == "curl":
            completed = subprocess.run(
                [
                    "curl",
                    "--max-time",
                    str(args.timeout),
                    "-sS",
                    args.rpc,
                    "-H",
                    "content-type: application/json",
                    "-d",
                    json.dumps(payload, separators=(",", ":")),
                ],
                capture_output=True,
                text=True,
                timeout=args.timeout + 5,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or "curl failed")
            return json.loads(completed.stdout)
        return http_json(
            args.rpc,
            payload,
            proxy_mode=args.proxy_mode,
            timeout=args.timeout,
        )

    launches = [
        row
        for row in json.loads(args.launches.read_text())
        if row["state"] == "Complete"
        and accepted_raw(row) / 1_000_000 >= args.minimum_accepted_usd
    ]
    launch_audit = json.loads(args.audit.read_text())
    commit = launch_audit["commit"]
    by_version: dict[str, list[dict[str, Any]]] = {}
    for launch in launches:
        by_version.setdefault(launch["version"], []).append(launch)

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    version_audit: dict[str, Any] = {}
    for version, version_launches in by_version.items():
        deployment = DEPLOYMENTS[version]
        idl_url = (
            f"https://raw.githubusercontent.com/{REPO}/{commit}/"
            f"{deployment['idl_path']}"
        )
        if args.source_transport == "curl":
            completed = subprocess.run(
                ["curl", "-L", "--max-time", str(args.timeout), "-sS", idl_url],
                capture_output=True,
                text=True,
                timeout=args.timeout + 5,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or "curl failed")
            source = completed.stdout
        else:
            source = http_text(idl_url, proxy_mode=args.proxy_mode, timeout=args.timeout)
        idl = typescript_idl_to_json(source)
        decoder = IdlDecoder(idl)
        funding_account = next(
            entry for entry in idl["accounts"] if entry["name"].lower() == "fundingrecord"
        )
        field_names = [field["name"] for field in funding_account["type"]["fields"]]
        if [name.lower() for name in field_names[:3]] != ["pdabump", "funder", "launch"]:
            raise RuntimeError(f"unexpected FundingRecord prefix for {version}: {field_names}")
        # 8-byte Anchor discriminator + u8 pdaBump + 32-byte funder pubkey.
        launch_memcmp_offset = 41
        version_count = 0
        for launch_index, launch in enumerate(version_launches, start=1):
            request = {
                "jsonrpc": "2.0",
                "id": launch["launch_account"],
                "method": "getProgramAccounts",
                "params": [
                    deployment["program"],
                    {
                        "commitment": "finalized",
                        "encoding": "base64",
                        "filters": [
                            {
                                "memcmp": {
                                    "offset": 0,
                                    "bytes": b58encode(FUNDING_RECORD_DISCRIMINATOR),
                                }
                            },
                            {
                                "memcmp": {
                                    "offset": launch_memcmp_offset,
                                    "bytes": launch["launch_account"],
                                }
                            },
                        ],
                    },
                ],
            }
            try:
                response = rpc_request(request)
                if "error" in response:
                    raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
                records = response["result"]
                for account in records:
                    raw = base64.b64decode(account["account"]["data"][0])
                    decoded, trailing = decode_funding_record(decoder, idl, raw)
                    if decoded["launch"] != launch["launch_account"]:
                        raise RuntimeError("launch memcmp/decode mismatch")
                    committed = int(decoded.get("committedAmount") or 0)
                    approved_value = decoded.get("approvedAmount")
                    launch_decoded = launch["decoded"]
                    final_raise = launch_decoded.get("finalRaiseAmount")
                    total_committed = launch_decoded.get("totalCommittedAmount")
                    if approved_value is not None:
                        # v0.7 stores the curator-approved amount directly.
                        actual_accepted = int(approved_value)
                        accepted_formula = "approved_amount"
                    elif (
                        final_raise is not None
                        and total_committed
                        and int(final_raise) < int(total_committed)
                    ):
                        # v0.6 refund.rs charges ceil(final_raise * commitment /
                        # total_committed) and refunds the rest.
                        numerator = int(final_raise) * committed
                        actual_accepted = numerator // int(total_committed)
                        if numerator % int(total_committed):
                            actual_accepted += 1
                        accepted_formula = "v06_pro_rata_ceil"
                    else:
                        actual_accepted = committed
                        accepted_formula = "committed_amount"
                    rows.append(
                        {
                            "version": version,
                            "program": deployment["program"],
                            "launch_account": launch["launch_account"],
                            "token_mint": launch["base_mint"],
                            "funding_record": account["pubkey"],
                            "funder": decoded["funder"],
                            "committed_raw": committed,
                            "approved_raw": (
                                int(approved_value) if approved_value is not None else None
                            ),
                            "actual_accepted_raw": actual_accepted,
                            "actual_accepted_formula": accepted_formula,
                            "committed_usd": committed / 1_000_000,
                            "actual_accepted_usd": actual_accepted / 1_000_000,
                            "acceptance_ratio": (
                                actual_accepted / committed if committed else None
                            ),
                            "is_tokens_claimed": decoded.get("isTokensClaimed"),
                            "is_quote_refunded": decoded.get("isUsdcRefunded")
                            if "isUsdcRefunded" in decoded
                            else decoded.get("isQuoteRefunded"),
                            "account_space": account["account"].get("space"),
                            "trailing_bytes": trailing,
                        }
                    )
                version_count += len(records)
            except Exception as exc:
                failures.append(
                    {"version": version, "launch_account": launch["launch_account"], "error": str(exc)}
                )
            print(
                json.dumps(
                    {
                        "version": version,
                        "launch_progress": f"{launch_index}/{len(version_launches)}",
                        "records_so_far": len(rows),
                        "failures": len(failures),
                    }
                ),
                flush=True,
            )
        version_audit[version] = {
            "program": deployment["program"],
            "idl_url": idl_url,
            "idl_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "funding_record_fields": field_names,
            "launch_memcmp_offset": launch_memcmp_offset,
            "material_launches": len(version_launches),
            "funding_records": version_count,
        }

    launch_counts = collections_counter = {
        launch["launch_account"]: sum(
            row["launch_account"] == launch["launch_account"] for row in rows
        )
        for launch in launches
    }
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": args.rpc,
        "official_repo": REPO,
        "commit": commit,
        "funding_record_discriminator_hex": FUNDING_RECORD_DISCRIMINATOR.hex(),
        "funding_record_discriminator_base58": b58encode(FUNDING_RECORD_DISCRIMINATOR),
        "selection": {
            "state": "Complete",
            "minimum_accepted_usd": args.minimum_accepted_usd,
            "material_launch_count": len(launches),
        },
        "versions": version_audit,
        "launch_record_counts": launch_counts,
        "records": rows,
        "failures": failures,
        "complete": not failures and len(launch_counts) == len(launches),
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    columns = [
        "version",
        "program",
        "launch_account",
        "token_mint",
        "funding_record",
        "funder",
        "committed_raw",
        "approved_raw",
        "actual_accepted_raw",
        "actual_accepted_formula",
        "committed_usd",
        "actual_accepted_usd",
        "acceptance_ratio",
        "is_tokens_claimed",
        "is_quote_refunded",
        "account_space",
        "trailing_bytes",
    ]
    with args.csv_output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "material_launches": len(launches),
                "funding_records": len(rows),
                "launches_with_zero_records": sum(value == 0 for value in launch_counts.values()),
                "failures": len(failures),
                "complete": output["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
