"""Probe L · T0 **独立数值核验**。
刻意与 L_12 **不共用任何代码路径**:自行下载官方 zip、自行校验 CHECKSUM、用 csv 模块解析、
独立实现时间戳单位归一,并**逐笔累计**每个交易对的候选首笔。
**不读取** t0rows / aggdl 任何摘要缓存;L_t0_exact_v2.json 仅在最后作为**比较对象**读入。
样本由 config.mother_universe.independent_verification 冻结(先固定后执行)。
用法: [--full]"""
import json,os,sys,io,csv,zipfile,hashlib,urllib.request,urllib.parse,datetime,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
cfg,H=load([__file__,"L_00_bootstrap.py"],["L_u_master.json","L_t0_exact_v2.json"])
IV=cfg["mother_universe"]["independent_verification"]
BASE="https://data.binance.vision/data/spot/daily/aggTrades"
FAIL=[]
def check(n,ok,got=None,want=None):
    print(f"[断言] {n}: got={got} want={want}  {'✅' if ok else '❌'}")
    if not ok: FAIL.append({"check":n,"got":got,"want":want})

# ---- 独立实现:单位归一(按数量级判定,不复用 L_12) ----
def to_us(raw):
    v=int(raw); n=len(raw.lstrip('-'))
    if n==13: return v*1000          # 毫秒
    if n==16: return v               # 微秒
    raise ValueError(f"未知时间戳位数 {n}: {raw}")

def pull(symbol,day):
    """独立下载与解析。返回 (rows_iter 汇总结果, sha256, 官方 checksum, 行数)。"""
    enc=urllib.parse.quote(symbol,safe='')
    u=f"{BASE}/{enc}/{enc}-aggTrades-{day}.zip"
    blob=urllib.request.urlopen(u,timeout=120).read()
    mine=hashlib.sha256(blob).hexdigest()
    official=urllib.request.urlopen(u+".CHECKSUM",timeout=60).read().split()[0].decode()
    if mine!=official: raise RuntimeError("checksum 不符")
    zf=zipfile.ZipFile(io.BytesIO(blob))
    names=zf.namelist()
    if len(names)!=1: raise RuntimeError(f"zip 内文件数 {len(names)}")
    return blob,mine,official,zf,names[0]

def scan_pair(symbol,day,thr_us):
    blob,mine,official,zf,name=pull(symbol,day)
    earliest_any=None; first_ge=None; count=0
    with zf.open(name) as raw:
        rd=csv.reader(io.TextIOWrapper(raw,encoding="utf-8"))
        for row in rd:
            if not row: continue
            if count==0 and not row[0].lstrip('-').isdigit(): continue   # 表头
            if len(row)!=8: raise RuntimeError(f"列数 {len(row)}")
            ts=to_us(row[5]); count+=1
            if earliest_any is None or ts<earliest_any: earliest_any=ts
            if ts>=thr_us:
                if first_ge is None or ts<first_ge[0]:
                    first_ge=(ts,{"agg_trade_id":int(row[0]),"price":row[1],"qty":row[2],
                                  "first_trade_id":int(row[3]),"last_trade_id":int(row[4]),
                                  "ts_us":ts,"is_buyer_maker":row[6]})
    if count==0: raise RuntimeError("空文件")
    return {"symbol":symbol,"day":day,"n_rows":count,"day_min_ts_us":earliest_any,
            "first_at_or_after":first_ge[1] if first_ge else None,
            "sha256":mine,"official_checksum":official}

U=json.load(open("L_u_master.json")); FETCH={f["base_asset"]:f for f in U["fetch_list"]}
sel=sorted(set(IV["selected"]["lag_positive"])|set(IV["selected"]["premarket"])|set(IV["selected"]["ontime"]))
check("样本数与冻结一致",len(sel)==IV["selected"]["n_total"],len(sel),IV["selected"]["n_total"])
hold=lambda b: hashlib.sha256(b.encode()).digest()[0]%5==0
check("样本不含留出资产",not [b for b in sel if hold(b)],[b for b in sel if hold(b)][:5],[])
if FAIL: sys.exit("FAIL-CLOSED:样本前置检查未通过")

