"""Probe L · 公告正文抓取(config v1.4.1)。
expected_ids 由 ann_raw 按冻结窗口算出,不依赖已存在文件。
限流策略:突发额度用尽后自适应收敛到 10–12s/请求;读取 Retry-After;随机抖动;失败项轮转队尾。
标题**只用于优先级排序**,绝不用于删减 expected_ids。"""
import json,os,urllib.request,time,datetime,sys,random,re,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load
cfg,_=load([__file__,"L_00_bootstrap.py"],["ann_raw.json"])
mu=cfg["mother_universe"]
W0=datetime.datetime.fromisoformat(mu["window_start_utc"]).replace(tzinfo=datetime.timezone.utc)-datetime.timedelta(days=mu["lookback_days"])
W1=datetime.datetime.fromisoformat(mu["window_end_utc"]).replace(tzinfo=datetime.timezone.utc)+datetime.timedelta(days=1)
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)
A=json.load(open("ann_raw.json"))
expected={a["id"]:a for a in A if W0<=f_(a["releaseDate"])<W1}
assert len(expected)==mu["expected_count_in_window"], f"窗口内 {len(expected)} != config {mu['expected_count_in_window']}"
print(f"expected_ids = {len(expected)}",flush=True)
os.makedirs("ann_body",exist_ok=True)
def flat(n,out):
    if isinstance(n,dict):
        if n.get("node")=="text": out.append(n.get("text",""))
        for c in n.get("child",[]) or []: flat(c,out)
    elif isinstance(n,list):
        for c in n: flat(c,out)
def ok_state(i):
    p=f"ann_body/{i}.json"
    if not os.path.exists(p): return False
    try: r=json.load(open(p))
    except Exception: return False
    return r.get("http")==200 and bool(r.get("text"))
PRI=re.compile(r'will list|will add|new trading pair|adds? .*on binance spot',re.I)
SKIP=re.compile(r'futures will (launch|list)|margin|earn|launchpool|convert|collateral|trading bots',re.I)
def rank(i):
    t=expected[i]["title"]
    return 0 if (PRI.search(t) and not SKIP.search(t)) else (2 if SKIP.search(t) else 1)
q=collections.deque(sorted([i for i in expected if not ok_state(i)],key=rank))
print(f"pending = {len(q)}  (优先{sum(1 for i in q if rank(i)==0)}/中性{sum(1 for i in q if rank(i)==1)}/后置{sum(1 for i in q if rank(i)==2)})",flush=True)
EP=mu["detail_endpoint"]
_ad=mu["crawl"]["adaptive"]      # 参数一律来自 config,代码内不硬编码
BURST=_ad["burst_start_seconds"]; FLOOR=_ad["floor_on_429_seconds"]; MAXD=_ad["max_seconds"]
delay=BURST; ok=0; codes=collections.Counter(); rot=0; t0=time.time()
while q:
    i=q.popleft(); a=expected[i]
    try:
        rq=urllib.request.Request(EP.format(code=a["code"]),headers={'User-Agent':'Mozilla/5.0'})
        resp=urllib.request.urlopen(rq,timeout=45)
        d=json.loads(resp.read())["data"]; o=[]
        flat(json.loads(d["body"]) if isinstance(d["body"],str) else d["body"],o)
        json.dump({"id":i,"code":a["code"],"title":a["title"],"releaseDate":a["releaseDate"],
                   "http":200,"text":" ".join(o)},open(f"ann_body/{i}.json","w"),ensure_ascii=False)
        ok+=1; codes["200"]+=1
        delay=max(BURST,delay*0.90)                       # 成功则缓慢加速,但不低于突发起步
    except Exception as e:
        c=str(getattr(e,'code',type(e).__name__)); codes[c]+=1
        ra=None
        try: ra=float(dict(getattr(e,'headers',{}) or {}).get('Retry-After') or 0)
        except Exception: ra=None
        if c=="429":
            delay=min(MAXD,max(FLOOR,delay*1.8))          # 收敛到 10–12s 量级
            if ra: time.sleep(min(120.0,ra))
        q.append(i); rot+=1                               # 失败轮转队尾,不阻塞单篇
    if (ok+rot)%100==0 and ok:
        el=(time.time()-t0)/60
        print(f"  ok={ok} 队列={len(q)} 轮转={rot} delay={delay:.1f}s 速率={ok/max(el,.01):.1f}/分 {dict(codes)}",flush=True)
    time.sleep(delay*(0.85+0.3*random.random()))          # 抖动
succ={i for i in expected if ok_state(i)}
miss=set(expected)-succ
extra={int(f[:-5]) for f in os.listdir("ann_body") if f[:-5].isdigit()}-set(expected)
print(f"\n[完整性] success={len(succ)} expected={len(expected)} missing={len(miss)} extra={len(extra)}  状态={dict(codes)}")
json.dump({"expected":len(expected),"success":len(succ),"missing":sorted(miss),"extra":sorted(extra),
           "codes":dict(codes)},open("crawl_report.json","w"))
print("  ✅ 断言通过" if not miss and not extra else "  ⚠ 断言未通过,不得进入分类阶段")
