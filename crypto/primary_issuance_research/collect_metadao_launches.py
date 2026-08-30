#!/usr/bin/env python3
"""Enumerate and decode current MetaDAO Launch accounts from official programs.

The collector deliberately starts from the official program registry, not the
curated projects page.  It is read-only.  Closed historical accounts require a
separate event-log pass and are not silently treated as absent launches.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import re
import shutil
import struct
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = "metaDAOproject/programs"
BRANCH = "develop"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
LAUNCH_DISCRIMINATOR = hashlib.sha256(b"account:Launch").digest()[:8]

DEPLOYMENTS = {
    "v0.4.1": {
        "program": "AfJJJ5UqxhBKoE3grkKAZZsoXDE9kncbMKvqSHGsCNrE",
        "idl_path": "sdk/src/launchpad/v0.4/types/launchpad.ts",
        "idl_file": "metadao_v04_type.ts",
    },
    "v0.5.0": {
        "program": "mooNhciQJi1LqHDmse2JPic2NqG2PXCanbE3ZYzP3qA",
        "idl_path": "sdk/src/launchpad/v0.5/types/launchpad.ts",
        "idl_file": "metadao_v05_type.ts",
    },
    "v0.6.x": {
        "program": "MooNyh4CBUYEKyXVnjGYQ8mEiJDpGvJMdvrZx1iGeHV",
        "idl_path": "sdk/src/launchpad/v0.6/types/launchpad.ts",
        "idl_file": "metadao_v06_type.ts",
    },
    "v0.7.0": {
        "program": "moontUzsdepotRGe5xsfip7vLPTJnVuafqdUWexVnPM",
        "idl_path": "sdk/src/launchpad/v0.7/types/launchpad_v7.ts",
        "idl_file": "metadao_v07_type.ts",
    },
    "v0.8.0": {
        "program": "moonDJUoHteKkGATejA5bdJVwJ6V6Dg74gyqyJTx73n",
        "idl_path": "sdk/src/launchpad/v0.8/types/launchpad_v8.ts",
        "idl_file": "metadao_v08_type.ts",
    },
}


def b58encode(raw: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    zeros = len(raw) - len(raw.lstrip(b"\0"))
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = alphabet[rem] + encoded
    return "1" * zeros + (encoded or ("1" if not zeros else ""))


def open_request(request: urllib.request.Request, proxy_mode: str, timeout: int) -> Any:
    modes = [proxy_mode] if proxy_mode != "auto" else ["env-proxy", "direct"]
    failures = []
    for mode in modes:
        handler = urllib.request.ProxyHandler() if mode == "env-proxy" else urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(handler)
        for attempt in range(2):
            try:
                return opener.open(request, timeout=timeout)
            except (OSError, urllib.error.URLError) as exc:
                failures.append(f"{mode} attempt {attempt + 1}: {exc}")
                if attempt == 0:
                    time.sleep(1)
    raise RuntimeError(f"all network paths failed for {request.full_url}: {'; '.join(failures)}")


def http_json(
    url: str,
    payload: Any = None,
    *,
    proxy_mode: str = "auto",
    timeout: int = 30,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json", "user-agent": "primary-issuance-research/0.1"},
    )
    with open_request(request, proxy_mode, timeout) as response:
        return json.load(response)


def http_text(url: str, *, proxy_mode: str = "auto", timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"user-agent": "primary-issuance-research/0.1"})
    with open_request(request, proxy_mode, timeout) as response:
        return response.read().decode()


def resolve_commit(proxy_mode: str, timeout: int) -> str:
    result = http_json(
        f"https://api.github.com/repos/{REPO}/commits/{BRANCH}",
        proxy_mode=proxy_mode,
        timeout=timeout,
    )
    return str(result["sha"])


def typescript_idl_to_json(source: str) -> dict[str, Any]:
    """Evaluate only the official IDL object literal in a restricted Node VM."""
    match = re.search(r"export const IDL:\s*\w+\s*=\s*", source)
    if not match:
        raise ValueError("IDL constant not found in official SDK type file")
    literal = source[match.end() :]
    js = r"""
