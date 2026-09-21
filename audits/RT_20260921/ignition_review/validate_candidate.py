"""Boundary and prefix checks for the single candidate event rule."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parents[3]
CASE = ROOT / "RT/case_timing"
OUT = Path(__file__).parent

def first_candidate(g, create_ts, entry_ts):
    g = g.sort_values(["slot", "tx_index"])
    prior = []
    for ix, q in g.iterrows():
        if q.kind != "buy":
            continue
        prior = [(seq, bt, sol) for seq, bt, sol in prior if q.block_time - bt <= 1800]
        # prior contains only earlier chain-ordered rows; CSV index labels do
        # not encode execution order (e.g. after concatenation or shuffling).
        pre30 = sum(sol for seq, bt, sol in prior)
        if (q.block_time - create_ts >= 1800 and 0 <= q.block_time - entry_ts < 86400
                and q.sol >= 4 and pre30 < 4):
            return ix, q.block_time, q.sol, pre30
        prior.append((ix, q.block_time, q.sol))
    return None

tr = pd.read_csv(CASE / "trades.csv")
cc = pd.read_csv(CASE / "raw/creation_and_counts.csv")
prefix_rows = []
for _, c in cc.iterrows():
    g = tr[(tr.mint == c.mint) & tr.price_post.notna()].copy()
    full = first_candidate(g, c.create_ts, c.create_ts + 1800)
    if full is None:
        prefix_rows.append({"mint": c.mint, "full": None, "after_delete": None, "unchanged": True})
        continue
    hit_ix = full[0]
    ordered = g.sort_values(["slot", "tx_index"])
    truncated = ordered.iloc[:ordered.index.get_loc(hit_ix) + 1]
    short = first_candidate(truncated, c.create_ts, c.create_ts + 1800)
    prefix_rows.append({"mint": c.mint, "full": full[1:], "after_delete": short[1:] if short else None,
                        "unchanged": full[1:] == short[1:]})
pd.DataFrame(prefix_rows).to_csv(OUT / "candidate_prefix_check.csv", index=False)

def synth(rows):
    return pd.DataFrame(rows, columns=["block_time", "slot", "tx_index", "kind", "sol"])

tests = []
def check(name, got, expected):
    tests.append({"case": name, "got": got, "expected": expected, "pass": got == expected})

# Current amount is inclusive at exactly 4 SOL.
g = synth([(1800, 1, 1, "buy", 4.0)])
check("current exactly 4 qualifies", first_candidate(g, 0, 0) is not None, True)
g = synth([(1800, 1, 1, "buy", 3.999999)])
check("current below 4 does not qualify", first_candidate(g, 0, 0) is not None, False)
# A buy exactly 1,800 seconds earlier is in the window; one second earlier is out.
g = synth([(0, 1, 1, "buy", 4.0), (1800, 2, 1, "buy", 4.0)])
check("prior exactly 1800s included", first_candidate(g, 0, 0), None)
g = synth([(-1, 1, 1, "buy", 4.0), (1800, 2, 1, "buy", 4.0)])
check("prior at 1801s excluded", first_candidate(g, 0, 0)[2], 4.0)
# Same second: tx_index determines whether the earlier buy contributes.
g = synth([(1800, 2, 1, "buy", 3.0), (1800, 2, 2, "buy", 4.0)])
check("same-second earlier tx counts", first_candidate(g, 0, 0)[3], 3.0)
g = synth([(1800, 2, 1, "buy", 4.0), (1800, 2, 2, "buy", 3.0)])
check("same-second later tx is not future info", first_candidate(g, 0, 0)[3], 0.0)
# Physical CSV row order must not change the ordered prefix.
g = synth([(1800, 2, 2, "buy", 4.0), (1800, 2, 1, "buy", 3.0)])
check("unsorted CSV follows chain order", first_candidate(g, 0, 0)[3], 3.0)
pd.DataFrame(tests).to_csv(OUT / "candidate_boundary_tests.csv", index=False)
assert all(x["unchanged"] for x in prefix_rows)
assert all(x["pass"] for x in tests)

f3 = pd.read_csv(ROOT / "RT/dq8/raw/F3_devA.csv")
mints = set(cc.mint)
rows = []
for _, r in f3[f3.mint.isin(mints) & f3.f_pm.notna() & (f3.last_dt <= 86400)].iterrows():
    g = tr[(tr.mint == r.mint) & tr.price_post.notna() & (tr.t_rel_entry <= r.last_dt)]
    q = g.sort_values(["t_rel_entry", "slot", "tx_index"]).iloc[-1]
    rows.append({"mint": r.mint, "iv": r.iv, "f3_pm": r.f_pm, "trade_pm": q.pm,
                 "abs_diff": abs(r.f_pm - q.pm)})
f3check = pd.DataFrame(rows)
f3check.to_csv(OUT / "f3_endpoint_check.csv", index=False)
assert len(f3check) == 42 and (f3check.abs_diff <= 2.4e-6).all()

print("prefix unchanged:", all(x["unchanged"] for x in prefix_rows), "of", len(prefix_rows))
print(pd.DataFrame(tests).to_string(index=False))
print("F3 endpoints:", len(f3check), "max abs diff:", f3check.abs_diff.max(),
      "within 2.4e-6:", int((f3check.abs_diff <= 2.4e-6).sum()))
