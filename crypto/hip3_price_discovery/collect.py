#!/usr/bin/env python3
"""HIP-3 闭市残差实验采集器 — 依据 PREREG_v4_2026-08-29.md (35970d23…34067942)
用法:  python3 collect.py observe   # 21:00 ET 建仓侧
       python3 collect.py exit      # 09:35 ET 平仓侧
只读。不下单。"""
import json,sys,math,time,datetime,urllib.request,os,hashlib
D=os.path.dirname(os.path.abspath(__file__)); UA={"User-Agent":"Mozilla/5.0"}
UNI=json.load(open(f"{D}/FROZEN_UNIVERSE.json"))
NOTIONAL=1400.0; MAXPOS=10; THRESH_BP=30.0

def hl(body,tries=4):
    for i in range(tries):
        try:
            r=urllib.request.Request("https://api.hyperliquid.xyz/info",data=json.dumps(body).encode(),
                headers={"Content-Type":"application/json","User-Agent":"curl/8.5.0"})
            return json.load(urllib.request.urlopen(r,timeout=30))
        except Exception as e:
            last=e; time.sleep(1.0*(i+1))
    raise last

def yahoo_one(t,tries=5):
    u=f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=5d&interval=1d"
    last=None
    for i in range(tries):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25))
            r=d["chart"]["result"][0]; q=r["indicators"]["quote"][0]
            return [(r["timestamp"][i2],q["open"][i2],q["close"][i2]) for i2 in range(len(r["timestamp"]))
                    if q["open"][i2] is not None and q["close"][i2] is not None]
        except Exception as e:
            last=e; time.sleep(2.5*(i+1))
    raise last

def yahoo_all(syms):
    """批量预取并缓存。Yahoo 会在连续请求后掐 TLS，故退避 + 逐个重试。"""
    out={}; fails=[]
    for s2 in syms:
        try: out[s2]=yahoo_one(s2); time.sleep(1.6)
        except Exception as e: fails.append((s2,str(e)[:40]))
    # 第二轮只补失败项，退避更长
    for s2,_ in list(fails):
        try: out[s2]=yahoo_one(s2); fails=[f for f in fails if f[0]!=s2]; time.sleep(4.0)
        except Exception: pass
    return out,fails

def vwap_slip(levels,notional,mid):
    rem=notional; qty=0.0
    for lv in levels:
        p=float(lv["px"]); s=float(lv["sz"]); take=min(p*s,rem)
        qty+=take/p; rem-=take
        if rem<=1e-9: break
    if rem>1e-9 or qty<=0: return None,None
    v=notional/qty
    return v, abs(v-mid)/mid*1e4

def snap_asset(sym,ctx):
    coin=f"xyz:{sym}"
    bk=hl({"type":"l2Book","coin":coin}); bids,asks=bk["levels"][0],bk["levels"][1]
    if not bids or not asks: return None
    bb=float(bids[0]["px"]); ba=float(asks[0]["px"]); mid=(bb+ba)/2
    depth={}
    for n in (1000,5000,25000,50000):
        vb,sb=vwap_slip(asks,n,mid); vs,ss=vwap_slip(bids,n,mid)
        depth[str(n)]={"buy_vwap":vb,"buy_slip_bp":sb,"sell_vwap":vs,"sell_slip_bp":ss}
    return {"coin":coin,"bid":bb,"ask":ba,"mid":mid,"spread_bp":(ba-bb)/mid*1e4,
            "markPx":float(ctx.get("markPx") or 0),"oraclePx":float(ctx.get("oraclePx") or 0),
            "funding_hr":float(ctx.get("funding") or 0),"dayNtlVlm":float(ctx.get("dayNtlVlm") or 0),
            "openInterest":float(ctx.get("openInterest") or 0),"depth":depth}

