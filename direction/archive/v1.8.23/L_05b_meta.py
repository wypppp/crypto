"""Probe L · T0 层1:全体交易对最早 daily/aggTrades key(**仅元数据,含留出集**)。config v1.6。
状态严格四分:OK / NO_ARCHIVE(HTTP200 且 KeyCount==0)/ UNEXPECTED_RESPONSE / FETCH_FAIL。
后两者**必须重试且禁止缓存为无归档**。URL 路径按 RFC 编码(存在 CJK 符号如 币安人生USDT)。"""
import json,os,re,sys,urllib.request,urllib.parse,threading,collections,time,concurrent.futures as cf
sys.path.insert(0,'.'); from L_00_bootstrap import load
cfg,_=load([__file__,"L_00_bootstrap.py"])
B="https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
C=json.load(open("u_trade_candidates.json"))
pairs=[r for r in C["pairs"] if r["leverage_class"]!="REMOVED"]     # SUSPECTED 保留
print(f"参与扫描的交易对 = {len(pairs)}(REMOVED {sum(1 for r in C['pairs'] if r['leverage_class']=='REMOVED')} 对已剔除,SUSPECTED 保留)")
os.makedirs("aggmeta",exist_ok=True)
lock=threading.Lock(); st=collections.Counter()
def probe(sym):
    p=f"aggmeta/{urllib.parse.quote(sym,safe='')}.json"
    if os.path.exists(p):
        try:
            r=json.load(open(p))
            okc = r.get("status")=="OK" and r.get("earliest_trade_day") and r.get("http")==200
            nac = r.get("status")=="NO_ARCHIVE" and r.get("http")==200 and r.get("key_count")==0
            if okc or nac:                      # 缓存复用仍须满足原始判据
                with lock: st[r["status"]]+=1
                return r
        except Exception: pass
    last=None
    for att in range(5):
        try:
            pref=urllib.parse.quote(f"data/spot/daily/aggTrades/{sym}/",safe="/")
            resp=urllib.request.urlopen(f"{B}?list-type=2&prefix={pref}&max-keys=1",timeout=40)
            t=resp.read().decode(); last=resp.status
            kc=re.search(r'<KeyCount>(\d+)</KeyCount>',t)
            m=re.search(r'<Key>[^<]*-aggTrades-(\d{4}-\d{2}-\d{2})\.zip</Key>',t)
            if m:                       r={"symbol":sym,"status":"OK","earliest_trade_day":m.group(1),"http":200}
            elif kc and kc.group(1)=="0": r={"symbol":sym,"status":"NO_ARCHIVE","http":200,"key_count":0}
            else:                       # KeyCount>0 但 key 未命中 / 无 KeyCount 标签 ⟹ 不得记 NO_ARCHIVE
                time.sleep(1.5*(att+1)); last=f"UNEXPECTED(kc={kc.group(1) if kc else None})"; continue
            json.dump(r,open(p,"w"))
            with lock: st[r["status"]]+=1
            return r
        except Exception as e:
            last=getattr(e,'code',type(e).__name__); time.sleep(1.5*(att+1))
    status="UNEXPECTED_RESPONSE" if str(last).startswith("UNEXPECTED") else "FETCH_FAIL"
    r={"symbol":sym,"status":status,"http":str(last)}
    json.dump(r,open(p,"w"))
    with lock: st[status]+=1
    return r
with cf.ThreadPoolExecutor(20) as ex: res=list(ex.map(lambda r:probe(r["symbol"]),pairs))
print(f"\n状态分布: {dict(st)}")
for k in ("OK","NO_ARCHIVE","UNEXPECTED_RESPONSE","FETCH_FAIL"):
    v=[r for r in res if r["status"]==k]
    print(f"  {k:<20}{len(v)}" + (f"   {[x['symbol'] for x in v][:6]}" if k!="OK" and v else ""))
json.dump({r["symbol"]:r for r in res},open("agg_earliest_day.json","w"),ensure_ascii=False)
print("-> agg_earliest_day.json")
