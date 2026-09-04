import json,os,urllib.request,zipfile,io,datetime,time,concurrent.futures as cf,threading
U=json.load(open("top20_universe.json")); MAIN=set(U["main"]); DAY=86400000
os.makedirs("metrics",exist_ok=True); os.makedirs("funding",exist_ok=True)
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc).strftime('%Y-%m-%d')
# 需要的 symbol-day(含前一日,供 24h OI 变化)
need=set()
for ms,syms in U["top20"].items():
    ms=int(ms)
    for s in syms:
        if s in MAIN: need.add((s,f_(ms))); need.add((s,f_(ms-DAY)))
need=sorted(need); print(f"metrics 需要 {len(need)} 个 symbol-day",flush=True)
lock=threading.Lock(); cnt=[0,0]
def gm(a):
    s,d=a; p=f"metrics/{s}_{d}.json"
    if os.path.exists(p): return
    try:
        raw=urllib.request.urlopen(f"https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip",timeout=45).read()
        z=zipfile.ZipFile(io.BytesIO(raw)); L=z.read(z.namelist()[0]).decode().splitlines()
        json.dump([[r.split(',')[0],r.split(',')[2]] for r in L[1:] if r],open(p,"w"))
        with lock: cnt[0]+=1
    except Exception:
        with lock: cnt[1]+=1
        json.dump([],open(p,"w"))
    with lock:
        if (cnt[0]+cnt[1])%2000==0: print(f"  metrics {cnt[0]+cnt[1]}/{len(need)} (缺{cnt[1]})",flush=True)
def gf(s):
    p=f"funding/{s}.json"
    if os.path.exists(p): return
    out=[]; st=1596240000000
    for _ in range(10):
        try:
            d=json.loads(urllib.request.urlopen(
              f"https://www.binance.com/fapi/v1/fundingRate?symbol={s}&startTime={st}&limit=1000",timeout=40).read())
        except Exception: time.sleep(2); continue
        if not d: break
        out+=[[r['fundingTime'],float(r['fundingRate'])] for r in d]
        if len(d)<1000: break
        st=d[-1]['fundingTime']+1
    json.dump(out,open(p,"w"))
t0=time.time()
with cf.ThreadPoolExecutor(6) as ex: list(ex.map(gf,sorted(MAIN)))
print(f"funding 完成 {len(os.listdir('funding'))} 个, 用时 {time.time()-t0:.0f}s",flush=True)
with cf.ThreadPoolExecutor(20) as ex: list(ex.map(gm,need))
print(f"metrics 完成: 成功 {cnt[0]}, 缺失 {cnt[1]}, 总用时 {time.time()-t0:.0f}s")
