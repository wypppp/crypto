"""Probe L · 精确 T0(公告匹配测量子集 · 仅 FETCHABLE 206 条)。
T_first_trade = **该公告所列现货交易对中,T_scheduled_final 之后(含等于)的最早 aggTrade**(冻结 timestamps)。
盘前转现货用**最终更新后**的精确阶段边界(RED = 16:00),不得用当天零点。
留出集资产**根本不下载** —— 取数清单由 L_11 固定,本脚本只读该清单并再次断言无留出资产。
校验链:HTTP 200 → 官方 CHECKSUM(fail-closed)→ ZIP 完整性 → 8 列 schema → 时间戳单位 → 文件名日期。
保留:所用交易对、成交时间、成交记录、文件哈希。 用法: --canary N | --full"""
import json,os,sys,io,zipfile,hashlib,datetime,urllib.request,urllib.parse,tempfile,collections,math
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
REC_FIELDS={"symbol","day","threshold_us","day_min_ts_us","n_rows",
            "local_sha256","official_checksum","checksum_verified","first_at_or_after"}
TRADE_FIELDS={"agg_trade_id","price","qty","first_trade_id","last_trade_id","ts_us","is_buyer_maker"}
def utc_day(us): return datetime.datetime.fromtimestamp(us/1_000_000,datetime.timezone.utc).strftime("%Y-%m-%d")
def record_ok(r,sym,day,thr):
    """记录准入(v1.8.36)。**缓存与新下载调用同一个函数** —— v1.8.35 只在缓存路径调用,
    新下载构造的记录从不验证。除元数据外,**必须验证实际用于计算 T0 的成交行**:
    审查实证仅把 first_at_or_after.ts_us 改为阈值前 1 微秒,事件仍标 VERIFIED_COMPLETE。"""
    if os.environ.get("NEG_BYPASS_ADMISSION"): return True,None      # 仅反例
    if not isinstance(r,dict) or not REC_FIELDS.issubset(r): return False,"MISSING_FIELDS"
    if r["symbol"]!=sym: return False,"SYMBOL_MISMATCH"
    if r["day"]!=day: return False,"DAY_MISMATCH"
    if r["threshold_us"]!=thr: return False,"THRESHOLD_MISMATCH"
    if r.get("checksum_verified") is not True: return False,"NOT_CHECKSUM_VERIFIED"
    if r.get("official_checksum")!=r.get("local_sha256"): return False,"CHECKSUM_MISMATCH"
    if not isinstance(r.get("n_rows"),int) or r["n_rows"]<=0: return False,"BAD_N_ROWS"
    m=r.get("day_min_ts_us")
    if not isinstance(m,int) or len(str(m))!=16: return False,"BAD_DAY_MIN_UNIT"
    if utc_day(m)!=day: return False,"DAY_MIN_DATE_MISMATCH"
    t=r.get("first_at_or_after")                                     # 可为 None(当日无 >=阈值 成交)
    if t is None: return True,None
    if not isinstance(t,dict) or not TRADE_FIELDS.issubset(t): return False,"TRADE_MISSING_FIELDS"
    ts=t.get("ts_us")
    if not isinstance(ts,int) or isinstance(ts,bool): return False,"TRADE_TS_NOT_INT"
    if len(str(ts))!=16: return False,"TRADE_TS_UNIT"
    if ts<thr: return False,"TRADE_TS_BEFORE_THRESHOLD"                # 审查反例正中此处
    if ts<m: return False,"TRADE_TS_BEFORE_DAY_MIN"
    if utc_day(ts)!=day: return False,"TRADE_DATE_MISMATCH"
    for k in ("agg_trade_id","first_trade_id","last_trade_id"):
        if not isinstance(t[k],int) or isinstance(t[k],bool) or t[k]<0: return False,f"TRADE_BAD_{k.upper()}"
    if t["last_trade_id"]<t["first_trade_id"]: return False,"TRADE_ID_ORDER"
    try:                                    # v1.8.37:须**有限且为正**;float("nan")<=0 与
        pv=float(t["price"]); qv=float(t["qty"])   # float("inf")<=0 均为 False,会漏放行
    except Exception: return False,"TRADE_NUMERIC_PARSE"
    if not (math.isfinite(pv) and math.isfinite(qv)): return False,"TRADE_NOT_FINITE"
    if pv<=0 or qv<=0: return False,"TRADE_NONPOSITIVE"
    if str(t["is_buyer_maker"]) not in ("True","False","true","false"): return False,"TRADE_BAD_FLAG"
    return True,None
