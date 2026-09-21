"""Parse Helius full transactions into per-trade rows for the six case mints.

Venue price is the post-trade reserve state, not the trader's fill:
  pump curve: k / vTok^2 with vTok = curve ATA balance + 73,000,000, k = 30 * 1,073,000,000 (SOL*token)
  PumpSwap pool: pool WSOL balance / pool token balance
Venue accounts are inferred as the token owners present in the most transactions (curve first, pool after migration).
"""
import gzip, json
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
RAW = HERE / "raw"
WSOL = "So11111111111111111111111111111111111111112"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
K = 30 * 1_073_000_000

def keys_of(t):
    m = t["transaction"]["message"]
    la = t["meta"].get("loadedAddresses") or {}
    return m["accountKeys"] + la.get("writable", []) + la.get("readonly", [])

def tok_deltas(t, mint):
    """{owner: (pre, post)} in UI units for one mint, summed over that owner's accounts."""
    d = defaultdict(lambda: [0.0, 0.0])
    for side, arr in ((0, t["meta"]["preTokenBalances"]), (1, t["meta"]["postTokenBalances"])):
        for b in arr or []:
            if b["mint"] == mint:
                d[b.get("owner")][side] += float(b["uiTokenAmount"]["uiAmount"] or 0)
    return d

def top_programs(t, keys):
    return sorted({keys[i["programIdIndex"]] for i in t["transaction"]["message"]["instructions"]})

def parse(mint, create_ts):
    txs = [json.loads(l) for l in gzip.open(RAW / f"full24h_{mint}.jsonl.gz", "rt")]
    # venue inference: owners with a nonzero delta in the most transactions
    freq = Counter()
    for t in txs:
        for o, (a, b) in tok_deltas(t, mint).items():
            if abs(b - a) > 0:
                freq[o] += 1
    # the curve owns ~1e9 tokens at creation; the pool owns WSOL too
    curve = pool = None
    for o, _ in freq.most_common(6):
        for t in txs:
            td = tok_deltas(t, mint)
            if o in td:
                pre, post = td[o]
                ws = tok_deltas(t, WSOL).get(o)
                if ws and max(ws) > 0:
                    pool = pool or o
                elif max(pre, post) > 1e8 and curve is None and o != pool:
                    curve = o
                break
    rows = []
    for t in txs:
        keys = keys_of(t)
        td = tok_deltas(t, mint)
        ws = tok_deltas(t, WSOL)
        pre_b, post_b = t["meta"]["preBalances"], t["meta"]["postBalances"]
        progs = top_programs(t, keys)
        venue, price, venue_sol, venue_tok = None, None, 0.0, 0.0
        if curve in td:
            venue = "curve"
            vt = td[curve][1] + 73_000_000
            price = K / vt ** 2 if vt > 0 else None
            venue_tok = td[curve][1] - td[curve][0]
            if curve in keys:
                i = keys.index(curve)
                venue_sol = (post_b[i] - pre_b[i]) / 1e9
        if pool in td and pool in ws:
            venue = "pool" if venue is None else venue + "+pool"
            pt, pw = td[pool][1], ws[pool][1]
            price = pw / pt if pt > 0 else price
            venue_tok += td[pool][1] - td[pool][0]
            venue_sol += ws[pool][1] - ws[pool][0]
        others = {o: b - a for o, (a, b) in td.items() if o not in (curve, pool) and abs(b - a) > 1e-9}
        signer = keys[0]
        if venue and abs(venue_sol) > 0:
            # SOL direction is robust even when the venue token account is created in this tx (creation buys)
            kind = "buy" if venue_sol > 0 else "sell"
        elif venue and abs(venue_tok) > 0:
            kind = "buy" if venue_tok < 0 else "sell"
        elif others:
            kind = "transfer"
        else:
            kind = "other"
        # the trader is the non-venue owner with the largest opposite token delta; fall back to signer
        trader = max(others, key=lambda o: abs(others[o])) if others else signer
        rows.append(dict(
            mint=mint, sig=t["transaction"]["signatures"][0], slot=t["slot"], tx_index=t["transactionIndex"],
            block_time=t["blockTime"], t_rel_entry=t["blockTime"] - create_ts - 1800,
            signer=signer, trader=trader, n_other_owners=len(others), kind=kind, venue=venue,
            tok=-venue_tok, sol=venue_sol, price_post=price, fee_lamports=t["meta"]["fee"],
            progs=" ".join(p[:8] for p in progs if p not in ("ComputeBudget111111111111111111111111111111",)),
            n_sigs=t["transaction"]["message"]["header"]["numRequiredSignatures"],
        ))
    df = pd.DataFrame(rows).sort_values(["slot", "tx_index"]).reset_index(drop=True)
    return df, curve, pool

if __name__ == "__main__":
    cc = pd.read_csv(RAW / "creation_and_counts.csv")
    out, meta = [], []
    for r in cc.itertuples():
        df, curve, pool = parse(r.mint, int(r.create_ts))
        pre = df[(df.t_rel_entry <= 0) & df.price_post.notna()]
        p0 = pre.price_post.iloc[-1] if len(pre) else float("nan")
        df["pm"] = df.price_post / p0
        out.append(df)
        meta.append(dict(role=r.role, pair=r.pair, mint=r.mint, curve=curve, pool=pool, entry_price=p0,
                         n=len(df), kinds=dict(Counter(df.kind))))
        print(meta[-1])
    pd.concat(out).to_csv(HERE / "trades.csv", index=False)
    pd.DataFrame(meta).to_csv(HERE / "venues.csv", index=False)
