# -*- coding: utf-8 -*-
"""直接问：在"未来赢家"和"未来被止损的非赢家"这两组之间，18 个特征能分开吗？
这是 DQ-1F/DQ-7/DQ-8A 真正需要、但从未被直接测过的那个判别任务。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")

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
    return d

def auc(s, y):
    ok = np.isfinite(s); s, y = s[ok], y[ok]
    if y.sum() == 0 or (~y).sum() == 0: return np.nan
    r = pd.Series(s).rank().values; n1, n0 = y.sum(), (~y).sum()
    return (r[y].sum() - n1*(n1+1)/2) / (n1*n0)

A = load("dq7/raw/F2_dev.csv", "b50", "ms_30d")
B = load("dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")

print("%-20s %-22s %-22s" % ("", "A 周", "B 周"))
print("%-20s %10s %10s %10s %10s" % ("特征", "赢家vs输家", "|偏离0.5|", "赢家vs输家", "|偏离0.5|"))
res = []
for f in FEATS:
    out = []
    for d in (A, B):
        m = d.winner.values | d.loser.values          # 只保留这两组
        s = d[f].astype(float).values[m]
        y = d.winner.values[m]
        out.append(auc(s, y))
    res.append((f, out[0], out[1]))
    print("%-20s %10.3f %10.3f %10.3f %10.3f" % (f, out[0], abs(out[0]-0.5), out[1], abs(out[1]-0.5)))
R = pd.DataFrame(res, columns=["f","a","b"])
R["da"], R["db"] = (R.a-0.5).abs(), (R.b-0.5).abs()
print("\n最强单特征：A 周 %s (AUC %.3f)，B 周 %s (AUC %.3f)"
      % (R.loc[R.da.idxmax(),"f"], R.loc[R.da.idxmax(),"a"], R.loc[R.db.idxmax(),"f"], R.loc[R.db.idxmax(),"b"]))
print("两周 AUC 的相关（方向是否一致）: %+.3f" % R[["a","b"]].corr().iloc[0,1])
print("两周都偏离 0.5 超过 0.05 且同向的特征数: %d / 18"
      % ((((R.a-0.5)*(R.b-0.5)) > 0) & (R.da > 0.05) & (R.db > 0.05)).sum())

print("\n=== 改善目标表：要把平均回收推到 1.02（4 cohort 可确认门槛）还差多少 ===")
for nm, d in (("A", A), ("B", B)):
    base = d.rec.mean(); need = 1.02 - base
    W = d.winner.values; L = d.loser.values
    cw = W.mean()*(d.rec.values[W].mean()-1); cl = L.mean()*(d.rec.values[L].mean()-1)
    print("%s 周：基线 %.4f，缺口 %+.4f" % (nm, base, need))
    print("   若只靠右尾捕获：赢家贡献须从 %+.4f 提到 %+.4f，即赢家兑现均值 %.2f → %.2f（占比不变）"
          % (cw, cw+need, d.rec.values[W].mean(), d.rec.values[W].mean() + need/W.mean()))
    print("   若只靠抑制那 25%%：须剔除其中 %.0f%%（且不误伤赢家）" % (100*min(need/(-cl), 1.0)))
    print("   若只靠降摩擦：每笔往返成本须降 %.2f 个百分点（当前约 2.5）" % (100*need))