mode="--full" if "--full" in sys.argv else "--canary"
N=int(sys.argv[sys.argv.index("--canary")+1]) if "--canary" in sys.argv and len(sys.argv)>sys.argv.index("--canary")+1 else 3
todo=FETCH if mode=="--full" else FETCH[:N]
out=[]; errs=[]
FORCE_FAIL=set(filter(None,os.environ.get("NEG_FAIL_PAIR","").split(",")))   # 反例注入
for i,f in enumerate(todo,1):
    b=f["base_asset"]; day=f["T_scheduled_final"][:10]
    thr=int(datetime.datetime.fromisoformat(f["T_scheduled_final"]).timestamp()*1_000_000)
    cand=[]; failed=[]
    for sym in f["announced_pairs"]:
        cp=f"t0rows/{urllib.parse.quote(sym,safe='')}__{day}__{thr}.json"
        if sym in FORCE_FAIL:
            failed.append({"symbol":sym,"reason":"INJECTED_FAILURE"}); errs.append({"base":b,"symbol":sym,"day":day,"error":"INJECTED_FAILURE"}); continue
        r=None
        if os.path.exists(cp):
            try: r=json.load(open(cp))
            except Exception: r=None
            good,why=record_ok(r,sym,day,thr) if r is not None else (False,"UNREADABLE")
            if not good:
                # 缓存未通过准入 ⟹ **进入证据不完整**,不静默丢弃、不静默重下。
                # 需重取时显式删除该缓存文件或加 --refresh。
                if "--refresh" in sys.argv:
                    r=None
                else:
                    failed.append({"symbol":sym,"reason":"CACHE_ADMISSION_FAILED","detail":why})
                    errs.append({"base":b,"symbol":sym,"day":day,"error":f"CACHE_ADMISSION_FAILED: {why}"})
                    continue
        if r is None:
            try:
                best,mn,n,loc,chk=scan(sym,day,thr)
            except Exception as e:
                # v1.8.33:交易对级失败**阻断该事件的完整验收** —— 其余交易对成功
                # 不能证明失败的交易对没有更早成交。
                why="ARCHIVE_EVIDENCE_MISSING" if "404" in str(e) else f"{type(e).__name__}"
                failed.append({"symbol":sym,"reason":why,"detail":f"{type(e).__name__}: {e}"})
                errs.append({"base":b,"symbol":sym,"day":day,"error":f"{type(e).__name__}: {e}"}); continue
            r={"symbol":sym,"day":day,"threshold_us":thr,"day_min_ts_us":mn,"n_rows":n,
               "local_sha256":loc,"official_checksum":chk,"checksum_verified":True,
               "first_at_or_after":best[1] if best else None}
            good,why=record_ok(r,sym,day,thr)          # v1.8.36:新下载走**同一个**验证函数
            if not good:
                failed.append({"symbol":sym,"reason":"DOWNLOAD_RECORD_REJECTED","detail":why})
                errs.append({"base":b,"symbol":sym,"day":day,"error":f"DOWNLOAD_RECORD_REJECTED: {why}"}); continue
            fd,tmp=tempfile.mkstemp(dir="t0rows"); os.close(fd)
            json.dump(r,open(tmp,"w"),ensure_ascii=False); os.replace(tmp,cp)
        if r["first_at_or_after"]: cand.append(r)
        else: cand.append(r)                       # 已验证但当日无 >=阈值成交,仍算已验证
    verified=[c for c in cand if c.get("checksum_verified") is True]
    withtr=[c for c in verified if c["first_at_or_after"]]
    # v1.8.35:结构性完整 —— **已验证交易对的完整集合必须与公告清单一致**。
    # 只查 len(failed)==0 会漏掉任何"被过滤但未记入 failed"的路径(审查实证:缓存
    # checksum_verified=false 时记录被静默滤除,事件仍标完整)。
    vs=sorted({c["symbol"] for c in verified}); ann=sorted(set(f["announced_pairs"]))
    missing=[x for x in ann if x not in vs]
    for m in missing:
        if not any(z["symbol"]==m for z in failed):
            failed.append({"symbol":m,"reason":"NOT_IN_VERIFIED_SET","detail":"已验证集合缺该对且无失败记录"})
    complete=(len(failed)==0 and vs==ann)
    base_rec={**f,"pairs_announced":len(f["announced_pairs"]),
              "pairs_verified":sorted(c["symbol"] for c in verified),
              "pairs_failed":failed,"evidence_complete":complete}
    if not withtr:
        out.append({**base_rec,"T0_exact_us":None,
            "status":"NO_TRADE_AT_OR_AFTER" if complete else "INCOMPLETE_PAIR_EVIDENCE"}); continue
    w=min(withtr,key=lambda z:z["first_at_or_after"]["ts_us"])
    t0=w["first_at_or_after"]["ts_us"]
    tie=sorted(c["symbol"] for c in withtr if c["first_at_or_after"]["ts_us"]==t0)
    # 独立于筛选条件的『是否存在更早成交』检查:当日最早时间戳 < 阈值
    earlier=[{"symbol":c["symbol"],"day_min_ts_us":c["day_min_ts_us"]} for c in verified if c["day_min_ts_us"]<thr]
    out.append({**base_rec,
        "T0_exact_us":t0 if complete else None,
        "T0_observed_us":t0,
        "T0_observed_iso":datetime.datetime.fromtimestamp(t0/1e6,datetime.timezone.utc).isoformat(),
        "T0_pair":w["symbol"],"T0_tied_pairs":tie,"T0_trade":w["first_at_or_after"],
        "lag_seconds":(t0-thr)/1e6,
        "pairs_trading_before_threshold":earlier,
        "evidence":[{"symbol":c["symbol"],"day":c["day"],"local_sha256":c["local_sha256"],
                     "official_checksum":c["official_checksum"],"day_min_ts_us":c["day_min_ts_us"]} for c in verified],
        "status":"VERIFIED_COMPLETE" if complete else "INCOMPLETE_PAIR_EVIDENCE",
        "caveat":None if complete else "存在未取证的公告所列交易对 ⟹ T0_observed 只是**已观测交易对中的最早成交**,不排除失败交易对有更早成交"})
    if i%20==0 or mode!="--full":
        r=out[-1]; print(f"  [{i}/{len(todo)}] {b:<10} T0={r['T0_observed_iso'][:19]} pair={r['T0_pair']} lag={r['lag_seconds']:.1f}s {r['status']}",flush=True)
