"""DQ-16 §4 (r1): ground-truth ledger for each sampled wallet from Helius full transactions.

results/truth_tx.csv  one row per (wallet, tx):
  in_signers / fee_payer   the wallet is among the tx signers / is the fee payer (first account key)
  fee_paid                 meta.fee if fee payer, else 0
  tip                      lamports gained by Jito tip accounts, if the wallet signed
  d_wallet                 lamport change of the wallet account
  d_lam_tok, d_lam_wsol    lamport change of wallet-owned token accounts (non-wSOL = rent; wSOL = rent + wrapped SOL)
  d_wsol_raw               wrapped-SOL amount change in wallet-owned wSOL accounts
  F                        d_wallet + d_lam_tok + d_lam_wsol  (all value held by the wallet and its token accounts)
  pump, amm, other_dex     programs invoked anywhere in the tx (other_dex: a fixed list of Solana DEX/aggregator ids)
  touched                  any wallet-owned SOL/token balance or token-account lamports changed
results/truth_tok.csv one row per (wallet, tx, mint != wSOL) where a wallet-owned token account of that mint appears:
  pre_raw, post_raw, decimals (summed over the wallet's accounts of that mint)
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
OTHER_DEX = {"675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",   # Raydium AMM v4
             "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",   # Raydium CPMM
             "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",   # Raydium CLMM
             "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",    # Raydium LaunchLab
             "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",    # Meteora DLMM
             "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB",   # Meteora DAMM v1
             "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG",    # Meteora DAMM v2
             "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN",    # Meteora DBC
             "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",    # Orca Whirlpool
             "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}    # Jupiter v6

def keys_of(t):
    la = t["meta"].get("loadedAddresses") or {}
    return t["transaction"]["message"]["accountKeys"] + la.get("writable", []) + la.get("readonly", [])

def programs(t, keys):
    msg, m = t["transaction"]["message"], t["meta"]
    return {keys[i["programIdIndex"]] for i in msg["instructions"]} | \
           {keys[i["programIdIndex"]] for g in (m.get("innerInstructions") or []) for i in g["instructions"]}

def one(k, wallet, t):
    m, keys = t["meta"], keys_of(t)
    pre, post = m["preBalances"], m["postBalances"]
    nsig = t["transaction"]["message"]["header"]["numRequiredSignatures"]
    tb = defaultdict(dict)
    for side, lst in (("pre", m["preTokenBalances"]), ("post", m["postTokenBalances"])):
        for x in lst:
            if x.get("owner") != wallet:
                continue
            d = tb[x["accountIndex"]]
            d[side] = int(x["uiTokenAmount"]["amount"]); d["mint"] = x["mint"]; d["dec"] = x["uiTokenAmount"]["decimals"]
    d_wallet = sum(post[i] - pre[i] for i, key in enumerate(keys) if key == wallet)
    d_lam_tok = d_lam_wsol = d_wsol_raw = 0
    mints = defaultdict(lambda: {"pre_raw": 0, "post_raw": 0, "decimals": None})
    for i, d in tb.items():
        dl = post[i] - pre[i]
        if d["mint"] == WSOL:
            d_lam_wsol += dl; d_wsol_raw += d.get("post", 0) - d.get("pre", 0)
        else:
            d_lam_tok += dl
            r = mints[d["mint"]]
            r["pre_raw"] += d.get("pre", 0); r["post_raw"] += d.get("post", 0); r["decimals"] = d["dec"]
    in_signers = wallet in keys[:nsig]
    progs = programs(t, keys)
    touched = bool(d_wallet or d_lam_tok or d_lam_wsol or any(r["pre_raw"] != r["post_raw"] for r in mints.values()))
    row = dict(k=k, wallet=wallet, sig=t["transaction"]["signatures"][0], slot=t["slot"], txi=t.get("transactionIndex"),
               ok=m["err"] is None, in_signers=in_signers, fee_payer=keys[0] == wallet,
               fee_paid=m["fee"] if keys[0] == wallet else 0,
               tip=sum(post[i] - pre[i] for i, key in enumerate(keys) if key in TIPS) if in_signers else 0,
               d_wallet=d_wallet, d_lam_tok=d_lam_tok, d_lam_wsol=d_lam_wsol, d_wsol_raw=d_wsol_raw,
               F=d_wallet + d_lam_tok + d_lam_wsol,
               pump=PUMP in progs, amm=AMM in progs, other_dex=bool(progs & OTHER_DEX), touched=touched)
    return row, mints

def main():
    ks = {r["wallet"]: int(r["k"]) for r in csv.DictReader(open(HERE / "raw" / "sample.csv"))}
    txrows, tokrows = [], []
    for f in sorted((HERE / "raw" / "helius").glob("*.jsonl.gz")):
        w = f.name.split(".")[0]
        for line in gzip.open(f, "rt"):
            r, mints = one(ks[w], w, json.loads(line))
            txrows.append(r)
            for mint, v in mints.items():
                tokrows.append(dict(k=r["k"], sig=r["sig"], slot=r["slot"], txi=r["txi"], mint=mint, **v))
    for name, rows in (("truth_tx.csv", txrows), ("truth_tok.csv", tokrows)):
        with open(HERE / "results" / name, "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
    print(len({r['k'] for r in txrows}), "wallets;", len(txrows), "tx rows;", len(tokrows), "token rows")

if __name__ == "__main__":
    main()
