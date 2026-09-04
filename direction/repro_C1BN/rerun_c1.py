import json,os,datetime,collections,math,hashlib
H=3600000; DAY=86400000
U=json.load(open("top20_universe.json"))
top20={int(k):set(v) for k,v in U["top20"].items()}
CUT=int(datetime.datetime(2026,3,1,tzinfo=datetime.timezone.utc).timestamp()*1000)   # 冻结主样本截止
SETTLED=lambda s: "SETTLED" in s.upper()
ALL=[s for s in U["members"] if not SETTLED(s)]
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)

def norm_series(sym):
    p=f"funding/{sym}.json"
    if not os.path.exists(p): return []
    fr=json.load(open(p))
    if len(fr)<10: return []
    out=[]
    for i,(t,r) in enumerate(fr):
        iv=(fr[1][0]-fr[0][0])/H if i==0 else (t-fr[i-1][0])/H
        out.append((t,r/max(1.0,round(iv))))
    return out

def crossings(sym,W,dist_mode):
    """滚动 W 日分位(排除当前观测)。dist_mode: settle=只用结算点 | ffill=按持续小时数加权重复"""
    import bisect
    ns=norm_series(sym)
    if not ns: return []
    n=len(ns); out=[]; prev_hit=False
    sl=[]           # 已排序的窗口值
    wt=[]           # 与 ns 同序的 (t, value, weight)
    for i,(t,v) in enumerate(ns):
        hrs=1
        if dist_mode=='ffill':
            hrs=max(1,round(((ns[i+1][0] if i+1<n else t+H)-t)/H))
        wt.append((t,v,hrs))
    lo_i=0
    for i,(t,v,_) in enumerate(wt):
        lo=t-W*DAY
        while lo_i<i and wt[lo_i][0]<lo:
            _t,_v,_h=wt[lo_i]
            for _ in range(_h):
                k=bisect.bisect_left(sl,_v)
                if k<len(sl) and sl[k]==_v: sl.pop(k)
            lo_i+=1
        if len(sl)>=50:
            if v>0:
                th=sl[min(len(sl)-1,int(0.99*(len(sl)-1)))]; hit=(v>=th>0)
            elif v<0:
                th=sl[int(0.01*(len(sl)-1))]; hit=(v<=th<0)
            else: hit=False
        else: hit=False
        if hit and not prev_hit: out.append((t,v))
        prev_hit=hit
        for _ in range(wt[i][2]): bisect.insort(sl,v)
    return out

_HIDX=json.load(open("hourly_index.json"))
def load_px(sym):
    px={}
    for f in _HIDX.get(sym,[]):
        try:
            for t,c in json.load(open(f"hourly/{f}")): px[t//H*H]=c
        except Exception: pass
    return px
def load_oi(sym,days):
    o={}
    for d in days:
        p=f"metrics/{sym}_{d}.json"
        if not os.path.exists(p): continue
        try: rows=json.load(open(p))
        except Exception: continue
        for ts,v in rows:
            try:
                t=int(datetime.datetime.strptime(ts,'%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()*1000)
                o[t//H*H]=float(v)
            except Exception: pass
    return o
print("loaded")
