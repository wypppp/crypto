import json,os,datetime,collections,urllib.request,zipfile,io,concurrent.futures as cf
exec(open("rerun_c1.py").read().split('print("loaded")')[0])
def stage(W,dist):
    c1=collections.defaultdict(list)
    for s in ALL:
        for t,v in crossings(s,W,dist):
            if t<CUT and s in top20.get(t//DAY*DAY,()): c1[s].append((t,v))
    n1=sum(len(v) for v in c1.values())
    c13=collections.defaultdict(list); nopx=0
    for s,cs in c1.items():
        px=load_px(s)
        if not px: nopx+=len(cs); continue
        for t,v in cs:
            h=t//H*H; h0=h-24*H
            if h in px and h0 in px:
                ch=(px[h]-px[h0])/px[h0]
                if (v>0 and ch>=0.10) or (v<0 and ch<=-0.10): c13[s].append((t,v,ch))
            else: nopx+=1
    n13=sum(len(v) for v in c13.values())
    # 定向补 OI
    need=set()
    for s,cs in c13.items():
        for t,v,ch in cs:
            for o in (0,-DAY,-2*DAY): need.add((s,datetime.datetime.fromtimestamp((t+o)/1000,datetime.timezone.utc).strftime('%Y-%m-%d')))
    miss=[x for x in need if not os.path.exists(f"metrics/{x[0]}_{x[1]}.json")]
    def gm(a):
        s,d=a
        try:
            raw=urllib.request.urlopen(f"https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip",timeout=45).read()
            z=zipfile.ZipFile(io.BytesIO(raw)); L=z.read(z.namelist()[0]).decode().splitlines()
            json.dump([[r.split(',')[0],r.split(',')[2]] for r in L[1:] if r],open(f"metrics/{s}_{d}.json","w"))
        except Exception: json.dump([],open(f"metrics/{s}_{d}.json","w"))
    if miss:
        with cf.ThreadPoolExecutor(20) as ex: list(ex.map(gm,miss))
    c123=collections.defaultdict(list); nooi=0
    for s,cs in c13.items():
        days=sorted({datetime.datetime.fromtimestamp((t+o)/1000,datetime.timezone.utc).strftime('%Y-%m-%d') for t,v,ch in cs for o in (0,-DAY,-2*DAY)})
        oi=load_oi(s,days)
        for t,v,ch in cs:
            h=t//H*H; h0=h-24*H
            if h in oi and h0 in oi and oi[h0]>0:
                d=(oi[h]-oi[h0])/oi[h0]
                if d>=0.20: c123[s].append((t,v,ch,d))
            else: nooi+=1
    ev=sorted([(t,s,v,ch,d) for s,cs in c123.items() for t,v,ch,d in cs])
    bys=collections.defaultdict(list)
    for t,s,v,ch,d in ev: bys[s].append((t,v))
    eps=[]
    for s,L in bys.items():
        cur=None
        for t,v in sorted(L):
            if cur and t-cur[-1][0]<8*H: cur.append((t,v))
            else:
                if cur: eps.append((s,cur)); 
                cur=[(t,v)]
        if cur: eps.append((s,cur))
    epev=sorted([(L[0][0],s,L[0][1]) for s,L in eps])
    clus=[]; i=0
    while i<len(epev):
        t0,s0,v0=epev[i]; d0=1 if v0>0 else -1
        grp=[(t0,s0)]; j=i+1
        while j<len(epev) and epev[j][0]<=t0+H:
            if (1 if epev[j][2]>0 else -1)==d0 and epev[j][1]!=s0: grp.append((epev[j][0],epev[j][1]))
            j+=1
        clus.append(grp); i+=1
    op=[]; adm=0; blk=0
    for g in clus:
        for t,s in sorted(g):
            op=[x for x in op if x>t-8*H]
            if len(op)<2: op.append(t); adm+=1
            else: blk+=1
    return dict(W=W,dist=dist,n1=n1,n13=n13,nopx=nopx,nooi=nooi,
                lam_sym=len(ev),lam_ep=len(eps),lam_cl=len(clus),adm=adm,blk=blk,
                sizes=dict(collections.Counter(len(g) for g in clus)),
                pos=sum(1 for e in ev if e[2]>0),neg=sum(1 for e in ev if e[2]<0),
                events=[[e[0],e[1],e[2],e[3],e[4]] for e in ev])
yrs=(datetime.datetime(2026,3,1)-datetime.datetime(2021,9,1)).days/365.25
out={}
for W,dist in [(365,'settle'),(365,'ffill'),(180,'settle')]:
    r=stage(W,dist); out[f"{W}_{dist}"]=r
    print(f"\n=== W={W}d  分布口径={dist} ===")
    print(f"  ① {r['n1']}   ①∩③ {r['n13']}   三条件 {r['lam_sym']}   (缺价{r['nopx']} 缺OI{r['nooi']})")
    print(f"  λ_symbol={r['lam_sym']} ({r['lam_sym']/yrs:.2f}/yr)  λ_episode={r['lam_ep']} ({r['lam_ep']/yrs:.2f}/yr)")
    print(f"  λ_cluster={r['lam_cl']} ({r['lam_cl']/yrs:.2f}/yr)  cluster内仓位数={r['sizes']}")
    print(f"  λ_slot_admitted={r['adm']}  λ_concurrency_blocked={r['blk']}")
    print(f"  方向: 正 funding {r['pos']}   负 funding {r['neg']}")
out['years']=yrs
json.dump(out,open("full_result.json","w"))
