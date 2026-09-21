"""Execute the rendered H1 S0 v1 SQL (transpiled Trino -> DuckDB) on MOCK Dune event tables built from the local
archives of the 06-01 case mints, and compare with the independent fixture (h1_s0_fixture_expected.csv).
Variant 'with_failed' adds the Pump/PumpAMM events found in FAILED transactions, to show the fixture rows detect
contamination if Dune's decoded tables were to include failed transactions. Tests SQL logic only, not Dune binding/cost."""
import base64, gzip, json, sys
from datetime import datetime, timezone
from pathlib import Path
import duckdb, pandas as pd, sqlglot
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from evt_decode import iter_events
ROOT = HERE.parents[1]
src = (ROOT / "audits/RT_20260921/ignition_review/decode_archived_events.py").read_text()
ns = {"__file__": str(ROOT / "audits/RT_20260921/ignition_review/decode_archived_events.py")}
exec(src.split("CASE_MINTS = set")[0], ns)
EVENTS, read_type, types, b58 = ns["events"], ns["read_type"], ns["types"], ns["b58"]
PUMP, AMM = ns["PUMP_ID"], ns["AMM_ID"]
import build_h1_s0 as B
from datetime import date
ARG = sys.argv[1] if len(sys.argv) > 1 else "2026-06-01"
if ":" in ARG:  # range mode: mock ALL case mints (out-of-range ones must be excluded by the cohort filter)
    D1, D2 = (date.fromisoformat(x) for x in ARG.split(":"))
    DAY = None
    MINTS = [m for ms in B.FIXTURES.values() for m in ms]
    IN_RANGE = [m for d, ms in B.FIXTURES.items() if D1 <= d <= D2 for m in ms]
else:
    DAY = date.fromisoformat(ARG); MINTS = B.FIXTURES[DAY]; IN_RANGE = MINTS
cc = pd.read_csv(HERE / "raw/creation_and_counts.csv").set_index("mint")

def rows_from(path, mint, failed=False):
    out = {k: [] for k in ["create", "trade", "buy", "sell", "deposit", "withdraw", "mig", "cpool"]}
    for line in gzip.open(path, "rt"):
        x = json.loads(line)
        sig = x["transaction"]["signatures"][0]
        bt = datetime.fromtimestamp(x["blockTime"], timezone.utc).replace(tzinfo=None)
        base = dict(evt_block_time=bt, evt_block_date=bt.date(), evt_block_slot=x["slot"], evt_tx_index=x["transactionIndex"], evt_tx_id=sig)
        if not failed and sig == cc.loc[mint, "first_sig"]:
            out["create"].append(dict(base, mint=mint, quote_mint=None, is_mayhem_mode=False))
        for ev in iter_events(x):
            name = ev["name"]; r = dict(base, evt_outer_executing_account=ev["outer"])
            if name == "TradeEvent":
                r.update(mint=ev["mint"], sol_amount=ev["sol_amount"], is_buy=ev["is_buy"], user=ev["user"]); out["trade"].append(r)
            elif name == "BuyEvent":
                r.update(pool=ev["pool"], user=ev["user"], quote_amount_in_with_lp_fee=ev["quote_amount_in_with_lp_fee"]); out["buy"].append(r)
            elif name == "SellEvent":
                r.update(pool=ev["pool"], user=ev["user"]); out["sell"].append(r)
            elif name in ("DepositEvent", "WithdrawEvent"):
                r.update(pool=ev["pool"]); out["deposit" if name == "DepositEvent" else "withdraw"].append(r)
            elif name == "CompletePumpAmmMigrationEvent":
                r.update(mint=ev["mint"]); out["mig"].append(r)
            elif name == "CreatePoolEvent":
                r.update(index=ev["index"], base_mint=ev["base_mint"], pool=ev["pool"]); out["cpool"].append(r)
    return out

