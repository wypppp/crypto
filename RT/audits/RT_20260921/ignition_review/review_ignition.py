"""Read-only audit of six case-timing mints and F2 top1_share."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parents[3]
CASE = ROOT / "RT/case_timing"
OUT = Path(__file__).parent

tr = pd.read_csv(CASE / "trades.csv")
cc = pd.read_csv(CASE / "raw/creation_and_counts.csv")
f2 = pd.read_csv(ROOT / "RT/dq7/raw/F2_dev.csv")

case = cc[["role", "pair", "mint", "create_utc", "create_ts"]].copy()
case["first_ge4_utc"] = None
case["first_ge4_hours_after_entry"] = None
case["first_ge4_sol"] = None
case["first_ge4_sig"] = None
case["post_entry_max_buy_sol"] = None
case["post_entry_buy_count"] = None

for i, row in case.iterrows():
    g = tr[(tr.mint == row.mint) & tr.price_post.notna()].sort_values(["slot", "tx_index"])
    post = g[(g.kind == "buy") & (g.t_rel_entry > 0)]
    ge4 = post[post.sol >= 4]
    if len(ge4):
        q = ge4.iloc[0]
        case.loc[i, "first_ge4_utc"] = pd.to_datetime(q.block_time, unit="s", utc=True).strftime("%Y-%m-%d %H:%M:%S")
        case.loc[i, "first_ge4_hours_after_entry"] = q.t_rel_entry / 3600
        case.loc[i, "first_ge4_sol"] = q.sol
        case.loc[i, "first_ge4_sig"] = q.sig
    case.loc[i, "post_entry_max_buy_sol"] = post.sol.max() if len(post) else 0
    case.loc[i, "post_entry_buy_count"] = len(post)

case.to_csv(OUT / "first_ge4_by_case.csv", index=False)

# Single review candidate rule requested by the reviewer.  The rolling sum is
# over prior buys in the 1,800-second time window; row order keeps same-second
# transactions deterministic and excludes the current row itself.
case["pre30_buy_sum_sol"] = None
case["candidate_utc"] = None
case["candidate_hours_after_entry"] = None
case["candidate_sol"] = None
case["candidate_pre30_buy_sum_sol"] = None
for i, row in case.iterrows():
    g = tr[(tr.mint == row.mint) & tr.price_post.notna()].sort_values(["slot", "tx_index"]).copy()
    buys = []
    hit = None
    for _, q in g.iterrows():
        if q.kind == "buy":
            buys = [(bt, sol) for bt, sol in buys if q.block_time - bt <= 1800]
            pre30 = sum(sol for bt, sol in buys)
            age = q.block_time - row.create_ts
            if (q.t_rel_entry >= 0 and q.t_rel_entry <= 86400 and age >= 1800
                    and q.sol >= 4 and pre30 < 4 and hit is None):
                hit = q.copy()
                hit["pre30"] = pre30
            buys.append((q.block_time, q.sol))
    if hit is not None:
        case.loc[i, "candidate_utc"] = pd.to_datetime(hit.block_time, unit="s", utc=True).strftime("%Y-%m-%d %H:%M:%S")
        case.loc[i, "candidate_hours_after_entry"] = hit.t_rel_entry / 3600
        case.loc[i, "candidate_sol"] = hit.sol
        case.loc[i, "candidate_pre30_buy_sum_sol"] = hit.pre30
    # For transparency, record the pre-window sum for the mechanical first >=4.
    ge4 = g[(g.kind == "buy") & (g.t_rel_entry > 0) & (g.sol >= 4)]
    if len(ge4):
        q = ge4.iloc[0]
        prior = g[(g.kind == "buy") & (g.block_time >= q.block_time - 1800)
                  & (g.block_time < q.block_time)]
        case.loc[i, "pre30_buy_sum_sol"] = prior.sol.sum()
case.to_csv(OUT / "first_ge4_by_case.csv", index=False)

# F2's documented winner definition is ms_30d >= 10; drop its explicit summary row.
f = f2[f2.mint != "__SUMMARY__"].copy()
f = f[f.top1_share.notna()].copy()
f["winner_ms30_ge10"] = f.ms_30d >= 10
f["top1_bucket"] = pd.cut(f.top1_share, [-float("inf"), .1, .2, .3, .5, .7, float("inf")],
                           labels=["<=0.1", "0.1-0.2", "0.2-0.3", "0.3-0.5", "0.5-0.7", ">0.7"],
                           right=True, include_lowest=True)
bucket = f.groupby("top1_bucket", observed=False).agg(
    n=("mint", "size"), winners=("winner_ms30_ge10", "sum"), mean_b50=("b50", "mean")
).reset_index()
bucket["winner_rate_pct"] = bucket.winners / bucket.n * 100
bucket.to_csv(OUT / "top1_share_buckets.csv", index=False)

selected = f[f.top1_share > .7]
summary = pd.DataFrame([{
    "f2_rows_after_summary_and_nonnull_top1": len(f),
    "top1_gt_0_7_n": len(selected),
    "top1_gt_0_7_winners_ms30_ge10": int(selected.winner_ms30_ge10.sum()),
    "top1_gt_0_7_winner_rate_pct": selected.winner_ms30_ge10.mean() * 100,
    "winner_definition": "ms_30d >= 10.0",
    "top1_definition": "top1_net / pos_net_total, rounded to 4 decimals in F2 export",
}])
summary.to_csv(OUT / "top1_share_summary.csv", index=False)

print("FIRST_GE4")
print(case[["role", "pair", "mint", "first_ge4_utc", "first_ge4_hours_after_entry", "first_ge4_sol", "pre30_buy_sum_sol", "post_entry_max_buy_sol"]].to_string(index=False))
print("\nCANDIDATE_RULE")
print(case[["role", "pair", "mint", "candidate_utc", "candidate_hours_after_entry", "candidate_sol", "candidate_pre30_buy_sum_sol"]].to_string(index=False))
print("\nTOP1_SUMMARY")
print(summary.to_string(index=False))
print("\nTOP1_BUCKETS")
print(bucket.to_string(index=False))
print("\nF3_NOTE: no F3_dev input was read; 42 endpoint prices are therefore not independently rechecked by this audit.")
