import json,urllib.request,math,statistics,time
UA={"User-Agent":"Mozilla/5.0"}
uni=json.load(open("FROZEN_UNIVERSE.json"))
data={}
for t in uni:
    for k in range(4):
        try:
            u=f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25))
            r=d["chart"]["result"][0]; q=r["indicators"]["quote"][0]; ts=r["timestamp"]
            o,c=q["open"],q["close"]
            data[t]={ts[i]:math.log(o[i]/c[i-1])*1e4 for i in range(1,len(ts)) if o[i] and c[i-1]}
            break
        except Exception: time.sleep(1.5*(k+1))
    time.sleep(0.25)
days=sorted(set().union(*[set(v) for v in data.values()]))
print(f"资产 {len(data)}  交易日 {len(days)}\n")
# 用【全隔夜收益】做规模估计：每日按 |收益| 降序取前10，等权、按符号建仓
sds=[]
for d0 in days:
    row=[(t,data[t][d0]) for t in data if d0 in data[t]]
    if len(row)<10: continue
    row.sort(key=lambda x:-abs(x[1]))
    top=row[:10]
    # 组合"暴露"规模：等权 10 仓、固定分母 14000（部署 14000）
    port=sum(abs(v) for _,v in top)/10
    sds.append(port)
print("=== 规模估计（用全隔夜收益，是 21:00→09:35 残差的【上界】）===")
print(f"  前10仓平均绝对隔夜收益：中位 {statistics.median(sds):.1f} bp   均值 {statistics.mean(sds):.1f} bp")
# 组合层面 sd：随机符号下的组合收益 sd
import random
random.seed(0)
sim=[]
for d0 in days:
    row=[(t,data[t][d0]) for t in data if d0 in data[t]]
    if len(row)<10: continue
    row.sort(key=lambda x:-abs(x[1]))
    top=[x for _,x in row[:10]]
    sgn=[1 if random.random()<0.5 else -1 for _ in top]
    sim.append(sum(s*v for s,v in zip(sgn,top))/10)
sd=statistics.pstdev(sim)
print(f"  随机方向下【窗口组合收益】标准差 σ ≈ {sd:.1f} bp/窗口\n")
print("=== 问题1：达到 100 万需要每窗口多少净收益？===")
cap=110000.0; tgt=1000000.0; yrs=3; wpw=4
n=int(52*yrs*wpw); mult=(cap+tgt)/cap
need=(mult**(1/n)-1)*1e4
print(f"  本金 11 万 → 目标 +100 万 = {mult:.2f}× ；周中 4 窗口/周 × 156 周 = {n} 个窗口")
print(f"  → 需要每窗口净 **{need:.1f} bp**（复利，扣完所有成本，固定分母）")
print(f"  参考：往返执行摩擦约 6 bp + funding；信号阈值 30 bp")
print("\n=== 问题1配套：不同真实 edge 下的年化与所需样本量（功效 80%, α=0.025 单侧）===")
z=1.96+0.84
print(f"  {'真实edge':>10s} {'年化(11万,无杠杆)':>18s} {'3年后':>10s} {'检测所需窗口数':>14s} {'≈周数':>8s}")
for e in (2,3,5,10,20,35.4):
    wk=(1+e/1e4)**wpw-1
    ann=(1+wk)**52-1
    n_need=z**2*(sd/e)**2
    print(f"  {e:>8.1f}bp {ann*100:>16.1f}% {cap*(1+ann)**3-cap:>9,.0f}元 {n_need:>14.0f} {n_need/wpw:>8.0f}")