def build(con, include_failed):
    tabs = {k: [] for k in ["create", "trade", "buy", "sell", "deposit", "withdraw", "mig", "cpool"]}
    for m in MINTS:
        paths = [(HERE / "raw" / f"full24h_{m}.jsonl.gz", False)]
        fp = HERE / "raw" / f"failed24h_{m}.jsonl.gz"
        if include_failed and fp.exists(): paths.append((fp, True))
        for p, f in paths:
            for k, v in rows_from(p, m, f).items(): tabs[k] += v
    names = {"create": "pump_evt_createevent", "trade": "pump_evt_tradeevent", "buy": "pump_amm_evt_buyevent",
             "sell": "pump_amm_evt_sellevent", "deposit": "pump_amm_evt_depositevent", "withdraw": "pump_amm_evt_withdrawevent",
             "mig": "pump_evt_completepumpammmigrationevent", "cpool": "pump_amm_evt_createpoolevent"}
    con.execute("CREATE SCHEMA IF NOT EXISTS pumpdotfun_solana")
    for k, t in names.items():
        evt = ["evt_block_time", "evt_block_date", "evt_block_slot", "evt_tx_index", "evt_tx_id", "evt_outer_executing_account"]
        extra = {"create": ["mint", "quote_mint", "is_mayhem_mode"], "trade": ["mint", "sol_amount", "is_buy", "user"],
                 "buy": ["pool", "user", "quote_amount_in_with_lp_fee"], "sell": ["pool", "user"], "deposit": ["pool"],
                 "withdraw": ["pool"], "mig": ["mint"], "cpool": ["pool", "base_mint", "index"]}[k]
        df = pd.DataFrame(tabs[k], columns=evt + extra)
        if k == "trade":
            df["isBuy"] = None; df["solAmount"] = None  # both spellings exist in Dune; old one null here
        con.register("tmp_df", df)
        typ = {"evt_block_time": "TIMESTAMP", "evt_block_date": "DATE", "evt_block_slot": "BIGINT", "evt_tx_index": "BIGINT",
               "sol_amount": "BIGINT", "quote_amount_in_with_lp_fee": "BIGINT", "is_buy": "BOOLEAN", "isBuy": "BOOLEAN",
               "solAmount": "BIGINT", "index": "INTEGER", "is_mayhem_mode": "BOOLEAN"}
        sel = ", ".join(f'CAST(CAST("{c}" AS VARCHAR) AS {typ.get(c, "VARCHAR")}) AS "{c}"' for c in df.columns)
        con.execute(f"CREATE OR REPLACE TABLE pumpdotfun_solana.{t} AS SELECT {sel} FROM tmp_df")
        con.unregister("tmp_df")
    return {k: len(v) for k, v in tabs.items()}

TAG = f"{DAY}" if DAY else f"{D1}_to_{D2}"
sql_trino = (HERE / "sql" / f"H1_S0_v1_{TAG}.sql").read_text()
sql_duck = sqlglot.transpile(sql_trino, read="trino", write="duckdb")[0]
(HERE / "sql" / f"_duckdb_H1_S0_v1_{TAG}.sql").write_text(sql_duck + "\n")
exp = pd.read_csv(HERE / "sql" / "h1_s0_fixture_expected.csv").set_index("mint")
for variant in ((False, True) if DAY == date(2026, 6, 1) else (False,)):
    con = duckdb.connect()
    counts = build(con, variant)
    res = con.execute(sql_duck).df()
    if not variant:
        res.to_csv(HERE / "sql" / f"_mock_S0_v1_{TAG}.csv", index=False)
    print(f"\n=== variant include_failed={variant}; mock rows {counts}")
    cols = ["mint", "row_type", "is_mayhem", "signal_time", "signal_slot", "signal_tx_index", "signal_buy_lamports",
            "signal_pre30_lamports", "n_created", "n_triggered_coins", "n_eligible_txs", "n_decoded_txs", "n_bad_txs", "n_large_mixed_txs"]
    print(res[cols].to_string(index=False))
    print("out-of-range case mints in output:", [m[:6] for m in MINTS if m not in IN_RANGE and (res.mint == m).any()])
    if "cday" in res: print(res[res.row_type.isin(["day_summary", "summary"])][["mint", "row_type", "cday", "n_created", "n_triggered_coins", "n_decoded_txs"]].to_string(index=False))
    for m in IN_RANGE:
        r = res[res.mint == m].iloc[0]; e = exp.loc[m]
        checks = {"n_decoded_txs": (int(r.n_decoded_txs), int(e.n_decoded_txs)), "n_eligible_txs": (int(r.n_eligible_txs), int(e.n_eligible_txs)),
                  "signal_signature": (r.signal_signature if pd.notna(r.signal_signature) else None,
                                       e.signal_signature if pd.notna(e.signal_signature) else None),
                  "signal_buy_lamports": (None if pd.isna(r.signal_buy_lamports) else int(r.signal_buy_lamports),
                                          None if pd.isna(e.signal_buy_lamports) else int(e.signal_buy_lamports)),
                  "signal_pre30_lamports": (None if pd.isna(r.signal_pre30_lamports) else int(r.signal_pre30_lamports),
                                            None if pd.isna(e.signal_pre30_lamports) else int(e.signal_pre30_lamports))}
        print(m[:6], {k: ("OK" if a == b else f"DIFF sql={a} fixture={b}") for k, (a, b) in checks.items()})