mine_out={}; errs=[]
for i,b in enumerate(sel,1):
    f=FETCH[b]; day=f["T_scheduled_final"][:10]
    thr=int(datetime.datetime.fromisoformat(f["T_scheduled_final"]).timestamp()*1_000_000)
    per={}
    for sym in f["announced_pairs"]:
        try: per[sym]=scan_pair(sym,day,thr)
        except Exception as e: errs.append({"base":b,"symbol":sym,"error":f"{type(e).__name__}: {e}"})
    withtr={s:r for s,r in per.items() if r["first_at_or_after"]}
    if withtr:
        m=min(r["first_at_or_after"]["ts_us"] for r in withtr.values())
        tied=sorted(s for s,r in withtr.items() if r["first_at_or_after"]["ts_us"]==m)
        win=withtr[tied[0]]
    else: m=None; tied=[]; win=None
    mine_out[b]={"threshold_us":thr,"day":day,"pairs":per,"pairs_failed":sorted(set(f["announced_pairs"])-set(per)),
                 "T0_us":m,"tied":tied,"trade":win["first_at_or_after"] if win else None}
    print(f"  [{i}/{len(sel)}] {b:<12} 对={len(per)}/{len(f['announced_pairs'])} T0={m} tied={tied}",flush=True)

# ---------- 与 L_12 产物逐项比较 ----------
R={r["base_asset"]:r for r in json.load(open("L_t0_exact_v2.json"))["records"]}
dif=collections.defaultdict(list)
for b,v in mine_out.items():
    o=R[b]
    if o["status"]!="VERIFIED_COMPLETE":
        dif["状态非完整验收"].append(b); continue
    if v["pairs_failed"]: dif["独立复算存在取不到的交易对"].append((b,v["pairs_failed"]))
    if v["T0_us"]!=o["T0_exact_us"]: dif["T0 数值不一致"].append((b,v["T0_us"],o["T0_exact_us"]))
    if v["tied"]!=sorted(o["T0_tied_pairs"]): dif["并列集合不一致"].append((b,v["tied"],sorted(o["T0_tied_pairs"])))
    if v["trade"]!=o["T0_trade"]: dif["成交记录不一致"].append((b,v["trade"],o["T0_trade"]))
    ev={e["symbol"]:e for e in o.get("evidence",[])}
    for s,r in v["pairs"].items():
        if s not in ev: dif["证据缺该交易对"].append((b,s)); continue
        if r["day_min_ts_us"]!=ev[s]["day_min_ts_us"]:
            dif["当日最早时间戳不一致"].append((b,s,r["day_min_ts_us"],ev[s]["day_min_ts_us"]))
        if r["sha256"]!=ev[s]["local_sha256"]:
            dif["文件哈希不一致"].append((b,s,r["sha256"][:12],ev[s]["local_sha256"][:12]))
print(f"\n下载错误 {len(errs)}: {errs[:3]}")
for k in ("T0 数值不一致","并列集合不一致","成交记录不一致","当日最早时间戳不一致","文件哈希不一致",
          "证据缺该交易对","独立复算存在取不到的交易对","状态非完整验收"):
    check(f"独立复算 · {k}",not dif[k],dif[k][:3],[])
check("独立复算全部交易对已取证",not errs or all(e["symbol"]=="NOTBTC" for e in errs),
      [e["symbol"] for e in errs][:5],"仅允许已知缺失 NOTBTC")
res={"config_sha256":H["L_config.json"],"stage":"INDEPENDENT_VERIFY_T0",
     "n_events":len(sel),"n_pairs":sum(len(v["pairs"]) for v in mine_out.values()),
     "errors":errs,"diffs":{k:v for k,v in dif.items() if v},"recomputed":mine_out}
if FAIL:
    for f_ in FAIL: print(f"  ❌ {f_['check']}  got={f_['got']}  want={f_['want']}")
    json.dump(res,open("L_t0_verify.json","w"),ensure_ascii=False,indent=1)
    sys.exit(f"FAIL-CLOSED:{len(FAIL)} 项不一致")
json.dump(res,open("L_t0_verify.json","w"),ensure_ascii=False,indent=1)
record_outputs(["L_t0_verify.json"])
print("\n独立复算与 L_12 完全一致 ✅")
