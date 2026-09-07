"""Probe L · JOIN(联合母表 U_master = U_trade ∪ U_announcement)。
①用稳定来源身份逐条连接 L03 / B_RESOLVE / TIME_CHAIN;②A/C 按证据做最终裁定(不以 generator 等同首次上市);
③按冻结 dedup_rule 合并并保留全部来源;④独立构建 U_trade 再与公告匹配;⑤逐条去向对账。
**不读 t0_exact.json / t0_manifest.json。** 用法: [--dryrun]"""
import json,os,re,sys,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
DRY="--dryrun" in sys.argv
REQ=["L_mother_events.json","L_b_resolve.json","L_time_chain.json","agg_earliest_day.json","u_trade_candidates.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
mu=cfg["mother_universe"]; L2=mu["rules"]["B_SPLIT"]["layer2_join_evidence"]; JC=mu["join_classes"]
FORBID=["t0_exact.json","t0_manifest.json"]
_open=open
def guarded(p,*a,**k):
    if os.path.basename(str(p)) in FORBID: sys.exit(f"ISOLATION VIOLATION: JOIN 读取了 {p}")
    return _open(p,*a,**k)
open=guarded
FAIL=[]
def check(n,ok,got=None,want=None):
    print(f"[断言] {n}: got={got} want={want}  {'✅' if ok else '❌'}")
    if not ok: FAIL.append({"check":n,"got":got,"want":want})
M=json.load(open("L_mother_events.json")); B=json.load(open("L_b_resolve.json")); T=json.load(open("L_time_chain.json"))
for nm,d in (("L03",M),("B_RESOLVE",B),("TIME_CHAIN",T)):
    check(f"{nm} config 与本次一致",d["config_sha256"]==H["L_config.json"],d["config_sha256"][:12],H["L_config.json"][:12])

# ---------- ① 稳定来源身份:逐条连接三阶段 ----------
SRID=lambda e: f'{e["article_id"]}:{e["base_asset"]}:{e["T_scheduled"]}'   # 用**原定时间**,不用更新后时间
l03={SRID(e):e for e in M["raw_events"]}
tc ={SRID(e):e for e in T["events"]}
br ={SRID(e):e for e in B["records"]}
check("L03 来源身份唯一",len(l03)==len(M["raw_events"]),len(l03),M["raw_events"].__len__())
check("TIME_CHAIN 覆盖全部 L03 记录",set(tc)==set(l03),len(set(l03)-set(tc)),0)
check("B_RESOLVE 记录是 L03 子集",set(br)<=set(l03),len(set(br)-set(l03)),0)
joined={}
for k,e in l03.items():
    t=tc[k]; b=br.get(k)
    joined[k]={"srid":k,"article_id":e["article_id"],"base_asset":e["base_asset"],
               "generator":e["generator"],"candidate_kind":e.get("candidate_kind"),
               "first_marker_source":e.get("first_marker_source"),
               "T_scheduled_original":e["T_scheduled"],"T_scheduled_final":t["T_scheduled_final"],
               "time_versions":t["time_versions"],
               "final_kind":(b or {}).get("final_kind"),
               "evidence_earliest_trade_day":(b or {}).get("evidence_earliest_trade_day"),
               "premarket_pairs":(b or {}).get("premarket_pairs"),
               "spot_pairs":(b or {}).get("spot_pairs")}
print(f"\n[连接] {len(joined)} 条来源记录,已带 原定时间 / 最终时间 / 时间版本 / 裁定")

# ---------- ② A/C 最终裁定(按证据,不以 generator 等同首次上市)----------
UC=json.load(open("u_trade_candidates.json")); AG=json.load(open("agg_earliest_day.json"))
s2b={r["symbol"]:r["base"] for r in UC["pairs"]}
pairs_of=collections.defaultdict(dict)
for s,v in AG.items():
    b=s2b.get(s)
    if b and v.get("status")=="OK" and v.get("earliest_trade_day"): pairs_of[b][s]=v["earliest_trade_day"]
if os.environ.get("NEG_JOIN")=="NO_ARCH":
    for _b in ("AERO","ARKM"): pairs_of.pop(_b,None)
    print("[反例] 已抹掉 AERO 与 ARKM 的全部归档成交记录")
E={b:min(d.values()) for b,d in pairs_of.items()}
ACG=("A","C_LAUNCH_THEN_LIST","C_PROGRAM_LIST_OPEN"); acb=collections.Counter()
for r in joined.values():
    if r["generator"] not in ACG: continue
    b=r["base_asset"]; sd=r["T_scheduled_final"][:10]; ed=E.get(b)
    if   ed is None: k="ANNOUNCEMENT_ONLY"
    elif ed==sd:     k="FIRST_SPOT_LISTING"
    elif ed< sd:     k="RELISTING_OR_AMBIGUOUS"      # 归档早于公告开盘日:证据与『首次』矛盾
    else:            k="AMBIGUOUS"                    # 归档晚于开盘日
    r["final_kind"]=k; r["evidence_earliest_trade_day"]=ed; acb[k]+=1
print(f"[A/C 裁定] {dict(acb)}")
AC=mu["ac_resolve_branch_coverage"]
for k,v in AC.items():
    if k.startswith("_"): continue
    check(f"A/C 分支 {k}",acb.get(k,0)==v["expected_records"],acb.get(k,0),v["expected_records"])
check("全部来源记录均已裁定",all(r["final_kind"] for r in joined.values()),
      sum(1 for r in joined.values() if not r["final_kind"]),0)

# ---------- ③ 按冻结 dedup_rule 合并 ----------
# v1.8.26:ANNOUNCEMENT_ONLY **必须保留为 U_master 行**(冻结 join_classes 明写「不得消失」)。
# 反例 NEG_JOIN=NO_ARCH 抓到:此前它落入 excluded,公告事件直接消失。
LIST_KINDS=("FIRST_SPOT_LISTING","PREMARKET_TO_SPOT","ANNOUNCEMENT_ONLY")
grp=collections.defaultdict(list); excluded=[]
for r in joined.values():
    if r["final_kind"] in LIST_KINDS: grp[(r["base_asset"],r["T_scheduled_final"],r["final_kind"])].append(r)
    else: excluded.append(r)
U_ann=[]
for (b,t,k),rs in sorted(grp.items()):
    rs=sorted(rs,key=lambda z:z["article_id"])
    U_ann.append({"base_asset":b,"T_scheduled":t,"kind":k,
                  "T_scheduled_original":sorted({x["T_scheduled_original"] for x in rs}),
                  "source_article_ids":[x["article_id"] for x in rs],
                  "source_srids":[x["srid"] for x in rs],
                  "source_generators":sorted({x["generator"] for x in rs}),
                  "time_versions":[v for x in rs for v in x["time_versions"]],
                  "evidence_earliest_trade_day":rs[0]["evidence_earliest_trade_day"],
                  "premarket_pairs":rs[0].get("premarket_pairs")})
nmerged=sum(len(g)-1 for g in grp.values())
print(f"[合并] 上市类记录 {sum(len(g) for g in grp.values())} 条 → {len(U_ann)} 个公告事件(合并掉 {nmerged} 条),非上市类 {len(excluded)} 条")
DR=mu["dedup_expectations"]
check("合并组数",len(U_ann)==DR["merged_events"],len(U_ann),DR["merged_events"])
check("被合并掉的记录数",nmerged==DR["merged_away"],nmerged,DR["merged_away"])
multi=sorted([x["base_asset"],sorted(x["source_article_ids"])] for x in U_ann if len(x["source_article_ids"])>1)
want=sorted([d["base"],sorted(d["articles"])] for d in DR["multi_source_groups"])
check("多来源组集合(逐组资产+来源篇)",multi==want,multi,want)
check("上市类记录数",sum(len(g) for g in grp.values())==DR["listing_records"],sum(len(g) for g in grp.values()),DR["listing_records"])
check("非上市类记录数",len(excluded)==DR["non_listing_records"],len(excluded),DR["non_listing_records"])
check("跨阶段来源全部留存",all(len(x["source_srids"])==len(x["source_article_ids"]) for x in U_ann),True,True)

# ---------- ④ 独立构建 U_trade,盘前成交不得充当正式现货 T0 ----------
PMF={r["base_asset"]:r["T_scheduled_final"][:10] for r in joined.values() if r["generator"]=="PREMARKET_TO_SPOT_FORMAL"}
U_trade={}; pre_excl={}
for b,d in pairs_of.items():
    use=dict(d)
    if b in PMF:
        drop={s:x for s,x in d.items() if x<PMF[b]}
        if drop: pre_excl[b]=drop; use={s:x for s,x in d.items() if x>=PMF[b]}
    if use: U_trade[b]={"T0_day":min(use.values()),"n_pairs":len(use)}
print(f"[U_trade] 独立构建 {len(U_trade)} 个 baseAsset;盘前对已排除: {pre_excl}")
check("U_trade 规模",len(U_trade)==mu["u_trade_expectations"]["n_base_assets"],len(U_trade),mu["u_trade_expectations"]["n_base_assets"])
check("盘前排除集合",{b:sorted(v) for b,v in pre_excl.items()}==mu["u_trade_expectations"]["premarket_excluded"],
      {b:sorted(v) for b,v in pre_excl.items()},mu["u_trade_expectations"]["premarket_excluded"])
for b,sd in PMF.items():
    check(f"{b} 正式现货 T0 未取盘前日",U_trade[b]["T0_day"]==sd,U_trade[b]["T0_day"],sd)

# ---------- ⑤ 联合与 join_classes ----------
annb={x["base_asset"]:x for x in U_ann}
U_master=[]; jc=collections.Counter()
for x in U_ann:
    b=x["base_asset"]; t=U_trade.get(b)
    if t is None: cls="ANNOUNCEMENT_ONLY"
    elif t["T0_day"]==x["T_scheduled"][:10]: cls="MATCHED"
    else: cls="AMBIGUOUS"
    if x["time_versions"]: cls_extra="SCHEDULE_UPDATED_OR_CANCELLED"
    else: cls_extra=None
    jc[cls]+=1
    if cls_extra: jc[cls_extra]+=1
    U_master.append({**x,"join_class":cls,"schedule_changed":bool(x["time_versions"]),
                     "T0_day":(t or {}).get("T0_day"),"source":"U_announcement"})
for b,t in sorted(U_trade.items()):
    if b in annb: continue
    jc["TRADE_ONLY"]+=1
    U_master.append({"base_asset":b,"T_scheduled":None,"kind":None,"join_class":"TRADE_ONLY",
                     "T0_day":t["T0_day"],"n_pairs":t["n_pairs"],"source":"U_trade",
                     "source_article_ids":[],"source_srids":[]})
print(f"[联合] U_master {len(U_master)} 行  join_classes={dict(jc)}")
JE=mu["join_expectations"]
for k,v in JE["classes"].items(): check(f"join_class {k}",jc.get(k,0)==v,jc.get(k,0),v)
check("U_master 行数",len(U_master)==JE["n_rows"],len(U_master),JE["n_rows"])

# ---------- ⑥ 逐条去向对账:每条输入都能追踪到输出/合并来源/明确排除理由 ----------
REASON={"NEW_QUOTE_PAIR_EXISTING_ASSET":"既有资产的新增报价对,非上市事件 —— 明确排除",
        "PENDING_ADJUDICATION":"SAME_DAY_OPEN_ONLY 证据不足 —— 保留待裁定,不并入",
        "RELISTING_OR_AMBIGUOUS":"归档早于公告开盘日,与『首次』矛盾 —— 单列",
        "AMBIGUOUS":"证据冲突 —— 单列","ANNOUNCEMENT_ONLY":"无归档记录 —— 保留公告事件"}
covered=set()
for r in U_master: covered.update(r.get("source_srids") or [])
ledger=[]
for k,r in joined.items():
    if k in covered: ledger.append({"srid":k,"outcome":"MERGED_INTO_U_MASTER","final_kind":r["final_kind"]})
    else:
        rs=REASON.get(r["final_kind"])
        ledger.append({"srid":k,"outcome":"EXCLUDED","final_kind":r["final_kind"],"reason":rs})
check("去向对账覆盖全部来源记录",len(ledger)==len(joined),len(ledger),len(joined))
noreason=[x for x in ledger if x["outcome"]=="EXCLUDED" and not x.get("reason")]
check("每条排除均有明确理由",not noreason,[x["final_kind"] for x in noreason][:5],[])
oc=collections.Counter((x["outcome"],x["final_kind"]) for x in ledger)
print("\n[去向对账]")
for k,n in sorted(oc.items()): print(f"   {k[0]:<22} {k[1]:<32} {n}")
check("对账总数守恒",sum(oc.values())==len(M["raw_events"]),sum(oc.values()),len(M["raw_events"]))

# ---------- 无归档分支反例:场景专属预期 ----------
if os.environ.get("NEG_JOIN")=="NO_ARCH":
    up=[f for f in FAIL if "config 与本次一致" in f["check"]]
    FAIL.clear(); FAIL.extend(up)
    tgt={"AERO","ARKM"}
    ao=[r for r in joined.values() if r["base_asset"] in tgt and r["generator"] in ACG]
    check("[NO_ARCH] A/C 记录裁定为 ANNOUNCEMENT_ONLY",
          bool(ao) and all(r["final_kind"]=="ANNOUNCEMENT_ONLY" for r in ao),
          sorted({(r["base_asset"],r["final_kind"]) for r in ao}),"全部 ANNOUNCEMENT_ONLY")
    check("[NO_ARCH] 同资产的 B 裁定不受影响(来自上游冻结产物)",
          all(r["final_kind"]!="ANNOUNCEMENT_ONLY" for r in joined.values()
              if r["base_asset"] in tgt and r["generator"].startswith("B_")),
          sorted({(r["base_asset"],r["final_kind"]) for r in joined.values()
                  if r["base_asset"] in tgt and r["generator"].startswith("B_")}),"不为 ANNOUNCEMENT_ONLY")
    jm=[r for r in U_master if r["base_asset"] in tgt and r["source"]=="U_announcement"]
    check("[NO_ARCH] 联合层 join_class 为 ANNOUNCEMENT_ONLY",
          all(r["join_class"]=="ANNOUNCEMENT_ONLY" for r in jm),
          sorted({(r["base_asset"],r["join_class"]) for r in jm}),"全部 ANNOUNCEMENT_ONLY")
    check("[NO_ARCH] 公告事件未消失(保留为 U_master 行)",len(jm)>=2,sorted((r["base_asset"],r["join_class"]) for r in jm),">=2 行")
    check("[NO_ARCH] 来源对账仍守恒",len(ledger)==len(joined),len(ledger),len(joined))
    if FAIL:
        for f in FAIL: print(f"  ❌ {f['check']}  got={f['got']}  want={f['want']}")
        sys.exit(f"SCENARIO-FAIL:{len(FAIL)} 项未通过")
    print("\n[NO_ARCH] 场景预期全部满足 ✅"); sys.exit(0)
if FAIL:
    for f in FAIL: print(f"  ❌ {f['check']}  got={f['got']}  want={f['want']}")
    sys.exit(f"FAIL-CLOSED:{len(FAIL)} 项未通过 ⟹ **拒绝写出联合母表**")
print("\n全部检查通过 ✅")
res={"config_sha256":H["L_config.json"],"stage":"JOIN","forbidden_inputs":FORBID,
     "n_source_records":len(joined),"n_u_announcement":len(U_ann),"n_u_trade":len(U_trade),
     "n_u_master":len(U_master),"join_classes":dict(jc),"ac_kinds":dict(acb),
     "premarket_excluded":{b:sorted(v) for b,v in pre_excl.items()},
     "u_master":U_master,"ledger":ledger,"joined_source_records":list(joined.values())}
if not DRY:
    json.dump(res,_open("L_u_master.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["L_u_master.json"])
else: print("[dryrun] 未写出")
