# -*- coding: utf-8 -*-
"""定点影响核验：创建者窗口口径不符能否翻转 DQ-1F 结论。0 credits，只读 F1_val.csv。
不计算修正值（需逐创建事件），只界定同一条规则在修正后的成员变化范围与阈值敏感性。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
d = pd.read_csv("dq1f/raw/F1_val.csv")
E = d.entry_x_sol >= 59.1866
RULE = E & (d.dev_prior_launches <= 11)
bn, bs = int(RULE.sum()), d.x50_1h[RULE].sum()
print("冻结主候选 n=%d 均值 %.8f" % (bn, bs/bn))

print("\nA. 窗口漂移（cday=1 恰 30 天，cday=7 为 36 天，计数只会高估）")
for c, g in d[d.cday <= 7].groupby("cday"):
    ge = g[g.entry_x_sol >= 59.1866]
    print("   cday=%d 超窗%d天  E层n=%d  计数>11 占比 %.1f%%" % (c, c-1, len(ge), 100*(ge.dev_prior_launches > 11).mean()))

print("\nB. 现实加回集合的影响")
for hi in (13, 15, 20, 30):
    S = E & (d.dev_prior_launches > 11) & (d.dev_prior_launches <= hi) & (d.cday > 1)
    m = (bs + d.x50_1h[S].sum())/(bn + S.sum())
    print("   计数∈(11,%2d] 且 cday>1: n=%4d 池均值 %.5f → 并入后 %.5f (%+.4f)" % (hi, S.sum(), d.x50_1h[S].mean(), m, m-bs/bn))

print("\nC. 阈值敏感性")
for t in (5, 8, 11, 13, 15, 20, 30, 50):
    m = E & (d.dev_prior_launches <= t)
    print("   <=%-3d n=%5d 均值 %.5f" % (t, m.sum(), d.x50_1h[m].mean()))

print("\nD. 重尾警告：排除池 n=%d，若只加回最好的 k 个" % int((E & (d.dev_prior_launches > 11)).sum()))
srt = np.sort(d.x50_1h[E & (d.dev_prior_launches > 11)].values)[::-1]
for k in (1, 5, 8, 20):
    print("   k=%-3d 均值 %.5f" % (k, (bs + srt[:k].sum())/(bn + k)))
print("   池中最大 5 个 x50_1h: %s" % np.round(srt[:5], 2).tolist())
print("\n数据质量: cday 超出 1-7 的行数 =", int((d.cday > 7).sum()))
