# -*- coding: utf-8 -*-
"""诊断：'赢家 vs 被止损非赢家'的判别力组合起来能不能跨周？A 训练 → B 测试，及反向。
两周均已打开，本文件只作描述，不构成判定。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

FEATS = ["entry_x_sol","n_trades_pre","n_buyers_pre","trades_per_sol","bot_share_pre",
         "net_sol_pre","sell_share_pre","secs_since_last","pre_peak_pm","dev_prior_launches",
         "dev_prior_grads","dev_net_share","dev_sold_sol","top1_share","top5_share",
         "slot0_buyers","slot0_share","early10_buyers"]
FEE = 0.004

def load(path, rec, ms):
    d = pd.read_csv(path).dropna(subset=[rec]).reset_index(drop=True)
    d["rec"] = d[rec].astype(float) - FEE
    d["winner"] = d[ms].astype(float) >= 10.0
    d["loser"] = (~d["winner"]) & (d["rec"] >= 0.5) & (d["rec"] < 0.9)
    for f in FEATS: d[f] = pd.to_numeric(d[f], errors="coerce")
    d[FEATS] = d[FEATS].fillna(d[FEATS].median())
    return d

def auc(s, y):
    r = pd.Series(s).rank().values; n1, n0 = y.sum(), (~y).sum()
    return (r[y].sum() - n1*(n1+1)/2) / (n1*n0)

A = load("dq7/raw/F2_dev.csv", "b50", "ms_30d")
B = load("dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")

for trn, tst, nm in [(A, B, "A → B"), (B, A, "B → A")]:
    m = trn.winner.values | trn.loser.values
    sc = StandardScaler().fit(trn.loc[m, FEATS])
    lr = LogisticRegression(max_iter=2000, C=0.1).fit(sc.transform(trn.loc[m, FEATS]), trn.winner.values[m])
    # 样本内
    p_in = lr.predict_proba(sc.transform(trn.loc[m, FEATS]))[:, 1]
    a_in = auc(p_in, trn.winner.values[m])
    # 跨周
    m2 = tst.winner.values | tst.loser.values
    p_ot = lr.predict_proba(sc.transform(tst.loc[m2, FEATS]))[:, 1]
    a_ot = auc(p_ot, tst.winner.values[m2])
    # 经济后果：把模型打分用到整个池上，按分位买入
    p_all = lr.predict_proba(sc.transform(tst[FEATS]))[:, 1]
    print("%s   判别 AUC: 样本内 %.3f → 跨周 %.3f   (最强单特征跨周约 0.64)" % (nm, a_in, a_ot))
    base = tst.rec.mean()
    for topq in (0.50, 0.20, 0.10, 0.05):
        sel = p_all >= np.quantile(p_all, 1-topq)
        print("     买分数最高 %4.0f%%：n=%5d 平均回收 %.4f (基线 %.4f, %+.4f)  赢家占比 %.2f%%"
              % (100*topq, sel.sum(), tst.rec.values[sel].mean(), base,
                 tst.rec.values[sel].mean()-base, 100*tst.winner.values[sel].mean()))
