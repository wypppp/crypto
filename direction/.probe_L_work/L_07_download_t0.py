"""Probe L · 下载最早日 aggTrades 并求精确 T0。**只读已冻结 t0_manifest.json,不重算母体/留出。**
校验链:HTTP 200 → 官方 CHECKSUM(**fail-closed**)→ ZIP 完整性 → 7 列 schema → 文件名日期 → 时间戳单位。
ZIP **流式解析**,不把全文与全部时间戳同时载入内存。写入用临时文件 + 原子改名。
T0 = 该 baseAsset 全部并列文件中实际时间戳的最小值(整数微秒)。
用法: --canary | --agg-canary BASE | --full"""
import json,os,sys,io,zipfile,hashlib,datetime,urllib.request,urllib.error,urllib.parse,tempfile,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
cfg,H=load([__file__,"L_00_bootstrap.py"],["t0_manifest.json"])
V="https://data.binance.vision/data/spot/daily/aggTrades"
MJ=json.load(open("t0_manifest.json"))
MAN=MJ["download_manifest"]; EMB={r["base"] for r in MJ["embargoed"]}
os.makedirs("aggdl",exist_ok=True)
def norm_us(v:int)->int:
    d=len(str(v))
    if d==13: return v*1000
    if d==16: return v
    raise RuntimeError(f"TIMESTAMP UNIT FAIL: {v} 有 {d} 位")
def fetch(sym,day):
    q=urllib.parse.quote(sym,safe='')
    url=f"{V}/{q}/{q}-aggTrades-{day}.zip"
    raw=urllib.request.urlopen(url,timeout=90).read()
    local=hashlib.sha256(raw).hexdigest()
    try:                                            # fail-closed:取不到 CHECKSUM 即失败
        chk=urllib.request.urlopen(url+".CHECKSUM",timeout=45).read().decode().split()[0]
    except Exception as e:
        raise RuntimeError(f"CHECKSUM UNAVAILABLE ({getattr(e,'code',type(e).__name__)})")
    if local!=chk: raise RuntimeError("CHECKSUM MISMATCH")
    z=zipfile.ZipFile(io.BytesIO(raw))
    if z.testzip(): raise RuntimeError("ZIP CORRUPT")
    mn=None; n=0
    with z.open(z.namelist()[0]) as fh:             # 流式,不 materialize
        for bl in io.TextIOWrapper(fh,encoding="utf-8"):
            bl=bl.strip()
            if not bl: continue
            if n==0 and bl[0].isalpha(): continue   # 可能的表头
            c=bl.split(',')
            if len(c)!=8: raise RuntimeError(f"SCHEMA FAIL: {len(c)} 列(应为 8)")   # 实测 2021-2026 全为 8 列
            t=norm_us(int(c[5])); n+=1
            if mn is None or t<mn: mn=t
    if not n: raise RuntimeError("EMPTY CSV")
    d=datetime.datetime.fromtimestamp(mn/1_000_000,datetime.timezone.utc)
    if d.strftime("%Y-%m-%d")!=day: raise RuntimeError(f"DATE MISMATCH: 归一后 {d:%Y-%m-%d}")
    if not (2017<=d.year<=2027): raise RuntimeError(f"YEAR OUT OF RANGE: {d.year}")
    rec={"symbol":sym,"day":day,"min_ts_us":mn,"n_rows":n,"official_checksum":chk,
         "local_sha256":local,"checksum_verified":True,"schema_columns":8}
    fd,tmp=tempfile.mkstemp(dir="aggdl"); os.close(fd)
    json.dump(rec,open(tmp,"w"),ensure_ascii=False); os.replace(tmp,f"aggdl/{q}__{day}.json")
    return rec
REQ_FIELDS={"symbol","day","min_ts_us","n_rows","official_checksum","local_sha256","checksum_verified","schema_columns"}
def cache_ok(p,sym,day):
    """缓存准入:字段完整 + symbol/day 一致 + checksum_verified + 官方==本地 + schema 8 列"""
    try: r=json.load(open(p))
    except Exception: return False
    if not isinstance(r,dict) or not REQ_FIELDS.issubset(r): return False
    if r["symbol"]!=sym or r["day"]!=day: return False
    if r.get("checksum_verified") is not True: return False
    if r.get("official_checksum")!=r.get("local_sha256"): return False
    if r.get("schema_columns")!=8: return False
    if not isinstance(r.get("min_ts_us"),int) or len(str(r["min_ts_us"]))!=16: return False
    return True

def run(tasks,label):
    ok=[];bad=[]
    for i,(b,s,d) in enumerate(tasks,1):
        p=f"aggdl/{urllib.parse.quote(s,safe='')}__{d}.json"
        if os.path.exists(p):
            if cache_ok(p,s,d): ok.append((b,json.load(open(p)))); continue
            os.remove(p)                       # 不合格缓存一律拒收并重取
        try: ok.append((b,fetch(s,d)))
        except Exception as e: bad.append({"base":b,"symbol":s,"day":d,"err":str(e)[:120]})
        if i%100==0: print(f"  {label} {i}/{len(tasks)} ok={len(ok)} fail={len(bad)}",flush=True)
    return ok,bad
