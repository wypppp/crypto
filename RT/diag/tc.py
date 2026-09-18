# -*- coding: utf-8 -*-
"""把 mu_winner 的周际差异拆成 T（机会大小）与 C（兑现效率）。
同时检查一个可能的口径混淆：A 周标签窗口 30 天，B 周 60 天。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
FEE = 0.004; D30 = 30*86400

A = pd.read_csv("dq7/raw/F2_dev.csv").dropna(subset=["b50"])
B = pd.read_csv("dq1f/raw/F1_val.csv").dropna(subset=["x50_24h"])
A["rec"], A["ms"], B["rec"], B["ms"] = A.b50-FEE, A.ms_30d, B.x50_24h-FEE, B.ms_60d

print("### 0. 口径核对")
for nm, d in (("A(30d)", A), ("B(60d)", B)):
    w = d.ms >= 10
    print("  %s  赢家 %d (%.2f%%)  赢家 peak_dt 中位 %.1f 天  超过 30 天见顶的赢家 %d (%.0f%%)"
          % (nm, w.sum(), 100*w.mean(), d.peak_dt[w].median()/86400,
             (d.peak_dt[w] > D30).sum(), 100*(d.peak_dt[w] > D30).mean()))

print("\n### 1. T（机会大小）与 C（兑现效率）分解，赢家组")
print("  %-24s %8s %8s %8s" % ("", "A 周", "B 周", "相对差"))
def row(lbl, a, b):
    print("  %-24s %8.3f %8.3f %7.1f%%" % (lbl, a, b, 100*abs(a-b)/max(abs(a),1e-9)))
for lbl, sel in (("全部赢家", lambda d: (d.ms >= 10).values),
                 ("赢家且 peak<=30 天", lambda d: ((d.ms >= 10) & (d.peak_dt <= D30)).values)):
    wa, wb = sel(A), sel(B)
    print("  --- %s：A n=%d, B n=%d ---" % (lbl, wa.sum(), wb.sum()))
    row("T: ms 中位（机会）", A.ms[wa].median(), B.ms[wb].median())
    row("T: ms 均值", A.ms[wa].mean(), B.ms[wb].mean())
    row("mu_winner（兑现）", A.rec[wa].mean(), B.rec[wb].mean())
    row("C: 兑现/机会 中位", (A.rec[wa]/A.ms[wa]).median(), (B.rec[wb]/B.ms[wb]).median())
    row("C: 兑现/机会 均值", (A.rec[wa]/A.ms[wa]).mean(), (B.rec[wb]/B.ms[wb]).mean())

print("\n### 2. V 标签污染：被判为'持平 0.9-1.1'的币里，路径最高倍数有多大？")
for nm, d in (("A", A), ("B", B)):
    flat = ((d.rec >= 0.9) & (d.rec < 1.1) & (d.ms < 10)).values
    print("  %s 周 持平桶 n=%d：ms 中位 %.2f，ms>=2 占 %.1f%%，ms>=4 占 %.1f%%，ms>=10 被排除"
          % (nm, flat.sum(), d.ms[flat].median(), 100*(d.ms[flat]>=2).mean(), 100*(d.ms[flat]>=4).mean()))

print("\n### 3. 若把 B 周赢家限制在 30 天内见顶，全池平均回收与赢家贡献怎么变？")
for nm, d, cap in (("A(本就30d)", A, None), ("B(限30d见顶)", B, D30)):
    w = (d.ms >= 10).values if cap is None else ((d.ms >= 10) & (d.peak_dt <= cap)).values
    print("  %-12s 赢家 %d (%.2f%%)  mu_winner %.3f  赢家贡献 %+.4f  全池平均回收 %.4f"
          % (nm, w.sum(), 100*w.mean(), d.rec[w].mean(), w.mean()*(d.rec[w].mean()-1), d.rec.mean()))
