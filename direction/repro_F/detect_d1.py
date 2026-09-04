import json,os,datetime,collections,csv
H=3600000
W0=int(datetime.datetime(2025,5,2,tzinfo=datetime.timezone.utc).timestamp()*1000)
W1=int(datetime.datetime(2026,9,1,tzinfo=datetime.timezone.utc).timestamp()*1000)
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)
caps={r['symbol']:float(r['adjustedFundingRateCap']) for r in json.load(open('fundinginfo_perp.json'))}
try:
    import urllib.request
    caps.update({r['symbol']:float(r['adjustedFundingRateCap'])
                 for r in json.loads(urllib.request.urlopen("https://www.binance.com/fapi/v1/fundingInfo",timeout=60).read())})
except Exception: pass
byS=collections.defaultdict(list)
for f in os.listdir("fr_arch"):
    s,ym=f[:-5].split("__")
    try: rows=json.load(open(f"fr_arch/{f}"))
    except Exception: rows=[]
    if rows: byS[s]+=rows
ev=[]; stats=collections.Counter(); miss=collections.Counter()
left_cens=[]; right_cens=[]
for s,rows in byS.items():
    rows.sort(key=lambda r:r[0])
    rows=[r for r in rows if r[0]<=W1]
    if not rows: continue
    inw=[r for r in rows if r[0]>=W0]
    if not inw: continue
    # 左截尾:窗口内第一笔已是 1h
    if inw[0][1]==1: left_cens.append(s); stats['left_censored']+=1
    # 右截尾:最后一笔仍是 1h
    if inw[-1][1]==1: right_cens.append(s); stats['right_censored']+=1
    for i in range(1,len(rows)):
        if rows[i][0]<W0: continue
        prev_iv,iv=rows[i-1][1],rows[i][1]
        if iv==1 and prev_iv in (4,8):
            t_touch=rows[i-1][0]; pre=rows[i-1][2]
            # 1h 连续段长度
            j=i; 
            while j<len(rows) and rows[j][1]==1: j+=1
            dur=(rows[j-1][0]-rows[i][0])/H+1
            cap=caps.get(s)
            if cap is None: cls="cap未知"
            elif abs(abs(pre)-cap)<=cap*0.001: cls=("正侧触cap" if pre>0 else "负侧触floor")
            elif abs(pre)>=0.98*cap: cls=("正侧近顶" if pre>0 else "负侧近底")
            else: cls="非cap切换"
            stats[cls]+=1
            ev.append(dict(symbol=s,t_touch=f_(t_touch).isoformat(),
                t_signal_available=f_(t_touch+15*60000).isoformat(),
                t_first_1h=f_(rows[i][0]).isoformat(),
                prev_interval_h=prev_iv,pre_switch_funding=pre,cap=cap,
                classification=cls,duration_1h_regime_hours=dur,
                right_censored=(j>=len(rows) and rows[-1][1]==1)))
print(f"=== F-λ 第一阶段 · D1-candidate 扫描 ===")
print(f"窗口 2025-05-02 ~ 2026-08-31(固定截止,非「至今」)")
print(f"母体 {len(byS)} 个标的有归档数据(全 1,019 中)\n")
print(f"D1-candidate 事件总数 = {len(ev)}")
yrs=(datetime.datetime(2026,9,1)-datetime.datetime(2025,5,2)).days/365.25
print(f"窗口 {yrs:.2f} 年 ⟹ 全母体 {len(ev)/yrs:.1f} 次/年\n")
print("按切换前费率分类:")
for k in ["正侧触cap","正侧近顶","负侧触floor","负侧近底","非cap切换","cap未知"]:
    print(f"  {k:<12}{stats[k]:>5}")
print(f"\n左截尾(窗口首笔已是1h)= {stats['left_censored']}   右截尾(窗口末笔仍是1h)= {stats['right_censored']}")
pos=stats["正侧触cap"]+stats["正侧近顶"]
print(f"\n>>> **主卡(正 funding)相关事件 = {pos}**  ⟹ {pos/yrs:.2f} 次/年")
with open("repro/F_lambda_events.csv","w",newline="") as f:
    if ev:
        w=csv.DictWriter(f,fieldnames=list(ev[0].keys())); w.writeheader()
        for e in sorted(ev,key=lambda x:x["t_touch"]): w.writerow(e)
json.dump(dict(total=len(ev),years=yrs,stats=dict(stats),events=ev),open("F_lambda.json","w"))
if ev:
    print(f"\n持续期 duration_1h_regime(小时):中位 {sorted(e['duration_1h_regime_hours'] for e in ev)[len(ev)//2]:.0f}"
          f"  最大 {max(e['duration_1h_regime_hours'] for e in ev):.0f}")
    print(f"\n前 12 条事件:")
    for e in sorted(ev,key=lambda x:x["t_touch"])[:12]:
        print(f"  {e['t_touch'][:16]}  {e['symbol']:<14}{e['prev_interval_h']}h→1h  前值={e['pre_switch_funding']*100:+.4f}%  {e['classification']:<10}持续{e['duration_1h_regime_hours']:.0f}h")
