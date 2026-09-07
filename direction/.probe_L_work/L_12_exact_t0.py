"""Probe L · 精确 T0(公告匹配测量子集 · 仅 FETCHABLE 206 条)。
T_first_trade = **该公告所列现货交易对中,T_scheduled_final 之后(含等于)的最早 aggTrade**(冻结 timestamps)。
盘前转现货用**最终更新后**的精确阶段边界(RED = 16:00),不得用当天零点。
留出集资产**根本不下载** —— 取数清单由 L_11 固定,本脚本只读该清单并再次断言无留出资产。
校验链:HTTP 200 → 官方 CHECKSUM(fail-closed)→ ZIP 完整性 → 8 列 schema → 时间戳单位 → 文件名日期。
保留:所用交易对、成交时间、成交记录、文件哈希。 用法: --canary N | --full"""
import json,os,sys,io,zipfile,hashlib,datetime,urllib.request,urllib.parse,tempfile,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
cfg,H=load([__file__,"L_00_bootstrap.py"],["L_u_master.json"])
mu=cfg["mother_universe"]; V="https://data.binance.vision/data/spot/daily/aggTrades"
U=json.load(open("L_u_master.json")); FETCH=U["fetch_list"]
FAIL=[]
def check(n,ok,got=None,want=None):
    print(f"[断言] {n}: got={got} want={want}  {'✅' if ok else '❌'}"); 
    if not ok: FAIL.append({"check":n,"got":got,"want":want})
check("上游 config 与本次一致",U["config_sha256"]==H["L_config.json"],U["config_sha256"][:12],H["L_config.json"][:12])
emb=lambda b: hashlib.sha256(b.encode()).digest()[0]%5==0
bad=[f["base_asset"] for f in FETCH if emb(f["base_asset"]) or f["embargo"]!="FETCHABLE"]
check("取数清单不含留出资产",not bad,bad[:5],[])
check("取数清单条数",len(FETCH)==mu["announcement_matched_measurement_subset"]["holdout_split"]["FETCHABLE"],
      len(FETCH),mu["announcement_matched_measurement_subset"]["holdout_split"]["FETCHABLE"])
if FAIL: sys.exit("FAIL-CLOSED:取数前置检查未通过")
os.makedirs("aggdl",exist_ok=True); os.makedirs("t0rows",exist_ok=True)
def norm_us(v:int)->int:
    d=len(str(v))
    if d==13: return v*1000
    if d==16: return v
    raise RuntimeError(f"TIMESTAMP UNIT FAIL: {v} 有 {d} 位")
def scan(sym,day,thr_us):
    """下载并流式扫描,返回 (>=thr 的最早成交行, 全日最早时间戳, 行数, 哈希)。"""
    q=urllib.parse.quote(sym,safe='')
    url=f"{V}/{q}/{q}-aggTrades-{day}.zip"
    raw=urllib.request.urlopen(url,timeout=120).read()
    local=hashlib.sha256(raw).hexdigest()
    chk=urllib.request.urlopen(url+".CHECKSUM",timeout=60).read().decode().split()[0]
    if local!=chk: raise RuntimeError("CHECKSUM MISMATCH")
    z=zipfile.ZipFile(io.BytesIO(raw))
    if z.testzip(): raise RuntimeError("ZIP CORRUPT")
    best=None; mn=None; n=0
    with z.open(z.namelist()[0]) as fh:
        for bl in io.TextIOWrapper(fh,encoding="utf-8"):
            bl=bl.strip()
            if not bl: continue
            if n==0 and bl[0].isalpha(): continue
            c=bl.split(',')
            if len(c)!=8: raise RuntimeError(f"SCHEMA FAIL: {len(c)} 列")
            t=norm_us(int(c[5])); n+=1
            if mn is None or t<mn: mn=t
            if t>=thr_us and (best is None or t<best[0]):
                best=(t,{"agg_trade_id":int(c[0]),"price":c[1],"qty":c[2],
                         "first_trade_id":int(c[3]),"last_trade_id":int(c[4]),
                         "ts_us":t,"is_buyer_maker":c[6]})
    if not n: raise RuntimeError("EMPTY CSV")
    d=datetime.datetime.fromtimestamp(mn/1_000_000,datetime.timezone.utc)
    if d.strftime("%Y-%m-%d")!=day: raise RuntimeError(f"DATE MISMATCH: {d:%Y-%m-%d}")
    return best,mn,n,local,chk
