"""Compare frozen P1 December signal VWAP with last-swap vault price.

Historical balances come from public getTransaction pre/post token balances.
For Raydium v4, current pool account data identifies immutable vault addresses;
that vault ratio remains a proxy when OpenOrders inventory or unsettled PnL
matters. For PumpSwap, vault owner is the pool PDA. No returns are computed.
"""

import base64
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "s2"
SOL = "So11111111111111111111111111111111111111112"
RAYDIUM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RPC = "https://api.mainnet-beta.solana.com"
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(raw):
    n = int.from_bytes(raw, "big")
    chars = ""
    while n:
        n, rem = divmod(n, 58)
        chars = ALPHABET[rem] + chars
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + chars


def rpc_account(pool):
    folder = RAW / "rpc_pool_accounts"
    folder.mkdir(exist_ok=True)
    path = folder / (pool + ".json")
    if path.exists():
        return json.loads(path.read_text())
    params = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
              "params": [pool, {"encoding": "base64"}]}
    for attempt in range(5):
        response = requests.post(RPC, json=params, timeout=20)
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(1 + 2 * attempt)
            continue
        response.raise_for_status()
        payload = response.json()
        if payload.get("error") or not payload.get("result", {}).get("value"):
            raise RuntimeError("Raydium pool account missing: " + pool)
        path.write_text(json.dumps(payload, ensure_ascii=False))
        return payload
    raise RuntimeError("public RPC unavailable for " + pool)


def raydium_vaults(pool, mint):
    state = rpc_account(pool)["result"]["value"]
    if state["owner"] != RAYDIUM_V4:
        raise ValueError("not Raydium AMM v4: " + pool)
    data = base64.b64decode(state["data"][0])
    if len(data) != 752:
        raise ValueError("unexpected Raydium v4 state length: " + pool)
    # Raydium SDK V2 liquidityStateV4Layout, after 32 u64 state fields,
    # two u128, one u64, two u128 and one u64.
    base_vault, quote_vault, base_mint, quote_mint = [
        base58_encode(data[offset:offset + 32])
        for offset in (336, 368, 400, 432)
    ]
    if {base_mint, quote_mint} != {mint, SOL}:
        raise ValueError("Raydium mint pair mismatch: " + pool)
    return ((base_vault, quote_vault) if base_mint == mint
            else (quote_vault, base_vault))


def transaction_balances(signature):
    payload = json.loads((RAW / "rpc_pool_last" / (signature + ".json")).read_text())
    tx = payload["result"]
    if tx["meta"]["err"] is not None:
        raise ValueError("last pool trade failed: " + signature)
    keys = tx["transaction"]["message"]["accountKeys"]
    before = {x["accountIndex"]: x for x in tx["meta"]["preTokenBalances"]}
    after = {x["accountIndex"]: x for x in tx["meta"]["postTokenBalances"]}
    output = {}
    for index in before.keys() | after.keys():
        row = after.get(index) or before[index]
        key = keys[index]
        address = key["pubkey"] if isinstance(key, dict) else key
        decimals = row["uiTokenAmount"]["decimals"]
        divisor = Decimal(10) ** decimals
        raw_pre = int(before.get(index, {}).get("uiTokenAmount", {}).get("amount", "0"))
        raw_post = int(after.get(index, {}).get("uiTokenAmount", {}).get("amount", "0"))
        output[address] = {
            "mint": row["mint"], "owner": row.get("owner"),
            "pre": Decimal(raw_pre) / divisor,
            "post": Decimal(raw_post) / divisor,
            "delta": Decimal(raw_post - raw_pre) / divisor,
        }
    return output


def sol_usd_close(stamp):
    dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.000 UTC").replace(
        tzinfo=timezone.utc)
    path = RAW / "sol_usd_minute" / (dt.strftime("%Y%m%d%H%M") + ".json")
    payload = json.loads(path.read_text())
    epoch = int(dt.replace(second=0, microsecond=0).timestamp())
    candles = [c for c in payload["candles"] if c[0] == epoch]
    if len(candles) != 1:
        raise ValueError("SOL/USD Coinbase minute missing: " + stamp)
    return Decimal(str(candles[0][4]))


def main():
    all_rows = json.loads((RAW / "P1_202512_pools.json").read_text())["rows"]
    main_pools = [r for r in all_rows if r["pool_rank"] == 1]
    p1_rows = json.loads((RAW / "P1_202512.json").read_text())["rows"]
    p1 = {(r["mint"], r["hour_start"][:19]): r for r in p1_rows
          if r["variant_name"] == "p1" and float(r["threshold_usd"]) == 1_000_000}
    output = []
    for row in main_pools:
        mint, pool = row["mint"], row["pool_id"]
        balances = transaction_balances(row["last_tx_id"])
        if row["project"] == "raydium":
            target_address, quote_address = raydium_vaults(pool, mint)
            evidence_type = "raydium_v4_vault_ratio_proxy"
        elif row["project"] == "pumpswap":
            target = [address for address, value in balances.items()
                      if value["mint"] == mint and value["owner"] == pool]
            quote = [address for address, value in balances.items()
                     if value["mint"] == SOL and value["owner"] == pool]
            if len(target) != 1 or len(quote) != 1:
                raise ValueError("PumpSwap vault pair not unique: " + mint)
            target_address, quote_address = target[0], quote[0]
            evidence_type = "pumpswap_vault_ratio"
        else:
            raise ValueError("unsupported main pool " + row["project"])
        target, quote = balances[target_address], balances[quote_address]
        if target["mint"] != mint or quote["mint"] != SOL:
            raise ValueError("vault mint mismatch: " + mint)
        usd = sol_usd_close(row["last_trade_at"])
        ref = Decimal(str(p1[(mint, row["hour_start"][:19])]["p1_vwap_cap_usd"]))
        reserve_cap = quote["post"] / target["post"] * usd * Decimal(1_000_000_000)
        hour_end = datetime.strptime(row["hour_start"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp() + 3600
        last = datetime.strptime(row["last_trade_at"],
                                 "%Y-%m-%d %H:%M:%S.000 UTC").replace(
                                     tzinfo=timezone.utc).timestamp()
        output.append({
            "mint": mint, "hour_start": row["hour_start"],
            "project": row["project"], "pool_id": pool,
            "pool_share_of_hour_usd": row["share_of_valid_usd_volume"],
            "last_tx_id": row["last_tx_id"],
            "last_trade_at": row["last_trade_at"],
            "seconds_from_last_trade_to_hour_end": int(hour_end - last),
            "target_vault": target_address, "quote_vault": quote_address,
            "target_reserve_post": str(target["post"]),
            "quote_reserve_post_sol": str(quote["post"]),
            "sol_usd_coinbase_minute_close": str(usd),
            "p1_hour_vwap_cap_usd": str(ref),
            "post_last_swap_reserve_cap_usd": str(reserve_cap),
            "relative_difference": str(reserve_cap / ref - 1),
            "evidence_type": evidence_type,
        })
    output.sort(key=lambda r: r["mint"])
    path = RAW / "P1_202512_pool_price_check.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    for row in output:
        print(row["mint"][:9], row["project"],
              "gap_s", row["seconds_from_last_trade_to_hour_end"],
              "rel_pct", round(100 * float(row["relative_difference"]), 2))
    print(path)


if __name__ == "__main__":
    main()
