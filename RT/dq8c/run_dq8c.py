import json, numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor as HGB
F="entry_x_sol n_trades_pre n_buyers_pre trades_per_sol bot_share_pre net_sol_pre sell_share_pre secs_since_last pre_peak_pm dev_prior_launches dev_prior_grads dev_net_share dev_sold_sol top1_share top5_share slot0_buyers slot0_share early10_buyers".split()
def load(path, lab, ms):
    d=pd.read_csv(path, low_memory=False); d=d[d.mint!="__SUMMARY__"].copy()
    for c in F+[lab,ms]: d[c]=pd.to_numeric(d[c], errors="coerce")
    d=d[d[lab].notna()].copy(); d["y"]=d[lab]-0.004; d["W"]=d[ms]>=10
    return d
W={"A":load("../dq7/raw/F2_dev.csv","b50","ms_30d"),"B":load("../dq1f/raw/F1_val.csv","x50_24h","ms_60d")}
def slog(X): return np.sign(X)*np.log1p(np.abs(X))
def fit_pred(tr, te, m):
    Xtr, Xte, y = tr[F].to_numpy(float), te[F].to_numpy(float), tr.y.to_numpy(float)
    if m=="M1":
        a, b = slog(Xtr), slog(Xte); med=np.nanmedian(a,0); a=np.where(np.isnan(a),med,a); b=np.where(np.isnan(b),med,b)
        mu, sd = a.mean(0), a.std(0); sd[sd==0]=1
        return Ridge(alpha=10).fit((a-mu)/sd, y).predict((b-mu)/sd)
    if m=="M2w": y=np.minimum(y, np.quantile(y, 0.995))
    return HGB(loss="squared_error", learning_rate=0.05, max_iter=300, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0, random_state=0).fit(Xtr, y).predict(Xte)
rng=np.random.default_rng(20260917); out={}
for tr_name, te_name in [("A","B"),("B","A")]:
    tr, te = W[tr_name], W[te_name]; base=float(te.y.mean())
    for m in ["M1","M2","M2w"]:
        p=fit_pred(tr, te, m); o=np.argsort(-p); y=te.y.to_numpy()[o]; w=te.W.to_numpy()[o]; n=len(y)
        tiers={f"top{q}%": round(float(y[:max(1,int(n*q/100))].mean()),4) for q in [1,5,10,20,50]}
        k=int(n*0.1); top=y[:k]; bs=[rng.choice(top,k).mean() for _ in range(2000)]
        dec=[float(y[int(n*i/10):int(n*(i+1)/10)].mean()) for i in range(10)]
        rho=pd.Series(range(10)).corr(pd.Series(dec[::-1]), method="spearman")
        wk=w[:k]
        out[f"{tr_name}->{te_name} {m}"]=dict(base=round(base,4), **tiers, top10_boot_p10=round(float(np.quantile(bs,0.1)),4),
            deciles_hi_to_lo=[round(x,3) for x in dec], spearman_dec=round(float(rho),3),
            top10_winner_share=round(float(wk.mean()),4), base_winner_share=round(float(te.W.mean()),4),
            top10_winner_mean=round(float(top[wk].mean()),3) if wk.any() else None, top10_nonwinner_mean=round(float(top[~wk].mean()),4),
            base_nonwinner_mean=round(float(te.y[~te.W].mean()),4), top10_n=k)
m2ab, m2ba = out["A->B M2"], out["B->A M2"]
out["verdict_M2"]=dict(c1=m2ab["top10%"]>=1.03, c2=m2ab["top10_boot_p10"]>1.0, c3=m2ba["top10%"]>1.0)
out["verdict_M2"]["PASS"]=all(out["verdict_M2"].values())
json.dump(out, open("dq8c_result.json","w"), ensure_ascii=False, indent=1)
for k,v in out.items(): print(k, v)
