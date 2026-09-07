"""Probe L · 公告分类与事件提取(config v1.8.4)。
**全部正则由 config.mother_universe.rules 编译,代码中不另写任何模式。**
阶段 = L03_CLASSIFY:只输出候选,不做 B 的首次/新增最终裁定,不解析时间链,不读任何 T0 文件。
用法: [--dryrun]"""
import json,os,re,sys,datetime,collections,hashlib
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
DRY="--dryrun" in sys.argv
REQ=["ann_raw.json","crawl_report.json","ann_body_manifest.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
mu=cfg["mother_universe"]; R=mu["rules"]
for forbidden in ("t0_exact.json","t0_manifest.json"):
    assert forbidden not in open(__file__).read().split("forbidden")[0], "本阶段禁止读取 T0 文件"

# ---------- 复现门 ----------
BM=json.load(open("ann_body_manifest.json"))
miss=[];mism=[]
for e in BM["entries"]:
    p=f"ann_body/{e['article_id']}.json"
    if not os.path.exists(p): miss.append(e["article_id"]); continue
    if hashlib.sha256(open(p,'rb').read()).hexdigest()!=e["sha256"]: mism.append(e["article_id"])
print(f"[复现门] manifest={len(BM['entries'])} 缺失={len(miss)} 哈希不符={len(mism)}")
if miss or mism: sys.exit(f"BODY VERIFY FAIL {miss[:5]} {mism[:5]}")
print(f"[复现门] 正文组合根哈希 = {BM['combined_root_sha256']}  ✅")
if not BM.get("complete") and not DRY: sys.exit("ann_body 不完整 ⟹ 拒绝正式产出")

# ---------- 从 config 编译全部规则 ----------
F=re.I|re.S
CP=lambda p: re.compile(p,F)
TIME=CP(R["TIME"]); PAIR=CP(R["PAIR"]); NAMEP=CP(R["ASSET_PAREN"])
EX={k:CP(v) for k,v in R["EXCLUDE"].items() if not k.startswith("_")}
GA=[CP(p) for p in R["GEN"]["A"]["require_all"]]
C1=CP(R["GEN"]["C_LAUNCH_THEN_LIST"]["require"])
C2T=CP(R["GEN"]["C_PROGRAM_LIST_OPEN"]["title_require"])
C2A=CP(R["GEN"]["C_PROGRAM_LIST_OPEN"]["body_require_time_after"])
C2B=CP(R["GEN"]["C_PROGRAM_LIST_OPEN"]["body_require_time_before"])
GB=CP(R["GEN"]["B"]["require"])
BFIRST=CP(R["B_SPLIT"]["layer1_L03_semantic_only"]["first_marker"])
NOTIME=CP(mu["time_version_chain"]["no_time_marker"])
ENT=re.compile(r'&nbsp;|&#160;| ')
def norm(t): return re.sub(r'\s+',' ',ENT.sub(' ',t).replace('&amp;','&'))
def parse_time(m):
    """按 TIME_12H_RULE 解析;m 为 TIME 的 match"""
    h=int(m.group('h')); mi=int(m.group('mi')); ap=(m.group('ap') or '').upper()
    if ap=='AM' and h==12: h=0
    elif ap=='PM' and h!=12: h+=12
    d=datetime.datetime.strptime(m.group('d'),"%Y-%m-%d").replace(
        hour=h,minute=mi,tzinfo=datetime.timezone.utc)
    return d
def first_time(s):
    m=TIME.search(s); return parse_time(m) if m else None
OPC={k:CP(v) for k,v in R["OPERATION_CLAUSE"].items() if not k.startswith("_")}
PX=set(R["PAIR_EXCLUDE"]["list"]); URLG=CP(R["PAIR_EXCLUDE"]["url_guard"])
def pairs_in_clause(x,which="generic"):
    """PAIR 仅在操作句内运行(v1.8.5);排除 URL 片段与伪资产"""
    out=set()
    for cm in OPC[which].finditer(x):
        seg=cm.group("clause")
        for m in PAIR.finditer(seg):
            b=m.group('base').upper()
            if b in PX: continue
            lo=max(0,m.start()-20)
            if URLG.search(seg[lo:m.end()+10]): continue
            out.add(b)
    return out

# ---------- 主循环 ----------
W0=datetime.datetime.fromisoformat(mu["window_start_utc"]).replace(tzinfo=datetime.timezone.utc)
W1=datetime.datetime.fromisoformat(mu["window_end_utc"]).replace(tzinfo=datetime.timezone.utc)+datetime.timedelta(days=1)
WB=W0-datetime.timedelta(days=mu["lookback_days"])
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)
A_=json.load(open("ann_raw.json"))
expected={a["id"]:a for a in A_ if WB<=f_(a["releaseDate"])<W1}
buckets=collections.Counter(); raw_events=[]; per_article={}; gen_hits=collections.Counter()
for i,meta in expected.items():
    r=json.load(open(f"ann_body/{i}.json")); x=norm(r["text"]); title=meta["title"]
    matched=[]
    if EX["OPERATIONAL_UPDATE"].search(x): matched.append("OPERATIONAL_UPDATE")
    if EX["FUTURES_ONLY"].search(x) or EX["FUTURES_ONLY"].search(title): matched.append("FUTURES_ONLY")
    if EX["PREMARKET_TO_SPOT"].search(x): matched.append("PREMARKET_TO_SPOT")
    if all(p.search(x) for p in GA): matched.append("A")
    if C1.search(x): matched.append("C_LAUNCH_THEN_LIST")
    if C2T.search(title) and (C2A.search(x) or C2B.search(x)): matched.append("C_PROGRAM_LIST_OPEN")
    if GB.search(x): matched.append("B")
    for g in matched: gen_hits[g]+=1
    kind=None; evs=[]
    for g in R["PRIORITY"]:
        if g in matched: kind=g; break
    if kind in ("OPERATIONAL_UPDATE","FUTURES_ONLY","PREMARKET_TO_SPOT"):
        pass
    elif kind=="C_LAUNCH_THEN_LIST":
        for m in C1.finditer(x):                                   # finditer:220669 两事件
            sym=m.group('sym').upper(); prep=(m.group('prep') or '').lower()
            tm=TIME.search(x[m.start():m.start()+300])
            if not tm: continue
            ok = (sym in pairs_in_clause(x,"generic")) if prep=="with" else (sym in title.upper())
            if ok: evs.append((sym,parse_time(tm),"C_LAUNCH_THEN_LIST"))
    elif kind=="C_PROGRAM_LIST_OPEN":
        for P in (C2A,C2B):
            for m in P.finditer(x):
                sym=m.group('sym').upper()
                tm=TIME.search(x[m.start():m.end()+120])
                if tm and sym in pairs_in_clause(x,"generic"): evs.append((sym,parse_time(tm),"C_PROGRAM_LIST_OPEN"))
    elif kind=="A":
        AP=pairs_in_clause(x,"A")
        for m in NAMEP.finditer(x):
            sym=m.group('sym').upper()
            if sym not in AP: continue
            tm=TIME.search(x[m.start():m.start()+400])
            if tm: evs.append((sym,parse_time(tm),"A")); break
    elif kind=="B":
        cand = "B_FIRST_CANDIDATE" if BFIRST.search(x) else "B_NEW_PAIR_CANDIDATE"
        BP=pairs_in_clause(x,"B")
        for m in NAMEP.finditer(x):
            sym=m.group('sym').upper()
            if sym not in BP: continue
            tm=TIME.search(x[m.start():m.start()+400])
            if tm: evs.append((sym,parse_time(tm),cand)); break
        if not evs:
            for cm in OPC["B"].finditer(x):
                tm=TIME.search(cm.group(0))
                if not tm: continue
                for b in sorted(pairs_in_clause(x,"B")):
                    evs.append((b,parse_time(tm),cand))
                break
        kind=cand
    seen=set(); uniq=[]
    for s,t,g in evs:
        if (s,t) in seen: continue
        seen.add((s,t)); uniq.append((s,t,g))
    if kind in (None,"OTHER") or (not uniq and kind not in ("OPERATIONAL_UPDATE","FUTURES_ONLY","PREMARKET_TO_SPOT")):
        if kind in ("A","C_LAUNCH_THEN_LIST","C_PROGRAM_LIST_OPEN","B_FIRST_CANDIDATE","B_NEW_PAIR_CANDIDATE"):
            buckets["PARSE_FAIL"]+=1; per_article[i]={"kind":"PARSE_FAIL","matched":matched}; continue
        buckets["OTHER"]+=1; per_article[i]={"kind":"OTHER","matched":matched}; continue
    buckets[kind]+=1
    per_article[i]={"kind":kind,"matched":matched,"n_events":len(uniq)}
    for s,t,g in uniq:
        raw_events.append({"article_id":i,"base_asset":s,"T_scheduled":t.isoformat(),
                           "generator":g,"candidate_kind":kind,"matched_generators":matched,
                           "title":meta["title"][:110],"release_date":f_(meta["releaseDate"]).isoformat()})
