#!/usr/bin/env python3
"""Cross-check ten S0 entry reserves against cached, independently decoded RPC transactions."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
from pathlib import Path

from evt_decode import iter_events


H = Path(__file__).resolve().parent
S0 = H / "raw/s0/S0_AB_v1_3_audit_columns.csv.gz"
H1 = H.parents[0] / "pump曲线_案例时序与点火跟随_H1" / "raw"


def yes(value: str) -> bool:
    return value.lower() in ("true", "1")


def source_files() -> dict[str, Path]:
    paths = list((H / "raw/helius").glob("coin__*.jsonl.gz"))
    paths += list(H1.glob("full24h_*.jsonl.gz"))
    out = {}
    for path in paths:
        name = path.name
        mint = name.split("__")[1] if name.startswith("coin__") else name[len("full24h_"):-len(".jsonl.gz")]
        out[mint] = path
    return out


def main() -> None:
    with gzip.open(S0, "rt", newline="") as src:
        formal = {r["mint"]: r for r in csv.DictReader(src)}
    found = []
    for mint, path in source_files().items():
        row = formal.get(mint)
        if row is None or not yes(row["eligible"]):
            continue
        created = dt.datetime.fromisoformat(
            row["created_at"].replace(" UTC", "+00:00").replace("Z", "+00:00")
        )
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.timezone.utc)
        cutoff = int(created.timestamp()) + int(row["t3_s"]) + 5
        pool = None
        with gzip.open(path, "rt") as src:
            for line in src:
                tx = json.loads(line)
                if tx.get("blockTime") is None or tx["blockTime"] > cutoff:
                    continue
                for ev in iter_events(tx):
                    if ev["name"] == "CreatePoolEvent" and ev.get("base_mint") == mint:
                        pool = ev["pool"]
        events = []
        with gzip.open(path, "rt") as src:
            for line in src:
                tx = json.loads(line)
                timestamp = tx.get("blockTime")
                if timestamp is None or timestamp > cutoff:
                    continue
                slot = tx["slot"]
                txi = tx.get("transactionIndex") or 0
                for ev in iter_events(tx):
                    if ev["name"] == "TradeEvent" and ev.get("mint") == mint:
                        state = (ev["virtual_sol_reserves"] / 1e9,
                                 ev["virtual_token_reserves"] / 1e6, 0)
                    elif ev["name"] in ("BuyEvent", "SellEvent"):
                        if not pool or ev.get("pool") != pool:
                            continue
                        if ev["name"] == "BuyEvent":
                            sol = ev["pool_quote_token_reserves"] + ev["quote_amount_in_with_lp_fee"]
                            token = ev["pool_base_token_reserves"] - ev["base_amount_out"]
                        else:
                            sol = ev["pool_quote_token_reserves"] - (ev["quote_amount_out"] - ev["lp_fee"])
                            token = ev["pool_base_token_reserves"] + ev["base_amount_in"]
                        state = (sol / 1e9, token / 1e6, 1)
                    else:
                        continue
                    events.append(((slot, txi, ev["oix"], ev["iix"]), timestamp, state))
        if not events:
            raise AssertionError(f"no cached trades at entry for {mint}")
        key, timestamp, state = max(events, key=lambda x: x[0])
        x, y, venue = state
        target = (float(row["e5_x"]), float(row["e5_y"]), int(row["e5_venue"]))
        # Raw integer reserve arithmetic should agree to floating-point precision.
        if abs(x - target[0]) > 1e-7 or abs(y - target[1]) > 1e-5 or venue != target[2]:
            raise AssertionError((mint, key, state, target, path))
        found.append({"mint": mint, "source": str(path.relative_to(H.parents[2])),
                      "cutoff_unix": cutoff, "last_trade_unix": timestamp,
                      "last_event_key": key, "venue": venue,
                      "reserve_sol": x, "reserve_token": y,
                      "abs_error_sol": abs(x - target[0]),
                      "abs_error_token": abs(y - target[1])})
    if len(found) < 10:
        raise AssertionError(f"only {len(found)} independent raw state checks")
    out = {"checked": len(found), "states": found,
           "verdict": "PASS_RAW_ENTRY_STATES"}
    (H / "raw/s0/S0_AB_v1_3_raw_state_audit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"checked": len(found), "verdict": out["verdict"]}))


if __name__ == "__main__":
    main()
