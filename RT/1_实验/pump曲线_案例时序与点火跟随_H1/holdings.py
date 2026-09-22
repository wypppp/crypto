"""Per-owner token ledger for the six case mints (all owner deltas, incl. transfers)."""
import gzip, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from parse_trades import tok_deltas

HERE = Path(__file__).parent
def ledger(mint):
    rows = []
    for l in gzip.open(HERE / "raw" / f"full24h_{mint}.jsonl.gz", "rt"):
        t = json.loads(l)
        for o, (a, b) in tok_deltas(t, mint).items():
            if abs(b - a) > 0:
                rows.append(dict(mint=mint, block_time=t["blockTime"], slot=t["slot"], tx_index=t["transactionIndex"],
                                 sig=t["transaction"]["signatures"][0], owner=o, delta=b - a,
                                 signer=t["transaction"]["message"]["accountKeys"][0]))
    return pd.DataFrame(rows)

if __name__ == "__main__":
    cc = pd.read_csv(HERE / "raw" / "creation_and_counts.csv")
    pd.concat([ledger(m) for m in cc.mint]).sort_values(["mint", "slot", "tx_index"]).to_csv(HERE / "ledger.csv", index=False)
