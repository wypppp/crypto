"""Check a downloaded Dune result of H1_S0_v1_<day>.sql against the local fixture, and summarize.
Usage: .venv/bin/python RT/case_timing/check_s0_output.py RT/case_timing/raw/dune/H1_S0_v1_2026-06-01.csv 2026-06-01"""
import sys
from datetime import date
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build_h1_s0 as B
path, arg = Path(sys.argv[1]), sys.argv[2]
d1, d2 = (date.fromisoformat(x) for x in (arg.split(":") if ":" in arg else (arg, arg)))
res = pd.read_csv(path)
exp = pd.read_csv(HERE / "sql" / "h1_s0_fixture_expected.csv").set_index("mint")
ok = True
for m in [m for d, ms in B.FIXTURES.items() if d1 <= d <= d2 for m in ms]:
    rows = res[res.mint == m]
    if len(rows) != 1:
        print(f"FIXTURE {m[:6]}: expected exactly one output row, got {len(rows)}"); ok = False; continue
    r, e = rows.iloc[0], exp.loc[m]
    for col in ["n_decoded_txs", "n_eligible_txs", "signal_signature", "signal_buy_lamports", "signal_pre30_lamports", "n_bad_txs"]:
        a, b = r.get(col), e.get(col)
        a = None if pd.isna(a) else (str(a) if col == "signal_signature" else int(float(a)))
        b = None if pd.isna(b) else (str(b) if col == "signal_signature" else int(float(b)))
        flag = "OK" if a == b else "DIFF"
        ok &= flag == "OK"
        print(f"FIXTURE {m[:6]} {col:22s} dune={a} local={b} {flag}")
s = res[res.row_type == "summary"].iloc[0]
print("\nSUMMARY", {k: s[k] for k in ["n_created", "n_sol_created", "n_sol_without_decoded_events", "n_triggered_coins",
                                     "n_triggered_mayhem", "n_eligible_txs", "n_decoded_txs", "n_bad_txs", "n_large_mixed_txs"]})
print("row types:", res.row_type.value_counts().to_dict())
if (res.row_type == "day_summary").any():
    print(res[res.row_type == "day_summary"][["cday", "n_created", "n_sol_created", "n_triggered_coins", "n_eligible_txs",
                                              "n_decoded_txs", "n_bad_txs", "n_large_mixed_txs"]].to_string(index=False))
c = res[res.row_type.str.startswith("candidate")].copy()
if len(c):
    c["age_h"] = (pd.to_datetime(c.signal_time) - pd.to_datetime(c.created_at)).dt.total_seconds() / 3600
    c["buy_sol"] = c.signal_buy_lamports / 1e9
    print("\ncandidates:", len(c), "| signal age h quantiles", c.age_h.quantile([0, .25, .5, .75, 1]).round(2).tolist(),
          "| buy SOL quantiles", c.buy_sol.quantile([0, .5, .9, 1]).round(2).tolist())
    print("venue:", c.signal_venue.value_counts().to_dict(), "| mayhem:", c.is_mayhem.value_counts().to_dict())
    print("pre30 SOL quantiles", (c.signal_pre30_lamports / 1e9).quantile([0, .5, .9, 1]).round(3).tolist())
    bad = c[(c.age_h < 0.5) | (c.age_h >= 24.5) | (c.signal_buy_lamports < 4e9) | (c.signal_pre30_lamports >= 4e9)]
    print("rule violations among candidates:", len(bad)); ok &= len(bad) == 0
print("\nFIXTURE+RULE CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
