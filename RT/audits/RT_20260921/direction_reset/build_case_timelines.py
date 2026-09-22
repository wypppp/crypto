#!/usr/bin/env python3
"""Build the six A-week case timelines from local F2/F3 extracts only."""
from pathlib import Path
import hashlib
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "audits/RT_20260921"
SEED = AUDIT / "strategy_followup/case_seed.csv"
F2 = ROOT / "RT/dq7/raw/F2_dev.csv"
F3 = ROOT / "RT/dq8/raw/F3_devA.csv"
OUT = AUDIT / "direction_reset"
TAUS = [0, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400, 259200, 604800]
F3_FIELDS = [
    "n", "first_dt", "first_after5_dt", "last_dt", "l_x", "l_y", "l_xr",
    "l_venue", "l_fee_bps", "l_sm", "e_x", "e_y", "e_xr", "e_venue",
    "e_fee_bps", "e_sm", "f_pm", "f_runmax", "f_maxpm", "f_newb30",
    "f_trades30", "f_trades30_prev", "f_buy30", "f_sell30", "f_nb_sell30",
    "f_ins_exit", "t50_dt", "t50_v", "t70_dt", "t70_v", "dead_dt",
    "dead_sm", "dead_rows", "trig_new", "bad_k0", "bad_early",
]

