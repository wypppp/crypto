import urllib.request,json,time,threading,queue,os,sys
S=json.load(open("universe_symbols.json"))["all"]
START=1596240000000  # 2020-08-01
OUT="daily_klines"; os.makedirs(OUT,exist_ok=True)
lock=threading.Lock(); done=[0]; errs=[]
def fetch(sym):
    if os.path.exists(f"{OUT}/{sym}.json"): return
    rows=[]; st=START
    for _ in range(6):
        u=f"https://www.binance.com/fapi/v1/klines?symbol={sym}&interval=1d&startTime={st}&limit=1500"
        for attempt in range(5):
            try:
                d=json.loads(urllib.request.urlopen(u,timeout=45).read()); break
            except Exception as e:
                if attempt==4: 
                    with lock: errs.append((sym,str(e)[:60]))
                    return
                time.sleep(2*(attempt+1))
        if not d: break
        # [openTime, o,h,l,c, vol, closeTime, quoteVol, trades, ...]
        rows += [[r[0],float(r[4]),float(r[7])] for r in d]
        if len(d)<1500: break
        st=d[-1][0]+86400000
    json.dump(rows,open(f"{OUT}/{sym}.json","w"))
def worker(q):
    while True:
        s=q.get()
        if s is None: return
        fetch(s)
        with lock:
            done[0]+=1
            if done[0]%100==0: print(f"  {done[0]}/{len(S)}",flush=True)
        q.task_done()
q=queue.Queue()
ths=[threading.Thread(target=worker,args=(q,),daemon=True) for _ in range(8)]
[t.start() for t in ths]
for s in S: q.put(s)
q.join()
print(f"完成。成功={len(os.listdir(OUT))}  失败={len(errs)}")
if errs: print("  失败样例:",errs[:5])
