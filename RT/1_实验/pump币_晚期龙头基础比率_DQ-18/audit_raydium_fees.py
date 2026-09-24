"""Infer 2024 Raydium AMM v4 pool fees from four public-RPC swaps.

Uses pre/post pool vault balances and constant-product swap algebra. This
checks the sampled pool/instruction, not every DEX route or the full period.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parent
RAW = ROOT / "raw"
SOL = "So11111111111111111111111111111111111111112"
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

rows = []
for name in (
    "S4a_202410_两个信号入场逐笔_dune_result.json",
    "S4b_另三币信号后逐笔_dune_result.json",
):
    data = json.loads((RAW / name).read_text())
    rows.extend(
        x
        for x in data["result"]["rows"]
        if x["project"] == "raydium"
        and x["variant"] in {"first", "first_at_least_50_usd"}
    )

seen = set()
out = []
for row in rows:
    if row["tx_id"] in seen:
        continue
    seen.add(row["tx_id"])
    result = json.loads((RAW / "rpc_entry" / f"{row['tx_id']}.json").read_text())["result"]
    logs = result["meta"]["logMessages"]
    if not any(f"Program {RAYDIUM_AMM_V4} invoke" in log for log in logs):
        raise ValueError("Expected Raydium AMM v4 in transaction logs")
    before = {x["accountIndex"]: x for x in result["meta"]["preTokenBalances"]}
    after = {x["accountIndex"]: x for x in result["meta"]["postTokenBalances"]}
    balances = []
    for idx in before.keys() | after.keys():
        token = before.get(idx) or after[idx]
        pre = int(before[idx]["uiTokenAmount"]["amount"]) if idx in before else 0
        post = int(after[idx]["uiTokenAmount"]["amount"]) if idx in after else 0
        balances.append((token["mint"], token.get("owner"), pre, post))

    direction = -1 if row["trade_direction"] == "token_bought" else 1
    token_delta_raw = round(float(row["token_amount"]) * 10**6) * direction
    target_vault = [
        (owner, pre, post)
        for mint, owner, pre, post in balances
        if mint == row["mint"] and post - pre == token_delta_raw
    ]
    if len(target_vault) != 1:
        raise ValueError("Target vault does not uniquely match printed swap")
    owner, target_pre, target_post = target_vault[0]
    quote_vault = [
        (pre, post)
        for mint, quote_owner, pre, post in balances
        if mint == SOL and quote_owner == owner and (post - pre) * direction < 0
    ]
    if len(quote_vault) != 1:
        raise ValueError("Quote vault does not uniquely match target vault")
    quote_pre, quote_post = quote_vault[0]

    if direction == -1:
        quote_in = quote_post - quote_pre
        target_out = target_pre - target_post
        effective_fraction = target_out * quote_pre / (
            quote_in * (target_pre - target_out)
        )
    else:
        target_in = target_post - target_pre
        quote_out = quote_pre - quote_post
        effective_fraction = quote_out * target_pre / (
            target_in * (quote_pre - quote_out)
        )

    out.append(
        {
            "mint": row["mint"],
            "variant": row["variant"],
            "tx_id": row["tx_id"],
            "pool_id_dune": row["pool_id"],
            "target_vault_owner": owner,
            "pool_program_in_logs": RAYDIUM_AMM_V4,
            "target_pre_raw": target_pre,
            "target_post_raw": target_post,
            "quote_pre_raw": quote_pre,
            "quote_post_raw": quote_post,
            "implied_fee_bps": (1 - effective_fraction) * 10000,
            "other_dex_program_in_same_tx": any(
                "Program LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo invoke"
                in log
                for log in logs
            ),
        }
    )

if len(out) != 4:
    raise ValueError(f"Expected four unique Raydium trades, got {len(out)}")
dest = RAW / "raydium_amm_v4_implied_fee_4trades.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
for x in out:
    print(
        x["mint"][:8],
        x["variant"],
        f"implied_fee_bps={x['implied_fee_bps']:.3f}",
        f"other_dex_in_tx={x['other_dex_program_in_same_tx']}",
    )
print(dest)
