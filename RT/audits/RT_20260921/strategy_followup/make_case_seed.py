"""Rebuild the six exploratory A-week winner/failure pairs."""
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
src = ROOT / "RT/dq7/raw/F2_dev.csv"
out = Path(__file__).resolve().parent / "case_seed.csv"
d = pd.read_csv(src)
d = d[d.mint != "__SUMMARY__"].copy()
d["recovery_internal"] = d.b50 - .004
d["entry_venue"] = (d["flags"].astype(int) & 1024) > 0
wins = d.sort_values("recovery_internal", ascending=False).head(3)
fails = d[d.recovery_internal < .9]
used = set(); rows = []
for pair_id, (_, w) in enumerate(wins.iterrows(), 1):
    c = fails[(fails.cday == w.cday) & (fails.entry_venue == w.entry_venue)
              & ~fails.mint.isin(used)].copy()
    q = pd.concat([c, w.to_frame().T], ignore_index=True)
    distances = np.zeros(len(c))
    for col in ["n_buyers_pre", "entry_x_sol", "net_sol_pre"]:
        rank = q[col].rank(method="average", pct=True)
        distances += (rank.iloc[:-1].to_numpy() - rank.iloc[-1]) ** 2
    j = int(np.sqrt(distances).argmin())
    m = c.iloc[j]; dist = float(np.sqrt(distances[j])); used.add(m.mint)
    for role, x, other in [("winner", w, m), ("failure_control", m, w)]:
        rows.append({"role": role, "pair_id": pair_id, "mint": x.mint,
                     "cday": int(x.cday), "entry_venue": int(x.entry_venue),
                     "n_buyers_pre": x.n_buyers_pre, "entry_x_sol": x.entry_x_sol,
                     "net_sol_pre": x.net_sol_pre, "paired_mint": other.mint,
                     "distance": dist, "recovery_internal": x.recovery_internal,
                     "paired_recovery_internal": other.recovery_internal})
pd.DataFrame(rows).to_csv(out, index=False)
print(out)
