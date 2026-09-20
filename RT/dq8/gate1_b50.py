"""DQ-8A Gate 1：A 周面板重建 b50 vs dq7/raw/F2_dev.csv；附工程自检（SQL 自检列、Python AMM 重放 vs SQL 回收）。不计算任何策略收益。"""
import json, numpy as np, pandas as pd
from pathlib import Path
H = Path(__file__).resolve().parent
P = pd.read_csv(H / "raw/F3_devA.csv", low_memory=False)
F2 = pd.read_csv(H.parent / "dq7/raw/F2_dev.csv", low_memory=False); F2 = F2[F2.mint != "__SUMMARY__"].copy()
for c in ["b50", "ms_30d"]: F2[c] = pd.to_numeric(F2[c], errors="coerce")
P = P.sort_values(["mint", "iv"]).reset_index(drop=True)
out = {"rows": len(P), "mints": int(P.mint.nunique()), "dup_mint_iv": int(P.duplicated(["mint", "iv"]).sum()),
       "bad_k0_true": int((P.bad_k0.astype(str) == "true").sum()), "bad_early_true": int((P.bad_early.astype(str) == "true").sum()),
       "mints_without_iv0": int(P.mint.nunique() - P.loc[P.iv == 0, "mint"].nunique())}

# ---- 面板重建 b50（与冒烟 pb 相同规则）----
ev = P[P.t50_dt.notna() | P.dead_dt.notna()].copy()
ev["v"] = np.where(ev.t50_dt.notna() & (ev.dead_dt.isna() | (ev.t50_dt <= ev.dead_dt)), ev.t50_v, ev.dead_sm)
first_ev = ev.groupby("mint").first()["v"]
last_sm = P[P.l_sm.notna()].groupby("mint").last()["l_sm"]
b50p = first_ev.reindex(last_sm.index.union(first_ev.index)).fillna(last_sm)
m = F2[["mint", "b50", "ms_30d"]].merge(b50p.rename("b50_panel").reset_index(), on="mint", how="outer", indicator=True)
both = m[m._merge == "both"].copy()
both["diff"] = both.b50_panel - both.b50
both["match"] = both["diff"].abs() <= 1e-5
out["merge"] = m._merge.value_counts().to_dict()
out["match_rate"] = round(float(both.match.mean()), 5)
out["mean_abs_diff_of_means"] = round(float(abs(both.b50_panel.mean() - both.b50.mean())), 6)
out["means"] = [round(float(both.b50.mean()), 6), round(float(both.b50_panel.mean()), 6)]
# 尾部标记：事后 ≥10×；F2 或面板 b50 位于前 1%
thr = max(both.b50.quantile(0.99), both.b50_panel.quantile(0.99))
mm = both[~both.match].copy()
mm["tail_ms10"] = mm.ms_30d >= 10
mm["top1pct"] = (mm.b50 >= thr) | (mm.b50_panel >= thr)
mm["contrib_to_mean_diff"] = mm["diff"] / len(both)
mm.sort_values("contrib_to_mean_diff", key=np.abs, ascending=False).to_csv(H / "results/gate1_mismatches.csv", index=False)
out["n_mismatch"] = len(mm); out["mismatch_tail_ms10"] = int(mm.tail_ms10.sum()); out["mismatch_top1pct"] = int(mm.top1pct.sum())
out["mismatch_abs_diff_quantiles"] = mm["diff"].abs().quantile([.5, .9, 1]).round(4).tolist() if len(mm) else []
out["only_in_F2"] = m.loc[m._merge == "left_only", "mint"].tolist()[:10]; out["only_in_panel"] = m.loc[m._merge == "right_only", "mint"].tolist()[:10]

# ---- Python AMM 重放 vs SQL 回收（工程自检）----
def sell(x, y, xr, v, fee, tok, feeb):
    x, y, xr, v, fee = map(np.asarray, (x, y, xr, v, fee))
    with np.errstate(invalid="ignore", divide="ignore"):
        curve = np.where(y > tok, (x * y / (y - tok) - x) * (1 - fee / 1e4), np.nan)
        curve = np.minimum(curve, xr + 0.5 * (1 - feeb / 1e4))
        pool = (x - x * y / (y + tok)) * (1 - fee / 1e4)
    return np.where(v == 0, curve, pool) / 0.5
e0 = P[P.iv == 0].set_index("mint")[["l_x", "l_y", "l_fee_bps"]]
e0["tok"] = e0.l_y - e0.l_x * e0.l_y / (e0.l_x + 0.5 * (1 - e0.l_fee_bps / 1e4))
Q = P.join(e0[["tok", "l_fee_bps"]].rename(columns={"l_fee_bps": "efee"}), on="mint")
chk = {}
for pre, col in (("l_", "l_sm"), ("e_", "e_sm")):
    q = Q[Q[col].notna() & Q[pre + "x"].notna()]
    py = sell(q[pre + "x"], q[pre + "y"], q[pre + "xr"].fillna(0), q[pre + "venue"], q[pre + "fee_bps"], q.tok, q.efee)
    rel = np.abs(py - q[col]) / np.maximum(np.abs(q[col]), 1e-9)
    chk[col] = {"n": len(q), "rel_err_p99": float(np.nanquantile(rel, .99)), "rel_err_max": float(np.nanmax(rel)), "n_rel_gt_1e-3": int((rel > 1e-3).sum())}
out["python_amm_vs_sql"] = chk
# trig_new 解析自检
tn = P.trig_new.dropna().str.split(";").explode().str.split(",", expand=True)
tn.columns = ["k", "s", "dt", "v"]
tn = tn.astype({"k": int, "s": int, "dt": int, "v": float})
TAUS = [0, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400, 259200, 604800]
out["trig_new"] = {"n": len(tn), "unvalued": int((tn.v < 0).sum()), "dt_before_buy": int((tn.dt <= tn.k.map(lambda k: TAUS[k])).sum()),
                   "s_values": sorted(tn.s.unique().tolist()), "k_range": [int(tn.k.min()), int(tn.k.max())]}
out["gate1"] = {"match_rate_ge_0.998": out["match_rate"] >= 0.998, "mean_diff_le_0.001": out["mean_abs_diff_of_means"] <= 0.001,
                "tail_mismatch_to_explain": int(mm.tail_ms10.sum() + mm.top1pct.sum())}
(H / "results/gate1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