def finite(x):
    return pd.notna(x) and math.isfinite(float(x))

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    seed = pd.read_csv(SEED, dtype={"mint": str, "paired_mint": str})
    f2 = pd.read_csv(F2, low_memory=False).set_index("mint")
    f3 = pd.read_csv(F3, low_memory=False)
    wanted = set(seed.mint)
    f3 = f3[f3.mint.isin(wanted)].copy()
    assert len(seed) == len(wanted) == 6, "Expected the existing six-case selection"
    assert not f3.duplicated(["mint", "iv"]).any(), "Duplicate mint/interval"
    assert set(f3.mint) == wanted, "A selected case is absent from F3"
    pair = seed.set_index("mint")["pair_id"].to_dict()
    role = seed.set_index("mint")["role"].to_dict()
    rows = []
    for mint in seed.mint:
        g = f3[f3.mint.eq(mint)].set_index("iv")
        r2 = f2.loc[mint]
        for iv in range(12):
            if iv == 0:
                left, right, label = None, 0, "(-inf,0]"
            elif iv <= 10:
                left, right, label = TAUS[iv - 1], TAUS[iv], f"({TAUS[iv-1]},{TAUS[iv]}]"
            else:
                left, right, label = 604800, 2592000, "(604800,2592000]"
            out = {"mint": mint, "pair": int(pair[mint]), "role": role[mint], "cday": seed.set_index("mint").loc[mint, "cday"],
                   "iv": iv, "iv_left_sec": left, "iv_right_sec": right, "iv_label": label,
                   "source_f3": "F3_devA", "source_f2": "F2_dev"}
            if iv in g.index:
                rr = g.loc[iv]
                for c in F3_FIELDS:
                    out[c] = rr.get(c, pd.NA)
            else:
                for c in F3_FIELDS:
                    out[c] = pd.NA
            # F2 values are deliberately repeated as case-level cross-checks.
            for c in ["entry_x_sol", "n_buyers_pre", "net_sol_pre", "b50", "b50_dt", "peak_dt", "ms_30d", "hv_30d", "dd_dt", "dd_ins_exit", "dd_sm"]:
                out["f2_" + c] = r2.get(c, pd.NA)
            rows.append(out)
    timeline = pd.DataFrame(rows)
    timeline.to_csv(OUT / "case_timelines.csv", index=False)

    # Read cached new-position outcomes, not the original position's l_sm.
    # These are selected winners and existing SQL model outputs, not strategy evidence.
    delayed = []
    for mint in seed.loc[seed.role.eq("winner"), "mint"]:
        g = timeline[timeline.mint.eq(mint)]
        for k in (5, 6, 7):  # 2h / 4h / 8h after the original entry
            buy_time = TAUS[k] + 5
            triggers = []
            dead = []
            for rr in g.itertuples():
                if isinstance(rr.trig_new, str):
                    for item in rr.trig_new.split(";"):
                        origin, stop, dt, value = item.split(",")
                        if int(origin) == k and int(stop) == 50:
                            triggers.append((float(dt), float(value)))
                if isinstance(rr.dead_rows, str):
                    dead += [float(item.split(",")[0]) for item in rr.dead_rows.split(";")]
            assert triggers, f"No cached stop for {mint}, k={k}"
            dt, value = min(triggers)
            assert dt > buy_time and value >= 0
            later = g[g.iv.gt(k + 1)].first_dt.dropna().tolist()
            after5 = g.loc[g.iv.eq(k + 1), "first_after5_dt"].dropna().tolist()
            next_trade = min(after5 + later)
            assert next_trade - buy_time <= 86400, "Immediate inactivity exit needs separate valuation"
            assert not any(buy_time < d < dt for d in dead), "Earlier inactivity event needs separate valuation"
            delayed.append({
                "mint": mint, "pair": int(pair[mint]), "checkpoint_k": k,
                "decision_sec": TAUS[k], "execution_sec": buy_time,
                "position_SOL": .5, "stop_pct": 50,
                "exit_sec": dt, "cached_recovery": value,
                "recovery_after_fixed_deduction": value - .004,
                "scope": "Selected winner; cached F3 execution model, not independent execution verification",
            })
    pd.DataFrame(delayed).to_csv(OUT / "delayed_entry_examples.csv", index=False)

    # Summary uses the interval-end observation for the >=2 statement; it is not a first-touch time.
    sums = []
    inconsistencies = []
    for mint in seed.mint:
        g = timeline[timeline.mint.eq(mint)]
        observed = g[g.last_dt.notna()]
        hit = observed[observed.f_pm.ge(2)]
        r2 = f2.loc[mint]
        peakrow = observed.loc[observed.f_runmax.idxmax()] if observed.f_runmax.notna().any() else None
        sums.append({
            "mint": mint, "pair": int(pair[mint]), "role": role[mint], "cday": int(seed.set_index("mint").loc[mint, "cday"]),
            "entry_status": "observed_iv0" if int(g[g.iv.eq(0)].n.notna().iloc[0]) else "iv0_missing",
            "observed_iv": ",".join(str(int(x)) for x in observed.iv),
            "first_observed_interval_end_price_ge2_iv": (int(hit.iv.iloc[0]) if len(hit) else pd.NA),
            "first_observed_interval_end_price_ge2_right_sec": (hit.iv_right_sec.iloc[0] if len(hit) else pd.NA),
            "first_observed_interval_end_price_ge2_last_trade_sec": (hit.last_dt.iloc[0] if len(hit) else pd.NA),
            "entry_x_sol": r2.entry_x_sol, "n_buyers_pre": r2.n_buyers_pre,
            "net_sol_pre": r2.net_sol_pre,
            "path_highest_multiple": (peakrow.f_runmax if peakrow is not None else pd.NA),
            "path_peak_interval_end_sec": (peakrow.iv_right_sec if peakrow is not None else pd.NA),
            "f2_peak_dt_sec": r2.get("peak_dt", pd.NA), "b50_recovery": r2.get("b50", pd.NA),
            "b50_recovery_after_fixed_deduction": r2.get("b50", pd.NA) - .004,
            "b50_exit_sec": r2.get("b50_dt", pd.NA), "f2_dd_exit_sec": r2.get("dd_dt", pd.NA),
            "timeline_last_dt_sec": (observed.last_dt.max() if len(observed) else pd.NA),
            "checkpoint_note": "F3 checkpoints are interval-end/5s-state summaries; suitable only for coarse signal-time localization, not tick reconstruction.",
        })
        for c in ["cday"]:
            sv = seed.set_index("mint").loc[mint, c]; fv = f2.loc[mint, c] if c in f2 else pd.NA
            if pd.notna(fv) and sv != fv:
                inconsistencies.append(f"{mint}: seed {c}={sv} vs F2 {c}={fv}")
        f3t = observed[observed.t50_v.notna()]
        if len(f3t) and pd.notna(r2.b50) and abs(float(f3t.t50_v.iloc[0]) - float(r2.b50)) > 1e-5:
            inconsistencies.append(f"{mint}: F3 first t50_v={f3t.t50_v.iloc[0]} vs F2 b50={r2.b50}; t50 alone and b50 with inactivity exit are not identical contracts, so this difference is not automatically a source error.")
    pd.DataFrame(sums).to_csv(OUT / "case_timelines_summary.csv", index=False)
    (OUT / "source_inconsistencies.txt").write_text(
        "Local source checks only; these are data/definition discrepancies, not economic findings.\n" +
        ("\n".join(inconsistencies) if inconsistencies else "No seed/F2 cday or F3/F2 b50 mismatches found.") + "\n" +
        "F3 omits no-trade intervals by SQL definition; case_timelines.csv materializes those iv rows with missing values.\n" +
        "No exact creation UTC timestamps were found in the permitted case extracts; cday is retained as calendar-day scope only.\n"
    )
    manifest = {
        "inputs": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (SEED, F2, F3, Path(__file__).resolve())},
        "case_count": len(wanted), "materialized_interval_rows": len(timeline),
        "delayed_entry_examples": len(delayed),
        "scope": "Opened A development week only. No confirmation cohorts accessed.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

if __name__ == "__main__":
    main()
