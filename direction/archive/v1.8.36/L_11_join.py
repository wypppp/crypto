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
               "announced_pairs":e.get("announced_pairs") or [],
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

# ---------- ④ 独立构建 U_trade:按**交易阶段**排除盘前,不永久剔除交易对 ----------
PMF={r["base_asset"]:r["T_scheduled_final"][:10] for r in joined.values() if r["generator"]=="PREMARKET_TO_SPOT_FORMAL"}
U_trade={}; phased={}
for b,d in pairs_of.items():
    sw=PMF.get(b); pinfo={}; qual={}
    for sym,ed in sorted(d.items()):
        if sw and ed<sw:
            # 盘前对:**保留**,记录阶段边界;正式现货区间内的最早成交日在日粒度**未定**
            pinfo[sym]={"archive_earliest_day":ed,"phase":"PREMARKET_THEN_SPOT",
                        "spot_window_start":sw,"qualifying_earliest_day":None,
                        "why":"该对在正式现货开盘前已有盘前成交;正式现货区间内的首笔成交日需逐日数据,日粒度未定"}
        else:
            pinfo[sym]={"archive_earliest_day":ed,"phase":"SPOT_ONLY",
                        "spot_window_start":sw,"qualifying_earliest_day":ed}
            qual[sym]=ed
    if sw: phased[b]={"spot_window_start":sw,
                      "premarket_pairs":sorted(k for k,v in pinfo.items() if v["phase"]=="PREMARKET_THEN_SPOT")}
    if qual:
        t0=min(qual.values())
        U_trade[b]={"T0_day":t0,"n_pairs":len(pinfo),"n_qualifying_pairs":len(qual),
                    "T0_day_source_pairs":sorted(k for k,v in qual.items() if v==t0),
                    "pairs":pinfo,"precision":"DAY_GRANULARITY_ONLY"}
print(f"[U_trade] 独立构建 {len(U_trade)} 个 baseAsset;阶段化资产: {sorted(phased)}")
for b,v in sorted(phased.items()):
    u=U_trade[b]
    print(f"   [阶段] {b:<6} 正式现货起 {v['spot_window_start']}  盘前对(保留)={v['premarket_pairs']}  "
          f"T0_day={u['T0_day']} 来自 {u['T0_day_source_pairs']}")
UE=mu["u_trade_expectations"]
check("U_trade 规模",len(U_trade)==UE["n_base_assets"],len(U_trade),UE["n_base_assets"])
check("阶段化资产集合",{b:v["premarket_pairs"] for b,v in phased.items()}==UE["phased_pairs"],
      {b:v["premarket_pairs"] for b,v in phased.items()},UE["phased_pairs"])
for b,sw in PMF.items():
    u=U_trade[b]
    check(f"{b} T0_day 等于正式现货开盘日",u["T0_day"]==sw,u["T0_day"],sw)
    check(f"{b} 盘前对已保留且标注阶段边界",
          all(u["pairs"][s_]["phase"]=="PREMARKET_THEN_SPOT" and u["pairs"][s_]["qualifying_earliest_day"] is None
              for s_ in phased[b]["premarket_pairs"]),
          {s_:u["pairs"][s_]["phase"] for s_ in phased[b]["premarket_pairs"]},"PREMARKET_THEN_SPOT / 合格最早日未定")
check("本阶段只声明 T0_day",all(u["precision"]=="DAY_GRANULARITY_ONLY" for u in U_trade.values()),
      sorted({u["precision"] for u in U_trade.values()}),["DAY_GRANULARITY_ONLY"])

