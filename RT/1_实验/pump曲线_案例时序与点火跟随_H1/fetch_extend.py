"""Extend seed archives beyond creation+24.5h so the S1 fixture covers exits (GDP to 150h, BUvu to 80h)."""
import sys, json, gzip
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import helius as H
cc = pd.read_csv(HERE / "raw/creation_and_counts.csv").set_index("mint")
for m, hours in [("5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump", 150), ("BUvuChjfCJxfUyCRMNWtm2W5ygTc7vV7mK4N22tGpump", 80)]:
    f = HERE / "raw" / f"ext_{m}.jsonl.gz"
    if f.exists(): continue
    c = int(cc.loc[m, "create_ts"])
    txs = H.all_full_ok(m, c + 1800 + 86400, c + hours * 3600)
    with gzip.open(f, "wt") as g:
        for t in txs: g.write(json.dumps(t) + "\n")
    print(m[:6], len(txs), H.CALLS, flush=True)
