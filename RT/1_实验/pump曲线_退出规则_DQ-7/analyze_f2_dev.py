"""DQ-7 开发分析：一致性核对 → 36 个组合 → 按卡片冻结规则选主候选 → 回撤解剖（描述）。"""
import json, hashlib
import numpy as np, pandas as pd
from pathlib import Path
H = Path(__file__).resolve().parent
RULES = ["b50","ins50_h70","c30_i02","c30_i05","c100_i02","c100_i05","tp2_r70","tp2_rNA","tp3_r70","tp3_rNA","tp2_c30_i02_r70","tp2_c100_i05_r70"]
COST = 0.004
raw = pd.read_csv(H/"raw/F2_dev.csv")
summ = raw[raw.mint=="__SUMMARY__"]; d = raw[raw.mint!="__SUMMARY__"].copy()
for c in d.columns[2:]: d[c] = pd.to_numeric(d[c], errors="coerce")
f1 = pd.read_csv(H.parent/"dq1f/raw/F1_dev.csv"); f1 = f1[f1.mint!="__SUMMARY__"].copy()
for c in f1.columns[3:]: f1[c] = pd.to_numeric(f1[c], errors="coerce")
m = d.merge(f1[["mint","net_sol_pre","entry_x_sol","x50_24h","ms_60d"]], on="mint", how="outer", suffixes=("","_f1"), indicator=True)
chk = {"rows": len(d), "summary": summ[["cday","flags"]].to_dict("records"), "dup": int(d.mint.duplicated().sum()),
       "merge": m._merge.value_counts().to_dict(),
       "net_sol_pre_equal": float(np.mean(np.isclose(m.net_sol_pre, m.net_sol_pre_f1, atol=1e-3))),
       "entry_x_equal": float(np.mean(np.isclose(m.entry_x_sol, m.entry_x_sol_f1, atol=1e-2))),
       "b50_vs_f1_x50_24h_mean": [round(d.b50.mean(),4), round(f1.x50_24h.mean(),4)],
       "b50_eq_f1_share": float(np.mean(np.isclose(m.b50, m.x50_24h, atol=1e-4))),
       "nan_rules": {r: int(d[r].isna().sum()) for r in RULES},
       "rule_gt_1.5ms": {r: int((d[r] > 1.5*d.ms_30d + 0.1).sum()) for r in RULES}}
print(json.dumps(chk, ensure_ascii=False, default=str, indent=0))
POP = {"P0": d.mint.notna(), "P1": d.net_sol_pre >= 5.3445, "P2": (d.entry_x_sol >= 59.1866) & (d.dev_prior_launches <= 11)}
rng = np.random.default_rng(20260917)
W = d.ms_30d >= 10
rows = []
for pn, pm in POP.items():
    s = d[pm]; n = len(s); idx = rng.integers(0, n, size=(2000, n))
    for r in RULES:
        x = s[r].values - COST
        bs = x[idx].mean(axis=1)
        w, o = s[W[pm]][r] - COST, s[~W[pm]][r] - COST
        rows.append(dict(pop=pn, rule=r, n=n, mean=x.mean(), p10=np.quantile(bs,.10), p05=np.quantile(bs,.05),
                         drop1=np.sort(x)[:-1].mean(), win_share=W[pm].mean(), win_mean=w.mean(), win_lt1=(w<1).mean(),
                         other_mean=o.mean(), dt_med_h=s[r+"_dt"].median()/3600, dt_p90_h=s[r+"_dt"].quantile(.9)/3600, max=x.max()))
T = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(T.round(3).sort_values(["pop","p10"], ascending=[True,False]).to_string(index=False))
ok = T[T.n >= 100]; best = ok.loc[ok.p10.idxmax()]
print("\n主候选（按卡片：P10 最高且 n≥100）:", best[["pop","rule","n","mean","p10"]].to_dict())
T.to_csv(H/"results/dev_combos.csv", index=False)
# 回撤解剖（描述）：首次 50% 回撤后反弹 ≥5 倍 vs 之后未回到回撤价 1.2 倍
a = d[d.dd_dt.notna()].copy()
a["up"] = a.dd_rebound >= 5; a["down"] = a.dd_rebound < 1.2
a["nb_share"] = a.dd_nb_sell30 / a.dd_sell30.replace(0, np.nan)
a["ins_share"] = a.dd_ins_sell30 / a.dd_sell30.replace(0, np.nan)
a["act_ratio"] = a.dd_trades30 / a.dd_trades30_prev.replace(0, np.nan)
a["bs_ratio"] = a.dd_buy30 / a.dd_sell30.replace(0, np.nan)
a["dd_h"] = a.dd_dt / 3600
from itertools import combinations
def auc(pos, neg):
    pos, neg = pos.dropna().values, neg.dropna().values
    if len(pos)==0 or len(neg)==0: return np.nan
    allv = np.concatenate([pos,neg]); rk = pd.Series(allv).rank().values
    return (rk[:len(pos)].sum() - len(pos)*(len(pos)+1)/2) / (len(pos)*len(neg))
print(f"\n回撤解剖：有首次 50% 回撤 {len(a)}；之后反弹≥5倍 {a.up.sum()}；未回到1.2倍 {a.down.sum()}；其中事后≥10x币 {int((a.ms_30d>=10).sum())}")
feats = ["dd_newb30","dd_ins_exit","nb_share","ins_share","act_ratio","bs_ratio","dd_trades30","dd_runmax","dd_h","dd_venue"]
out=[]
for f in feats:
    out.append(dict(feat=f, up_med=a.loc[a.up,f].median(), down_med=a.loc[a.down,f].median(), auc_up_vs_down=auc(a.loc[a.up,f], a.loc[a.down,f]), na_share=a[f].isna().mean()))
print(pd.DataFrame(out).round(3).to_string(index=False))
# 同一分析仅限 P1
b = a[a.net_sol_pre >= 5.3445]
print(f"\nP1 内：回撤 {len(b)}，反弹≥5倍 {b.up.sum()}，未回到1.2倍 {b.down.sum()}")
print(pd.DataFrame([dict(feat=f, up_med=b.loc[b.up,f].median(), down_med=b.loc[b.down,f].median(), auc=auc(b.loc[b.up,f], b.loc[b.down,f])) for f in feats]).round(3).to_string(index=False))
print("insider持仓>0 的币占比:", round((d.ins_hold_share>0).mean(),3), " dd_ins_exit 分位:", a.dd_ins_exit.quantile([.05,.5,.95]).round(3).tolist())
