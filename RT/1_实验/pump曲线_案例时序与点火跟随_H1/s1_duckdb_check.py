"""Execute the H1 S1 SQL (rendered for the 3 seed events, transpiled Trino -> DuckDB) on mock Dune tables built from
local seed archives, and compare with the independent Python fixture (h1_s1_fixture_expected.csv, status ok rows)."""
import gzip, json, sys
from datetime import datetime, timezone
from pathlib import Path
import duckdb, pandas as pd, sqlglot
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from evt_decode import iter_events, PUMP
import build_h1_s1 as S1

ev = pd.read_csv(HERE / "h1_events_A.csv"); ev = ev[ev.is_seed].reset_index(drop=True)
ven = pd.read_csv(HERE / "venues.csv").set_index("mint")
T = {k: [] for k in ["trade", "buy", "sell", "cpool"]}
for m in ev.mint:
    pool = ven.loc[m, "pool"]
    for f in [HERE / "raw" / f"full24h_{m}.jsonl.gz", HERE / "raw" / f"ext_{m}.jsonl.gz"]:
        if not f.exists(): continue
        for line in gzip.open(f, "rt"):
            x = json.loads(line)
            bt = datetime.fromtimestamp(x["blockTime"], timezone.utc).replace(tzinfo=None)
            for e in iter_events(x):
                b = dict(evt_block_time=bt, evt_block_date=bt.date(), evt_block_slot=x["slot"], evt_tx_index=x["transactionIndex"],
                         evt_outer_instruction_index=e["oix"], evt_inner_instruction_index=e["iix"], evt_outer_executing_account=e["outer"])
                n = e["name"]
                if n == "TradeEvent" and e["mint"] == m:
                    T["trade"].append(dict(b, mint=m, virtual_sol_reserves=e["virtual_sol_reserves"], virtual_token_reserves=e["virtual_token_reserves"],
                                           real_sol_reserves=e["real_sol_reserves"], fee_basis_points=e["fee_basis_points"],
                                           creator_fee_basis_points=e["creator_fee_basis_points"]))
                elif n in ("BuyEvent", "SellEvent") and e["pool"] == pool:
                    r = dict(b, pool=pool, pool_quote_token_reserves=e["pool_quote_token_reserves"], pool_base_token_reserves=e["pool_base_token_reserves"],
                             lp_fee_basis_points=e["lp_fee_basis_points"], protocol_fee_basis_points=e["protocol_fee_basis_points"],
                             coin_creator_fee_basis_points=e["coin_creator_fee_basis_points"])
                    if n == "BuyEvent":
                        r.update(quote_amount_in_with_lp_fee=e["quote_amount_in_with_lp_fee"], base_amount_out=e["base_amount_out"]); T["buy"].append(r)
                    else:
                        r.update(quote_amount_out=e["quote_amount_out"], lp_fee=e["lp_fee"], base_amount_in=e["base_amount_in"]); T["sell"].append(r)
                elif n == "CreatePoolEvent" and e["base_mint"] == m:
                    T["cpool"].append(dict(b, base_mint=m, pool=e["pool"], index=e["index"], base_mint_decimals=6, quote_mint_decimals=9))
con = duckdb.connect(); con.execute("SET TimeZone = 'UTC'"); con.execute("CREATE SCHEMA pumpdotfun_solana")
names = {"trade": "pump_evt_tradeevent", "buy": "pump_amm_evt_buyevent", "sell": "pump_amm_evt_sellevent", "cpool": "pump_amm_evt_createpoolevent"}
for k, t in names.items():
    df = pd.DataFrame(T[k])
    if k == "trade":
        for c in ["virtualSolReserves", "virtualTokenReserves", "buyback_fee_basis_points"]: df[c] = None
    con.register("tmp", df)
    typ = {"evt_block_time": "TIMESTAMPTZ", "evt_block_date": "DATE"}  # Dune: timestamp with time zone (UTC)
    sel = ", ".join(f'CAST("{c}" AS {typ[c]}) AS "{c}"' if c in typ else (f'CAST("{c}" AS DOUBLE) AS "{c}"' if c in ("virtualSolReserves", "virtualTokenReserves", "buyback_fee_basis_points") else f'"{c}"') for c in df.columns)
    con.execute(f"CREATE TABLE pumpdotfun_solana.{t} AS SELECT {sel} FROM tmp"); con.unregister("tmp")
    print(t, len(df))
sql = S1.render(ev)
duck = sqlglot.transpile(sql, read="trino", write="duckdb")[0]
(HERE / "sql" / "_duckdb_H1_S1_seeds.sql").write_text(duck + "\n")
res = con.execute(duck).df()
res.to_csv(HERE / "sql" / "_mock_S1_seeds.csv", index=False)
exp = pd.read_csv(HERE / "sql" / "h1_s1_fixture_expected.csv")
ok = True
for r in exp.itertuples():
    q = res[(res.mint == r.mint) & (res.d == r.d)]
    if r.status != "ok":
        print(r.mint[:6], r.d, "fixture not_covered; sql:", q[["exit_kind", "recovery"]].values.tolist()); continue
    q = q.iloc[0]
    checks = {"exit_kind": (q.exit_kind, r.exit_kind), "recovery": (round(q.recovery, 6), round(r.recovery, 6)),
              "exit_ts": (int(pd.Timestamp(q.exit_ts).timestamp()), int(r.exit_ts)),
              "entry_state_ts": (int(pd.Timestamp(q.entry_state_ts).timestamp()), int(r.entry_state_ts)),
              "entry_venue": (int(q.entry_venue), int(r.entry_venue)),
              "entry_over_signal": (round(q.entry_over_signal, 6), round(r.entry_over_signal, 6)),
              "runmax_at_exit": (round(q.runmax_at_exit, 6), round(r.runmax_at_exit, 6))}
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    ok &= not bad
    print(r.mint[:6], r.d, "OK" if not bad else f"DIFF {bad}")
print("S1 MOCK CHECK:", "PASS" if ok else "FAIL")
