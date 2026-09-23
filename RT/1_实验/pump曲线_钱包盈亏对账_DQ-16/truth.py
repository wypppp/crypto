"""DQ-16 §4: ground-truth per-transaction ledger for each sampled wallet from Helius full transactions.

Per (wallet, tx):  F = total lamport change of the wallet plus every token account it owns (rent stays an
asset, wSOL counts as SOL); fee (if fee payer); tip (lamports gained by Jito tip accounts); rent (lamports
locked in the wallet's token accounts, wSOL amount excluded); program class; per-mint token delta.
Outputs results/truth_tx.csv and results/truth_tok.csv (one row per wallet, tx, mint with delta != 0).
"""
import csv, gzip, json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL = "So11111111111111111111111111111111111111112"
TIPS = {"HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
        "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
        "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh"}   # Jito getTipAccounts, 09-23

def keys_of(t):
    la = t["meta"].get("loadedAddresses") or {}
    return t["transaction"]["message"]["accountKeys"] + la.get("writable", []) + la.get("readonly", [])

def programs(t, keys):
    msg, m = t["transaction"]["message"], t["meta"]
    top = [keys[i["programIdIndex"]] for i in msg["instructions"]]
    inner = [keys[i["programIdIndex"]] for g in (m.get("innerInstructions") or []) for i in g["instructions"]]
    return top, set(top) | set(inner)

def one(wallet, t):
    m, keys = t["meta"], keys_of(t)
    pre, post = m["preBalances"], m["postBalances"]
    nsig = t["transaction"]["message"]["header"]["numRequiredSignatures"]
    tb = defaultdict(dict)                                   # accountIndex -> {"pre":, "post":, "mint":, "owner":}
    for side, lst in (("pre", m["preTokenBalances"]), ("post", m["postTokenBalances"])):
        for x in lst:
            d = tb[x["accountIndex"]]
            d[side] = int(x["uiTokenAmount"]["amount"]); d["mint"] = x["mint"]; d["owner"] = x.get("owner")
    own = {i: d for i, d in tb.items() if d.get("owner") == wallet}
    widx = [i for i, k in enumerate(keys) if k == wallet]
    d_wallet = sum(post[i] - pre[i] for i in widx)
    rent = dwsol = 0
    tok = defaultdict(int)
    for i, d in own.items():
        dam = d.get("post", 0) - d.get("pre", 0)
        dl = post[i] - pre[i]
        if d["mint"] == WSOL:
            dwsol += dam; rent += dl - dam
        else:
            rent += dl
            if dam:
                tok[d["mint"]] += dam
    F = d_wallet + rent + dwsol
    signer = wallet in keys[:nsig]
    tip = sum(post[i] - pre[i] for i, k in enumerate(keys) if k in TIPS) if signer else 0
    top, allp = programs(t, keys)
    cls = "pump" if PUMP in allp else "amm" if AMM in allp else ("transfer_only" if not signer else "other")
    return dict(wallet=wallet, sig=t["transaction"]["signatures"][0], slot=t["slot"], txi=t.get("transactionIndex"),
                ts=t["blockTime"], ok=m["err"] is None, fee_payer=keys[0] == wallet, signer=signer,
                fee=m["fee"] if keys[0] == wallet else 0, tip=tip, rent=rent, dwsol=dwsol, d_wallet=d_wallet, F=F,
                cls=cls, n_mints=len(tok), top=";".join(sorted(set(top)))), tok

def main():
    txrows, tokrows = [], []
    for f in sorted((HERE / "raw" / "helius").glob("*.jsonl.gz")):
        w = f.name.split(".")[0]
        for line in gzip.open(f, "rt"):
            t = json.loads(line)
            r, tok = one(w, t)
            txrows.append(r)
            for mint, dam in tok.items():
                tokrows.append(dict(wallet=w, sig=r["sig"], slot=r["slot"], txi=r["txi"], mint=mint, d_tok=dam,
                                    ok=r["ok"], cls=r["cls"]))
    out = HERE / "results"
    for name, rows in (("truth_tx.csv", txrows), ("truth_tok.csv", tokrows)):
        with open(out / name, "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
    print(len(txrows), "tx rows;", len(tokrows), "token rows")

if __name__ == "__main__":
    main()