# ---------- ⑤ 联合与 join_classes ----------
annb={x["base_asset"]:x for x in U_ann}
U_master=[]; jc=collections.Counter(); lab=collections.Counter()
for x in U_ann:
    b=x["base_asset"]; t=U_trade.get(b)
    if t is None: cls="ANNOUNCEMENT_ONLY"
    elif x["kind"]=="ANNOUNCEMENT_ONLY": cls="ANNOUNCEMENT_ONLY"
    elif t["T0_day"]==x["T_scheduled"][:10]: cls="MATCHED"
    else: cls="AMBIGUOUS"
    jc[cls]+=1
    if x["time_versions"]: lab["SCHEDULE_UPDATED_OR_CANCELLED"]+=1   # **附加标签,非互斥类别**
    U_master.append({**x,"join_class":cls,"schedule_changed":bool(x["time_versions"]),
                     "T0_day":(t or {}).get("T0_day"),"T0_precision":(t or {}).get("precision"),
                     "T0_day_source_pairs":(t or {}).get("T0_day_source_pairs"),"source":"U_announcement"})
for b,t in sorted(U_trade.items()):
    if b in annb: continue
    jc["TRADE_ONLY"]+=1
    U_master.append({"base_asset":b,"T_scheduled":None,"kind":None,"join_class":"TRADE_ONLY",
                     "T0_day":t["T0_day"],"T0_precision":t["precision"],
                     "T0_day_source_pairs":t["T0_day_source_pairs"],"n_pairs":t["n_pairs"],
                     "source":"U_trade","source_article_ids":[],"source_srids":[]})
print(f"[联合] U_master {len(U_master)} 行  互斥类别={dict(jc)}  附加标签={dict(lab)}")
JE=mu["join_expectations"]
for k,v in JE["exclusive_classes"].items(): check(f"互斥类别 {k}",jc.get(k,0)==v,jc.get(k,0),v)
for k,v in JE["labels"].items(): check(f"附加标签 {k}",lab.get(k,0)==v,lab.get(k,0),v)
check("互斥类别求和 == U_master 行数",sum(jc.values())==len(U_master),sum(jc.values()),len(U_master))
check("U_master 行数",len(U_master)==JE["n_rows"],len(U_master),JE["n_rows"])
check("标签不参与类别守恒",set(lab)&set(jc)==set(),sorted(set(lab)&set(jc)),[])

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

# ---------- ⑦ TRADE_ONLY 归因 + 主分析集 ----------
TA=mu["trade_only_attribution"]; MS=mu["announcement_matched_measurement_subset"]
EMB=mu["embargo_rule"]; TE=mu["trade_only_eligibility"]
import hashlib as _h
embargoed=lambda b: _h.sha256(b.encode()).digest()[0]%5==0
W0d,W1d=mu["window_start_utc"][:10],mu["window_end_utc"][:10]
QSET=set(json.load(open("spot_exchangeinfo.json"))["quote_assets"])
have_rec={r["base_asset"] for r in joined.values()}
bodies={}
for a in json.load(open("ann_raw.json")):
    fp=f"ann_body/{a['id']}.json"
    if os.path.exists(fp):
        bodies[a["id"]]=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",json.load(open(fp))["text"]))+" || "+a["title"]
BSTOCK=re.compile(r"bStocks|Tokenized Securities",re.I)
titles={a["id"]:a["title"] for a in json.load(open("ann_raw.json"))}
def mentioned(b):
    pat=re.compile(rf"\(\s*{re.escape(b)}\s*\)|(?<![A-Z0-9]){re.escape(b)}/(?:USDT|USDC|FDUSD|TRY|BTC|BNB|EUR)")
    return [i for i,x in bodies.items() if pat.search(x)]
attrib=collections.Counter(); adet=collections.defaultdict(list)
for r in U_master:
    if r["join_class"]!="TRADE_ONLY": continue
    b=r["base_asset"]; t0=r["T0_day"]
    if   t0<W0d:            k="T1_窗口前"
    elif b in QSET:         k="T2_报价资产作为base"
    elif b in have_rec:     k="T3_有公告但裁定非上市类"
    else:
        mt=mentioned(b)
        # v1.8.29:代币化证券按**公告证据**识别(bStocks 专项公告),不用代号形态启发式
        if mt and all(BSTOCK.search(titles.get(i,"")) for i in mt): k="T4_bStocks代币化证券"
        elif mt:            k="T5_仅有服务新增公告"
        else:               k="T6_公告目录完全无提及"
    r["trade_only_reason"]=k; attrib[k]+=1; adet[k].append(b)