const vm = require('vm');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  const context = Object.create(null);
  vm.runInNewContext('IDL = ' + input, context, {
    timeout: 1000,
    contextCodeGeneration: { strings: false, wasm: false },
  });
  process.stdout.write(JSON.stringify(context.IDL));
});
"""
    if shutil.which("node"):
        completed = subprocess.run(
            ["node", "-e", js],
            input=literal,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        return json.loads(completed.stdout)

    # Anchor's generated TypeScript IDL literal is JSON5-shaped: values are
    # JSON primitives, while object keys are bare identifiers and containers
    # have trailing commas.  This fallback keeps collection reproducible on
    # minimal hosts that do not ship Node.  It deliberately does not evaluate
    # arbitrary JavaScript.
    literal = literal.strip()
    if literal.endswith(";"):
        literal = literal[:-1].rstrip()
    json_source = re.sub(
        r'([\{\[,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)(\s*:)',
        r'\1"\2"\3',
        literal,
    )
    json_source = re.sub(r",\s*([}\]])", r"\1", json_source)
    value = json.loads(json_source)
    if not isinstance(value, dict) or "accounts" not in value:
        raise ValueError("parsed TypeScript IDL is not an Anchor IDL object")
    return value


@dataclass
class BorshReader:
    data: bytes
    offset: int = 0

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise ValueError(f"borsh underflow at {self.offset}: need {size}, have {len(self.data) - self.offset}")
        value = self.data[self.offset : end]
        self.offset = end
        return value

    def uint(self, size: int, *, signed: bool = False) -> int:
        return int.from_bytes(self.take(size), "little", signed=signed)


class IdlDecoder:
    def __init__(self, idl: dict[str, Any]):
        self.idl = idl
        self.definitions = {entry["name"]: entry["type"] for entry in idl.get("types", [])}

    def decode_spec(self, reader: BorshReader, spec: Any) -> Any:
        if isinstance(spec, str):
            primitives = {
                "u8": (1, False),
                "i8": (1, True),
                "u16": (2, False),
                "i16": (2, True),
                "u32": (4, False),
                "i32": (4, True),
                "u64": (8, False),
                "i64": (8, True),
                "u128": (16, False),
                "i128": (16, True),
            }
            if spec in primitives:
                size, signed = primitives[spec]
                return reader.uint(size, signed=signed)
            if spec in {"publicKey", "pubkey"}:
                return b58encode(reader.take(32))
            if spec == "bool":
                value = reader.uint(1)
                if value not in (0, 1):
                    raise ValueError(f"invalid borsh bool {value}")
                return bool(value)
            if spec == "string":
                return reader.take(reader.uint(4)).decode()
            if spec == "bytes":
                return base64.b64encode(reader.take(reader.uint(4))).decode()
            raise NotImplementedError(f"unsupported primitive {spec!r}")

        if "option" in spec:
            tag = reader.uint(1)
            if tag == 0:
                return None
            if tag != 1:
                raise ValueError(f"invalid option tag {tag}")
            return self.decode_spec(reader, spec["option"])
        if "vec" in spec:
            return [self.decode_spec(reader, spec["vec"]) for _ in range(reader.uint(4))]
        if "array" in spec:
            item_spec, count = spec["array"]
            return [self.decode_spec(reader, item_spec) for _ in range(count)]
        if "defined" in spec:
            return self.decode_definition(reader, spec["defined"])
        raise NotImplementedError(f"unsupported IDL spec {spec!r}")

    def decode_definition(self, reader: BorshReader, name: str) -> Any:
        definition = self.definitions[name]
        kind = definition["kind"]
        if kind == "struct":
            return {
                field["name"]: self.decode_spec(reader, field["type"])
                for field in definition.get("fields", [])
            }
        if kind == "enum":
            index = reader.uint(1)
            variants = definition["variants"]
            if index >= len(variants):
                raise ValueError(f"enum {name} index {index} outside {len(variants)} variants")
            variant = variants[index]
            fields = variant.get("fields", [])
            if not fields:
                return variant["name"]
            if all(isinstance(field, dict) and "name" in field for field in fields):
                value = {field["name"]: self.decode_spec(reader, field["type"]) for field in fields}
            else:
                value = [self.decode_spec(reader, field) for field in fields]
            return {"variant": variant["name"], "value": value}
        raise NotImplementedError(f"unsupported definition kind {kind!r}")

    def decode_launch(self, raw: bytes) -> tuple[dict[str, Any], int]:
        if raw[:8] != LAUNCH_DISCRIMINATOR:
            raise ValueError("account discriminator is not Launch")
        account = next(entry for entry in self.idl["accounts"] if entry["name"].lower() == "launch")
        reader = BorshReader(raw, 8)
        result = {
            field["name"]: self.decode_spec(reader, field["type"])
            for field in account["type"]["fields"]
        }
        return result, len(raw) - reader.offset


def get_launch_accounts(
    rpc_url: str,
    program: str,
    *,
    proxy_mode: str,
    timeout: int,
) -> list[dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getProgramAccounts",
        "params": [
            program,
            {
                "commitment": "finalized",
                "encoding": "base64",
                "filters": [{"memcmp": {"offset": 0, "bytes": b58encode(LAUNCH_DISCRIMINATOR)}}],
            },
        ],
    }
    response = http_json(rpc_url, payload, proxy_mode=proxy_mode, timeout=timeout)
    if "error" in response:
        raise RuntimeError(f"RPC error for {program}: {response['error']}")
    return list(response["result"])


def state_label(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("variant", json.dumps(value, sort_keys=True)))
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).with_name("data"))
    parser.add_argument("--commit", help="Pin the official programs repository commit")
    parser.add_argument(
        "--idl-dir",
        type=Path,
        help="Read previously downloaded official IDLs from this directory",
    )
    parser.add_argument(
        "--proxy-mode",
        choices=("auto", "env-proxy", "direct"),
        default="auto",
        help="Network path; auto tries the environment proxy and then direct access",
    )
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    if args.idl_dir and not args.commit:
        parser.error("--idl-dir requires --commit so cached source remains auditable")
    commit = args.commit or resolve_commit(args.proxy_mode, args.timeout)
    collected_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    audit: dict[str, Any] = {
        "collected_at": collected_at,
        "rpc": args.rpc,
        "repo": REPO,
        "commit": commit,
        "launch_discriminator_hex": LAUNCH_DISCRIMINATOR.hex(),
        "launch_discriminator_base58": b58encode(LAUNCH_DISCRIMINATOR),
        "versions": {},
        "limitation": "Current program accounts only; closed historical launches require an event-log pass.",
    }

    for version, deployment in DEPLOYMENTS.items():
        idl_url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{deployment['idl_path']}"
        if args.idl_dir:
            source = (args.idl_dir / deployment["idl_file"]).read_text()
        else:
            source = http_text(idl_url, proxy_mode=args.proxy_mode, timeout=args.timeout)
        idl = typescript_idl_to_json(source)
        decoder = IdlDecoder(idl)
        accounts = get_launch_accounts(
            args.rpc,
            deployment["program"],
            proxy_mode=args.proxy_mode,
            timeout=args.timeout,
        )
        version_states: Counter[str] = Counter()
        failures: list[dict[str, str]] = []

        for account in accounts:
            raw = base64.b64decode(account["account"]["data"][0])
            try:
                decoded, trailing_bytes = decoder.decode_launch(raw)
                label = state_label(decoded.get("state"))
                version_states[label] += 1
                rows.append(
                    {
                        "version": version,
                        "program": deployment["program"],
                        "launch_account": account["pubkey"],
                        "account_space": account["account"]["space"],
                        "trailing_bytes": trailing_bytes,
                        "state": label,
                        "base_mint": decoded.get("baseMint") or decoded.get("tokenMint", ""),
                        "quote_mint": decoded.get("quoteMint") or decoded.get("usdcMint", ""),
                        "started_at": decoded.get("unixTimestampStarted"),
                        "closed_at": decoded.get("unixTimestampClosed"),
                        "minimum_raise_raw": decoded.get("minimumRaiseAmount"),
                        "total_committed_raw": decoded.get("totalCommittedAmount"),
                        "final_raise_raw": decoded.get("finalRaiseAmount"),
                        "decoded": decoded,
                    }
                )
            except Exception as exc:  # preserve failures in the completeness audit
                failures.append({"launch_account": account["pubkey"], "error": str(exc)})

        audit["versions"][version] = {
            "program": deployment["program"],
            "idl_url": idl_url,
            "idl_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "account_count": len(accounts),
            "decoded_count": len(accounts) - len(failures),
            "states": dict(version_states),
            "decode_failures": failures,
        }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "metadao_current_launch_accounts.json"
    csv_path = args.out_dir / "metadao_current_launch_accounts.csv"
    audit_path = args.out_dir / "metadao_current_launch_audit.json"
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")

    columns = [
        "version",
        "program",
        "launch_account",
        "account_space",
        "trailing_bytes",
        "state",
        "base_mint",
        "quote_mint",
        "started_at",
        "closed_at",
        "minimum_raise_raw",
        "total_committed_raw",
        "final_raise_raw",
    ]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows([{key: row.get(key) for key in columns} for row in rows])

    print(json.dumps({"rows": len(rows), "audit": str(audit_path), "csv": str(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
