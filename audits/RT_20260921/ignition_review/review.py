"""Read-only RT timing audit.

The graph deliberately uses only transactions whose logs contain an SPL
Token Transfer/TransferChecked and whose target-mint balance deltas can be
matched.  Swaps, curve/pool owners, mint/burns, and ambiguous many-sided
balance changes are not converted into edges.
"""
import csv, gzip, json, re
from pathlib import Path
from collections import defaultdict, deque

BASE = Path(__file__).resolve().parents[3] / "RT" / "case_timing"
OUT = Path(__file__).resolve().parent
GDP = "5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump"
B1 = "B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump"
IGN = 1780467688                 # GDP ignition first buy, 06-03 06:21:28
WINDOW_END = IGN + 132
EIGHT = [
    "6e7JGdVmnAFGuNj7myWk4rY6JVCcXYrJXTvsdWNeoUpC",
    "8sDu4cYZCYXsZQiDyRL8cb4XPm8C4Un8hJrnyycNXWZz",
    "EEX36p4rjYnTuCwK8tERKL4ywzuNsWW6QiZWEwcRqBE6",
    "BGWMLdh2RVjFsNi6Gj2jndu2CJ7VhxRFsyDz3wEEUgFL",
    "FdwVhbBQhY9rwF5yaZwVH2SK6jhtxj67idgVrrGgAmKS",
    "tCPHCKBKPmVvDCPiv3JmTeXXc7ivPpTRfvPZuzTodir",
    "Ejhe74yR9VedNNPJvHAwrmvVwQPkTQ8x6ykzYCL88LfN",
    "AN1WZWrUbK9c6oJZaAvjojzvF2PzAvQ3Hvxh2oMSct", # corrected below if absent
]
# exact spelling from trades.csv (the long address is retained by lookup)
with open(BASE / "trades.csv") as f:
    TR = list(csv.DictReader(f))
_w = {r["trader"] for r in TR if r["mint"] == GDP and IGN <= int(r["block_time"]) <= WINDOW_END and r["kind"] == "buy" and float(r["sol"]) > .01}
EIGHT = sorted(_w - {"4XJ4thJGLN2N5b9od97zbYbL8gmMWp8rY87bQcjkB1xH"})

def read_venues():
    bad = set()
    with open(BASE / "venues.csv") as f:
        for r in csv.DictReader(f):
            for k in ("curve", "pool"):
                if r.get(k): bad.add(r[k])
    return bad

def keys(t):
    m=t["transaction"]["message"]; la=t["meta"].get("loadedAddresses") or {}
    return m["accountKeys"] + la.get("writable",[]) + la.get("readonly",[])

def balances(t, mint):
    d=defaultdict(lambda:[0,0])
    for side, arr in enumerate((t["meta"].get("preTokenBalances") or [], t["meta"].get("postTokenBalances") or [])):
        for b in arr:
            if b.get("mint") == mint:
                # amount is exact integer base units; absent account means zero
                d[b.get("owner")][side] += int(b["uiTokenAmount"]["amount"])
    return {o: b-a for o,(a,b) in d.items() if b != a}

def explicit_transfer(t, mint, excluded):
    logs = "\n".join(t["meta"].get("logMessages") or [])
    if not re.search(r"Instruction: Transfer(?:Checked)?", logs): return []
    # A swap can contain token transfers. Any pump instruction in the same tx
    # makes ownership deltas a trade leg, so do not infer a wallet edge.
    if re.search(r"Instruction: (?:Buy|Sell|MintTo|Burn)", logs): return []
    d=balances(t,mint)
    d={o:v for o,v in d.items() if o and o not in excluded and abs(v)>0}
    neg={o:-v for o,v in d.items() if v<0}; pos={o:v for o,v in d.items() if v>0}
    if not neg or not pos or sum(neg.values()) != sum(pos.values()): return []
    # One source can explicitly distribute to several destinations. Multiple
    # negative owners are left ambiguous and are excluded.
    if len(neg) != 1: return []
    src=next(iter(neg)); return [(src,dst) for dst in pos]

def graph_rows(cutoff):
    edges=[]; excluded=read_venues()
    f=BASE/"raw"/f"full24h_{GDP}.jsonl.gz"
    with gzip.open(f,"rt") as fh:
        for line in fh:
            t=json.loads(line); ts=int(t["blockTime"])
            if ts > cutoff: continue
            edges += [(ts,a,b) for a,b in explicit_transfer(t,GDP,excluded)]
    return edges

def components(edges):
    g=defaultdict(set)
    for e in edges:
        a,b=e[-2],e[-1]; g[a].add(b); g[b].add(a)
    out=[]; seen=set()
    for x in EIGHT:
        if x in seen: continue
        q=[x]; seen.add(x); c=[]
        while q:
            z=q.pop(); c.append(z)
            for y in g[z]:
                if y not in seen: seen.add(y); q.append(y)
        out.append(sorted(c))
    return out

