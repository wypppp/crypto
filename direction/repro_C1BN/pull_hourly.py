import json,os,urllib.request,zipfile,io,time,concurrent.futures as cf,threading
U=json.load(open("top20_universe.json")); MAIN=sorted(U["main"])
os.makedirs("hourly",exist_ok=True)
months=[f"{y}-{m:02d}" for y in range(2021,2027) for m in range(1,13)]
months=[m for m in months if "2021-08"<=m<="2026-09"]
lock=threading.Lock(); c=[0,0]
def one(a):
    s,ym=a; p=f"hourly/{s}_{ym}.json"
    if os.path.exists(p): return
    try:
        raw=urllib.request.urlopen(f"https://data.binance.vision/data/futures/um/monthly/klines/{s}/1h/{s}-1h-{ym}.zip",timeout=45).read()
        z=zipfile.ZipFile(io.BytesIO(raw)); L=z.read(z.namelist()[0]).decode().splitlines()
        rows=[]
        for r in L:
            p_=r.split(',')
            if not p_[0].replace('.','').isdigit(): continue
            rows.append([int(float(p_[0])),float(p_[4])])
        json.dump(rows,open(p,"w"))
        with lock: c[0]+=1
    except Exception:
        json.dump([],open(p,"w"))
        with lock: c[1]+=1
    with lock:
        if (c[0]+c[1])%2000==0: print(f"  hourly {c[0]+c[1]} (缺{c[1]})",flush=True)
tasks=[(s,m) for s in MAIN for m in months]
print(f"hourly 任务 {len(tasks)}",flush=True)
t0=time.time()
with cf.ThreadPoolExecutor(12) as ex: list(ex.map(one,tasks))
print(f"hourly 完成: 有数据 {c[0]}, 缺 {c[1]}, 用时 {time.time()-t0:.0f}s")
