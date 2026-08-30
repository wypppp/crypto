#!/usr/bin/env python3
"""目标—验证可行性前沿。纯算术，无外部数据依赖。
g(L)=Lu - 0.5 L^2 s^2  →  Kelly 最优 g* = S^2/2
"""
import math
def req_sharpe(mult, years, kelly=1.0):
    g=math.log(mult)/years
    f={1.0:0.5,0.5:0.375}[kelly]        # 全 Kelly: 0.5 S^2 ; 半 Kelly: 0.375 S^2
    return math.sqrt(g/f)
def years_to_detect(S_ann, power=0.80, alpha=0.025):
    z={0.025:1.9600}[alpha]+{0.80:0.8416}[power]
    return z*z/(S_ann**2)
print("="*72)
print("站① 目标 → 所需年化 Sharpe（含杠杆，Kelly 近似）")
print("="*72)
print("  关键恒等式：S_ann_required = sqrt( 2·ln(M) / T )  ← 与事件率无关")
for M,T,lbl in [(10.09,3,"11万→+100万 / 3年"),(10.09,5,"同上 / 5年"),(2.0,1,"翻倍 / 1年")]:
    print(f"  {lbl:22s} 全Kelly {req_sharpe(M,T,1.0):.2f}   半Kelly {req_sharpe(M,T,0.5):.2f}")
print()
print("="*72)
print("站⑤ 验证一个 Sharpe=S 的策略需要多久（80% 功效, α=0.025 单侧）")
print("="*72)
print("  关键恒等式：years = (z_a+z_b)^2 / S_ann^2 = 7.849 / S^2   ← 同样与事件率无关")
print("  （事件率↑ 同时增加样本数并等比稀释单事件 Sharpe，两者相消）\n")
print(f"  {'年化Sharpe':>10s} {'验证所需年数':>12s} {'≈周':>8s}")
for S in (0.5,1.0,1.24,1.43,2.0,3.0,5.8):
    y=years_to_detect(S); print(f"  {S:>10.2f} {y:>12.2f} {y*52:>8.0f}")
print()
print("="*72)
print("两条恒等式的交点 —— 这才是真正的门")
print("="*72)
S_need=req_sharpe(10.09,3,1.0)
y_need=years_to_detect(S_need)
print(f"  目标要求               S_ann >= {S_need:.2f}")
print(f"  验证该 Sharpe 需要      {y_need:.2f} 年 = {y_need*52:.0f} 周")
print(f"  你的前向验证预算        8-12 周 = {12/52:.2f} 年")
S_verifiable=math.sqrt(7.849/(12/52))
print(f"  → 12 周【只能】确认    S_ann >= {S_verifiable:.1f}")
print()
print(f"  ★ 缺口：能达标的策略 Sharpe {S_need:.2f}，12 周能验证的最低 Sharpe {S_verifiable:.1f}，相差 {S_verifiable/S_need:.1f} 倍")
print(f"  ★ 结论：8-12 周前向验证框架与 3 年 10 倍目标【结构上互斥】，与选哪个方向无关")
