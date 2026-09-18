# -*- coding: utf-8 -*-
"""检验外部评审的两个主张（0 credits，两周均已打开，描述性）：
(1) 旧特征做的是"持平 → 高波动"，高波动再分裂成 少量赢家 + 大量被止损币？
(2) 控制活跃度之后，"赢家 vs 被止损输家"的残差信号有没有经济价值？"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

FEATS = ["entry_x_sol","n_trades_pre","n_buyers_pre","trades_per_sol","bot_share_pre",
         "net_sol_pre","sell_share_pre","secs_since_last","pre_peak_pm","dev_prior_launches",
         "dev_prior_grads","dev_net_share","dev_sold_sol","top1_share","top5_share",
         "slot0_buyers","slot0_share","early10_buyers"]
FEE = 0.004
BUCK = ["赢家>=10x","上涨>1.1","止损0.5-0.9","深跌<0.5","持平0.9-1.1"]

def load(path, rec, ms):
    d = pd.read_csv(path).dropna(subset=[rec]).reset_index(drop=True)
    d["rec"] = d[rec].astype(float) - FEE
    d["winner"] = d[ms].astype(float) >= 10.0
    r, w = d.rec.values, d.winner.values
    d["bucket"] = np.where(w, BUCK[0], np.where(r >= 1.1, BUCK[1],
                  np.where(r >= 0.9, BUCK[4], np.where(r >= 0.5, BUCK[2], BUCK[3]))))
    for f in FEATS: d[f] = pd.to_numeric(d[f], errors="coerce")
    d[FEATS] = d[FEATS].fillna(d[FEATS].median())
    return d

A = load("dq7/raw/F2_dev.csv", "b50", "ms_30d")
B = load("dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")

print("### (1) 概率质量搬运：净流入最高 20% vs 全池  ΔE = Σ Δp_k × (mean_k − 1)")
for nm, d in (("A 周", A), ("B 周", B)):
    q = d.net_sol_pre; hi = (q >= q.quantile(0.80)).values
    print("  %s  全池 %.4f → 该层 %.4f" % (nm, d.rec.mean(), d.rec.values[hi].mean()))
    print("     %-13s %8s %8s %8s %9s %9s" % ("桶","p全池","p该层","Δp","桶内均值","Δp×(均值-1)"))
    for k in BUCK:
        m0 = (d.bucket == k).values; m1 = m0 & hi
        p0, p1 = m0.mean(), m1.sum()/hi.sum()
        mu = d.rec.values[m1].mean() if m1.sum() else np.nan
        print("     %-13s %8.4f %8.4f %+8.4f %9.3f %+9.4f"
              % (k, p0, p1, p1-p0, mu, (p1-p0)*(mu-1) if m1.sum() else 0))

print("\n### (2) 控制活跃度后，残差判别信号的经济价值（A 训练 → B 测试）")
m = A.winner.values | (A.bucket == BUCK[2]).values
sc = StandardScaler().fit(A.loc[m, FEATS])
lr = LogisticRegression(max_iter=2000, C=0.1).fit(sc.transform(A.loc[m, FEATS]), A.winner.values[m])
B = B.copy(); B["score"] = lr.predict_proba(sc.transform(B[FEATS]))[:, 1]
qa = B.net_sol_pre
B["act"] = pd.qcut(qa.rank(method="first"), 5, labels=["Q1低","Q2","Q3","Q4","Q5高"])
print("  %-7s %6s %9s | %9s %9s %9s | %9s" % ("活跃层","n","层基线","分下半","分上半","上-下","上半赢家%"))
for lab, g in B.groupby("act"):
    if len(g) < 50: continue
    med = g.score.median(); lo = g[g.score < med]; hi2 = g[g.score >= med]
    print("  %-7s %6d %9.4f | %9.4f %9.4f %+9.4f | %8.2f%%"
          % (lab, len(g), g.rec.mean(), lo.rec.mean(), hi2.rec.mean(),
             hi2.rec.mean()-lo.rec.mean(), 100*hi2.winner.mean()))
print("  → 若'控制活跃度后残差有经济价值'成立，'上-下'应稳定为正。")
