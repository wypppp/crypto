#!/usr/bin/env python3
"""Append-only forward observer for new MetaDAO Launch accounts.

The initialization snapshot freezes every account that already exists.  Only
accounts first observed later enter the forward cohort.  The observer is
read-only and never constructs or submits a Solana transaction.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_metadao_launches import (
    DEPLOYMENTS,
    IdlDecoder,
    get_launch_accounts,
    http_json,
    http_text,
    resolve_commit,
    state_label,
    typescript_idl_to_json,
)


USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
MATERIAL_MINIMUM_RAW = 10_000 * 10**6


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


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


def concise_account(
    version: str,
    program: str,
    account: dict[str, Any],
    decoder: IdlDecoder,
) -> dict[str, Any]:
    raw = base64.b64decode(account["account"]["data"][0])
    decoded, trailing = decoder.decode_launch(raw)
    return {
        "version": version,
        "program": program,
        "launch_account": account["pubkey"],
        "account_space": account["account"].get("space", len(raw)),
        "data_sha256": sha256_bytes(raw),
        "trailing_bytes": trailing,
        "state": state_label(decoded.get("state")),
        "base_mint": decoded.get("baseMint") or decoded.get("tokenMint", ""),
        "quote_mint": decoded.get("quoteMint") or decoded.get("usdcMint", ""),
        "started_at": decoded.get("unixTimestampStarted"),
        "closed_at": decoded.get("unixTimestampClosed"),
        "seconds_for_launch": decoded.get("secondsForLaunch"),
        "minimum_raise_raw": decoded.get("minimumRaiseAmount"),
        "total_committed_raw": decoded.get("totalCommittedAmount"),
        "final_raise_raw": decoded.get("finalRaiseAmount"),
        "dao": decoded.get("dao"),
        "launch_authority": decoded.get("launchAuthority"),
        "performance_package_grantee": decoded.get("performancePackageGrantee"),
        "performance_package_token_amount": decoded.get("performancePackageTokenAmount"),
        "months_until_insiders_can_unlock": decoded.get("monthsUntilInsidersCanUnlock"),
        "team_address": decoded.get("teamAddress"),
    }


def load_decoders(
    state_dir: Path,
    commit: str,
    proxy_mode: str,
    timeout: int,
    allow_download: bool,
) -> tuple[dict[str, IdlDecoder], dict[str, dict[str, str]]]:
    idl_dir = state_dir / "idls"
    idl_dir.mkdir(parents=True, exist_ok=True)
    decoders: dict[str, IdlDecoder] = {}
    audit: dict[str, dict[str, str]] = {}
    for version, deployment in DEPLOYMENTS.items():
        path = idl_dir / deployment["idl_file"]
        url = (
            f"https://raw.githubusercontent.com/metaDAOproject/programs/{commit}/"
            f"{deployment['idl_path']}"
        )
        if not path.exists():
            if not allow_download:
                raise RuntimeError(f"missing frozen IDL cache: {path}")
            path.write_text(
                http_text(url, proxy_mode=proxy_mode, timeout=timeout),
                encoding="utf-8",
            )
        source = path.read_text(encoding="utf-8")
        decoders[version] = IdlDecoder(typescript_idl_to_json(source))
        audit[version] = {
            "program": deployment["program"],
            "source_url": url,
            "source_sha256": sha256_bytes(source.encode()),
            "cache_file": str(path),
        }
    return decoders, audit


def fetch_accounts(
    rpc_url: str,
    decoders: dict[str, IdlDecoder],
    proxy_mode: str,
    timeout: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    audit: dict[str, Any] = {}
    for version, deployment in DEPLOYMENTS.items():
        accounts = get_launch_accounts(
            rpc_url,
            deployment["program"],
            proxy_mode=proxy_mode,
            timeout=timeout,
        )
        decoded = []
        failures = []
        for account in accounts:
            try:
                row = concise_account(
                    version, deployment["program"], account, decoders[version]
                )
                if row["launch_account"] in rows:
                    raise RuntimeError("duplicate launch account across programs")
                rows[row["launch_account"]] = row
                decoded.append(row)
            except Exception as exc:
                failures.append(
                    {"launch_account": account.get("pubkey"), "error": str(exc)}
                )
        audit[version] = {
            "program": deployment["program"],
            "account_count": len(accounts),
            "decoded_count": len(decoded),
            "failures": failures,
        }
        if failures:
            raise RuntimeError(f"{version} account decoding incomplete: {failures[:3]}")
    return rows, audit


def material_candidate(row: dict[str, Any]) -> bool:
    return (
        row.get("quote_mint") == USDC_MINT
        and int(row.get("minimum_raise_raw") or 0) >= MATERIAL_MINIMUM_RAW
    )


def queue_row(observed_at: str, slot: int, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "queued_at": observed_at,
        "observed_slot": slot,
        "launch_account": row["launch_account"],
        "version": row["version"],
        "base_mint": row["base_mint"],
        "state_at_queue": row["state"],
        "started_at": row.get("started_at"),
        "closed_at": row.get("closed_at"),
        "minimum_raise_usdc": int(row["minimum_raise_raw"]) / 10**6,
        "score_status": "pending_pre_outcome_evidence_capture",
        "material_rule": "USDC quote and minimumRaiseAmount >= 10,000 USDC",
    }


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-dir", type=Path, default=base_dir / "forward/metadao"
    )
    parser.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    parser.add_argument("--commit", help="Official programs commit; fixed on first run")
    parser.add_argument("--proxy-mode", choices=("auto", "env-proxy", "direct"), default="auto")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    args.state_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.state_dir / "manifest.json"
    state_path = args.state_dir / "state.json"
    baseline_path = args.state_dir / "baseline_launches.json"
    discovered_path = args.state_dir / "launch_discovered.jsonl"
    changes_path = args.state_dir / "launch_state_changes.jsonl"
    queue_path = args.state_dir / "scoring_queue.jsonl"
    scores_path = args.state_dir / "scores.jsonl"
    deadline_path = args.state_dir / "score_deadline_missed.jsonl"
    runs_path = args.state_dir / "runs.jsonl"
    protocol_path = base_dir / "METADAO_FORWARD_BLIND_2026-08-28.md"

    initializing = not state_path.exists()
    if initializing:
        if manifest_path.exists():
            raise RuntimeError("manifest exists without state; refusing ambiguous reinitialization")
        commit = args.commit or resolve_commit(args.proxy_mode, args.timeout)
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        commit = manifest["programs_commit"]
        if args.commit and args.commit != commit:
            raise RuntimeError("observer commit is already frozen and cannot be changed")

    decoders, idl_audit = load_decoders(
        args.state_dir,
        commit,
        args.proxy_mode,
        args.timeout,
        allow_download=initializing,
    )
    slot = int(
        rpc_call(args.rpc, "getSlot", [{"commitment": "finalized"}], args.proxy_mode, args.timeout)
    )
    block_time = rpc_call(
        args.rpc, "getBlockTime", [slot], args.proxy_mode, args.timeout
    )
    observed_at = utc_now()
    rows, version_audit = fetch_accounts(
        args.rpc, decoders, args.proxy_mode, args.timeout
    )

    if initializing:
        baseline = sorted(rows.values(), key=lambda row: (row["version"], row["launch_account"]))
        atomic_json(baseline_path, baseline)
        manifest = {
            "created_at": observed_at,
            "purpose": "MetaDAO forward blind paper observer; read-only",
            "freeze_slot": slot,
            "freeze_block_time": block_time,
            "rpc_at_initialization": args.rpc,
            "programs_repo": "metaDAOproject/programs",
            "programs_commit": commit,
            "deployments": DEPLOYMENTS,
            "idl_audit": idl_audit,
            "baseline_account_count": len(rows),
            "baseline_file": str(baseline_path),
            "baseline_sha256": sha256_file(baseline_path),
            "protocol_path": str(protocol_path.relative_to(base_dir.parent.parent)),
            "protocol_sha256": sha256_file(protocol_path),
            "material_rule": {
                "quote_mint": USDC_MINT,
                "minimum_raise_raw": MATERIAL_MINIMUM_RAW,
            },
            "forward_rule": "only launch accounts first observed after freeze slot",
        }
        state = {
            "initialized_at": observed_at,
            "freeze_slot": slot,
            "last_observed_slot": slot,
            "runs": 0,
            "accounts": {
                address: {
                    "data_sha256": row["data_sha256"],
                    "state": row["state"],
                    "last_seen_slot": slot,
                    "forward": False,
                    "queued": False,
                    "base_mint": row.get("base_mint"),
                    "closed_at": row.get("closed_at"),
                }
                for address, row in rows.items()
            },
        }
        atomic_json(manifest_path, manifest)
        atomic_json(state_path, state)
        append_jsonl(
            runs_path,
            [
                {
                    "run_at": observed_at,
                    "mode": "initialize_forward_boundary",
                    "slot": slot,
                    "block_time": block_time,
                    "accounts": len(rows),
                    "new_launches": 0,
                    "version_audit": version_audit,
                }
            ],
        )
        print(
            json.dumps(
                {
                    "initialized": True,
                    "freeze_slot": slot,
                    "baseline_accounts": len(rows),
                    "new_launches": 0,
                    "state_dir": str(args.state_dir),
                },
                indent=2,
            )
        )
        return

    state = json.loads(state_path.read_text(encoding="utf-8"))
    known: dict[str, dict[str, Any]] = state["accounts"]
    new_rows: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []
    queue_rows: list[dict[str, Any]] = []

    for address, row in sorted(rows.items()):
        previous = known.get(address)
        if previous is None:
            discovery = {
                "observed_at": observed_at,
                "observed_slot": slot,
                "observed_block_time": block_time,
                **row,
            }
            new_rows.append(discovery)
            queued = material_candidate(row)
            if queued:
                queue_rows.append(queue_row(observed_at, slot, row))
            known[address] = {
                "data_sha256": row["data_sha256"],
                "state": row["state"],
                "last_seen_slot": slot,
                "forward": True,
                "queued": queued,
                "base_mint": row.get("base_mint"),
                "closed_at": row.get("closed_at"),
            }
            continue

        was_forward = bool(previous.get("forward"))
        was_queued = bool(previous.get("queued"))
        if previous["data_sha256"] != row["data_sha256"] and was_forward:
            change_rows.append(
                {
                    "observed_at": observed_at,
                    "observed_slot": slot,
                    "observed_block_time": block_time,
                    "launch_account": address,
                    "previous_data_sha256": previous["data_sha256"],
                    "previous_state": previous["state"],
                    **row,
                }
            )
        queued = was_queued or (was_forward and material_candidate(row))
        if queued and not was_queued:
            queue_rows.append(queue_row(observed_at, slot, row))
        previous.update(
            {
                "data_sha256": row["data_sha256"],
                "state": row["state"],
                "last_seen_slot": slot,
                "queued": queued,
                "base_mint": row.get("base_mint"),
                "closed_at": row.get("closed_at"),
            }
        )

    missing = sorted(set(known) - set(rows))
    for address in missing:
        previous = known[address]
        if previous.get("forward") and previous.get("state") != "AccountMissing":
            change_rows.append(
                {
                    "observed_at": observed_at,
                    "observed_slot": slot,
                    "observed_block_time": block_time,
                    "launch_account": address,
                    "previous_data_sha256": previous["data_sha256"],
                    "previous_state": previous["state"],
                    "state": "AccountMissing",
                    "data_sha256": None,
                }
            )
            previous["state"] = "AccountMissing"
            previous["data_sha256"] = None

    scored = {
        row["launch_account"]
        for row in read_jsonl(scores_path)
        if row.get("score_status") == "frozen_pre_outcome"
    }
    already_missed = {
        row["launch_account"] for row in read_jsonl(deadline_path)
    }
    deadline_rows = []
    terminal_states = {"Complete", "Refunding", "Closed", "AccountMissing"}
    for address, current in sorted(known.items()):
        if not current.get("forward") or not current.get("queued"):
            continue
        if address in scored or address in already_missed:
            continue
        closed_at = int(current.get("closed_at") or 0)
        deadline_passed = bool(closed_at and block_time and int(block_time) >= closed_at)
        if deadline_passed or current.get("state") in terminal_states:
            deadline_rows.append(
                {
                    "recorded_at": observed_at,
                    "recorded_slot": slot,
                    "recorded_block_time": block_time,
                    "launch_account": address,
                    "base_mint": current.get("base_mint"),
                    "state": current.get("state"),
                    "closed_at": current.get("closed_at"),
                    "score_status": "deadline_missed_all_dimensions_zero",
                    "scores": {
                        "product_usage_revenue": 0,
                        "team_delivery": 0,
                        "valuation": 0,
                        "token_rights": 0,
                        "float_lockup_dilution": 0,
                        "ordinary_allocation_capacity": 0,
                        "liquidity_and_backstop": 0,
                        "code_security_governance": 0,
                    },
                    "total_score": 0,
                }
            )

    append_jsonl(discovered_path, new_rows)
    append_jsonl(changes_path, change_rows)
    append_jsonl(queue_path, queue_rows)
    append_jsonl(deadline_path, deadline_rows)
    state["last_observed_slot"] = slot
    state["last_run_at"] = observed_at
    state["runs"] = int(state.get("runs", 0)) + 1
    state["accounts"] = known
    atomic_json(state_path, state)
    append_jsonl(
        runs_path,
        [
            {
                "run_at": observed_at,
                "slot": slot,
                "block_time": block_time,
                "accounts": len(rows),
                "new_launches": len(new_rows),
                "state_changes": len(change_rows),
                "new_scoring_queue": len(queue_rows),
                "score_deadlines_missed": len(deadline_rows),
                "version_audit": version_audit,
            }
        ],
    )
    print(
        json.dumps(
            {
                "initialized": False,
                "slot": slot,
                "accounts": len(rows),
                "new_launches": len(new_rows),
                "state_changes": len(change_rows),
                "new_scoring_queue": len(queue_rows),
                "score_deadlines_missed": len(deadline_rows),
                "state_dir": str(args.state_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
