import json,urllib.request,time,os,sys
sys.path.insert(0,'.'); from L_00_bootstrap import load
cfg,_=load([__file__,"L_00_bootstrap.py"])
mu=cfg["mother_universe"]; EP=mu["endpoint"]; CID=mu["catalog_id"]
def page(n,size=50):
    u=f"{EP}?type=1&catalogId={CID}&pageNo={n}&pageSize={size}"
    r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=45).read())
d=page(1,1); c=d["data"]["catalogs"][0]
assert c["catalogName"]==mu["catalog_name_expected"], f"catalogName 不符:{c['catalogName']}"
total=c["total"]; print(f"catalogName={c['catalogName']}  total={total}")
arts={}; n=1
while len(arts)<total and n<=total//50+3:
    try:
        cc=page(n,50)["data"]["catalogs"][0]; got=cc.get("articles") or []
    except Exception as e:
        print(f"  page {n} 失败: {type(e).__name__}"); time.sleep(2); n+=1; continue
    if not got: break
    for a in got: arts[a["id"]]=a
    if n%10==0: print(f"  page {n}  累计 {len(arts)}",flush=True)
    n+=1; time.sleep(0.25)
json.dump(list(arts.values()),open("ann_raw.json","w"),ensure_ascii=False)
print(f"取得 {len(arts)} / {total} 条公告  -> ann_raw.json")
if arts:
    a=list(arts.values())[0]; print(f"  字段: {sorted(a.keys())}")
