"""DQ-16 §4: fetch every transaction (succeeded and failed, incl. token-account-only ones) of the 30 sampled
wallets on 2026-06-07 UTC. Count first (signatures mode), then full pages. Budget: 3,000 credits per wallet,
60,000 total, at an assumed 10 credits per getTransactionsForAddress call (F92⑥)."""
import csv, gzip, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import helius as H

T0, T1 = 1780790400, 1780790400 + 86400
HERE = Path(__file__).parent
OUT = HERE / "raw" / "helius"; OUT.mkdir(parents=True, exist_ok=True)
PER_WALLET, TOTAL, CR = 3000, 60000, 10
TA = "balanceChanged"

def calls():
    return H.CALLS.get("getTransactionsForAddress", 0)

rows = []
for r in csv.DictReader(open(HERE / "raw" / "sample.csv")):
    w, f = r["wallet"], OUT / f"{r['wallet']}.jsonl.gz"
    c0 = calls()
    n, tok = 0, None
    while True:                                         # count
        p = H.gtfa_page(w, T0, T1, details="signatures", limit=1000, token=tok, token_accounts=TA)
        n += len(p.get("data", [])); tok = p.get("paginationToken")
        if not tok or not p.get("data"):
            break
    need = (n + 99) // 100
    status = "ok"
    if (need + calls() - c0) * CR > PER_WALLET or (calls() + need) * CR > TOTAL:
        status = "over_budget"
    elif not f.exists():
        got, tok = [], None
        while True:
            p = H.gtfa_page(w, T0, T1, details="full", limit=100, token=tok, token_accounts=TA)
            got += p.get("data", []); tok = p.get("paginationToken")
            if not tok or not p.get("data"):
                break
        with gzip.open(f, "wt") as g:
            for t in got:
                g.write(json.dumps(t) + "\n")
        if len(got) != n:
            status = f"count_mismatch_{len(got)}"
    rows.append(dict(k=r["k"], wallet=w, n_sig=n, status=status, calls=calls() - c0))
    print(rows[-1], "total_calls", calls(), flush=True)

with open(HERE / "raw" / "fetch_log.csv", "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
print("DONE total getTransactionsForAddress calls", calls(), "≈ credits", calls() * CR)