mode="--full" if "--full" in sys.argv else "--canary"
N=int(sys.argv[sys.argv.index("--canary")+1]) if "--canary" in sys.argv and len(sys.argv)>sys.argv.index("--canary")+1 else 3
todo=FETCH if mode=="--full" else FETCH[:N]
out=[]; errs=[]
for i,f in enumerate(todo,1):
    b=f["base_asset"]; day=f["T_scheduled_final"][:10]
    thr=int(datetime.datetime.fromisoformat(f["T_scheduled_final"]).timestamp()*1_000_000)
    cand=[]
    for sym in f["announced_pairs"]:
        cp=f"t0rows/{urllib.parse.quote(sym,safe='')}__{day}__{thr}.json"
        if os.path.exists(cp):
            r=json.load(open(cp))
        else:
            try:
                best,mn,n,loc,chk=scan(sym,day,thr)
            except Exception as e:
                errs.append({"base":b,"symbol":sym,"day":day,"error":f"{type(e).__name__}: {e}"}); continue
            r={"symbol":sym,"day":day,"threshold_us":thr,"day_min_ts_us":mn,"n_rows":n,
               "local_sha256":loc,"official_checksum":chk,"checksum_verified":True,
               "first_at_or_after":best[1] if best else None}
            fd,tmp=tempfile.mkstemp(dir="t0rows"); os.close(fd)
            json.dump(r,open(tmp,"w"),ensure_ascii=False); os.replace(tmp,cp)
        if r["first_at_or_after"]: cand.append(r)
    if not cand:
        out.append({**f,"T0_exact":None,"status":"NO_TRADE_AT_OR_AFTER_T_SCHEDULED"}); continue
    w=min(cand,key=lambda z:z["first_at_or_after"]["ts_us"])
    t0=w["first_at_or_after"]["ts_us"]
    tie=sorted(c["symbol"] for c in cand if c["first_at_or_after"]["ts_us"]==t0)
    out.append({**f,"T0_exact_us":t0,
        "T0_exact_iso":datetime.datetime.fromtimestamp(t0/1e6,datetime.timezone.utc).isoformat(),
        "T0_pair":w["symbol"],"T0_tied_pairs":tie,"T0_trade":w["first_at_or_after"],
        "lag_seconds":(t0-thr)/1e6,
        "evidence":[{"symbol":c["symbol"],"day":c["day"],"local_sha256":c["local_sha256"],
                     "official_checksum":c["official_checksum"],"day_min_ts_us":c["day_min_ts_us"],
                     "premarket_day_start":c["day_min_ts_us"]<thr} for c in cand],
        "status":"OK"})
    if i%20==0 or mode!="--full": print(f"  [{i}/{len(todo)}] {b:<10} T0={out[-1]['T0_exact_iso'][:19]} pair={w['symbol']} lag={out[-1]['lag_seconds']:.1f}s",flush=True)
ok=[r for r in out if r["status"]=="OK"]
print(f"\n完成 {len(out)} 条:成功 {len(ok)},无成交 {len(out)-len(ok)},下载错误 {len(errs)}")
for r in ok:
    if r["lag_seconds"]<0: check(f"{r['base_asset']} T0 不早于 T_scheduled",False,r["lag_seconds"],">=0")
res={"config_sha256":H["L_config.json"],"stage":"EXACT_T0","mode":mode,
     "subset":"announcement_matched_measurement_subset / FETCHABLE",
     "n":len(out),"n_ok":len(ok),"errors":errs,"records":out}
if mode=="--full" and not FAIL:
    json.dump(res,open("L_t0_exact_v2.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["L_t0_exact_v2.json"])
if FAIL: sys.exit(f"FAIL-CLOSED:{len(FAIL)} 项未通过")
print("全部检查通过 ✅")
