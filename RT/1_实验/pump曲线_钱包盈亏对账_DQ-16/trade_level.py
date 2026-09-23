"""DQ-16 descriptive (not a pre-registered criterion): event-based trade SOL per wallet vs truth (each tx once).
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
# r3.1 (third review): a tx that changes several mints must be counted once, so compare per wallet, per distinct tx
txs = tr.drop_duplicates(["k", "sig"])
truth = txs.assign(x=txs.F + txs.fee_paid + txs.tip).groupby("k").x.sum()
q1 = pd.read_csv(HERE / "raw/dune/Q1.csv", dtype=str); q1["k"] = pd.to_numeric(q1.k)
ev = q1[q1.kind == "ev"].copy(); pm = rc.pool_mints(sorted(ev[ev.v1 == "amm"].key.unique()))
ev["rev"] = [v == "amm" and pm[key][1] for key, v in zip(ev.key, ev.v1)]
ev["sol"] = [float(rc.D(b) - rc.D(s)) if r else float(rc.D(x)) for r, b, s, x in zip(ev.rev, ev.v3, ev.v4, ev.v5)]
ev["vol"] = ev.sol.abs()
d = ev.groupby("k")[["sol", "vol"]].sum()
w = pd.concat([truth.rename("truth"), d], axis=1).fillna(0)
w["gap"] = w.truth - w.sol; w["r"] = w.gap / w.vol.replace(0, float("nan"))
w["multi_mint_tx"] = tr.groupby(["k", "sig"]).mint.nunique().gt(1).groupby(level=0).sum()
w.to_csv(HERE / "results/trade_level_sol.csv")
print("wallets", len(w), " |gap|/vol <= 0.1%:", int((w.r.abs() <= 0.001).sum()), " <= 1%:", int((w.r.abs() <= 0.01).sum()))
print("sum |gap| / sum vol:", round(w.gap.abs().sum() / w.vol.sum(), 5), "  signed:", round(w.gap.sum() / w.vol.sum(), 5))
print(w.reindex(w.gap.abs().sort_values(ascending=False).index).head(6)[["gap", "vol", "r", "multi_mint_tx"]].assign(gap=lambda x: x.gap / 1e9, vol=lambda x: x.vol / 1e9).round(4).to_string())
print("top-3 share of sum |gap|:", round(w.gap.abs().sort_values(ascending=False).head(3).sum() / w.gap.abs().sum(), 3))
