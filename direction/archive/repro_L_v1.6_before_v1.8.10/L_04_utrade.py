"""Probe L · U_pair → U_trade(config v1.6)。可完整复现 u_trade_candidates.json。
拆分优先级:①官方 exchangeInfo 的 base/quote ②显式 fallback 表 ③失败则单列。
杠杆代币:**显式剔除表**,禁止后缀正则;SUSPECTED 项保留在母体。"""
import json,os,sys,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load
cfg,H=load([__file__,"L_00_bootstrap.py"])
U=[s for s in json.load(open("u_pair.json")) if s!="klines"]
E=json.load(open("spot_exchangeinfo.json")); official=E["pairs"]
FB={r["symbol"]:(r["base"],r["quote"]) for r in json.load(open("fallback_mapping_evidence.json"))}
LW=json.load(open("leverage_whitelist.json"))
SUSPECTED=set(LW["suspected"])                       # BEAR/BULL:标记但保留
REMOVE=set(LW["leveraged_whitelist"])-SUSPECTED      # 确认剔除项
print(f"确认剔除的杠杆代币 baseAsset = {len(REMOVE)}   SUSPECTED(保留)= {sorted(SUSPECTED)}")
rows=[]; unresolved=[]
for s in U:
    if s in official: b,q,src=official[s]["base"],official[s]["quote"],"official"
    elif s in FB:     b,q,src=FB[s][0],FB[s][1],"fallback"
    else:             unresolved.append(s); continue
    rows.append({"symbol":s,"base":b,"quote":q,"src":src,
                 "leverage_class":("REMOVED" if b in REMOVE else "SUSPECTED_LEVERAGED" if b in SUSPECTED else "NORMAL")})
print(f"U_pair={len(U)}  官方={sum(1 for r in rows if r['src']=='official')}  fallback={sum(1 for r in rows if r['src']=='fallback')}  未解析={len(unresolved)}")
cnt=collections.Counter(r["leverage_class"] for r in rows)
print(f"  杠杆分类: {dict(cnt)}")
core=[r for r in rows if r["leverage_class"]!="REMOVED"]     # SUSPECTED 保留
byb=collections.defaultdict(list)
for r in core: byb[r["base"]].append(r["symbol"])
print(f"  **参与扫描的交易对 = {len(core)}**   U_trade 候选 baseAsset = {len(byb)}")
for k in ("JUP","SYRUP","BEAR","BULL"): print(f"    {k:<7} 在候选中: {k in byb}  交易对 {byb.get(k,[])}")
json.dump({"u_pair_n":len(U),"pairs":rows,"unresolved":unresolved,
           "removed_leveraged_bases":sorted(REMOVE),"suspected_leveraged_bases":sorted(SUSPECTED),
           "u_trade_candidates":{b:sorted(v) for b,v in sorted(byb.items())}},
          open("u_trade_candidates.json","w"),ensure_ascii=False)
print("-> u_trade_candidates.json(已重建)")
