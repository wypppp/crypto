"""Read-only audit of the frozen RT snapshot; does not import project analysis code.

Run: /home/ancillary/.venv/bin/python audits/RT_20260920/independent_checks.py
Scope: arithmetic, stored-hash correspondence, panel-level reconstruction and
targeted semantic counterexamples. This is not a new market validation cohort.
"""
from pathlib import Path
import hashlib
import json
import platform
import statistics
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RT = HERE / "snapshot/RT"
OUT = HERE / "checks"
OUT.mkdir(exist_ok=True)


def read_csv(path):
    d = pd.read_csv(RT / path, low_memory=False)
    if "mint" in d:
        d = d[d.mint != "__SUMMARY__"].copy()
    return d


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                     default=lambda x: x.item() if hasattr(x, "item") else str(x)))


checks = {"environment": {"python": platform.python_version(),
                         "numpy": np.__version__, "pandas": pd.__version__}}

# Check existing manifests against captured bytes. A hash match does not prove
# that its registration preceded viewing the results.
hc = []
fr = json.loads((RT / "dq8/results/FREEZE_manifest.json").read_text())
for path, expected in fr["sha256"].items():
    p = RT / "dq8" / path
    actual = sha(p) if p.exists() else None
    hc.append({"path": str(p.relative_to(RT)), "expected": expected,
               "actual": actual, "match": actual == expected})
v = json.loads((RT / "dq1f/results/val_result.json").read_text())
for key, path in [("val_csv_sha256", "dq1f/raw/F1_val.csv"),
                  ("frozen_sha256", "dq1f/results/frozen_candidates_v1.1.json"),
                  ("script_sha256", "dq1f/analyze_f1_val.py")]:
    actual = sha(RT / path)
    hc.append({"path": path, "expected": v[key], "actual": actual,
               "match": actual == v[key]})
c = json.loads((RT / "dq2b/contrast.json").read_text())
for key, path in [("results_csv_sha256", "dq2/runs/20260915T013907Z-full/results.csv"),
                  ("card_sha256", "dq2b/DQ2b_卡.md"),
                  ("script_sha256", "dq2b/features_contrast.py")]:
    hc.append({"path": path, "expected": c["inputs"][key], "actual": sha(RT / path),
               "match": sha(RT / path) == c["inputs"][key]})
checks["hash_correspondence"] = hc

# CEX feature screen: recompute every frozen categorical gate from the CSV.
c = read_csv("dq2b/features.csv")
sizes = c.groupby("group").size().to_dict()
bools = ["Launchpad", "Launchpool", "HODLer Airdrop", "Megadrop", "Pre-Market",
         "Seed Tag", "Monitoring Tag", "无渠道关键词"]
screens = []
for f in bools + ["X3_lead", "X4_btc90"]:
    vals = [True] if f in bools else list(c[f].dropna().unique())
    for val in vals:
        z = c[c[f] == val]
        nw = int((z.group == "W").sum())
        screens.append({"feature": f, "value": str(val), "n": len(z), "winners": nw,
                        "pass": nw / sizes["W"] >= .5 and len(z) / len(c) <= .3})
checks["dq2b"] = {"groups": sizes, "screens": screens,
                   "winner_t50_median": c.loc[c.group == "W", "mpi_T50"].median(),
                   "passes_selection_gate": any(x["pass"] for x in screens)}

# M1/M2: fixed population, rather than rerunning either author script.
m1, m2 = (read_csv("dq1m/raw/" + x) for x in ["M1_full.csv", "M2_full.csv"])
main1 = m1[(m1["flags"] & (1 | 2 | 64)) == 0]
main2 = m2[(m2["flags"] & (1 | 2 | 64)) == 0]
pair = main1.set_index("mint")[["mpi_t50"]].join(
    main2.set_index("mint")[["mpi_t50"]], lsuffix="_old", rsuffix="_new", how="inner")