def deployer_snapshot():
    """字段集必须与 t03_deployer_baseline.json 完全一致，否则哈希不可比。"""
    d=hl({"type":"perpDexs"})
    x=[y for y in d if y and y.get("name")=="xyz"][0]
    s={"deployer":x["deployer"],"oracleUpdater":x["oracleUpdater"],"feeRecipient":x["feeRecipient"],
       "subDeployers":x["subDeployers"],
       "fundingMultipliers":dict(x["assetToFundingMultiplier"]),
       "oiCaps":dict(x["assetToStreamingOiCap"]),
       "fundingInterestRates":dict(x["assetToFundingInterestRate"])}
    core={k:v for k,v in s.items() if k!="ts"}
    return s, hashlib.sha256(json.dumps(core,sort_keys=True).encode()).hexdigest()

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "observe"
    now=datetime.datetime.now(datetime.timezone.utc)
    meta,ctxs=hl({"type":"metaAndAssetCtxs","dex":"xyz"})
    cm={a["name"]:c for a,c in zip(meta["universe"],ctxs)}
    dsnap,dhash=deployer_snapshot()
    rec={"mode":mode,"ts_utc":now.isoformat(),"prereg":"PREREG_v6_2026-08-29.md",
         "prereg_sha256":"ef694e1b652888cc0c9f49118243c23ae9903397f20426e8182dc14796af5283",
         "deployer_hash":dhash,"deployer":dsnap,"assets":{}}
    print("  预取 Yahoo 现金价（约 60s）…")
    ycache,yfail=yahoo_all(UNI)
    print(f"  Yahoo 取得 {len(ycache)}/{len(UNI)}，失败 {len(yfail)}")
    miss=list(yfail)
    for s in UNI:
        try:
            if s not in ycache: continue
            ctx=cm.get(f"xyz:{s}")
            if ctx is None: miss.append((s,"not_live")); continue
            a=snap_asset(s,ctx)
            if a is None: miss.append((s,"empty_book")); continue
            rows=ycache[s]
            a["yahoo_rows"]=rows[-3:]
            a["cash_close_date_et"]=datetime.datetime.fromtimestamp(rows[-1][0],
                datetime.timezone(datetime.timedelta(hours=-4))).strftime("%Y-%m-%d")
            if mode=="observe":
                cash_close=rows[-1][2]
                a["cash_close"]=cash_close
                a["r_bp"]=math.log(a["mid"]/cash_close)*1e4 if cash_close else None
            else:
                a["cash_open_latest"]=rows[-1][1]
            rec["assets"][s]=a
        except Exception as e:
            miss.append((s,str(e)[:40]))
        time.sleep(0.25)
    rec["missing"]=miss
    if mode=="observe":
        sig=[(s,v["r_bp"]) for s,v in rec["assets"].items() if v.get("r_bp") is not None and abs(v["r_bp"])>=THRESH_BP]
        sig.sort(key=lambda x:(-abs(x[1]),x[0]))
        rec["signals_all"]=sig
        rec["selected"]=[{"sym":s,"r_bp":r,"side":"LONG" if r>0 else "SHORT","notional":NOTIONAL} for s,r in sig[:MAXPOS]]
        rec["n_signal"]=len(sig); rec["n_selected"]=len(rec["selected"])
        rec["window_status"]="no-signal(不计入N)" if len(sig)==0 else "active"
    fn=f"{D}/data/{mode}_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    json.dump(rec,open(fn,"w"),indent=1)
    print(f"[{mode}] {now.isoformat()}  资产 {len(rec['assets'])}/{len(UNI)}  缺失 {len(miss)}")
    if miss: print("  缺失:",miss)
    if mode=="observe":
        print(f"  触发 |r|>=30bp: {rec['n_signal']}   建仓: {rec['n_selected']}   状态: {rec['window_status']}")
        for x in rec["selected"]: print(f"    {x['side']:5s} {x['sym']:6s} r={x['r_bp']:+8.1f}bp  ${x['notional']:.0f}")
    print(f"  deployer_hash={dhash[:16]}…")
    print(f"  → {fn}")

if __name__=="__main__": main()
