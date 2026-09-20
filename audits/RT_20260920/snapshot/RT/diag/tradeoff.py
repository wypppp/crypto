# -*- coding: utf-8 -*-
"""删左尾会删掉多少右尾？挑右尾会留下多少左尾？(0 credits)
lift = 被剔除的"被止损非赢家"比例 / 被剔除的赢家比例。lift≈1 等于随机剔除。"""
import numpy as np, pandas as pd

FEATS = ["entry_x_sol","n_trades_pre","n_buyers_pre","trades_per_sol","bot_share_pre",
         "net_sol_pre","sell_share_pre","secs_since_last","pre_peak_pm","dev_prior_launches",
         "dev_prior_grads","dev_net_share","dev_sold_sol","top1_share","top5_share",
         "slot0_buyers","slot0_share","early10_buyers"]
FEE, CUTS = 0.004, (0.10, 0.20, 0.30, 0.50)

def load(path, rec, ms):
    d = pd.read_csv(path).dropna(subset=[rec]).reset_index(drop=True)
    d["rec"] = d[rec].astype(float) - FEE
    d["winner"] = d[ms].astype(float) >= 10.0
    d["loser"] = (~d["winner"]) & (d["rec"] >= 0.5) & (d["rec"] < 0.9)
    return d

def auc(score, label):
    ok = np.isfinite(score); s, y = score[ok], label[ok]
    if y.sum() == 0 or (~y).sum() == 0: return np.nan
    r = pd.Series(s).rank().values; n1, n0 = y.sum(), (~y).sum()
    return (r[y].sum() - n1*(n1+1)/2) / (n1*n0)

for name, path, rec, ms in [("A 周 (b50)", "dq7/raw/F2_dev.csv", "b50", "ms_30d"),
                            ("B 周 (x50_24h)", "dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")]:
    d = load(path, rec, ms)
    W, L, R = d["winner"].values, d["loser"].values, d["rec"].values
    base = R.mean()
    print("=" * 100)
    print("%s  n=%d  赢家=%d  被止损非赢家=%d(%.1f%%)  基线平均回收=%.4f"
          % (name, len(d), W.sum(), L.sum(), 100*L.mean(), base))
    print("%-19s %6s %6s |" % ("特征","AUCw","AUCl"),
          " ".join("剔%2d%%:输/赢/lift/回收" % int(100*c) for c in CUTS))
    rows = []
    for f in FEATS:
        x = d[f].astype(float).values
        a_w, a_l = auc(x, W), auc(x, L)
        line, rec_best = "", {}
        for c in CUTS:
            best = None
            for sign in (+1, -1):
                s = sign * x; ok = np.isfinite(s)
                thr = np.nanquantile(s[ok], c)
                cut = ok & (s <= thr)
                keep = ~cut
                if keep.sum() == 0: continue
                dl = L[cut].sum()/max(L.sum(),1); dw = W[cut].sum()/max(W.sum(),1)
                mu = R[keep].mean()
                if best is None or mu > best[0]: best = (mu, dl, dw)
            mu, dl, dw = best
            lift = dl/dw if dw > 0 else np.inf
            rec_best[c] = mu
            line += " %4.0f/%4.0f/%4.2f/%.4f" % (100*dl, 100*dw, lift, mu)
        rows.append(dict(feat=f, auc_w=a_w, auc_l=a_l, **{("mu%d"%int(100*c)): rec_best[c] for c in CUTS}))
        print("%-19s %6.3f %6.3f |%s" % (f, a_w, a_l, line))
    T = pd.DataFrame(rows)
    print("  → AUC(挑赢家) 与 AUC(挑输家) 的相关 = %+.3f  [+ 越接近 1，两个任务越是同一件事]"
          % T[["auc_w","auc_l"]].corr().iloc[0,1])
    for c in CUTS:
        col = "mu%d" % int(100*c)
        i = T[col].idxmax()
        print("  → 剔除最差 %2d%%：最好平均回收 %.4f (%s)，比基线 %+.4f"
              % (100*c, T[col].max(), T.loc[i,"feat"], T[col].max()-base))
