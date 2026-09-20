"""DQ-1F 开发分析：按 DQ1F_卡.md 第五节执行，冻结前 3 个"筛选 + 退出"组合。"""
import hashlib, itertools, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
RAW, OUT = HERE / "raw", HERE / "results"
OUT.mkdir(exist_ok=True)
SOL = 69.76
RULES = [f"x{s}_{d}" for s in ("30", "50", "70", "NA") for d in ("1h", "24h")]
R_FEATS = ["entry_x_sol", "n_trades_pre", "n_buyers_pre", "trades_per_sol", "bot_share_pre", "net_sol_pre",
           "sell_share_pre", "secs_since_last", "pre_peak_pm"]
L_FEATS = ["dev_prior_launches", "dev_prior_grads", "dev_net_share", "dev_sold_sol", "top1_share", "top5_share",
           "slot0_buyers", "slot0_share", "early10_buyers", "mayhem", "entry_on_pool"]
CONC = ["top1_share", "top5_share", "slot0_share"]
QS = [0.2, 0.4, 0.6, 0.8]
MIN_N, MIN_W = 140, 3
S = {}

raw = pd.read_csv(RAW / "F1_dev.csv")
S["csv_sha256"] = hashlib.sha256((RAW / "F1_dev.csv").read_bytes()).hexdigest()
S["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
summ = raw[raw.mint == "__SUMMARY__"]
d = raw[raw.mint != "__SUMMARY__"].copy()
S["summary_row"] = {"sol_cohort": int(summ.cday.iloc[0]), "non_sol": int(summ["flags"].iloc[0])}
d["mayhem"] = ((d["flags"] & 128) > 0).astype(int)
d["entry_on_pool"] = ((d["flags"] & 1024) > 0).astype(int)
d["winner"] = d.mpi_t50 >= 10
S["active_rows"] = len(d); S["winners"] = int(d.winner.sum())
S["dup_mints"] = int(d.mint.duplicated().sum())

# ---- 1. 与 M2 交叉核对 ----
m2 = pd.read_csv(HERE.parent / "dq1m/raw/M2_full.csv")
b = lambda x, k: (x["flags"] & k) > 0
m2m = m2[~b(m2, 1) & ~b(m2, 2) & ~b(m2, 64)]
m2a = m2m[(m2m.entry_x_sol >= 30.5) | b(m2m, 1024)]
j = d.merge(m2a[["mint", "mpi_t50", "ms_60d", "hv_60d", "entry_x_sol"]], on="mint", how="outer", suffixes=("", "_m2"), indicator=True)
both = j[j._merge == "both"]
S["cross_check_m2"] = {
    "m2_active": len(m2a), "f1_active": len(d), "both": len(both),
    "only_f1": int((j._merge == "left_only").sum()), "only_m2": int((j._merge == "right_only").sum()),
    "mpi_t50_max_abs_diff": float((both.mpi_t50 - both.mpi_t50_m2).abs().max()),
    "mpi_t50_share_diff_gt_1e-4": float(((both.mpi_t50 - both.mpi_t50_m2).abs() > 1e-4).mean()),
    "ms_60d_share_diff_gt_1e-4": float(((both.ms_60d - both.ms_60d_m2).abs() > 1e-4).mean()),
    "entry_x_max_abs_diff": float((both.entry_x_sol - both.entry_x_sol_m2).abs().max()),
    "winners_m2_in_active": int((m2a.mpi_t50 >= 10).sum())}

# ---- 2. 集中度特征核查（事先规定：非 mayhem 中位数 ≥0.95 即排除 L5/L6/L8）----
nm = d[d.mayhem == 0]
S["concentration_check"] = {
    "mayhem": {c: d[d.mayhem == 1][c].quantile([.1, .5, .9]).round(4).to_dict() for c in CONC},
    "non_mayhem": {c: nm[c].quantile([.1, .5, .9]).round(4).to_dict() for c in CONC},
    "non_mayhem_share_top1_ge_0.99": round(float((nm.top1_share >= .99).mean()), 4)}
exclude_conc = nm.top1_share.median() >= 0.95
S["concentration_excluded"] = bool(exclude_conc)
L_USE = [f for f in L_FEATS if not (exclude_conc and f in CONC)]

# ---- 3. 基准 ----
S["base_active"] = {r: round(float(d[r].mean()), 4) for r in RULES + ["mpi_t50"]}
S["base_active_excl_top1"] = {r: round(float(d[r].drop(d[r].idxmax()).mean()), 4) for r in RULES}

# ---- 4. 候选搜索 ----
def conditions(feats):
    out = []
    for f in feats:
        vals = d[f].to_numpy(dtype=float)
        cuts = sorted(set(np.nanquantile(vals, QS).round(6)))
        for c in cuts:
            for op in (">=", "<="):
                mask = (vals >= c) if op == ">=" else (vals <= c)
                mask = np.where(np.isnan(vals), False, mask)
                out.append((f"{f} {op} {c:g}", mask))
    return out

R_C, L_C = conditions(R_FEATS), conditions(L_USE)
RV = {r: d[r].to_numpy(dtype=float) for r in RULES}
W = d.winner.to_numpy()
seen, rows, tried = set(), [], 0
def evaluate(label, mask):
    global tried
    key = hashlib.md5(np.packbits(mask).tobytes()).hexdigest()
    if key in seen: return
    seen.add(key)
    n, w = int(mask.sum()), int(W[mask].sum())
    tried += len(RULES)
    if n < MIN_N or w < MIN_W: return
    for r in RULES:
        v = RV[r][mask]
        rows.append({"filter": label, "rule": r, "n": n, "per_day": round(n / 7, 1), "winners": w,
                     "mean": v.mean(), "robust": (v.sum() - v.max()) / (n - 1)})
for lab, m in R_C + L_C: evaluate(lab, m)
for (la, ma), (lb, mb) in itertools.product(R_C, L_C): evaluate(f"{la} AND {lb}", ma & mb)
res = pd.DataFrame(rows).sort_values("robust", ascending=False).reset_index(drop=True)
S["search"] = {"conditions_R": len(R_C), "conditions_L": len(L_C), "unique_selections": len(seen),
               "filter_rule_evaluations_tried": tried, "passing_min_size": len(res),
               "passing_mean_gt_1": int((res["mean"] > 1).sum()), "passing_robust_gt_1": int((res.robust > 1).sum())}
res.head(40).round(4).to_csv(OUT / "dev_top40.csv", index=False)

# ---- 冻结前 3 ----
top3 = res.head(3)
frozen = []
for i, row in top3.iterrows():
    # 重建掩码
    parts = row["filter"].split(" AND ")
    mask = np.ones(len(d), bool)
    for p in parts:
        f, op, c = p.split(" "); vals = d[f].to_numpy(dtype=float); c = float(c)
        mask &= np.where(np.isnan(vals), False, (vals >= c) if op == ">=" else (vals <= c))
    g = d[mask]; r = row["rule"]
    cap = g.entry_x_sol * (np.sqrt(1.05) - 1) * SOL
    frozen.append({
        "rank": i + 1, "primary": i == 0, "filter": row["filter"], "rule": r,
        "dev_n": int(row["n"]), "dev_per_day": row["per_day"], "dev_winners": int(row["winners"]),
        "dev_mean": round(float(row["mean"]), 4), "dev_robust": round(float(row["robust"]), 4),
        "dev_base_active_same_rule": S["base_active"][r],
        "turnover_mean_hold_hours": round(float(g[r + "_dt"].mean() / 3600), 2),
        "turnover_median_hold_hours": round(float(g[r + "_dt"].median() / 3600), 2),
        "capacity_entry_usd_p10_p50_p90": [round(float(x), 1) for x in cap.quantile([.1, .5, .9])],
        "gross_usd_per_year_at_60usd_each": round(float(((g[r] - 1) * 60).sum() / 7 * 365), 0),
        "winners_rule_vs_t50": [[round(float(a), 2), round(float(b_), 2)] for a, b_ in zip(g[g.winner][r], g[g.winner].mpi_t50)],
    })
S["frozen_candidates"] = frozen
blob = json.dumps({"card": "DQ1F_卡.md", "frozen_at": pd.Timestamp.utcnow().isoformat(), "candidates": frozen,
                   "excluded_features": CONC if exclude_conc else [], "dev_csv_sha256": S["csv_sha256"],
                   "script_sha256": S["script_sha256"]}, ensure_ascii=False, indent=1, default=str)
(OUT / "frozen_candidates.json").write_text(blob, encoding="utf-8")
S["frozen_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
(OUT / "dev_summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(S, ensure_ascii=False, indent=1, default=str))
print("\n=== 前 15 名 ===")
print(res.head(15).round(4).to_string())
