"""Probe L · 由 u_trade_candidates.json + agg_earliest_day.json + config 重建 T0 下载清单。
输出 reconciliation(K线月份口径 vs aggTrades 口径),不做任何下载。"""
import json,hashlib,collections,sys
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
REQ=["u_trade_candidates.json","agg_earliest_day.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
mu=cfg["mother_universe"]; W0=mu["window_start_utc"]; W1=mu["window_end_utc"]
C=json.load(open("u_trade_candidates.json")); M=json.load(open("agg_earliest_day.json"))
byb=collections.defaultdict(list)
for r in C["pairs"]:
    if r["leverage_class"]=="REMOVED": continue
    m=M.get(r["symbol"])
    if m and m["status"]=="OK": byb[r["base"]].append((m["earliest_trade_day"],r["symbol"]))
hold=lambda b: hashlib.sha256(b.encode()).digest()[0]%5==0
rows=[]
for b,v in byb.items():
    d0=min(d for d,_ in v)
    rows.append({"base":b,"earliest_trade_day":d0,"tied_pairs":sorted(s for d,s in v if d==d0),
                 "n_tied":sum(1 for d,_ in v if d==d0),"in_window":W0<=d0<=W1,"holdout":hold(b)})
inw=[r for r in rows if r["in_window"]]
main=[r for r in inw if not r["holdout"]]; ho=[r for r in inw if r["holdout"]]
print(f"有 aggTrades 归档的 baseAsset = {len(rows)}")
print(f"窗口内 [{W0},{W1}] = {len(inw)}   主集 {len(main)}   留出 {len(ho)}(T0=EMBARGOED)")
print(f"下载清单 = {sum(r['n_tied'] for r in main)} 个 aggTrades 日文件;留出若下载会是 {sum(r['n_tied'] for r in ho)} 个 —— 不下载")
assert not (set(r['base'] for r in main) & set(r['base'] for r in ho)), "主集与留出集交集非空"
print("[断言] 主集 ∩ 留出集 == ∅  ✅")
try:
    K=json.load(open("t0_month_by_base.json"))
    Kb={b:min(m for m,_,_ in v) for b,v in K.items()}
    kin={b for b,m in Kb.items() if W0[:7]<=m<=W1[:7]}; ain={r["base"] for r in inw}
    same=sum(1 for b in set(Kb)&set(byb) if Kb[b]==min(d for d,_ in byb[b])[:7])
    print(f"\n[reconciliation] K线月份口径窗口内={len(kin)}  aggTrades 口径={len(ain)}")
    print(f"  共有 baseAsset={len(set(Kb)&set(byb))},最早月份相同={same}")
    print(f"  新增={sorted(ain-kin)}   减少={sorted(kin-ain)}")
    print(f"  ⟹ {len(kin)} + {len(ain-kin)} - {len(kin-ain)} = {len(kin)+len(ain-kin)-len(kin-ain)}")
except FileNotFoundError: print("\n[reconciliation] 跳过(无 K线口径产物)")
json.dump({"config_sha256":H["L_config.json"],"all":rows,"download_manifest":main,
           "embargoed":[{**r,"T0":"EMBARGOED"} for r in ho]},open("t0_manifest.json","w"),ensure_ascii=False,indent=1)
record_outputs(["t0_manifest.json"])
