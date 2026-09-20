# -*- coding: utf-8 -*-
"""三件事（0 credits，两周均已打开，描述性）：
(a) V/Q/capture 三层里，哪些量两周稳定、哪些不稳定；
(b) 质量搬运改用 top20% vs bottom80%（去掉包含关系）；
(c) 把活跃度真正残差化后，增量信息还在不在（上一轮只做了粗分层，ρ 残留 0.574）。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.preprocessing import StandardScaler

ACT = ["net_sol_pre","n_trades_pre","n_buyers_pre","entry_x_sol","early10_buyers","slot0_buyers"]
FEATS = ACT + ["trades_per_sol","bot_share_pre","sell_share_pre","secs_since_last","pre_peak_pm",
               "dev_prior_launches","dev_prior_grads","dev_net_share","dev_sold_sol",
               "top1_share","top5_share","slot0_share"]
OTHER = [f for f in FEATS if f not in ACT]
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
    d["loser"] = (~d.winner) & (d.rec >= 0.5) & (d.rec < 0.9)
    return d

A = load("dq7/raw/F2_dev.csv", "b50", "ms_30d")
B = load("dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")

print("### (a) 哪些量两周稳定？  p_k = 桶概率, mu_k = 桶内平均回收")
for scope, sel in (("全池", lambda d: np.ones(len(d), bool)),
                   ("净流入前20%", lambda d: (d.net_sol_pre >= d.net_sol_pre.quantile(0.80)).values)):
    print("  [%s]  %-13s %8s %8s %8s | %8s %8s %8s" % (scope,"桶","p(A)","p(B)","p 相对差","mu(A)","mu(B)","mu 相对差"))
    for k in BUCK:
        out = []
        for d in (A, B):
            m = sel(d); mk = m & (d.bucket == k).values
            out.append((mk.sum()/m.sum(), d.rec.values[mk].mean()))
        dp = abs(out[0][0]-out[1][0])/max(out[0][0],1e-9)
        dm = abs(out[0][1]-out[1][1])/max(abs(out[0][1]),1e-9)
        print("       %-13s %8.4f %8.4f %7.1f%% | %8.3f %8.3f %7.1f%%"
              % (k, out[0][0], out[1][0], 100*dp, out[0][1], out[1][1], 100*dm))

print("\n### (b) 质量搬运：净流入 top20% vs bottom80%（去掉包含关系）")
for nm, d in (("A", A), ("B", B)):
    hi = (d.net_sol_pre >= d.net_sol_pre.quantile(0.80)).values
    pos = neg = 0.0
    line = []
    for k in BUCK:
        m = (d.bucket == k).values
        p1, p0 = (m & hi).sum()/hi.sum(), (m & ~hi).sum()/(~hi).sum()
        line.append("%s %+.4f" % (k, p1-p0))
        if k in (BUCK[0], BUCK[1]): pos += max(p1-p0, 0)
        if k in (BUCK[2], BUCK[3]): neg += max(p1-p0, 0)
    print("  %s 周: %s" % (nm, " | ".join(line)))
    print("     新增高波动质量中 正向 %.1f%% / 负向 %.1f%%" % (100*pos/(pos+neg), 100*neg/(pos+neg)))

print("\n### (c) 真正残差化活跃度之后，增量信息还在吗？（A→B 与 B→A）")
def residualize(trn, tst):
    """把 12 个非活跃特征对 6 个活跃特征线性回归，取残差。"""
    sa = StandardScaler().fit(trn[ACT]); Xa_t, Xa_s = sa.transform(trn[ACT]), sa.transform(tst[ACT])
    Rt, Rs = {}, {}
    for f in OTHER:
        lr = LinearRegression().fit(Xa_t, trn[f].values)
        Rt[f] = trn[f].values - lr.predict(Xa_t); Rs[f] = tst[f].values - lr.predict(Xa_s)
    return pd.DataFrame(Rt), pd.DataFrame(Rs), Xa_t, Xa_s

def auc(s, y):
    r = pd.Series(s).rank().values; n1, n0 = y.sum(), (~y).sum()
    return (r[y].sum() - n1*(n1+1)/2)/(n1*n0)

for nm, trn, tst in (("A → B", A, B), ("B → A", B, A)):
    Rt, Rs, Xa_t, Xa_s = residualize(trn, tst)
    m = (trn.winner | trn.loser).values; m2 = (tst.winner | tst.loser).values
    # 仅活跃度 vs 活跃度+残差
    res = {}
    for tag, Xt, Xs in (("仅活跃度", Xa_t, Xa_s),
                        ("活跃度+残差", np.hstack([Xa_t, StandardScaler().fit_transform(Rt)]),
                                        np.hstack([Xa_s, StandardScaler().fit(Rt).transform(Rs)])),
                        ("仅残差", StandardScaler().fit_transform(Rt), StandardScaler().fit(Rt).transform(Rs))):
        lr = LogisticRegression(max_iter=3000, C=0.1).fit(Xt[m], trn.winner.values[m])
        p = lr.predict_proba(Xs)[:, 1]
        res[tag] = (auc(p[m2], tst.winner.values[m2]), p)
    print("  %s  跨周 AUC(赢家vs输家)：仅活跃度 %.3f → 活跃度+残差 %.3f  (增量 %+.3f)；仅残差 %.3f"
          % (nm, res["仅活跃度"][0], res["活跃度+残差"][0], res["活跃度+残差"][0]-res["仅活跃度"][0], res["仅残差"][0]))
    p = res["仅残差"][1]
    a = pd.qcut(pd.Series(tst.net_sol_pre.values).rank(method="first"), 5, labels=["Q1","Q2","Q3","Q4","Q5"])
    rho = pd.Series(p).corr(pd.Series(tst.net_sol_pre.values), method="spearman")
    print("     仅残差分数与净流入的全样本 Spearman ρ = %+.3f（上一轮综合分数为 +0.4~+0.6）" % rho)
    for lab in ["Q3","Q4","Q5"]:
        g = (a == lab).values
        med = np.median(p[g]); hi2 = g & (p >= med); lo2 = g & (p < med)
        print("     %s 层：上半 %.4f  下半 %.4f  上-下 %+.4f"
              % (lab, tst.rec.values[hi2].mean(), tst.rec.values[lo2].mean(),
                 tst.rec.values[hi2].mean()-tst.rec.values[lo2].mean()))
