"""Independent Python implementation of H1 S1 for the seed events, from local Helius archives (CPI-decoded events).

Same economic contract as build_h1_s1.py (see its docstring), implemented separately:
states in chain order (slot, tx_index, outer_ix, inner_ix); entry = last state with ts <= signal + D; 0.5 SOL buy;
F2 valuation; 50% trailing stop executed at the last state with ts <= trigger_ts + 5 s; 24 h idle exit; 30 d horizon.
Archives only cover part of the 30 days (B1C2 to creation+24.5h, GDP to 150h, BUvu to 80h): an exit is reported only
if it is decided within coverage; otherwise status 'not_covered'."""
import gzip, json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from evt_decode import iter_events

COVER_H = {"B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump": 24.5, "5i1SVh2AwSFgdYuhFnM2K74n6MxBjxjWKcP3vHAcpump": 150,
           "BUvuChjfCJxfUyCRMNWtm2W5ygTc7vV7mK4N22tGpump": 80}


def load_states(mint, pool):
    files = [HERE / "raw" / f"full24h_{mint}.jsonl.gz", HERE / "raw" / f"ext_{mint}.jsonl.gz"]
    curve, pool_ev = [], []
    for f in files:
        if not f.exists(): continue
        for line in gzip.open(f, "rt"):
            x = json.loads(line)
            for e in iter_events(x):
                key = (x["slot"], x["transactionIndex"], e["oix"], e["iix"])
                if e["name"] == "TradeEvent" and e["mint"] == mint:
                    curve.append(dict(key=key, ts=x["blockTime"], venue=0, x=e["virtual_sol_reserves"] / 1e9,
                                      y=e["virtual_token_reserves"] / 1e6, xr=e["real_sol_reserves"] / 1e9,
                                      fee=e["fee_basis_points"] + e["creator_fee_basis_points"]))
                elif e["name"] in ("BuyEvent", "SellEvent") and e["pool"] == pool:
                    if e["name"] == "BuyEvent":
                        dq, db = e["quote_amount_in_with_lp_fee"], -e["base_amount_out"]
                    else:
                        dq, db = -(e["quote_amount_out"] - e["lp_fee"]), e["base_amount_in"]
                    pool_ev.append(dict(key=key, ts=x["blockTime"], q=e["pool_quote_token_reserves"], b=e["pool_base_token_reserves"],
                                        dq=dq, db=db, fee=e["lp_fee_basis_points"] + e["protocol_fee_basis_points"] + e["coin_creator_fee_basis_points"]))
    pool_ev.sort(key=lambda r: r["key"])
    ps = []
    for i, r in enumerate(pool_ev):
        nq, nb = (pool_ev[i + 1]["q"], pool_ev[i + 1]["b"]) if i + 1 < len(pool_ev) else (r["q"] + r["dq"], r["b"] + r["db"])
        ps.append(dict(key=r["key"], ts=r["ts"], venue=1, x=nq / 1e9, y=nb / 1e6, xr=None, fee=r["fee"]))
    st = sorted([s for s in curve + ps if s["x"] > 0 and s["y"] > 0], key=lambda r: r["key"])
    return st


def sm_of(s, tok, efee):
    x, y, f = s["x"], s["y"], s["fee"]
    if s["venue"] == 0:
        if y <= tok: return None
        v = (x * y / (y - tok) - x) * (1 - f / 1e4)
        v = min(v, s["xr"] + 0.5 * (1 - efee / 1e4))
    else:
        v = (x - x * y / (y + tok)) * (1 - f / 1e4)
    return v / 0.5


def simulate(st, sig_ts, sig_key, d, cover_end):
    st = [s for s in st if s["ts"] >= sig_ts]
    t_entry = sig_ts + d; t_end = t_entry + 30 * 86400
    ent = [i for i, s in enumerate(st) if s["ts"] <= t_entry][-1]
    E = st[ent]; ex, ey, efee = E["x"], E["y"], E["fee"]
    sig = [s for s in st if s["key"][:2] == sig_key][-1]
    tok = ey - ex * ey / (ex + 0.5 * (1 - efee / 1e4))
    runmax = 1.0
    for j in range(ent, len(st)):
        s = st[j]; pm = (s["x"] / s["y"]) / (ex / ey); runmax = max(runmax, pm)
        if j > ent and pm <= 0.5 * max(1.0, runmax):
            if s["ts"] + 5 > cover_end: return dict(status="not_covered")
            k = max(i for i in range(j, len(st)) if st[i]["ts"] <= s["ts"] + 5)
            return dict(status="ok", exit_kind="stop", exit_ts=s["ts"], recovery=sm_of(st[k], tok, efee), entry_venue=E["venue"],
                        entry_state_ts=E["ts"], entry_over_signal=(ex / ey) / (sig["x"] / sig["y"]), runmax_at_exit=runmax)
        nxt = st[j + 1]["ts"] if j + 1 < len(st) else None
        base = max(s["ts"], t_entry)
        if nxt is None and cover_end < t_end and cover_end - base <= 86400:
            return dict(status="not_covered")
        if (nxt if nxt is not None else t_end) - base > 86400:
            return dict(status="ok", exit_kind="idle", exit_ts=s["ts"], recovery=sm_of(s, tok, efee), entry_venue=E["venue"],
                        entry_state_ts=E["ts"], entry_over_signal=(ex / ey) / (sig["x"] / sig["y"]), runmax_at_exit=runmax)
    return dict(status="not_covered")


if __name__ == "__main__":
    cc = pd.read_csv(HERE / "raw/creation_and_counts.csv").set_index("mint")
    ven = pd.read_csv(HERE / "venues.csv").set_index("mint")
    ev = pd.read_csv(HERE / "h1_events_A.csv")
    ev = ev[ev.is_seed]
    rows = []
    for r in ev.itertuples():
        st = load_states(r.mint, ven.loc[r.mint, "pool"])
        sig_ts = int(pd.Timestamp(r.signal_time).timestamp())
        # coverage = what is actually on disk: full24h to creation+24.5h, ext (if present) to creation+COVER_H
        has_ext = (HERE / "raw" / f"ext_{r.mint}.jsonl.gz").exists()
        cover_end = int(cc.loc[r.mint, "create_ts"]) + int((COVER_H[r.mint] if has_ext else 24.5) * 3600)
        for d in (30, 120, 300):
            out = simulate(st, sig_ts, (int(r.signal_slot), int(r.signal_tx_index)), d, cover_end)
            rows.append(dict(mint=r.mint, d=d, **out))
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "sql" / "h1_s1_fixture_expected.csv", index=False)
    print(df.assign(mint=df.mint.str[:6]).to_string(index=False))