w1, w2 = main1[main1.mpi_t50 >= 10], main2[main2.mpi_t50 >= 10]
checks["dq1m"] = {
    "raw_n": [len(m1), len(m2)], "main_n": [len(main1), len(main2)],
    "mean": [main1.mpi_t50.mean(), main2.mpi_t50.mean()],
    "winner_n": [len(w1), len(w2)], "overlap_winners": len(set(w1.mint) & set(w2.mint)),
    "winner_days_v2": w2.cday.nunique(),
    "moves_from_below_half_to_at_least_0_9": int(((pair.mpi_t50_old < .5) & (pair.mpi_t50_new >= .9)).sum()),
    "winner_entry_capacity_median_usd_under_report_formula":
        float((w2.entry_x_sol * (np.sqrt(1.05) - 1) * 69.76).median()),
    "winner_entry_capacity_at_least_1400": int((w2.entry_x_sol * (np.sqrt(1.05) - 1) * 69.76 >= 1400).sum()),
}

b = read_csv("dq1f/raw/F1_val.csv")
candidates = [("v1_primary", (b.net_sol_pre >= 5.34452) & (b.slot0_buyers <= 0), "x50_24h"),
              ("v1_1_primary", (b.entry_x_sol >= 59.1866) & (b.dev_prior_launches <= 11), "x50_1h"),
              ("descriptive_third", (b.entry_x_sol <= 33.4564) & (b.dev_prior_launches <= 0), "x30_24h")]
checks["dq1f"] = []
for name, mask, rule in candidates:
    x = sorted(b.loc[mask, rule].tolist())
    checks["dq1f"].append({"candidate": name, "n": len(x), "mean": statistics.mean(x),
        "drop_largest1": statistics.mean(x[:-1]), "drop_largest2": statistics.mean(x[:-2]),
        "base_mean": b[rule].mean(), "passes_mean_gt_1": statistics.mean(x) > 1,
        "mean_after_extra_0_004_return_cost": statistics.mean(x) - .004})

# Exit-family means and paired gains, separately in the three frozen populations.
a = read_csv("dq7/raw/F2_dev.csv")
rules = ["b50", "ins50_h70", "c30_i02", "c30_i05", "c100_i02", "c100_i05", "tp2_r70",
         "tp2_rNA", "tp3_r70", "tp3_rNA", "tp2_c30_i02_r70", "tp2_c100_i05_r70"]
pops = {"P0": np.ones(len(a), bool), "P1": a.net_sol_pre >= 5.3445,
        "P2": (a.entry_x_sol >= 59.1866) & (a.dev_prior_launches <= 11)}
checks["dq7"] = {pn: {"n": int(np.sum(mask)), "means_after_cost":
    {rule: float(a.loc[mask, rule].mean() - .004) for rule in rules},
    "mean_gain_over_b50": {rule: float((a.loc[mask, rule] - a.loc[mask, "b50"]).mean()) for rule in rules[1:]}}
    for pn, mask in pops.items()}