print(f"\n[TRADE_ONLY 归因] {dict(attrib)}")
for k,v in TA["categories"].items():
    check(f"归因 {k}",attrib.get(k,0)==v["n"],attrib.get(k,0),v["n"])
    if "assets" in v: check(f"归因 {k} 资产集合",sorted(adet[k])==sorted(v["assets"]),sorted(adet[k]),sorted(v["assets"]))
check("归因求和 == TRADE_ONLY 总数",sum(attrib.values())==TA["total"],sum(attrib.values()),TA["total"])
check("归因类别互斥",all(r.get("trade_only_reason") for r in U_master if r["join_class"]=="TRADE_ONLY"),True,True)

# ---------- ⑧ 公告匹配测量子集 + 留出标记 + 固定取数清单 ----------
main=[r for r in U_master if r["join_class"]=="MATCHED" and W0d<=r["T_scheduled"][:10]<=W1d]
lb=[r for r in U_master if r["join_class"]=="MATCHED" and r["T_scheduled"][:10]<W0d]
for r in U_master:
    r["in_announcement_matched_subset"]=(r in main)
    r["embargo"]="EMBARGOED" if embargoed(r["base_asset"]) else "FETCHABLE"
print(f"[公告匹配测量子集] {len(main)} 条(回看缓冲期排除 {len(lb)} 条)")
check("子集规模",len(main)==MS["n"],len(main),MS["n"])
check("子集 kind 分布",dict(collections.Counter(r["kind"] for r in main))==MS["kinds"],
      dict(collections.Counter(r["kind"] for r in main)),MS["kinds"])
check("回看缓冲期资产集合",sorted(r["base_asset"] for r in lb)==sorted(MS["excluded_lookback"]["assets"]),
      sorted(r["base_asset"] for r in lb),sorted(MS["excluded_lookback"]["assets"]))
check("子集按年",dict(sorted(collections.Counter(r["T_scheduled"][:4] for r in main).items()))==MS["by_year"],
      dict(sorted(collections.Counter(r["T_scheduled"][:4] for r in main).items())),MS["by_year"])
check("子集 T0 仅日粒度",all(r["T0_precision"]=="DAY_GRANULARITY_ONLY" for r in main),
      sorted({r["T0_precision"] for r in main}),["DAY_GRANULARITY_ONLY"])
emb=[r for r in main if r["embargo"]=="EMBARGOED"]; fet=[r for r in main if r["embargo"]=="FETCHABLE"]
print(f"[留出] EMBARGOED {len(emb)} / FETCHABLE {len(fet)}")
check("留出划分",{"EMBARGOED":len(emb),"FETCHABLE":len(fet)}==MS["holdout_split"],
      {"EMBARGOED":len(emb),"FETCHABLE":len(fet)},MS["holdout_split"])
check("留出比例与全体一致",sum(1 for r in U_master if r["embargo"]=="EMBARGOED")==EMB["measured"]["全体746资产"],
      sum(1 for r in U_master if r["embargo"]=="EMBARGOED"),EMB["measured"]["全体746资产"])
# 固定取数清单:只含 FETCHABLE,携带公告所列交易对与最终阶段边界
srmap={r["srid"]:r for r in joined.values()}
fetch=[]
for r in sorted(fet,key=lambda z:z["T_scheduled"]):
    prs=sorted({p for sid in r["source_srids"] for p in (srmap[sid].get("announced_pairs") or [])})
    fetch.append({"base_asset":r["base_asset"],"kind":r["kind"],
                  "T_scheduled_final":r["T_scheduled"],          # **最终更新后**的精确阶段边界
                  "T_scheduled_original":r["T_scheduled_original"],
                  "announced_pairs":prs,"source_article_ids":r["source_article_ids"],
                  "T0_day":r["T0_day"],"embargo":"FETCHABLE"})
