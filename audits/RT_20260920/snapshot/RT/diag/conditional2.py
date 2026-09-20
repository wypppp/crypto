# -*- coding: utf-8 -*-
"""对上一步的正结果做三项诚实性检验：双向、是否只是活跃度残余、绝对值能否过 1。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

FEATS = ["entry_x_sol","n_trades_pre","n_buyers_pre","trades_per_sol","bot_share_pre",
         "net_sol_pre","sell_share_pre","secs_since_last","pre_peak_pm","dev_prior_launches",
         "dev_prior_grads","dev_net_share","dev_sold_sol","top1_share","top5_share",
         "slot0_buyers","slot0_share","early10_buyers"]
FEE = 0.004; rng = np.random.default_rng(20260918)

def load(path, rec, ms):
    d = pd.read_csv(path).dropna(subset=[rec]).reset_index(drop=True)
    d["rec"] = d[rec].astype(float) - FEE
    d["winner"] = d[ms].astype(float) >= 10.0
    d["loser"] = (~d["winner"]) & (d["rec"] >= 0.5) & (d["rec"] < 0.9)
    for f in FEATS: d[f] = pd.to_numeric(d[f], errors="coerce")
    d[FEATS] = d[FEATS].fillna(d[FEATS].median())
    return d

A = load("dq7/raw/F2_dev.csv", "b50", "ms_30d")
B = load("dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")

def fit_apply(trn, tst):
    m = trn.winner.values | trn.loser.values
    sc = StandardScaler().fit(trn.loc[m, FEATS])
    lr = LogisticRegression(max_iter=2000, C=0.1).fit(sc.transform(trn.loc[m, FEATS]), trn.winner.values[m])
    t = tst.copy(); t["score"] = lr.predict_proba(sc.transform(tst[FEATS]))[:, 1]
    t["act"] = pd.qcut(t.net_sol_pre.rank(method="first"), 5, labels=["Q1","Q2","Q3","Q4","Q5"])
    return t

def boot_diff(lo, hi, n=2000):
    d = [rng.choice(hi, len(hi), True).mean() - rng.choice(lo, len(lo), True).mean() for _ in range(n)]
    return np.percentile(d, 5), np.percentile(d, 95)

for nm, trn, tst in (("A → B", A, B), ("B → A", B, A)):
    t = fit_apply(trn, tst)
    print("=== %s ===" % nm)
    print("  %-4s %6s %8s | %8s %8s %8s %-16s | %9s %9s" %
          ("层","n","层基线","下半","上半","上-下","自助90%区间","层内分数~净流入 ρ","上半绝对值>1?"))
    for lab, g in t.groupby("act"):
        med = g.score.median(); lo = g[g.score < med]; hi = g[g.score >= med]
        d = hi.rec.mean() - lo.rec.mean()
        c = boot_diff(lo.rec.values, hi.rec.values)
        rho = g[["score","net_sol_pre"]].corr(method="spearman").iloc[0,1]
        print("  %-4s %6d %8.4f | %8.4f %8.4f %+8.4f [%+.4f,%+.4f] | %13.3f %9s" %
              (lab, len(g), g.rec.mean(), lo.rec.mean(), hi.rec.mean(), d, c[0], c[1], rho,
               "是" if hi.rec.mean() > 1 else "否"))
