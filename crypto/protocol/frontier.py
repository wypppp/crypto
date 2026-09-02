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
for n,lab in ((1,"单次预设检验"),(18,"Bonferroni n=18(17前史+1新)")):
    a=0.025/n; z=nd.inv_cdf(1-a)+0.8416
    print(f"  {lab:26s} α={a:.5f}  T={z*z/S_half**2:.2f} 年")
print(f"\n零 edge（财富为鞅）P=(1-a)/(b-a)。§0 为分段注资：10万仅在触及5万后释放，")
print(f"故完成111万 = 两段连续成功。总资产(含未释放储备)亦为鞅，可独立复核。")
print(f"  {'止损档':<10}{'阶段1 1万→5万':>14}{'阶段2 15万→111万':>16}{'联合完成111万':>14}")
for a,lab in ((0.5,"亏50%止"),(0.3,"亏70%止"),(0.1,"亏90%止"),(0.01,"亏99%止"),(0.0,"亏100%止")):
    P1=(1-a)/(5-a); P2=(1-a)/(7.4-a)
    print(f"  {lab:<10}{P1:>14.2%}{P2:>16.2%}{P1*P2:>14.2%}")
print(f"  复核 a=0.5: 阶段1 10.5(1-P)+15P=11 -> P={0.5/4.5:.4f}; 阶段2 7.5(1-P)+111P=15 -> P={7.5/103.5:.4f}")
print(f"  注：11万于 t=0 一次性投入为 5.2%-9.9%，但 §0 禁止该路径，不作为基线。")
print(f"\n成本吃掉目标增长所需周转 n_max = g/往返成本（对数口径）：")
for c,lab in ((0.0006,"6bp"),(0.0022,"22bp"),(0.04,"400bp"),(0.107,"1070bp")):
    print(f"  {lab:>8s} → {g/c:>6.0f} 次/年")
