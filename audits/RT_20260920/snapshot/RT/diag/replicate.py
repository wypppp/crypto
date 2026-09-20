# -*- coding: utf-8 -*-
"""同一条"删左尾"规则在 A、B 两周的复现性。
规则 = (特征, 方向, 剔除分位)。分位在每周各自计算，所以是可执行的。
约束：保留池 >=30%，保留赢家 >=50%（否则不是"删左尾"，是把右尾也删了）。"""
import numpy as np, pandas as pd

FEATS = ["entry_x_sol","n_trades_pre","n_buyers_pre","trades_per_sol","bot_share_pre",
         "net_sol_pre","sell_share_pre","secs_since_last","pre_peak_pm","dev_prior_launches",
         "dev_prior_grads","dev_net_share","dev_sold_sol","top1_share","top5_share",
         "slot0_buyers","slot0_share","early10_buyers"]
FEE = 0.004
CUTS = (0.10, 0.20, 0.30, 0.40, 0.50)

def load(path, rec, ms):
    d = pd.read_csv(path).dropna(subset=[rec]).reset_index(drop=True)
    d["rec"] = d[rec].astype(float) - FEE
    d["winner"] = d[ms].astype(float) >= 10.0
    return d

A = load("dq7/raw/F2_dev.csv", "b50", "ms_30d")
B = load("dq1f/raw/F1_val.csv", "x50_24h", "ms_60d")
baseA, baseB = A.rec.mean(), B.rec.mean()

def evaluate(d, f, sign, c):
    s = sign * d[f].astype(float).values
    ok = np.isfinite(s)
    thr = np.nanquantile(s[ok], c)
    cut = ok & (s <= thr)
    keep = ~cut
    frac, wk = keep.mean(), d.winner.values[keep].sum() / max(d.winner.sum(), 1)
    degen = abs(np.nanquantile(s[ok], min(c+0.2, 1.0)) - thr) < 1e-12
    return d.rec.values[keep].mean(), frac, wk, degen

rows = []
for f in FEATS:
    for sign in (+1, -1):
        for c in CUTS:
            ma, fa, wa, da = evaluate(A, f, sign, c)
            mb, fb, wb, db = evaluate(B, f, sign, c)
            if min(fa, fb) < 0.30 or min(wa, wb) < 0.50:  continue
            rows.append(dict(rule="%s%s@%d" % ("+" if sign > 0 else "-", f, int(100*c)),
                             dA=ma-baseA, dB=mb-baseB, muA=ma, muB=mb,
                             keepA=fa, keepB=fb, winA=wa, winB=wb, degen=da or db))
T = pd.DataFrame(rows)
print("基线：A %.4f，B %.4f。合格规则数 %d（共 %d 个组合）" % (baseA, baseB, len(T), len(FEATS)*2*len(CUTS)))
print("\n--- 按 A 周改善排序，前 12 条 ---")
print("%-26s %8s %8s %8s %8s %6s" % ("规则","ΔA","ΔB","保留池A/B","赢家留A/B","退化"))
for _, r in T.sort_values("dA", ascending=False).head(12).iterrows():
    print("%-26s %+8.4f %+8.4f  %3.0f%%/%3.0f%%  %3.0f%%/%3.0f%%  %s"
          % (r["rule"], r.dA, r.dB, 100*r.keepA, 100*r.keepB, 100*r.winA, 100*r.winB,
             "是" if r.degen else ""))
print("\n--- 复现性 ---")
print("  ΔA 与 ΔB 的相关: %+.3f" % T[["dA","dB"]].corr().iloc[0,1])
pos = T[(T.dA > 0) & (T.dB > 0)]
print("  两周同时为正的规则: %d / %d" % (len(pos), len(T)))
print("  A 周前 5 名在 B 周的 Δ: %s" % ", ".join("%+.4f" % v for v in T.sort_values("dA", ascending=False).head(5).dB))
print("  B 周前 5 名在 A 周的 Δ: %s" % ", ".join("%+.4f" % v for v in T.sort_values("dB", ascending=False).head(5).dA))
print("  两周都为正者的 min(ΔA,ΔB) 最大值: %+.4f" % (pos[["dA","dB"]].min(axis=1).max() if len(pos) else 0))
if len(pos):
    b = pos.loc[pos[["dA","dB"]].min(axis=1).idxmax()]
    print("    → %s   ΔA %+.4f  ΔB %+.4f  绝对值 A %.4f / B %.4f" % (b["rule"], b.dA, b.dB, b.muA, b.muB))