vc=[r for r in out if r["status"]=="VERIFIED_COMPLETE"]
inc=[r for r in out if r["status"]=="INCOMPLETE_PAIR_EVIDENCE"]
nt=[r for r in out if r["status"]=="NO_TRADE_AT_OR_AFTER"]
print(f"\n完成 {len(out)} 条:完整验收 {len(vc)},证据不完整 {len(inc)},无成交 {len(nt)},交易对级失败 {len(errs)}")
for r in inc: print(f"  ⚠ {r['base_asset']:<10} 未取证对={[x['symbol'] for x in r['pairs_failed']]} 原因={[x['reason'] for x in r['pairs_failed']]}")
E=mu.get("exact_t0_expectations",{})
if E:
    check("完整验收条数",len(vc)==E["verified_complete"],len(vc),E["verified_complete"])
    check("证据不完整条数",len(inc)==E["incomplete"],len(inc),E["incomplete"])
    check("证据不完整清单",sorted(r["base_asset"] for r in inc)==sorted(E["incomplete_assets"]),
          sorted(r["base_asset"] for r in inc),sorted(E["incomplete_assets"]))
check("完整验收者的 T0_exact_us 非空",all(r["T0_exact_us"] for r in vc),
      sum(1 for r in vc if not r["T0_exact_us"]),0)