# New independent panel walk; retain source-level limitations: the panel and old
# CSV share event sources, and differ in both ordering and (B only) horizon.
panel_metrics = {}
for week, old, oldret, oldms in [("A", a, "b50", "ms_30d"), ("B", b, "x50_24h", "ms_60d")]:
    panel = read_csv(f"dq8/raw/F3_dev{week}.csv")
    rows = []
    for mint, g in panel.groupby("mint", sort=False):
        g = g.sort_values("iv")
        exit_value = None
        for r in g.itertuples():
            if pd.notna(r.t50_dt) or pd.notna(r.dead_dt):
                take_stop = pd.notna(r.t50_dt) and (pd.isna(r.dead_dt) or r.t50_dt <= r.dead_dt)
                exit_value = r.t50_v if take_stop else r.dead_sm
                break
        if exit_value is None:
            vals = g.l_sm.dropna()
            exit_value = vals.iloc[-1] if len(vals) else np.nan
        rows.append({"mint": mint, "panel_return": exit_value,
                     "panel_ms30": g.f_maxpm.max()})
    z = old.merge(pd.DataFrame(rows), on="mint", how="outer", indicator=True)
    both = z[z._merge == "both"].copy()
    both["delta"] = both.panel_return - both[oldret]
    bad = both[both.delta.abs() > 1e-5]
    panel_metrics[week] = {"old_n": len(old), "panel_n": len(rows),
        "common": len(both), "mismatches": len(bad), "mean_difference_common": both.delta.mean(),
        "max_abs_diff": both.delta.abs().max(), "old_only": int((z._merge == "left_only").sum()),
        "panel_only": int((z._merge == "right_only").sum()),
        "old_mean_common": both[oldret].mean(), "panel_mean_common": both.panel_return.mean()}
    bad.to_csv(OUT / f"panel_{week}_mismatches.csv", index=False)
    # Isolate original F96's filter from a genuine 30d label reconstructed from
    # interval maxima. Mixing old return with corrected label is intentional
    # here to isolate label choice; report a separate panel-return calculation.
    proxy = (both[oldms] >= 10) & (both.peak_dt <= 30*86400)
    actual = both.panel_ms30 >= 10
    panel_metrics[week]["label_check"] = {
        "old_winners_common": int((both[oldms] >= 10).sum()),
        "peak_time_filter_n": int(proxy.sum()), "panel_30d_winners_n": int(actual.sum()),
        "missed_by_peak_filter": int((actual & ~proxy).sum()),
        "proxy_only": int((proxy & ~actual).sum()),
        "mean_old_return_peak_filter": both.loc[proxy, oldret].mean() - .004,
        "mean_old_return_true30_label": both.loc[actual, oldret].mean() - .004,
        "mean_panel_return_true30_label": both.loc[actual, "panel_return"].mean() - .004,
        "mean_panel_ms30_among_winners": both.loc[actual, "panel_ms30"].mean()}
    both.loc[actual ^ proxy].to_csv(OUT / f"label_{week}_differences.csv", index=False)
checks["panel_reconstruction"] = panel_metrics

# F93/F96 metrics are descriptive, not a new confirmation experiment.
checks["diagnostic_buckets"] = {}
for name, d, ret, ms in [("A", a, "b50", "ms_30d"), ("B", b, "x50_24h", "ms_60d")]:
    r = d[ret] - .004
    w = d[ms] >= 10
    groups = {"winner": w, "up_nonwinner": ~w & (r > 1.1),
              "stopped_nonwinner": ~w & (r >= .5) & (r < .9),
              "deep_nonwinner": ~w & (r < .5), "flat_nonwinner": ~w & (r >= .9) & (r <= 1.1)}
    q = d.net_sol_pre
    buckets = {k: {"n": int(m.sum()), "contribution": float((r[m]-1).sum()/len(d))}
               for k, m in groups.items()}
    layers = {}
    for label, quantile in [("top20", .8), ("top5", .95)]:
        threshold = q.quantile(quantile)
        m = q >= threshold
        layers[label] = {"threshold": threshold, "n": int(m.sum()), "share": float(m.mean()),
                         "mean": r[m].mean(), "ties_at_threshold": int((q == threshold).sum())}
    checks["diagnostic_buckets"][name] = {"n": len(d), "mean": r.mean(), "buckets": buckets,
        "sum_check": 1 + sum(x["contribution"] for x in buckets.values()), "layers": layers}

# Stored DQ8 gate recomputation: validates report->decision mapping, not all DP math.
stored = json.loads((RT / "dq8/results/final_dq8a.json").read_text())
checks["dq8_gate_only"] = {}
for space in ["S1", "S2"]:
    ab = stored["results"][space]["A->B"]["P0"]
    ba = stored["results"][space]["B->A"]["P0"]
    conds = [ab["policy_delta"] >= .03, ab["delta_boot_p10"] > 0, ba["policy_delta"] > 0]
    checks["dq8_gate_only"][space] = {"conditions": conds, "pass": all(conds),
        "borderline": not all(conds) and (.015 <= ab["policy_delta"] < .03 or sum(conds) == 2),
        "values": [ab["policy_delta"], ab["delta_boot_p10"], ba["policy_delta"]]}

dump("independent_results.json", checks)
print(json.dumps({"output": str(OUT / "independent_results.json"),
    "hash_matches": [sum(x["match"] for x in hc), len(hc)],
    "panel_reconstruction": panel_metrics, "dq1f": checks["dq1f"],
    "dq2b_pass": checks["dq2b"]["passes_selection_gate"]}, ensure_ascii=False, indent=2))
