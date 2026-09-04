import json,os,hashlib,datetime,collections
D="daily_klines"; DAY=86400000
series={}
for f in os.listdir(D):
    rows=json.load(open(f"{D}/{f}"))
    if rows: series[f[:-5]]={r[0]:r[2] for r in rows}
print(f"有数据标的 = {len(series)}")
days=sorted({t for s in series.values() for t in s})
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)
print(f"跨度 {f_(days[0]):%Y-%m-%d} ~ {f_(days[-1]):%Y-%m-%d},共 {len(days)} 天")
# 每符号 30 日滚动名义额(增量维护)
roll={s:0.0 for s in series}; win=collections.deque()
start=datetime.datetime(2021,9,1,tzinfo=datetime.timezone.utc).timestamp()*1000
top20={}; members=collections.Counter()
for d in days:
    win.append(d)
    for s,v in series.items():
        if d in v: roll[s]+=v[d]
    if len(win)>30:
        old=win.popleft()
        for s,v in series.items():
            if old in v: roll[s]-=v[old]
    if d<start or len(win)<30: continue
    t20=sorted((x for x in roll.items() if x[1]>0),key=lambda x:-x[1])[:20]
    top20[d]=[s for s,_ in t20]
    for s,_ in t20: members[s]+=1
print(f"\n点时 top-20 天数 = {len(top20)}")
print(f"曾进入 top-20 的不同标的 = {len(members)}")
print(f"总 symbol-day = {sum(members.values())}")
print("\n出现最多的 15 个:")
for s,c in members.most_common(15): print(f"    {s:<16}{c:>5} 天")
print(f"\n出现 <30 天的标的数 = {sum(1 for c in members.values() if c<30)}")
def hold(s): return hashlib.sha256(s.encode()).digest()[0]%5==0
CONTAM={"TUSDT","ONGUSDT","SKRUSDT","1000PEPEUSDT","WIFUSDT","HYPEUSDT","1000BONKUSDT","PNUTUSDT",
        "MOODENGUSDT","AI16ZUSDT","TRUMPUSDT","MELANIAUSDT","VINEUSDT","SUSDT","KAITOUSDT","BTCUSDT"}
holdout=sorted(s for s in members if hold(s) and s not in CONTAM)
main=sorted(set(members)-set(holdout))
print(f"\n留出确认集 = {len(holdout)}   主分析集 = {len(main)}")
print(f"  留出集 symbol-day = {sum(members[s] for s in holdout)}")
print(f"  主分析集 symbol-day = {sum(members[s] for s in main)}")
json.dump({"top20":{str(k):v for k,v in top20.items()},"members":dict(members),
           "holdout":holdout,"main":main},open("top20_universe.json","w"))
print("\n已存 top20_universe.json")
