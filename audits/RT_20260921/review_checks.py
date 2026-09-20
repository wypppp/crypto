"""Bounded follow-up audit. No paid queries, no new cohort, no author imports."""
from pathlib import Path
from datetime import datetime, timedelta
import json
import hashlib
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
raw = ROOT / "RT/dq1f/raw/F1_val.csv"
allrows = pd.read_csv(raw)
d = allrows[allrows.mint != "__SUMMARY__"].copy()
assert d.cday.between(1, 7).all()
mask = d.entry_x_sol.ge(59.1866) & d.dev_prior_launches.le(11)
excluded = d[d.entry_x_sol.ge(59.1866) & d.dev_prior_launches.gt(11)].copy()
base_n, base_sum = int(mask.sum()), float(d.loc[mask, "x50_1h"].sum())
top = excluded.sort_values("x50_1h", ascending=False)
oracle = (base_sum + top.x50_1h.cumsum()) / (base_n + pd.Series(range(1,len(top)+1),index=top.index))
cross = next((i+1 for i,v in enumerate(oracle) if v>1),None)
top.head(8).to_csv(HERE / "checks/top8_excluded_scenario.csv",index=False)

panel = pd.read_csv(ROOT / "audits/RT_20260920/checks/panel_B_mismatches.csv")
selected = panel[panel.mint.isin(d.loc[mask,"mint"])]
scenarios=[]
for hi in [13,15,20,30]:
    add = d.entry_x_sol.ge(59.1866) & d.dev_prior_launches.gt(11) & d.dev_prior_launches.le(hi) & d.cday.gt(1)
    scenarios.append({"upper_count":hi,"n_added":int(add.sum()),
                      "scenario_mean":float((base_sum+d.loc[add,"x50_1h"].sum())/(base_n+add.sum()))})

# Creation-time rolling history, even on cohort day 1, differs intraday.
created=datetime(2026,6,8,12)
history=[datetime(2026,5,9,6)]
fixed=sum(datetime(2026,5,9)<=t<created for t in history)
rolling=sum(created-timedelta(days=30)<=t<created for t in history)
assert (fixed,rolling)==(1,0)
# If the desired as-of is entry, creator can launch more during the next 30m.
old_count=11; removed_old=0; added_before_entry=1
assert old_count<=11 and old_count-removed_old+added_before_entry>11

catalog_path=ROOT/"RT/dq4/raw/dune_datasets_dynamic_bonding_curve.json"
catalog=json.loads(catalog_path.read_text())
schema=next(x for x in catalog if x["full_name"]=="meteora_solana.dynamic_bonding_curve_evt_evtswap2")
fields={f["name"]:f["type"] for f in schema["schema"]["fields"]}
assert fields["swap_result"]=="varchar" and "fee_basis_points" not in fields
(HERE/"checks/existing_meteora_schema.json").write_text(json.dumps(schema,ensure_ascii=False,indent=2))

# Logical counterexamples for policy thresholds / fee identification.
fees=[125]*60+[25]*40
assert sorted(fees)[50]==125
# Two latent structures have the same observed fee and same remainder.
fee_1_signature_plus_priority=5000+5000
fee_2_signatures_zero_priority=2*5000
assert fee_1_signature_plus_priority==fee_2_signatures_zero_priority==10000

result={
 "data_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),
 "summary_rows":allrows.loc[allrows.mint=="__SUMMARY__",["mint","cday","flags"]].to_dict("records"),
 "real_rows":len(d),"real_rows_invalid_cday":int((~d.cday.between(1,7)).sum()),
 "creator": {"main_n":base_n,"saved_mean":base_sum/base_n,"scenarios":scenarios,
   "excluded_n":len(excluded),"oracle_min_add_to_cross1":cross,
   "oracle_mean_add8":float(oracle.iloc[7]),"oracle_mean_add8_is_actual_fix":False,
   "first_day_counterexample":{"created":str(created),"old_event":str(history[0]),"fixed":fixed,"rolling30":rolling},
   "entry_asof_counterexample":{"creation_count":11,"new_launch_before_entry":1,"entry_count":12}},
 "ordering": {"b50_mismatch_selected_n":len(selected),"b50_delta_sum":float(selected.delta.sum()),
   "b50_delta_over_old_candidate_n":float(selected.delta.sum()/base_n),
   "candidate_old_exit_rules_differ_n":int((d.loc[mask,"x50_1h"]-d.loc[mask,"x50_24h"]).abs().gt(1e-5).sum()),
   "direct_x50_1h_reconstruction":False},
 "existing_catalog":{"path":str(catalog_path.relative_to(ROOT)),"sha256":hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
   "table":schema["full_name"],"has_fee_basis_points":False,"swap_result_type":"varchar"},
 "counterexamples":{"venue_100_pool_median_bps":125,"venue_lowfee_pool_count":40,
   "fee_10000_lamports_can_be_single_signature_plus5000_priority_or_two_signature_no_priority":True,
   "small_error_0_004_can_flip_1_003":1.003-.004,
   "large_nonnegative_omitted_cost_0_03_keeps_0_974_below1":.974-.03}
}
(HERE/"checks/results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
cached = []
for p in sorted((ROOT/"RT/dq1m/raw/rpc_verify").glob("scan_failed_*_*.json")):
    obj=json.loads(p.read_text())
    tx=obj.get("result")
    if not isinstance(tx,dict) or "meta" not in tx: continue
    meta=tx["meta"]; transaction=tx["transaction"]
    cached.append({"path":str(p.relative_to(ROOT)),"signature":transaction["signatures"][0],
                   "block_time":tx["blockTime"],"fee_lamports":meta.get("fee"),
                   "required_signatures":transaction["message"].get("header",{}).get("numRequiredSignatures"),
                   "failed":meta.get("err") is not None,
                   "emitted_program_data":any(x.startswith("Program data:") for x in meta.get("logMessages",[])),
                   "pump_invoked":any(x.startswith("Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke") for x in meta.get("logMessages",[]))})
result["existing_failed_rpc"]={"n":len(cached),"with_fee":sum(x["fee_lamports"] is not None for x in cached),
    "with_required_signatures":sum(x["required_signatures"] is not None for x in cached),
    "all_failed":all(x["failed"] for x in cached),
    "with_program_data":sum(x["emitted_program_data"] for x in cached),
    "pump_actually_invoked":sum(x["pump_invoked"] for x in cached),
    "population_failure_rate_identified":False}
(HERE/"checks/cached_failed_rpc.json").write_text(json.dumps(cached,ensure_ascii=False,indent=2))
(HERE/"checks/results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
