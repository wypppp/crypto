"""Compare PumpSwap event reserves/fees with the public RPC transaction ledger.

The three transactions are predefined by the S4b entry smoke check. This is
not a trading-return calculation or a fee estimate for other pools/periods.
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path


ROOT = Path(__file__).parent
RAW = ROOT / "raw"
IDL = json.loads(
    (ROOT.parent / "pump曲线_右尾测量_DQ-1M/raw/pumpdocs/pump_amm.json").read_text()
)
DISCRIMINATORS = {
    bytes(e["discriminator"]): e["name"]
    for e in IDL["events"]
    if e["name"] in {"BuyEvent", "SellEvent"}
}
FIELDS = {
    t["name"]: [f["name"] for f in t["type"]["fields"]]
    for t in IDL["types"]
    if t["name"] in {"BuyEvent", "SellEvent"}
}
SOL = "So11111111111111111111111111111111111111112"
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    chars = []
    while number:
        number, index = divmod(number, 58)
        chars.append(ALPHABET[index])
    zeros = len(data) - len(data.lstrip(b"\0"))
    return "1" * zeros + "".join(reversed(chars))


def decode_event(log: str) -> dict | None:
    if "Program data: " not in log:
        return None
    data = base64.b64decode(log.split("Program data: ", 1)[1])
    name = DISCRIMINATORS.get(data[:8])
    if name is None:
        return None
    # The historical records used here and the locally cached PumpSwap IDL
    # share this fixed Borsh prefix. Later appended fields are not needed.
    values = struct.unpack_from("<q" + "Q" * 13, data, 8)
    event = {key: value for key, value in zip(FIELDS[name], values)}
    offset = 8 + 14 * 8
    pubkeys = FIELDS[name][14:21]
    for key in pubkeys:
        event[key] = base58(data[offset : offset + 32])
        offset += 32
    for key in FIELDS[name][21:23]:
        event[key] = struct.unpack_from("<Q", data, offset)[0]
        offset += 8
    event["event_name"] = name
    return event


def pool_vaults(tx: dict, pool_id: str, mint: str) -> dict[str, dict]:
    res = tx["result"]
    keys = res["transaction"]["message"]["accountKeys"]
    before = {x["accountIndex"]: x for x in res["meta"]["preTokenBalances"]}
    after = {x["accountIndex"]: x for x in res["meta"]["postTokenBalances"]}
    output = {}
    for idx in before.keys() | after.keys():
        row = before.get(idx) or after[idx]
        if row["mint"] not in {mint, SOL} or row.get("owner") != pool_id:
            continue
        key = keys[idx]
        address = key["pubkey"] if isinstance(key, dict) else key
        output[row["mint"]] = {
            "address": address,
            "pre_raw": int(before[idx]["uiTokenAmount"]["amount"]) if idx in before else 0,
            "post_raw": int(after[idx]["uiTokenAmount"]["amount"]) if idx in after else 0,
        }
    if set(output) != {mint, SOL}:
        raise ValueError(f"Two pool vaults not found: {mint}, {pool_id}")
    return output


entries = json.loads((RAW / "S4b_另三币信号后逐笔_dune_result.json").read_text())["result"]["rows"]
selected = [
    row
    for row in entries
    if row["project"] == "pumpswap"
    and row["variant"] in {"first", "first_at_least_50_usd"}
]
if len(selected) != 3:
    raise ValueError(f"Expected three PumpSwap smoke trades, got {len(selected)}")

results = []
for row in selected:
    tx = json.loads((RAW / "rpc_entry" / f"{row['tx_id']}.json").read_text())
    events = [
        e
        for log in tx["result"]["meta"]["logMessages"]
        if (e := decode_event(log)) is not None and e["pool"] == row["pool_id"]
    ]
    if len(events) != 1:
        raise ValueError(f"Expected one event matching {row['pool_id']}, got {len(events)}")
    event = events[0]
    vaults = pool_vaults(tx, row["pool_id"], row["mint"])
    base = vaults[row["mint"]]
    quote = vaults[SOL]
    if event["pool_base_token_reserves"] != base["pre_raw"]:
        raise ValueError("Base event reserve differs from RPC pretrade vault")
    if event["pool_quote_token_reserves"] != quote["pre_raw"]:
        raise ValueError("Quote event reserve differs from RPC pretrade vault")
    if event["event_name"] == "BuyEvent":
        expected_base_post = base["pre_raw"] - event["base_amount_out"]
        legacy_quote_post = (
            quote["pre_raw"]
            + event["quote_amount_in"]
            - event["protocol_fee"]
            - event["coin_creator_fee"]
        )
        expected_quote_post = quote["pre_raw"] + event["quote_amount_in_with_lp_fee"]
    else:
        expected_base_post = base["pre_raw"] + event["base_amount_in"]
        legacy_quote_post = None
        expected_quote_post = quote["pre_raw"] - event["quote_amount_out_without_lp_fee"]
    results.append(
        {
            "mint": row["mint"],
            "variant": row["variant"],
            "tx_id": row["tx_id"],
            "pool_id": row["pool_id"],
            "event_name": event["event_name"],
            "base_event_pre_reserve_matches_rpc": True,
            "quote_event_pre_reserve_matches_rpc": True,
            "base_post_model_error_raw": base["post_raw"] - expected_base_post,
            "quote_post_model_error_raw": quote["post_raw"] - expected_quote_post,
            "quote_post_legacy_formula_error_raw": (
                quote["post_raw"] - legacy_quote_post
                if legacy_quote_post is not None
                else None
            ),
            "lp_fee_basis_points": event["lp_fee_basis_points"],
            "protocol_fee_basis_points": event["protocol_fee_basis_points"],
            "coin_creator_fee_basis_points": event["coin_creator_fee_basis_points"],
            "total_fee_basis_points": event["lp_fee_basis_points"]
            + event["protocol_fee_basis_points"]
            + event["coin_creator_fee_basis_points"],
            "pool_quote_pre_raw": quote["pre_raw"],
            "pool_quote_post_raw": quote["post_raw"],
        }
    )

dest = RAW / "pumpswap_event_rpc_3trades.json"
dest.write_text(json.dumps(results, ensure_ascii=False, indent=2))
for item in results:
    print(
        item["mint"][:8],
        item["variant"],
        item["event_name"],
        "fee_bps=" + str(item["total_fee_basis_points"]),
        "base_post_error=" + str(item["base_post_model_error_raw"]),
        "quote_post_error=" + str(item["quote_post_model_error_raw"]),
        "old_buy_formula_error=" + str(item["quote_post_legacy_formula_error_raw"]),
    )
print(dest)
