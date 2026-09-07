"""Probe L · B0:永续原始合约表。保留交易所原始字段,**完全不剥数字前缀**,不做任何链接。
按 config v1.3 b_leg.must_store。最终链接须等公告母表完成(否则无完整参照系)。"""
import json,urllib.request,hashlib,datetime,collections,sys
sys.path.insert(0,'.'); from L_00_bootstrap import load
cfg,_=load([__file__,"L_00_bootstrap.py"])
URL="https://www.binance.com/fapi/v1/exchangeInfo"
req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0'})
raw=urllib.request.urlopen(req,timeout=60).read()
snap=datetime.datetime.now(datetime.timezone.utc).isoformat()
h=hashlib.sha256(raw).hexdigest()
d=json.loads(raw)
KEEP=["symbol","pair","baseAsset","quoteAsset","marginAsset","contractType","status","onboardDate","deliveryDate"]
rows=[{k:s.get(k) for k in KEEP} for s in d["symbols"]]
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc).isoformat() if ms else None
for r in rows:
    r["onboard_utc"]=f_(r.get("onboardDate")); r["delivery_utc"]=f_(r.get("deliveryDate"))
out={"_snapshot_utc":snap,"_source_url":URL,"_raw_response_sha256":h,
     "_config_version":cfg["_meta"]["version"],
     "_note":"原始快照,未做任何前缀剥离或链接。当前快照可能遗漏已被彻底移除的合约。",
     "n_total":len(rows),"contracts":rows}
json.dump(out,open("perp_contracts_raw.json","w"),ensure_ascii=False,indent=1)
print(f"快照时间 {snap}")
print(f"原始响应 sha256 {h}")
print(f"合约总数 {len(rows)}")
print(f"  contractType 分布: {dict(collections.Counter(r['contractType'] for r in rows))}")
print(f"  status 分布:       {dict(collections.Counter(r['status'] for r in rows))}")
perp=[r for r in rows if r['contractType']=='PERPETUAL']
print(f"  PERPETUAL = {len(perp)};其中有 onboardDate {sum(1 for r in perp if r['onboardDate'])}"
      f",有 deliveryDate {sum(1 for r in perp if r['deliveryDate'])}")
print(f"  quoteAsset 分布(永续): {dict(collections.Counter(r['quoteAsset'] for r in perp))}")
print(f"  原始 baseAsset 唯一数(永续,未剥前缀)= {len({r['baseAsset'] for r in perp})}")
import re
numpre=[r['baseAsset'] for r in perp if re.match(r'^\d',r['baseAsset'] or '')]
print(f"  以数字开头的原始 baseAsset({len(numpre)} 个,全部原样保留):{sorted(set(numpre))}")
