"""DQ-16 descriptive (not a pre-registered criterion): event-based trade SOL per (wallet, mint) vs truth.
truth = sum over truth trade txs of (F + fee_paid + tip): the wallet's SOL-equivalent change in the trade txs excluding
tx fees and Jito tips; dune = sum of event user-side SOL (reversed base=wSOL pools use base amounts).
The gap is in-transaction non-event flows (token-account rent, terminal/bot fees paid inside the swap tx, other legs)."""
import pandas as pd, sys
from decimal import Decimal as Dec
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.argv = [sys.argv[0]]
import importlib.util
spec = importlib.util.spec_from_file_location("rc", HERE / "reconcile.py"); rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)
tt = pd.read_csv(HERE / "results/truth_tx.csv"); tk = pd.read_csv(HERE / "results/truth_tok.csv")
tk = tk.merge(tt[["k", "sig", "ok", "pump", "amm", "F", "fee_paid", "tip"]], on=["k", "sig"])
tr = tk[tk.ok & (tk.pump | tk.amm) & (tk.pre_raw != tk.post_raw)]
truth = tr.assign(x=tr.F + tr.fee_paid + tr.tip).groupby(["k", "mint"]).x.sum()
q1 = pd.read_csv(HERE / "raw/dune/Q1.csv", dtype=str); q1["k"] = pd.to_numeric(q1.k)
ev = q1[q1.kind == "ev"].copy(); pm = rc.pool_mints(sorted(ev[ev.v1 == "amm"].key.unique()))
ev["mint"] = [key if v == "curve" else pm[key][0] for key, v in zip(ev.key, ev.v1)]
ev["rev"] = [v == "amm" and pm[key][1] for key, v in zip(ev.key, ev.v1)]
ev["sol"] = [float(rc.D(b) - rc.D(s)) if r else float(rc.D(x)) for r, b, s, x in zip(ev.rev, ev.v3, ev.v4, ev.v5)]
dune = ev.groupby(["k", "mint"]).sol.sum()
j = pd.concat([truth.rename("truth"), dune.rename("dune")], axis=1).dropna()
j["gap"] = j.truth - j.dune; j["vol"] = j.dune.abs()
j.to_csv(HERE / "results/trade_level_sol.csv")
rel = (j.gap.abs() / j.vol.replace(0, float("nan")))
print("cells", len(j), " |gap|<=1000 lamports:", int((j.gap.abs() <= 1000).sum()),
      " rel<=0.1%:", int((rel <= 0.001).sum()), " rel<=1%:", int((rel <= 0.01).sum()))
print("total |gap| / total |dune SOL|:", round(j.gap.abs().sum() / j.vol.sum(), 5), "  signed gap / vol:", round(j.gap.sum() / j.vol.sum(), 5))
w = j.groupby("k")[["gap", "vol"]].sum(); w["r"] = w.gap / w.vol
print("per-wallet signed gap/vol quantiles:", w.r.quantile([0, .25, .5, .75, 1]).round(4).to_dict())
