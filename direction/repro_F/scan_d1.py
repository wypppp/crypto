import json,os,urllib.request,zipfile,io,concurrent.futures as cf,threading,collections
S=json.load(open("universe_symbols.json"))["all"]
MONTHS=[f"{y}-{m:02d}" for y in (2025,2026) for m in range(1,13)]
MONTHS=[m for m in MONTHS if "2025-04"<=m<="2026-08"]   # 多取 2025-04 作跨月前一行
os.makedirs("fr_arch",exist_ok=True)
lock=threading.Lock(); c=[0,0,0]
def one(a):
    s,ym=a; p=f"fr_arch/{s}__{ym}.json"
    if os.path.exists(p): return
    try:
        raw=urllib.request.urlopen(f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{ym}.zip",timeout=45).read()
        z=zipfile.ZipFile(io.BytesIO(raw)); L=z.read(z.namelist()[0]).decode().splitlines()
        rows=[]
        for r in L[1:]:
            q=r.split(',')
            if len(q)<3: continue
            try: rows.append([int(float(q[0])),int(float(q[1])),float(q[2])])
            except Exception: pass
        json.dump(rows,open(p,"w"))
        with lock: c[0]+=1
    except Exception:
        json.dump([],open(p,"w"))
        with lock: c[1]+=1
    with lock:
        c[2]+=1
        if c[2]%3000==0: print(f"  {c[2]} (有{c[0]} 无{c[1]})",flush=True)
tasks=[(s,m) for s in S for m in MONTHS]
print(f"任务 {len(tasks)}",flush=True)
with cf.ThreadPoolExecutor(24) as ex: list(ex.map(one,tasks))
print(f"完成: 有数据 {c[0]}, 无 {c[1]}")