tot=sum(buckets.values())
print(f"\n桶: {dict(buckets)}   求和={tot} / {len(expected)}")
assert tot==len(expected), f"桶和 {tot} != expected {len(expected)}"
print("  [断言] 各桶互斥且求和 == expected  ✅")
print(f"\n生成器命中(可重叠): {dict(gen_hits)}")
# ---- v1.8.5:本阶段**不合并**,只出非破坏性分组视图 ----
groups={}
for e in raw_events:
    k=(e["base_asset"],e["T_scheduled"])
    g=groups.setdefault(k,{"base_asset":e["base_asset"],"T_scheduled":e["T_scheduled"],"source_records":[]})
    g["source_records"].append({"article_id":e["article_id"],"generator":e["generator"],
                                "matched_generators":e["matched_generators"]})
GR=sorted(groups.values(),key=lambda z:z["T_scheduled"])
for g in GR: g["source_generators"]=sorted({r["generator"] for r in g["source_records"]})
print(f"\nraw_events={len(raw_events)}  candidate_groups={len(GR)}(**未合并、未删除**)")
print(f"  按 generator(raw): {dict(collections.Counter(e['generator'] for e in raw_events))}")
EC=mu["expected_counts"]
c1r=[e for e in raw_events if e["generator"]=="C_LAUNCH_THEN_LIST"]
c1a={e["article_id"] for e in c1r}
c2r=[e for e in raw_events if e["generator"]=="C_PROGRAM_LIST_OPEN"]
c2a={e["article_id"] for e in c2r}
c2g=[g for g in GR if "C_PROGRAM_LIST_OPEN" in g["source_generators"]]
print(f"\n[断言] C1 raw 篇={len(c1a)}/{EC['C1_raw_articles']} 事件={len(c1r)}/{EC['C1_raw_events']}  "
      f"{'✅' if len(c1a)==EC['C1_raw_articles'] and len(c1r)==EC['C1_raw_events'] else '❌'}")