check("证据不完整者不得给出 T0_exact_us",all(r["T0_exact_us"] is None for r in inc),
      [r["base_asset"] for r in inc if r["T0_exact_us"] is not None],[])
check("完整验收者:已验证集合 == 公告清单",
      all(sorted(r["pairs_verified"])==sorted(set(r["announced_pairs"])) for r in vc),
      [r["base_asset"] for r in vc if sorted(r["pairs_verified"])!=sorted(set(r["announced_pairs"]))][:5],[])
check("完整验收者:已验证对数 == 公告对数",
      all(len(r["pairs_verified"])==len(set(r["announced_pairs"])) for r in vc),
      [(r["base_asset"],len(r["pairs_verified"]),len(set(r["announced_pairs"]))) for r in vc
       if len(r["pairs_verified"])!=len(set(r["announced_pairs"]))][:5],[])
# v1.8.36:写出前的**独立**时间约束断言 —— 不复用 record_ok,直接核验产物本身
viol=[]
for r in out:
    t0=r.get("T0_exact_us")
    if t0 is None: continue
    thr=int(datetime.datetime.fromisoformat(r["T_scheduled_final"]).timestamp()*1_000_000)
    day=r["T_scheduled_final"][:10]; tr=r.get("T0_trade") or {}
    if t0<thr: viol.append((r["base_asset"],"T0<阈值",t0,thr))
    if utc_day(t0)!=day: viol.append((r["base_asset"],"UTC 日期不符",utc_day(t0),day))
    if tr.get("ts_us")!=t0: viol.append((r["base_asset"],"T0_trade.ts_us 与 T0 不一致",tr.get("ts_us"),t0))
    if r.get("lag_seconds",0)<0: viol.append((r["base_asset"],"lag<0",r.get("lag_seconds"),">=0"))
    for e in r.get("evidence",[]):
        if e["symbol"]==r.get("T0_pair") and t0<e["day_min_ts_us"]:
            viol.append((r["base_asset"],"T0 早于该对当日最早成交",t0,e["day_min_ts_us"]))
check("非空精确 T0 全部满足时间约束",not viol,viol[:5],[])
check("所有已验证交易对均通过官方 CHECKSUM",
      all(e["local_sha256"]==e["official_checksum"] for r in out for e in r.get("evidence",[])),True,True)
pre=[(r["base_asset"],x["symbol"]) for r in out for x in r.get("pairs_trading_before_threshold",[])]
print(f"\n[独立检查] 当日最早成交**早于**阈值的交易对(不依赖筛选条件): {len(pre)} {pre}")
res={"config_sha256":H["L_config.json"],"stage":"EXACT_T0","mode":mode,
     "subset":"announcement_matched_measurement_subset / FETCHABLE",
     "n":len(out),"n_verified_complete":len(vc),"n_incomplete":len(inc),"n_no_trade":len(nt),
     "pairs_trading_before_threshold":pre,"errors":errs,"records":out}
if mode=="--full" and not FAIL:
    json.dump(res,open("L_t0_exact_v2.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["L_t0_exact_v2.json"])
if FAIL: sys.exit(f"FAIL-CLOSED:{len(FAIL)} 项未通过")
print("全部检查通过 ✅")