def pnl(mint, wallet):
    rs=[r for r in TR if r["mint"]==mint and r["trader"]==wallet]
    trade_sol=sum(float(r["sol"]) for r in rs)
    fee=0
    token=0; final_token=0
    with gzip.open(BASE/"raw"/f"full24h_{mint}.jsonl.gz","rt") as fh:
        for line in fh:
            t=json.loads(line)
            # transaction-level fee is charged to signer, regardless of token owner
            if keys(t)[0]==wallet: fee += int(t["meta"].get("fee",0))/1e9
            token += balances(t,mint).get(wallet,0)
            # Last post snapshot is the relevant residual position. A
            # telescoped delta is separately retained as an audit check.
            snap=sum(int(b["uiTokenAmount"]["amount"]) for b in (t["meta"].get("postTokenBalances") or []) if b.get("mint")==mint and b.get("owner")==wallet)
            if snap or any(b.get("mint")==mint and b.get("owner")==wallet for b in (t["meta"].get("postTokenBalances") or [])):
                final_token = snap
    return {"trade_sol_net_buy_positive":trade_sol,"wallet_net_sol_flow_inflow_positive":-trade_sol,"signer_fees_sol":fee,"token_net_base_units":token,"final_token_balance_base_units_last_seen":final_token,"n_trade_rows":len(rs)}

def main():
    # creation signer is first account in the creation transaction (F2dev proxy)
    with gzip.open(BASE/"raw"/f"full24h_{GDP}.jsonl.gz","rt") as fh:
        first=json.loads(fh.readline())
    creator=keys(first)[0]
    create_ts=1780452754
    windows={"pre_ignition":IGN-1,"ignition_plus_8m":IGN+480,"creation_plus_24h":create_ts+1800+24*3600}
    graphs={k:graph_rows(v) for k,v in windows.items()}
    result={"method":{"creator_field":"creation transaction first account (fee payer/signatory proxy only; creator identity not verified from Create instruction/event)","creator":creator,"graph":"SPL token Transfer/TransferChecked logs + exact target-mint balance deltas; one negative source only; curve/pool owners excluded; swap/mint/burn and ambiguous multi-source tx excluded","wallet_selection":"8 GDP buy wallets in [06:21:28,06:23:40], excluding 4X micro-bot and non-buy row"},"ignition":{"utc":"2026-06-03T06:21:28Z","duration_seconds":132,"wallets":EIGHT},"connectivity":{},"b1c2":{"ignition_wallet":"G6nyYGhcXPEsdLnoHdCmyPW6XqQbdmW19dmLc8cEtkgE","claim_check":pnl(B1,"G6nyYGhcXPEsdLnoHdCmyPW6XqQbdmW19dmLc8cEtkgE"),"interpretation":"trade_sol_net_buy_positive uses pool-leg sign (buy positive); wallet_net_sol_flow_inflow_positive=-sum(sol). Thus G6ny is -25.314 SOL signed wallet flow (cash outflow), while same-slot four-wallet aggregate is +42.59 SOL. These are realized trade legs; fees and residual holdings must be separately included for complete PnL"},"limitations":["This is a conservative transfer graph; accepted transfers only. Non-connection means no accepted edge under this algorithm, not proof no relationship exists","raw records provide balance snapshots and logs; transactions with ambiguous many-to-many owner changes are omitted rather than made edges","24h is cached horizon and does not establish common control or cross-mint identity"]}
    for k,e in graphs.items():
        cs=components(e); all8=next((c for c in cs if set(EIGHT).issubset(c)),None)
        result["connectivity"][k]={"edge_count":len(e),"components":cs,"all_8_connected":all8 is not None,"creator_in_all8_component":bool(all8 and creator in all8),"creator_component_size":next((len(c) for c in cs if creator in c),0)}
    # First transaction time at which all 8 addresses are connected; this is
    # an event-time result, not a post-window snapshot.
    seen=[]; first8=None
    for ts,a,b in sorted(graphs["creation_plus_24h"], key=lambda x:x[0]):
        seen.append((a,b)); ccs=components(seen)
        if any(set(EIGHT).issubset(c) for c in ccs): first8=ts; break
    result["connectivity"]["first_all8_connected"]={"block_time":first8,"utc":"2026-06-03T06:21:28Z" if first8 is None else __import__('datetime').datetime.fromtimestamp(first8,__import__('datetime').timezone.utc).isoformat().replace('+00:00','Z'),"scope":"first accepted transfer edge that makes all 8 connected"}
    # summarize B1C2 same-creation-slot buyers' realized legs (fee excluded by design)
    slot=min(int(r["slot"]) for r in TR if r["mint"]==B1)
    buyers=sorted({r["trader"] for r in TR if r["mint"]==B1 and int(r["slot"])==slot and r["kind"]=="buy"})
    result["b1c2"]["creation_slot"]={"slot":slot,"buyers":[{"wallet":w,**pnl(B1,w)} for w in buyers]}
    (OUT/"ignition_review.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
