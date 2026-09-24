"""DQ-18 step 1: cross-check five first-trade pool vaults from public RPC.

This checks a single pool at each $20m signal. It does not estimate total
cross-pool capacity, exit capacity, or investment returns.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path


ROOT = Path(__file__).parent
RAW = ROOT / "raw"
SOL = "So11111111111111111111111111111111111111112"
ENTRY_HOURS = {
    "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump": "2024-10-13T02:00:00Z",
    "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump": "2024-10-19T18:00:00Z",
    "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump": "2024-11-02T17:00:00Z",
    "a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump": "2025-12-26T23:00:00Z",
    "8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump": "2026-01-23T23:00:00Z",
}


def token_balances(tx: dict) -> list[dict]:
    res = tx["result"]
    meta = res["meta"]
    before = {x["accountIndex"]: x for x in meta["preTokenBalances"]}
    after = {x["accountIndex"]: x for x in meta["postTokenBalances"]}
    keys = res["transaction"]["message"]["accountKeys"]
    output = []
    for idx in sorted(before.keys() | after.keys()):
        row = before.get(idx) or after[idx]
        decimals = int(row["uiTokenAmount"]["decimals"])
        scale = 10**decimals
        pre_raw = int(before[idx]["uiTokenAmount"]["amount"]) if idx in before else 0
        post_raw = int(after[idx]["uiTokenAmount"]["amount"]) if idx in after else 0
        key = keys[idx]
        output.append(
            {
                "address": key["pubkey"] if isinstance(key, dict) else key,
                "owner": row.get("owner"),
                "mint": row["mint"],
                "pre_raw": pre_raw,
                "delta_raw": post_raw - pre_raw,
                "pre": pre_raw / scale,
                "delta": (post_raw - pre_raw) / scale,
                "decimals": decimals,
            }
        )
    return output


rows: list[dict] = []
for name in (
    "S4a_202410_两个信号入场逐笔_dune_result.json",
    "S4b_另三币信号后逐笔_dune_result.json",
):
    data = json.loads((RAW / name).read_text())
    rows.extend(x for x in data["result"]["rows"] if x["variant"] == "first")

candles = json.loads((RAW / "coinbase_sol_usd_entry_hours.json").read_text())
out = []
for row in rows:
    mint = row["mint"]
    tx = json.loads((RAW / "rpc_entry" / f"{row['tx_id']}.json").read_text())
    bs = token_balances(tx)
    direction = -1 if row["trade_direction"] == "token_bought" else 1
    target_raw = round(float(row["token_amount"]) * 10**6)
    target = [
        x
        for x in bs
        if x["mint"] == mint and x["delta_raw"] == direction * target_raw
    ]
    if len(target) != 1:
        raise ValueError(f"target vault not unique for {mint}: {len(target)}")
    target = target[0]
    quote = [
        x
        for x in bs
        if x["mint"] == SOL
        and x["owner"] == target["owner"]
        and x["delta_raw"] * direction < 0
    ]
    if len(quote) != 1:
        raise ValueError(f"quote vault not unique for {mint}: {len(quote)}")
    quote = quote[0]
    hour = ENTRY_HOURS[mint]
    epoch = int(datetime.fromisoformat(hour.replace("Z", "+00:00")).timestamp())
    matching = [c for c in candles[hour]["candles"] if c[0] == epoch]
    if len(matching) != 1:
        raise ValueError(f"Coinbase candle missing for {hour}")
    _, low, high, _, close, _ = matching[0]
    cap_buy_sol = quote["pre"] * (sqrt(1.05) - 1)
    cap_sell_sol = quote["pre"] * (1 - 1 / sqrt(1.05))
    out.append(
        {
            "mint": mint,
            "tx_id": row["tx_id"],
            "pool_id_dune": row["pool_id"],
            "direction": row["trade_direction"],
            "target_vault": target["address"],
            "quote_vault": quote["address"],
            "target_reserve_pre": target["pre"],
            "quote_reserve_pre_sol": quote["pre"],
            "target_vault_delta": target["delta"],
            "quote_vault_delta_sol": quote["delta"],
            "coinbase_sol_low": low,
            "coinbase_sol_high": high,
            "coinbase_sol_close": close,
            "single_pool_buy_5pct_impact_usd_low": cap_buy_sol * low,
            "single_pool_buy_5pct_impact_usd_high": cap_buy_sol * high,
            "single_pool_sell_5pct_impact_usd_low": cap_sell_sol * low,
            "single_pool_sell_5pct_impact_usd_high": cap_sell_sol * high,
        }
    )

dest = RAW / "entry_pool_vaults_5known.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
for x in out:
    print(
        x["mint"][:7],
        x["pool_id_dune"][:8],
        f"reserve={x['quote_reserve_pre_sol']:.2f} SOL",
        f"single-pool buy cap=${x['single_pool_buy_5pct_impact_usd_low']:.0f}"
        f"-${x['single_pool_buy_5pct_impact_usd_high']:.0f}",
    )
print(dest)
