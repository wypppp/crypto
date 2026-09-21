"""Expected H1 S0 v1 per-coin output for the six case mints, from local SUCCESSFUL transactions only.

Independent re-implementation of the S0 v1 semantics (not a copy of the SQL):
- per (mint, tx): curve buys = TradeEvent(is_buy, mint match).sol_amount; pool buys = BuyEvent(pool match).quote_amount_in_with_lp_fee;
  sells = TradeEvent sells (mint match) + SellEvent; special = creation tx, Deposit/Withdraw/CreatePool/CompletePumpAmmMigration.
  (CompleteEvent of the curve is NOT special in S0, because S0 does not read that table.)
- monitored window [created, created+1470min); age >= 30min; buy >= 4 SOL; pre30 (clock in [t-1800, t], strictly earlier chain order) < 4 SOL;
  sells = 0, special = 0, one venue. n_decoded_txs = txs with buy>0 or sells>0.
Compare with the Dune output rows for the fixture mints of each creation day."""
import base64, gzip, json
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58decode(t):
    n = 0
    for ch in t: n = n * 58 + ALPH.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(t) - len(t.lstrip("1"))) + raw
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
ROOT = HERE.parents[1]
src = (ROOT / "audits/RT_20260921/ignition_review/decode_archived_events.py").read_text()
ns = {"__file__": str(ROOT / "audits/RT_20260921/ignition_review/decode_archived_events.py")}
exec(src.split("CASE_MINTS = set")[0], ns)
decode_event, PUMP_ID, AMM_ID = ns["decode_event"], ns["PUMP_ID"], ns["AMM_ID"]
SPECIAL = {"DepositEvent", "WithdrawEvent", "CreatePoolEvent", "CompletePumpAmmMigrationEvent"}

cc = pd.read_csv(HERE / "raw/creation_and_counts.csv")
venues = pd.read_csv(HERE / "venues.csv").set_index("mint")
out = []
for c in cc.itertuples():
    mint, create_ts, pool = c.mint, int(c.create_ts), venues.loc[c.mint, "pool"]
    POOLRAW = b58decode(pool) if isinstance(pool, str) else None
    rows = []
    for line in gzip.open(HERE / "raw" / f"full24h_{mint}.jsonl.gz", "rt"):
        x = json.loads(line)
        sig = x["transaction"]["signatures"][0]
        buy, sells, special, vset, stack, bad, cfail = 0, 0, 0, set(), [], 0, 0
        if sig == c.first_sig:
            special += 1; vset.add("creation")
        for log in x["meta"].get("logMessages") or []:
            if log.startswith("Program ") and " invoke [" in log:
                stack.append(log.split(" ", 2)[1]); continue
            if log.startswith("Program ") and (log.endswith(" success") or " failed" in log):
                pid = log.split(" ", 2)[1]
                if stack and stack[-1] == pid: stack.pop()
                continue
            if not (log.startswith("Program data: ") and stack and stack[-1] in {PUMP_ID, AMM_ID}):
                continue
            try:
                ev = decode_event(log.split(": ", 1)[1])
            except Exception:
                # only the creation tx's CreateEvent fails with the checked-in IDL (newer layout); not an S0 data issue
                if "Create" in str(ns["events"].get(__import__("base64").b64decode(log.split(": ", 1)[1])[:8])): cfail += 1
                else: bad += 1
                continue
            if not ev: continue
            n, o = ev
            if n == "TradeEvent" and o.get("mint") == mint:
                vset.add("curve")
                if o["is_buy"]: buy += o["sol_amount"]
                else: sells += 1
            elif n == "BuyEvent" and o.get("pool") == pool:
                vset.add("pool"); buy += o["quote_amount_in_with_lp_fee"]
            elif n == "SellEvent" and base64.b64decode(log.split(": ", 1)[1])[120:152] == POOLRAW:
                # pool at a fixed offset (SellEvent: 14 u64/i64 fields precede it); a sell of ANOTHER pool in a
                # rotation tx ("sell A, buy this coin") is not this coin's sell, matching the SQL's pool join
                vset.add("pool"); sells += 1
            elif n in SPECIAL:
                special += 1; vset.add({"DepositEvent": "pool", "WithdrawEvent": "pool", "CreatePoolEvent": "pool_create",
                                        "CompletePumpAmmMigrationEvent": "migration"}[n])
        if not vset:
            continue  # S0 never sees transactions without these events
        rows.append(dict(sig=sig, ts=x["blockTime"], slot=x["slot"], txi=x["transactionIndex"], buy=buy, sells=sells,
                         special=special, nven=len(vset), bad=bad, cfail=cfail))
    g = pd.DataFrame(rows).sort_values(["slot", "txi", "sig"]).reset_index(drop=True)
    g = g[(g.ts >= create_ts) & (g.ts < create_ts + 1470 * 60)].reset_index(drop=True)
    g["clock"] = g.ts.cummax()
    pre30 = []
    for i, r in g.iterrows():
        w = g.iloc[:i]
        pre30.append(int(w.loc[w.clock >= r.clock - 1800, "buy"].sum()))
    g["pre30"] = pre30
    g["eligible"] = ((g.ts >= create_ts + 1800) & (g.buy >= 4_000_000_000) & (g.pre30 < 4_000_000_000)
                     & (g.sells == 0) & (g.special == 0) & (g.nven == 1) & (g.ts == g.clock) & (g.bad == 0))
    e = g[g.eligible]
    first = e.iloc[0] if len(e) else None
    out.append(dict(mint=mint, role=c.role, creation_day=pd.to_datetime(create_ts, unit="s").date(),
                    n_decoded_txs=int(((g.buy > 0) | (g.sells > 0)).sum()),
                    n_bad_txs=int(((g.ts != g.clock) | (g.bad > 0)).sum()),
                    local_create_decode_fail=int(g.cfail.sum()),
                    n_large_mixed_txs=int(((g.ts >= create_ts + 1800) & (g.buy >= 4e9) & ((g.sells > 0) | (g.special > 0) | (g.nven != 1))).sum()),
                    n_eligible_txs=int(len(e)),
                    signal_time=(pd.to_datetime(first.ts, unit="s") if first is not None else None),
                    signal_slot=(int(first.slot) if first is not None else None),
                    signal_tx_index=(int(first.txi) if first is not None else None),
                    signal_signature=(first.sig if first is not None else None),
                    signal_buy_lamports=(int(first.buy) if first is not None else None),
                    signal_pre30_lamports=(int(first.pre30) if first is not None else None)))
df = pd.DataFrame(out)
df.to_csv(HERE / "sql" / "h1_s0_fixture_expected.csv", index=False)
print(df.drop(columns=["signal_signature"]).to_string(index=False))