def expand(rows):
    t=[(r["base"],s,r["earliest_trade_day"]) for r in rows for s in r["tied_pairs"]]
    assert len(t)==len(set(t)), "任务有重复"
    assert not ({b for b,_,_ in t} & EMB), "任务集含留出标的"
    return t
MODE=[a for a in sys.argv[1:] if a.startswith("--")]
if "--canary" in MODE:
    pick=[]
    for yr in ("2024","2025","2026"):
        for r in MAN:
            if r["earliest_trade_day"].startswith(yr) and len(pick)<3:
                pick.append((r["base"],r["tied_pairs"][0],r["earliest_trade_day"])); break
    for r in MAN:
        if any(ord(c)>127 for c in r["base"]): pick.append((r["base"],r["tied_pairs"][0],r["earliest_trade_day"])); break
    ok,bad=run(pick,"canary")
    for b,r in ok: print(f"  ✅ {r['symbol']:<16}{r['day']}  min_ts_us={r['min_ts_us']}  rows={r['n_rows']}  checksum={r['checksum_verified']}")
    print("CANARY 全部通过" if not bad else f"CANARY 失败: {bad}"); sys.exit(0 if not bad else 1)
if "--agg-canary" in MODE:
    tgt=sys.argv[sys.argv.index("--agg-canary")+1]
    r=[x for x in MAN if x["base"]==tgt]
    if not r: sys.exit(f"{tgt} 不在下载清单")
    r=r[0]; print(f"聚合 canary: {tgt}  并列对 {r['n_tied']} 个  日期 {r['earliest_trade_day']}")
    ok,bad=run(expand([r]),"agg")
    if bad: sys.exit(f"失败: {bad}")
    for b,x in sorted(ok,key=lambda y:y[1]['min_ts_us']):
        print(f"    {x['symbol']:<18}min_ts_us={x['min_ts_us']}  rows={x['n_rows']:>7}")
    T0=min(x['min_ts_us'] for _,x in ok)
    print(f"  ⟹ T0(全部并列对最小)= {T0} = "
          f"{datetime.datetime.fromtimestamp(T0/1e6,datetime.timezone.utc):%Y-%m-%d %H:%M:%S.%f} UTC")
    print(f"  [断言] 聚合覆盖 {len(ok)}/{r['n_tied']} 个并列对  {'✅' if len(ok)==r['n_tied'] else '❌'}"); sys.exit(0)
if "--full" in MODE:
    tasks=expand(MAN)
    print(f"[断言] 唯一任务数={len(tasks)}  期望=880  {'✅' if len(tasks)==880 else '❌'}")
    print(f"[断言] 任务集 ∩ 留出集 == ∅  ✅（expand 已校验）")
    assert len(tasks)==880, f"任务数 {len(tasks)} != 880"
    ok,bad=run(tasks,"full")
    byb=collections.defaultdict(list)
    for b,r in ok: byb[b].append(r)
    out={}
    for b,rs in byb.items():
        out[b]={"T0_us":min(x["min_ts_us"] for x in rs),
                "T0_utc":datetime.datetime.fromtimestamp(min(x["min_ts_us"] for x in rs)/1e6,datetime.timezone.utc).isoformat(),
                "n_tied":len(rs),"files":sorted(rs,key=lambda x:x["symbol"])}
    print(f"\n[断言] 文件 成功={len(ok)}/880 失败={len(bad)}  {'✅' if len(ok)==880 and not bad else '❌'}")
    print(f"[断言] baseAsset 有 T0 = {len(out)}/282  {'✅' if len(out)==282 else '❌'}")
    print(f"[断言] downloaded ∩ embargoed == ∅  {'✅' if not (set(out)&EMB) else '❌'}")
    ks={tuple(sorted(x.keys())) for _,x in ok}
    print(f"[断言] 880 个文件字段集合统一 = {len(ks)} 种  {'✅' if len(ks)==1 else '❌ '+str(ks)}")
    nz=[x for _,x in ok if x.get("official_checksum")!=x.get("local_sha256")]
    print(f"[断言] 官方 checksum == 本地 SHA-256 全部一致  {'✅' if not nz else '❌ '+str(len(nz))}")
    if bad: print(f"  失败明细(前 10): {bad[:10]}")
    json.dump({"config_sha256":H["L_config.json"],"n_files":len(ok),"n_bases":len(out),
               "failures":bad,"t0":out},open("t0_exact.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["t0_exact.json"]); sys.exit(0 if len(ok)==880 and not bad else 1)
print(f"下载清单: {len(MAN)} 个 baseAsset,{sum(r['n_tied'] for r in MAN)} 个文件")
print("用法: --canary | --agg-canary BASE | --full")