nop=[f["base_asset"] for f in fetch if not f["announced_pairs"]]
check("取数清单条数",len(fetch)==MS["holdout_split"]["FETCHABLE"],len(fetch),MS["holdout_split"]["FETCHABLE"])
check("取数清单均有公告所列交易对",not nop,nop[:6],[])
check("取数清单不含留出资产",not [f for f in fetch if embargoed(f["base_asset"])],
      [f["base_asset"] for f in fetch if embargoed(f["base_asset"])][:5],[])
red=[f for f in fetch if f["base_asset"]=="RED"]
check("RED 阶段边界用最终更新后时间",bool(red) and red[0]["T_scheduled_final"]=="2025-03-06T16:00:00+00:00",
      red[0]["T_scheduled_final"] if red else None,"2025-03-06T16:00:00+00:00")
embargo_meta=[{"base_asset":r["base_asset"],"kind":r["kind"],"T_scheduled_final":r["T_scheduled"],
               "T0_day":r["T0_day"],"embargo":"EMBARGOED",
               "note":"只保留元数据,行情文件不下载"} for r in sorted(emb,key=lambda z:z["T_scheduled"])]

# ---------- ⑨ 窗口内 TRADE_ONLY 资格表 ----------
elig=[]; ec=collections.Counter()
for r in U_master:
    if r["join_class"]!="TRADE_ONLY" or not (W0d<=r["T0_day"]<=W1d): continue
    rsn=r["trade_only_reason"]
    v="EXCLUDED_PROVEN" if rsn=="T4_bStocks代币化证券" else "PENDING_EVIDENCE"
    ev=(TE["EXCLUDED_PROVEN_criteria"] if v=="EXCLUDED_PROVEN" else TE["PENDING_EVIDENCE_criteria"])
    ec[v]+=1
    elig.append({"base_asset":r["base_asset"],"T0_day":r["T0_day"],"attribution":rsn,
                 "verdict":v,"evidence":ev,"embargo":r["embargo"]})
print(f"[TRADE_ONLY 资格表] 窗口内 {len(elig)} 条  {dict(ec)}")
check("资格表覆盖窗口内 TRADE_ONLY",len(elig)==sum(v["n"] for k,v in TA["categories"].items() if k!="T1_窗口前"),
      len(elig),sum(v["n"] for k,v in TA["categories"].items() if k!="T1_窗口前"))
check("已证明不合格仅限 bStocks",ec["EXCLUDED_PROVEN"]==TA["categories"]["T4_bStocks代币化证券"]["n"],
      ec["EXCLUDED_PROVEN"],TA["categories"]["T4_bStocks代币化证券"]["n"])
check("其余全部待定(不得当作已排除)",ec["PENDING_EVIDENCE"]==len(elig)-ec["EXCLUDED_PROVEN"],
      ec["PENDING_EVIDENCE"],len(elig)-ec["EXCLUDED_PROVEN"])

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
     "n_u_master":len(U_master),"join_classes_exclusive":dict(jc),"u_trade":U_trade,"ac_kinds":dict(acb),
     "phased_assets":{b:v for b,v in phased.items()},"labels":dict(lab),
     "trade_only_attribution":dict(attrib),"n_announcement_matched_subset":len(main),"fetch_list":fetch,"embargo_metadata":embargo_meta,"trade_only_eligibility":elig,"stage_positioning":mu["stage_positioning"],"u_master":U_master,"ledger":ledger,"joined_source_records":list(joined.values())}
if not DRY:
    json.dump(res,_open("L_u_master.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["L_u_master.json"])
else: print("[dryrun] 未写出")
