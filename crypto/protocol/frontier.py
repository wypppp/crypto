#!/usr/bin/env python3
"""可行性算术。纯算术，无外部依赖，可独立复算。
资金路径: 1万 --5x--> 5万, 释放10万 → 15万 --7.4x--> 111万  ⇒ M_eff = 37
"""
import math, statistics
M = 5.0 * (111/15)          # = 37.0  分段路径的有效倍数
T = 3.0
g = math.log(M)/T           # 所需对数增长/年
print(f"M_eff={M:.1f}  ln(M)={math.log(M):.4f}  所需对数增长 g={g:.4f}/年  年化={math.exp(g)-1:+.1%}")
for lab,f in (("全 Kelly (g=0.5·S²)",0.5), ("半 Kelly (g=0.375·S²)",0.375)):
    S=math.sqrt(g/f); print(f"  {lab:26s} 组合 Sharpe 需 {S:.2f}")
S_half=math.sqrt(g/0.375)
print(f"\n  组合 Sharpe {S_half:.2f} 可由 k 条相关性≈0 的 sleeve 合成：")
for k in (1,2,3,4): print(f"    k={k} → 每条需 {S_half/math.sqrt(k):.2f}")
print(f"\n验证时间 = (z_a+z_b)²/S²，80% 功效：")
nd=statistics.NormalDist()
for n,lab in ((1,"单次预设检验"),(18,"含 17 条前史 Bonferroni")):
    a=0.025/n; z=nd.inv_cdf(1-a)+0.8416
    print(f"  {lab:26s} α={a:.5f}  T={z*z/S_half**2:.2f} 年")
print(f"\n零 edge（财富为鞅）先触及 b× 而非 a× 的概率 = (1-a)/(b-a)：")
for a,lab in ((0.5,"亏50%止"),(0.3,"亏70%止"),(0.1,"亏90%止"),(0.01,"亏99%止")):
    print(f"  1万→5万 {lab}: {(1-a)/(5-a):.1%}   11万→111万: {(1-a)/(10.09-a):.1%}")
print(f"\n成本吃掉目标增长所需周转 n_max = g/往返成本（对数口径）：")
for c,lab in ((0.0006,"6bp"),(0.0022,"22bp"),(0.04,"400bp"),(0.107,"1070bp")):
    print(f"  {lab:>8s} → {g/c:>6.0f} 次/年")
