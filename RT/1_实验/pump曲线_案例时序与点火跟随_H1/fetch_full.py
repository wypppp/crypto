"""Fetch succeeded full transactions for the six case mints, creation .. entry+24h."""
import sys, json, gzip
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import helius as H
OUT = Path(__file__).parent / "raw"
cc = pd.read_csv(OUT / "creation_and_counts.csv")
for r in cc.itertuples():
    f = OUT / f"full24h_{r.mint}.jsonl.gz"
    if f.exists():
        continue
    txs = H.all_full_ok(r.mint, int(r.create_ts), int(r.create_ts) + 1800 + 86400)
    with gzip.open(f, "wt") as g:
        for t in txs:
            g.write(json.dumps(t) + "\n")
    print(r.role, r.pair, r.mint[:6], len(txs), "expected ok", r.n_ok_24h, H.CALLS, flush=True)
