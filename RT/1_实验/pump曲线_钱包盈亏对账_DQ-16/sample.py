"""DQ-16 §3: draw 30 distinct A-class traders from 2026-06-07 UTC successful pump / PumpSwap transactions.

Slot-uniform draw, then one frame transaction uniformly within the block. A-class: first signer's own
token balance changes in the tx (self-custody trade). B-class (token change only in accounts not owned
by the first signer) is counted, not sampled. Output: raw/sample_draws.csv (every draw), raw/sample.csv.
"""
import csv, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import helius as H

SEED, N = 20260923, 30
S0, S1 = 424781069, 424998001            # [06-07 00:00, 06-08 00:00) UTC, via getBlockTime bisection
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
OUT = Path(__file__).parent / "raw"

def keys_of(tx):
    la = tx["meta"].get("loadedAddresses") or {}
    return tx["transaction"]["message"]["accountKeys"] + la.get("writable", []) + la.get("readonly", [])

def owner_changed(meta, who):
    pre = {x["accountIndex"]: x for x in meta["preTokenBalances"]}
    post = {x["accountIndex"]: x for x in meta["postTokenBalances"]}
    for i in set(pre) | set(post):
        x = post.get(i) or pre.get(i)
        if x.get("owner") != who:
            continue
        a = pre[i]["uiTokenAmount"]["amount"] if i in pre else "0"
        b = post[i]["uiTokenAmount"]["amount"] if i in post else "0"
        if a != b:
            return True
    return False

def main():
    rng = random.Random(SEED)
    draws, picked = [], {}
    while len(picked) < N:
        slot = rng.randrange(S0, S1)
        try:
            b = H.rpc("getBlock", [slot, {"encoding": "json", "maxSupportedTransactionVersion": 0,
                                          "transactionDetails": "full", "rewards": False}])
        except RuntimeError as e:                     # skipped slot
            draws.append(dict(slot=slot, n_block=0, n_frame=0, sig="", signer="", cls="skipped_slot"))
            continue
        frame = [t for t in b["transactions"]
                 if t["meta"]["err"] is None and (PUMP in keys_of(t) or AMM in keys_of(t))]
        if not frame:
            draws.append(dict(slot=slot, n_block=len(b["transactions"]), n_frame=0, sig="", signer="", cls="no_frame_tx"))
            continue
        t = frame[rng.randrange(len(frame))]
        signer = keys_of(t)[0]
        cls = "A" if owner_changed(t["meta"], signer) else "B"
        if cls == "A" and signer in picked:
            cls = "A_dup"
        draws.append(dict(slot=slot, n_block=len(b["transactions"]), n_frame=len(frame),
                          sig=t["transaction"]["signatures"][0], signer=signer, cls=cls))
        if cls == "A":
            picked[signer] = draws[-1]
        print(len(draws), slot, len(frame), cls, len(picked), H.CALLS, flush=True)
    with open(OUT / "sample_draws.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(draws[0].keys()))
        w.writeheader(); w.writerows(draws)
    with open(OUT / "sample.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["k", "wallet", "draw_slot", "draw_sig"])
        for k, (wal, d) in enumerate(picked.items()):
            w.writerow([k, wal, d["slot"], d["sig"]])

if __name__ == "__main__":
    main()