print(f"[断言] C2 raw 篇={len(c2a)}/{EC['C2_raw_articles']} 分组={len(c2g)}/{EC['C2_groups']}  "
      f"{'✅' if len(c2a)==EC['C2_raw_articles'] and len(c2g)==EC['C2_groups'] else '❌'}")
me=EC["MEME_group"]
mg=[g for g in GR if g["base_asset"]=="MEME" and g["T_scheduled"].startswith(me["T_scheduled"][:16])]
ok_me = len(mg)==me["groups"] and mg and len(mg[0]["source_records"])==me["sources"] and mg[0]["source_generators"]==sorted(me["source_generators"])
print(f"[断言] MEME 分组={len(mg)}/{me['groups']} 来源={len(mg[0]['source_records']) if mg else 0}/{me['sources']} "
      f"generators={mg[0]['source_generators'] if mg else None}  {'✅' if ok_me else '❌'}")
bad=[e for e in raw_events if e["base_asset"] in R["PAIR_EXCLUDE"]["list"]]
print(f"[断言] 伪资产(COM/IOS 等)在事件中出现 = {len(bad)}  {'✅' if not bad else '❌ '+str(sorted({b['base_asset'] for b in bad}))}")
out={"config_sha256":H["L_config.json"],"ann_body_combined_root_sha256":BM["combined_root_sha256"],
     "stage":"L03_CLASSIFY","buckets":dict(buckets),"generator_hits":dict(gen_hits),
     "n_raw_events":len(raw_events),"raw_events":raw_events,"candidate_groups":GR,"per_article":{str(k):v for k,v in per_article.items()}}
if not DRY:
    json.dump(out,open("L_mother_events.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["L_mother_events.json"])
else: print("\n[DRYRUN] 未写母表")
