"""Probe L · TIME_CHAIN(时间版本链)。
对 OPERATIONAL_UPDATE 公告应用 rules.UPDATE_ADVANCED,按 (baseAsset, old_time) 链接既有事件,
更新 T_scheduled 并保存完整 time_versions[]。链接失败标 AMBIGUOUS 并保留原因,不删除记录。
**不读 t0_exact.json / t0_manifest.json。** 用法: [--dryrun]"""
import json,os,re,sys,collections,datetime,hashlib
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
DRY="--dryrun" in sys.argv
REQ=["L_mother_events.json","ann_raw.json","ann_body_manifest.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
mu=cfg["mother_universe"]; R=mu["rules"]; F=re.I|re.S; CP=lambda p: re.compile(p,F)
FORBID=["t0_exact.json","t0_manifest.json"]
_open=open
def guarded(p,*a,**k):
    if os.path.basename(str(p)) in FORBID: sys.exit(f"ISOLATION VIOLATION: TIME_CHAIN 读取了 {p}")
    return _open(p,*a,**k)
open=guarded
FAIL=[]
def check(name,ok,got=None,want=None):
    print(f"[断言] {name}: got={got} want={want}  {'✅' if ok else '❌'}")
    if not ok: FAIL.append({"check":name,"got":got,"want":want})
    return ok

M=json.load(open("L_mother_events.json")); raw=M["raw_events"]
check("上游母表 config 与本次一致",M["config_sha256"]==H["L_config.json"],M["config_sha256"][:16],H["L_config.json"][:16])
NZ=R["NORMALIZE"]; ENT=CP(NZ["entities"]); WS=CP(NZ["collapse_ws"])
def norm(t): return WS.sub(' ',ENT.sub(' ',t).replace(NZ["amp"],'&'))
TIME=CP(R["TIME"]); NAMEP=CP(R["ASSET_PAREN"])
UA=R["UPDATE_ADVANCED"]; EXT=CP(UA["extract"]); FB=CP(UA["fallback"]); SC=CP(UA["asset_scope"]["clause"])
def parse_time(m):
    h=int(m.group('h')); mi=int(m.group('mi')); ap=(m.group('ap') or '').upper()
    if ap=='AM' and h==12: h=0
    elif ap=='PM' and h!=12: h+=12
    return datetime.datetime.strptime(m.group('d'),"%Y-%m-%d").replace(hour=h,minute=mi,tzinfo=datetime.timezone.utc)

idx=collections.defaultdict(list)
for e in raw: idx[(e["base_asset"],e["T_scheduled"])].append(e)
ids=[a["id"] for a in json.load(open("ann_raw.json"))]
updates=[]; nofit=[]
for i in ids:
    p=f"ann_body/{i}.json"
    if not os.path.exists(p): continue
    x=norm(json.load(open(p))["text"])
    m=EXT.search(x); src="EXTRACT"
    if m: syms=[m.group("sym").upper()]
    else:
        m=FB.search(x)
        if not m: continue
        src="FALLBACK"; sc=SC.search(x)
        syms=sorted({s.group('sym').upper() for s in NAMEP.finditer(sc.group("who"))}) if sc else []
    to,tn=TIME.search(m.group("old")),TIME.search(m.group("new"))
    if not (to and tn):
        nofit.append({"article_id":i,"reason":"old/new 无法用 rules.TIME 解析"}); continue
    ot,nt=parse_time(to).isoformat(),parse_time(tn).isoformat()
    act=(m.groupdict().get("action2") or "").lower()
    if not syms: nofit.append({"article_id":i,"reason":"未取到资产代号"}); continue
    for s in syms: updates.append({"article_id":i,"base_asset":s,"old":ot,"new":nt,"action":act,"extractor":src})
print(f"\n[UPDATE_ADVANCED] 更新公告 {len({u['article_id'] for u in updates})} 篇,(base,old) 键 {len(updates)} 个")

applied=[]; ambiguous=[]
final={id(e):e["T_scheduled"] for e in raw}
chain=collections.defaultdict(list)
for u in sorted(updates,key=lambda z:(z["base_asset"],z["old"])):
    tgt=idx.get((u["base_asset"],u["old"]),[])
    if not tgt:
        ambiguous.append({**u,"final_kind":"AMBIGUOUS",
                          "reason":"按 (baseAsset, old_time) 未匹配到既有事件;记录保留,不删除"})
        print(f"  ❕ {u['base_asset']:<6} {u['old'][:16]} → {u['new'][:16]}  AMBIGUOUS(无可链接事件)")
        continue
    for e in tgt:
        chain[(u["base_asset"],e["article_id"])].append({"from":u["old"],"to":u["new"],
            "action":u["action"],"update_article_id":u["article_id"],"extractor":u["extractor"]})
        final[id(e)]=u["new"]
        applied.append({"base_asset":u["base_asset"],"origin_article_id":e["article_id"],
                        "update_article_id":u["article_id"],"old":u["old"],"new":u["new"],
                        "action":u["action"],"extractor":u["extractor"]})
        print(f"  ✔ {u['base_asset']:<6} {u['old'][:16]} → {u['new'][:16]}  {u['action']:<9} 源={e['article_id']} 更新={u['article_id']}")

out=[]
for e in raw:
    tv=chain.get((e["base_asset"],e["article_id"]),[])
    out.append({**e,"T_scheduled_final":final[id(e)],"time_versions":tv,
                "time_updated":bool(tv)})
print(f"\n应用 {len(applied)} 条更新,AMBIGUOUS {len(ambiguous)} 条,事件 {len(out)} 条(守恒)")

# ---------- 断言 ----------
LK=mu["time_chain_linkage"]
check("事件守恒",len(out)==len(raw),len(out),len(raw))
wl=[(x["article_id"],x["base"],x["old"],x["new"]) for x in LK["linkable"]]
gl=sorted((a["update_article_id"],a["base_asset"],a["old"],a["new"]) for a in applied)
check("可链接更新集合",gl==sorted((i,b,o.replace("Z","+00:00"),n.replace("Z","+00:00")) for i,b,o,n in wl),
      [f"{b}@{o[:16]}→{n[:16]}" for _,b,o,n in gl],
      [f"{b}@{o[:16]}→{n[:16]}" for _,b,o,n in sorted(wl)])
wu={(x["article_id"],x["base"]) for x in LK["unlinkable"]}
gu={(a["article_id"],a["base_asset"]) for a in ambiguous}
check("AMBIGUOUS 集合",gu==wu,sorted(gu),sorted(wu))
check("AMBIGUOUS 均保留原因",all(a.get("reason") for a in ambiguous),len(ambiguous),len(ambiguous))
noup={x["article_id"] for x in LK["no_update_articles"]}
check("非时间变更公告未被误取",not (noup & {u["article_id"] for u in updates}),
      sorted(noup & {u["article_id"] for u in updates}),[])
rs=[s for s in mu["regression_samples"] if s.get("stage")=="TIME_CHAIN"]
print(f"\n--- TIME_CHAIN 回归样本({len(rs)} 条)---")
byb=collections.defaultdict(list)
for o in out: byb[(o["article_id"],o["base_asset"])].append(o)
for s in rs:
    aid=s["article_id"]; b=s["expect_base"]
    if "expect_update" in s:
        u=[a for a in applied if a["update_article_id"]==aid and a["base_asset"]==b]
        check(f"regr {aid} 更新已应用",len(u)==1,len(u),1)
        if u:
            e=s["expect_update"]
            check(f"regr {aid} old/new/action",
                  (u[0]["old"],u[0]["new"],u[0]["action"])==(e["old"].replace("Z","+00:00"),e["new"].replace("Z","+00:00"),e["action"]),
                  (u[0]["old"][:16],u[0]["new"][:16],u[0]["action"]),(e["old"][:16],e["new"][:16],e["action"]))
        check(f"regr {aid} 更新公告自身不产生事件",
              len([o for o in out if o["article_id"]==aid])==s["expect_events"],
              len([o for o in out if o["article_id"]==aid]),s["expect_events"])
    if "expect_final_time" in s:
        got=byb.get((aid,b),[])
        w=s["expect_final_time"].replace("Z","+00:00")
        check(f"regr {aid} 最终时间",[o["T_scheduled_final"] for o in got]==[w],
              [o["T_scheduled_final"] for o in got],w)
        check(f"regr {aid} L03 原始时间保持",[o["T_scheduled"] for o in got]==["2023-05-03T12:15:00+00:00"],
              [o["T_scheduled"] for o in got],"2023-05-03T12:15:00+00:00")
        check(f"regr {aid} time_versions 完整链",
              [(v["from"][:16],v["to"][:16],v["action"]) for o in got for v in o["time_versions"]]
              ==[("2023-05-03T12:15","2023-05-03T12:00","advanced")],
              [(v["from"][:16],v["to"][:16],v["action"]) for o in got for v in o["time_versions"]],
              [("2023-05-03T12:15","2023-05-03T12:00","advanced")])
if FAIL:
    for f in FAIL: print(f"  ❌ {f['check']}  got={f['got']}  want={f['want']}")
    sys.exit(f"FAIL-CLOSED:{len(FAIL)} 项检查未通过 ⟹ **拒绝写出 TIME_CHAIN 产物**")
print("\n全部检查通过 ✅")
res={"config_sha256":H["L_config.json"],"stage":"TIME_CHAIN","n_events":len(out),
     "n_applied":len(applied),"applied":applied,"ambiguous":ambiguous,"unparsed":nofit,
     "forbidden_inputs":FORBID,"events":out}
if not DRY:
    json.dump(res,_open("L_time_chain.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["L_time_chain.json"])
else: print("[dryrun] 未写出")
