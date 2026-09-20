# -*- coding: utf-8 -*-
"""定点影响核验：创建者窗口口径不符能否翻转 DQ-1F 结论。0 credits，只读 F1_val.csv。
不计算修正值或误差上界（需逐创建事件），只计算假定加回集合与旧门槛敏感性。"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
d = pd.read_csv("dq1f/raw/F1_val.csv")
d = d[d.mint != "__SUMMARY__"].copy()
assert d.cday.between(1, 7).all(), "real token cday outside cohort"
E = d.entry_x_sol >= 59.1866
RULE = E & (d.dev_prior_launches <= 11)
bn, bs = int(RULE.sum()), d.x50_1h[RULE].sum()
print("冻结主候选 n=%d 均值 %.8f" % (bn, bs/bn))

print("\nA. 按 cohort 日分组（固定起日窗口约 30–37 天；这里只描述旧计数）")
for c, g in d[d.cday <= 7].groupby("cday"):
    ge = g[g.entry_x_sol >= 59.1866]
    print("   cday=%d cohort日偏移%d天  E层n=%d  计数>11 占比 %.1f%%" % (c, c-1, len(ge), 100*(ge.dev_prior_launches > 11).mean()))

print("\nB. 假定加回集合的影响（不是实际修正或误差上界）")
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
