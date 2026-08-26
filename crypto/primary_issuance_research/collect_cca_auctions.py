#!/usr/bin/env python3
"""Enumerate Uniswap TWA/CCA auction factories from EVM logs.

The factory list is copied from Uniswap's append-only SDK registry.  Every
factory and every supported mainnet is queried; failures remain in the audit
instead of silently shrinking the denominator.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_metadao_launches import http_json


EVENT_SIGNATURE = "AuctionCreated(address,address,uint256,bytes)"

FACTORIES = {
    "v1_twa": "0xcccccccae7503cac057829bf2811de42e16e0bd5",
    "v2_early_test": "0x088ca22b591f2f4bf0ad2780d2a44fa692e948d0",
    "v2_legacy": "0x00cCa200BF124dBfA848937c553864f4B4CE0632",
    "v2_current_2026_07_09": "0x000000001F26a0044BaA66024e7b6599c61963F8",
}

CHAINS = {
    "ethereum": {"chain_id": 1, "rpc": "https://ethereum-rpc.publicnode.com"},
    "unichain": {"chain_id": 130, "rpc": "https://mainnet.unichain.org"},
    "base": {"chain_id": 8453, "rpc": "https://mainnet.base.org"},
    "arbitrum": {"chain_id": 42161, "rpc": "https://arb1.arbitrum.io/rpc"},
    "avalanche": {"chain_id": 43114, "rpc": "https://api.avax.network/ext/bc/C/rpc"},
    "xlayer": {"chain_id": 196, "rpc": "https://rpc.xlayer.tech"},
    "robinhood": {"chain_id": 4663, "rpc": "https://rpc.mainnet.chain.robinhood.com"},
}


class RpcError(RuntimeError):
    pass


class EvmRpc:
    def __init__(self, url: str, proxy_mode: str, timeout: int):
        self.url = url
        self.proxy_mode = proxy_mode
        self.timeout = timeout
        self.request_id = 0

    def call(self, method: str, params: list[Any]) -> Any:
        self.request_id += 1
        response = http_json(
            self.url,
            {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params},
            proxy_mode=self.proxy_mode,
            timeout=self.timeout,
        )
        if "error" in response:
            raise RpcError(json.dumps(response["error"], ensure_ascii=False))
        return response["result"]


def block_hex(value: int) -> str:
    return hex(value)


def address_from_topic(topic: str) -> str:
    return "0x" + topic[-40:]


def abi_word(raw: bytes, index: int) -> bytes:
    start = index * 32
    end = start + 32
    if end > len(raw):
        raise ValueError(f"ABI word {index} outside {len(raw)} bytes")
    return raw[start:end]


def decode_event_data(data_hex: str, factory_name: str) -> dict[str, Any]:
    raw = bytes.fromhex(data_hex[2:] if data_hex.startswith("0x") else data_hex)
    amount = int.from_bytes(abi_word(raw, 0), "big")
    bytes_offset = int.from_bytes(abi_word(raw, 1), "big")
    config_length = int.from_bytes(raw[bytes_offset : bytes_offset + 32], "big")
    config = raw[bytes_offset + 32 : bytes_offset + 32 + config_length]
    result: dict[str, Any] = {
        "token_amount_raw": amount,
        "config_data_abi": "0x" + config.hex(),
    }
    if factory_name.startswith("v2_") and len(config) >= 12 * 32:
        # Factory emits abi.encode(parameters). Because AuctionParameters has a
        # dynamic bytes member, the first word points to the tuple head.
        tuple_base = int.from_bytes(abi_word(config, 0), "big")

        def tuple_word(index: int) -> bytes:
            start = tuple_base + index * 32
            end = start + 32
            if end > len(config):
                raise ValueError(f"auction tuple word {index} outside config data")
            return config[start:end]

        def config_address(index: int) -> str:
            return "0x" + tuple_word(index)[-20:].hex()

        steps_offset = int.from_bytes(tuple_word(10), "big")
        steps_start = tuple_base + steps_offset
        steps_length = (
            int.from_bytes(config[steps_start : steps_start + 32], "big")
            if steps_start + 32 <= len(config)
            else 0
        )
        steps = config[steps_start + 32 : steps_start + 32 + steps_length]
        result.update(
            {
                "currency": config_address(0),
                "tokens_recipient": config_address(1),
                "funds_recipient": config_address(2),
                "start_block": int.from_bytes(tuple_word(3), "big"),
                "end_block": int.from_bytes(tuple_word(4), "big"),
                "claim_block": int.from_bytes(tuple_word(5), "big"),
                "tick_spacing_q96": int.from_bytes(tuple_word(6), "big"),
                "validation_hook": config_address(7),
                "floor_price_q96": int.from_bytes(tuple_word(8), "big"),
                "required_currency_raised_raw": int.from_bytes(tuple_word(9), "big"),
                "auction_steps_data": "0x" + steps.hex(),
            }
        )
    return result


def find_deployment_block(rpc: EvmRpc, address: str, latest: int) -> int | None:
    if rpc.call("eth_getCode", [address, "latest"]) in ("0x", "0x0"):
        return None
    low, high = 0, latest
    while low < high:
        middle = (low + high) // 2
        code = rpc.call("eth_getCode", [address, block_hex(middle)])
        if code in ("0x", "0x0"):
            low = middle + 1
        else:
            high = middle
    return low


def get_logs_adaptive(
    rpc: EvmRpc,
    address: str,
    start_block: int,
    end_block: int,
    max_queries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pending = [(start_block, end_block)]
    logs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    calls = 0
    while pending and calls < max_queries:
        start, end = pending.pop()
        calls += 1
        try:
            result = rpc.call(
                "eth_getLogs",
                [{"fromBlock": block_hex(start), "toBlock": block_hex(end), "address": address}],
            )
            logs.extend(result)
        except RpcError as exc:
            if start == end:
                failures.append({"from_block": start, "to_block": end, "error": str(exc)})
                continue
            middle = (start + end) // 2
            pending.append((middle + 1, end))
            pending.append((start, middle))
    return logs, {
        "rpc_calls": calls,
        "complete": not pending and not failures,
        "unqueried_ranges": pending,
        "single_block_failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    base_dir = Path(__file__).resolve().parent
    parser.add_argument("--chain", action="append", choices=sorted(CHAINS))
    parser.add_argument("--out-dir", type=Path, default=base_dir / "data")
    parser.add_argument(
        "--output-prefix",
        default="cca_auction",
        help="Filename prefix; use one prefix per chain so partial runs cannot overwrite each other",
    )
    parser.add_argument(
        "--proxy-mode",
        choices=("auto", "env-proxy", "direct"),
        default="auto",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-log-queries", type=int, default=4_000)
    args = parser.parse_args()

    selected_chains = args.chain or list(CHAINS)
    rows: list[dict[str, Any]] = []
    audit: dict[str, Any] = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "event_signature": EVENT_SIGNATURE,
        "factory_registry_source": (
            "Uniswap/sdks main: sdks/liquidity-launcher-sdk/src/addresses.ts"
        ),
        "factories": FACTORIES,
        "chains": {},
    }

    for chain_name in selected_chains:
        chain = CHAINS[chain_name]
        rpc = EvmRpc(chain["rpc"], args.proxy_mode, args.timeout)
        chain_audit: dict[str, Any] = {"rpc": chain["rpc"], "factories": {}}
        audit["chains"][chain_name] = chain_audit
        try:
            observed_chain_id = int(rpc.call("eth_chainId", []), 16)
            latest = int(rpc.call("eth_blockNumber", []), 16)
            signature_hex = "0x" + EVENT_SIGNATURE.encode().hex()
            topic0 = rpc.call("web3_sha3", [signature_hex])
            chain_audit.update(
                {
                    "expected_chain_id": chain["chain_id"],
                    "observed_chain_id": observed_chain_id,
                    "latest_block": latest,
                    "auction_created_topic0": topic0,
                }
            )
            if observed_chain_id != chain["chain_id"]:
                raise RuntimeError(
                    f"chain-id mismatch: expected {chain['chain_id']}, got {observed_chain_id}"
                )
        except Exception as exc:
            chain_audit["fatal_error"] = str(exc)
            continue

        for factory_name, factory_address in FACTORIES.items():
            factory_audit: dict[str, Any] = {"address": factory_address}
            chain_audit["factories"][factory_name] = factory_audit
            try:
                try:
                    deployment_block = find_deployment_block(rpc, factory_address, latest)
                    factory_audit["deployment_block_method"] = "historical_eth_getCode_binary_search"
                except RpcError as exc:
                    # Some public nodes prune historical state while retaining
                    # logs. Latest code was already confirmed by the first call
                    # in find_deployment_block, so fall back without pretending
                    # the deployment block is known.
                    deployment_block = 0
                    factory_audit["deployment_block_method"] = "full_log_scan_fallback"
                    factory_audit["deployment_probe_error"] = str(exc)
                factory_audit["deployment_block"] = deployment_block
                if deployment_block is None:
                    factory_audit.update({"deployed": False, "log_count": 0})
                    continue
                factory_audit["deployed"] = True
                logs, query_audit = get_logs_adaptive(
                    rpc,
                    factory_address,
                    deployment_block,
                    latest,
                    args.max_log_queries,
                )
                factory_audit.update(query_audit)
                factory_audit["log_count"] = len(logs)
                event_logs = 0
                unknown_topics: dict[str, int] = {}
                for log in logs:
                    topics = log.get("topics", [])
                    observed_topic = topics[0] if topics else ""
                    if observed_topic.lower() != topic0.lower() or len(topics) < 3:
                        unknown_topics[observed_topic] = unknown_topics.get(observed_topic, 0) + 1
                        continue
                    event_logs += 1
                    decoded_data = decode_event_data(log.get("data", "0x"), factory_name)
                    rows.append(
                        dict(
                            {
                            "chain": chain_name,
                            "chain_id": chain["chain_id"],
                            "factory_version": factory_name,
                            "factory": factory_address,
                            "auction": address_from_topic(topics[1]),
                            "token": address_from_topic(topics[2]),
                            "block_number": int(log["blockNumber"], 16),
                            "transaction_hash": log["transactionHash"],
                            "transaction_index": int(log["transactionIndex"], 16),
                            "log_index": int(log["logIndex"], 16),
                            "removed": bool(log.get("removed", False)),
                            },
                            **decoded_data,
                        )
                    )
                factory_audit["auction_created_count"] = event_logs
                factory_audit["unknown_topics"] = unknown_topics
            except Exception as exc:
                factory_audit["error"] = str(exc)

    unique = {}
    for row in rows:
        key = (row["chain_id"], row["transaction_hash"], row["log_index"])
        unique[key] = row
    rows = sorted(
        unique.values(),
        key=lambda row: (row["chain_id"], row["block_number"], row["log_index"]),
    )
    audit["unique_auction_created_events"] = len(rows)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.output_prefix}_created_events.json"
    csv_path = args.out_dir / f"{args.output_prefix}_created_events.csv"
    audit_path = args.out_dir / f"{args.output_prefix}_audit.json"
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    columns = [
        "chain",
        "chain_id",
        "factory_version",
        "factory",
        "auction",
        "token",
        "token_amount_raw",
        "block_number",
        "transaction_hash",
        "transaction_index",
        "log_index",
        "removed",
        "currency",
        "tokens_recipient",
        "funds_recipient",
        "start_block",
        "end_block",
        "claim_block",
        "tick_spacing_q96",
        "validation_hook",
        "floor_price_q96",
        "required_currency_raised_raw",
        "auction_steps_data",
        "config_data_abi",
    ]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows([{column: row.get(column) for column in columns} for row in rows])
    print(json.dumps({"events": len(rows), "audit": str(audit_path), "csv": str(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
