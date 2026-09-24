"""Fetch free public transaction evidence for frozen P1 pool-price checks.

No Helius/Dune execution, wallet key, or live trade. Coinbase SOL/USD minute
close is an independent conversion reference; this does not claim a pool state
is exactly the state at the end of the signal hour if later LP events occurred.
"""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "s2"
RPC = "https://api.mainnet-beta.solana.com"
CB = "https://api.exchange.coinbase.com/products/SOL-USD/candles"
SAMPLE_SHA = "d3976fc120e3cc21dfd9d6f6c8745e7f41b91876edbb3ab5838ae198e284ae84"


def fetch_json(session, method, url, **kwargs):
    for attempt in range(5):
        try:
            response = session.request(method, url, timeout=25, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(1 + 2 * attempt)
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(1 + 2 * attempt)
    raise RuntimeError("public endpoint unavailable after retries")


def main():
    sample_blob = (RAW / "P1_202512_sample10.json").read_bytes()
    assert hashlib.sha256(sample_blob).hexdigest() == SAMPLE_SHA
    sample = json.loads(sample_blob)
    expected = {x["mint"] for x in sample}
    all_rows = json.loads((RAW / "P1_202512_pools.json").read_text())["rows"]
    main_rows = [x for x in all_rows if x["pool_rank"] == 1]
    assert {x["mint"] for x in main_rows} == expected
    assert len(main_rows) == 10

    rpc_dir = RAW / "rpc_pool_last"
    sol_dir = RAW / "sol_usd_minute"
    rpc_dir.mkdir(exist_ok=True)
    sol_dir.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "DQ18-price-audit/1.0"})

    for row in main_rows:
        sig = row["last_tx_id"]
        tx_path = rpc_dir / (sig + ".json")
        if not tx_path.exists():
            params = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                      "params": [sig, {"encoding": "jsonParsed",
                                       "maxSupportedTransactionVersion": 0}]}
            tx = fetch_json(session, "POST", RPC, json=params)
            if tx.get("error") or not tx.get("result"):
                print("RPC_MISSING", row["mint"], str(tx.get("error"))[:120])
                continue
            tx_path.write_text(json.dumps(tx, ensure_ascii=False))
            time.sleep(0.25)

        stamp = datetime.strptime(row["last_trade_at"],
                                  "%Y-%m-%d %H:%M:%S.000 UTC").replace(
                                      tzinfo=timezone.utc)
        minute = stamp.replace(second=0, microsecond=0)
        sol_path = sol_dir / (minute.strftime("%Y%m%d%H%M") + ".json")
        if not sol_path.exists():
            candles = fetch_json(session, "GET", CB, params={
                "start": (minute - timedelta(minutes=1)).isoformat(),
                "end": (minute + timedelta(minutes=2)).isoformat(),
                "granularity": 60,
            })
            sol_path.write_text(json.dumps({"minute": minute.isoformat(),
                                            "candles": candles}))
            time.sleep(0.25)
        print("cached", row["mint"][:9], row["project"],
              row["last_trade_at"], tx_path.name[:10])


if __name__ == "__main__":
    main()
