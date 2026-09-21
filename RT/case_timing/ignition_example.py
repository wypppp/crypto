"""Illustration only (selected winners): follow the first post-entry buy >= 4 SOL with delay D.
Mid-price multiples from the reserve state; no fees/impact; 50% trailing stop on mid-price; horizon = fetched 24h."""
import pandas as pd
HERE = __import__("pathlib").Path(__file__).parent
tr = pd.read_csv(HERE / "trades.csv")
rows = []
for m, g in tr[tr.price_post.notna()].groupby("mint"):
    g = g.sort_values(["slot", "tx_index"])
    ign = g[(g.kind == "buy") & (g.t_rel_entry > 0) & (g.sol >= 4)]
    if ign.empty:
        rows.append(dict(mint=m[:6], ignition_h=None)); continue
    t0 = ign.t_rel_entry.iloc[0]
    for d in (0, 30, 120, 300):
        before = g[g.t_rel_entry <= t0 + d]
        p_in = before.pm.iloc[-1]
        after = g[g.t_rel_entry > t0 + d]
        runmax, exit_pm = p_in, None
        for pm in after.pm:
            runmax = max(runmax, pm)
            if pm <= 0.5 * runmax:
                exit_pm = pm; break
        rows.append(dict(mint=m[:6], ignition_h=round(t0 / 3600, 3), ign_sol=round(ign.sol.iloc[0], 2), delay_s=d,
                         pm_at_entry=round(p_in, 3), max_pm_24h=round(max(after.pm.max(), p_in) if len(after) else p_in, 3),
                         stop50_exit_over_entry=(round(exit_pm / p_in, 3) if exit_pm else None),
                         last_pm_over_entry_if_no_stop=(round(after.pm.iloc[-1] / p_in, 3) if (exit_pm is None and len(after)) else None)))
out = pd.DataFrame(rows); out.to_csv(HERE / "ignition_example.csv", index=False); print(out.to_string(index=False))
