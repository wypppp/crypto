"""DQ-1F 验证分析：按 DQ1F_卡.md v1.1 第六节判定主候选。写于验证数据到达之前，运行时不得修改。"""
import hashlib, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "results" / "frozen_candidates_v1.1.json"
CSV = HERE / "raw" / "F1_val.csv"
SOL = 69.76  # 与开发集相同的美元换算，仅用于容量描述

fr = json.loads(FROZEN.read_text(encoding="utf-8"))
raw = pd.read_csv(CSV)
summ = raw[raw.mint == "__SUMMARY__"]
d = raw[raw.mint != "__SUMMARY__"].copy()
d["mayhem"] = ((d["flags"] & 128) > 0).astype(int)
d["entry_on_pool"] = ((d["flags"] & 1024) > 0).astype(int)

def mask_of(flt):
    m = np.ones(len(d), bool)
    for part in flt.split(" AND "):
        f, op, c = part.split(" ")
        v = d[f].to_numpy(float); c = float(c)
        m &= np.where(np.isnan(v), False, (v >= c) if op == ">=" else (v <= c))
    return m

S = {"val_csv_sha256": hashlib.sha256(CSV.read_bytes()).hexdigest(),
     "frozen_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
     "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
     "summary_row": {"sol_cohort": int(summ.cday.iloc[0]), "non_sol": int(summ["flags"].iloc[0])} if len(summ) else None,
     "active_rows": len(d), "winners_t50": int((d.mpi_t50 >= 10).sum()), "dup_mints": int(d.mint.duplicated().sum())}
rules = [f"x{s}_{t}" for s in ("30", "50", "70", "NA") for t in ("1h", "24h")]
S["base_active"] = {r: round(float(d[r].mean()), 4) for r in rules + ["mpi_t50"]}

out = []
for c in fr["candidates"]:
    g = d[mask_of(c["filter"])]; r = c["rule"]; v = g[r].sort_values(ascending=False)
    n = len(v); tot = v.sum()
    rec = {"v1_0_rank": c["v1_0_rank"], "primary": c["primary"], "filter": c["filter"], "rule": r, "n": n,
           "winners_t50": int((g.mpi_t50 >= 10).sum()),
           "mean": round(tot / n, 4) if n else None,
           "excl_top1": round((tot - v.iloc[0]) / (n - 1), 4) if n > 1 else None,
           "excl_top2": round((tot - v.iloc[:2].sum()) / (n - 2), 4) if n > 2 else None,
           "median": round(float(v.median()), 4) if n else None,
           "base_active_same_rule": S["base_active"][r],
           "mean_hold_hours": round(float(g[r + "_dt"].mean() / 3600), 2) if n else None,
           "concurrent_capital_usd_at_60": round(float(n / 7 * g[r + "_dt"].mean() / 86400 * 60), 0) if n else None,
           "entry_capacity_usd_p10_p50_p90": [round(float(x), 1) for x in (g.entry_x_sol * (np.sqrt(1.05) - 1) * SOL).quantile([.1, .5, .9])] if n else None,
           "top3_by_rule": g.sort_values(r, ascending=False).head(3)[["mint", r, "mpi_t50", "ms_60d"]].round(2).values.tolist()}
    if c["primary"]:
        rec["criteria"] = {"c1_mean_gt_1": bool(n and rec["mean"] > 1.00),
                           "c2_excl_top1_ge_0.95": bool(n > 1 and rec["excl_top1"] >= 0.95),
                           "c3_n_ge_70": bool(n >= 70),
                           "c4_beats_active_pool": bool(n and rec["mean"] > rec["base_active_same_rule"])}
        rec["PASS"] = all(rec["criteria"].values())
    out.append(rec)
S["candidates"] = out
(HERE / "results" / "val_result.json").write_text(json.dumps(S, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(S, ensure_ascii=False, indent=1, default=str))
