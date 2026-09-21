"""Fetch FAILED transactions (creation .. +24.5h) for the 06-01 case mints and decode Pump/PumpAMM events in their logs.
Purpose: size the check of whether Dune decoded event tables include events from failed transactions (F60 had n=1)."""
import sys, json, gzip
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import helius as H
# reuse the reviewer's IDL decoder (functions only; the module body processes archives)
src = (ROOT / "audits/RT_20260921/ignition_review/decode_archived_events.py").read_text()
ns = {"__file__": str(ROOT / "audits/RT_20260921/ignition_review/decode_archived_events.py")}
exec(src.split("CASE_MINTS = set")[0], ns)
decode_event, PUMP_ID, AMM_ID = ns["decode_event"], ns["PUMP_ID"], ns["AMM_ID"]

cc = pd.read_csv(HERE / "raw/creation_and_counts.csv").set_index("mint")
venues = pd.read_csv(HERE / "venues.csv").set_index("mint")
rows = []
for mint in ["B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump", "YxUstMyYDyqPNz78auhYfhdUKrBQgg7uctnKNDEpump"]:
    c = int(cc.loc[mint, "create_ts"])
    f = HERE / "raw" / f"failed24h_{mint}.jsonl.gz"
    if not f.exists():
        out, token = [], None
        while True:
            opts = {"transactionDetails": "full", "sortOrder": "asc", "limit": 100, "maxSupportedTransactionVersion": 0,
                    "encoding": "json", "filters": {"blockTime": {"gte": c, "lt": c + 1800 + 86400}, "status": "failed"}}
            if token: opts["paginationToken"] = token
            H.CALLS["gtfa_full"] += 1
            r = H.rpc("getTransactionsForAddress", [mint, opts])
            out += r.get("data", []); token = r.get("paginationToken")
            if not token or not r.get("data"): break
        with gzip.open(f, "wt") as g:
            for t in out: g.write(json.dumps(t) + "\n")
    pool = venues.loc[mint, "pool"]
    for line in gzip.open(f, "rt"):
        x = json.loads(line); stack = []; evs = []
        for log in x["meta"].get("logMessages") or []:
            if log.startswith("Program ") and " invoke [" in log:
                stack.append(log.split(" ", 2)[1]); continue
            if log.startswith("Program ") and (log.endswith(" success") or " failed" in log):
                pid = log.split(" ", 2)[1]
                if stack and stack[-1] == pid: stack.pop()
                continue
            if log.startswith("Program data: ") and stack and stack[-1] in {PUMP_ID, AMM_ID}:
                try: ev = decode_event(log.split(": ", 1)[1])
                except Exception: ev = ("decode_fail", {})
                if ev:
                    n, o = ev
                    if (n == "TradeEvent" and o.get("mint") == mint) or (n == "BuyEvent" and o.get("pool") == pool) or n == "SellEvent":
                        evs.append(n + (":buy" if o.get("is_buy") else "") + (":%d" % (o.get("sol_amount") or o.get("quote_amount_in_with_lp_fee") or 0)))
        rows.append(dict(mint=mint, sig=x["transaction"]["signatures"][0], slot=x["slot"], ts=x["blockTime"],
                         err=json.dumps(x["meta"]["err"]), n_events=len(evs), events=";".join(evs)))
df = pd.DataFrame(rows); df.to_csv(HERE / "failed_tx_events.csv", index=False)
print(H.CALLS)
print(df.groupby("mint").agg(failed=("sig", "size"), with_events=("n_events", lambda s: (s > 0).sum())))
print(df[df.n_events > 0].head(8)[["mint", "sig", "err", "events"]].to_string())
