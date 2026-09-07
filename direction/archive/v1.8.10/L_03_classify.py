"""Probe L · 公告分类与事件提取(config v1.8.8)。
**全部正则由 config.mother_universe.rules 编译;代码中不出现任何硬编码模式。**
阶段 = L03_CLASSIFY:只出候选,不做 B 的首次/新增裁定,不解析时间链,不读任何 T0 文件。
输出 raw_events(不合并)+ candidate_groups(非破坏性分组视图)。
用法: [--dryrun]"""
import json,os,re,sys,datetime,collections,hashlib
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
DRY="--dryrun" in sys.argv
REQ=["ann_raw.json","crawl_report.json","ann_body_manifest.json",
     "u_trade_candidates.json","spot_exchangeinfo.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
mu=cfg["mother_universe"]; R=mu["rules"]; F=re.I|re.S
CP=lambda p: re.compile(p,F)

# ---------- 复现门 ----------
BM=json.load(open("ann_body_manifest.json")); miss=[];mism=[]
for e in BM["entries"]:
    p=f"ann_body/{e['article_id']}.json"
    if not os.path.exists(p): miss.append(e["article_id"]); continue
    if hashlib.sha256(open(p,'rb').read()).hexdigest()!=e["sha256"]: mism.append(e["article_id"])
print(f"[复现门] manifest={len(BM['entries'])} 缺失={len(miss)} 哈希不符={len(mism)}")
if miss or mism: sys.exit(f"BODY VERIFY FAIL {miss[:5]} {mism[:5]}")
print(f"[复现门] 正文组合根哈希 = {BM['combined_root_sha256']}  ✅")
if not BM.get("complete") and not DRY: sys.exit("ann_body 不完整 ⟹ 拒绝正式产出")

# ---------- 交易对校验来源(v1.8.8 显式闭包)----------
PV=R["PAIR_VALIDATE"]
UC=json.load(open("u_trade_candidates.json")); SE=json.load(open("spot_exchangeinfo.json"))
ARCH={r["symbol"] for r in UC["pairs"]}
QSET=set(SE["quote_assets"])|{r["quote"] for r in UC["pairs"]}
a=PV["archive_pair_assert"]
assert len(ARCH)==a["count"], f"archive_pair {len(ARCH)} != {a['count']}"
assert len(UC["unresolved"])==a["unresolved"] and not (set(a["must_not_contain"]) & ARCH)
assert len(QSET)==PV["quote_asset_assert"]["count"], f"quote {len(QSET)} != {PV['quote_asset_assert']['count']}"
print(f"[来源断言] archive_pairs={len(ARCH)} ✅  quote_assets={len(QSET)} ✅")

# ---------- 从 config 编译 ----------
NZ=R["NORMALIZE"]; ENT=CP(NZ["entities"]); WS=CP(NZ["collapse_ws"])
def norm(t): return WS.sub(' ',ENT.sub(' ',t).replace(NZ["amp"],'&'))
TIME=CP(R["TIME"]); PAIR=CP(R["PAIR"]); NAMEP=CP(R["ASSET_PAREN"])
AH=CP(R["A_LISTING_HEAD"]); PB_S=CP(R["PAIR_BLOCK"]["start"])
PB_T=[CP(t) for t in R["PAIR_BLOCK"]["terminators"]]; PB_MAX=R["PAIR_BLOCK"]["max_chars_after_head"]
EX={k:CP(v) for k,v in R["EXCLUDE"].items() if not k.startswith("_")}
SCOPE=R["EXCLUDE_SCOPE"]
GA=[CP(p) for p in R["GEN"]["A"]["require_all"]]
C1=CP(R["GEN"]["C_LAUNCH_THEN_LIST"]["require"])
C2T=CP(R["GEN"]["C_PROGRAM_LIST_OPEN"]["title_require"])
C2A=CP(R["GEN"]["C_PROGRAM_LIST_OPEN"]["body_require_time_after"])
C2B=CP(R["GEN"]["C_PROGRAM_LIST_OPEN"]["body_require_time_before"])
GB=CP(R["GEN"]["B"]["require"]); OPB=CP(R["OPERATION_CLAUSE"]["B"])
BFIRST=CP(R["B_SPLIT"]["layer1_L03_semantic_only"]["first_marker"])
PX=set(R["PAIR_EXCLUDE"]["list"]); URLG=CP(R["PAIR_EXCLUDE"]["url_guard"])
SEG_P=CP(R["ASSET_SEGMENT"]["paren"])
def parse_time(m):
    h=int(m.group('h')); mi=int(m.group('mi')); ap=(m.group('ap') or '').upper()
    if ap=='AM' and h==12: h=0
    elif ap=='PM' and h!=12: h+=12
    return datetime.datetime.strptime(m.group('d'),"%Y-%m-%d").replace(hour=h,minute=mi,tzinfo=datetime.timezone.utc)
def excluded(k,x,title):
    sc=SCOPE.get(k,"body_or_title")
    if sc=="title_only": return bool(EX[k].search(title))
    return bool(EX[k].search(x) or EX[k].search(title))
TRI=collections.Counter()
def classify_pair(b,q,assets):
    """三态 + 条件去空格规范化"""
    b2=re.sub(r'\s+','',b)
    if b2!=b and b2.upper() in assets: b=b2          # PAIR_NORMALIZE_SPACE:仅当等于已知资产
    B,Q=b.upper(),q.upper()
    if B in PX or Q in PX: TRI["INVALID_PAIR"]+=1; return None
    if Q not in QSET: TRI["INVALID_PAIR"]+=1; return None
    st="ARCHIVE_CONFIRMED" if (B+Q) in ARCH else "UNSEEN_IN_ARCHIVE"
    TRI[st]+=1; return (B,Q,st)
def pairs_from(seg,assets):
    out=[]
    for m in PAIR.finditer(seg):
        lo=max(0,m.start()-20)
        if URLG.search(seg[lo:m.end()+10]): TRI["INVALID_PAIR"]+=1; continue
        r=classify_pair(m.group('base'),m.group('quote'),assets)
        if r: out.append(r)
    return out
def pair_block(x,pos):
    m=PB_S.search(x,pos)
    if not m: return ""
    seg=x[m.end():m.end()+PB_MAX]
    cut=len(seg)
    for t in PB_T:
        tm=t.search(seg)
        if tm: cut=min(cut,tm.start())
    return seg[:cut]

# ---------- 主循环 ----------
W0=datetime.datetime.fromisoformat(mu["window_start_utc"]).replace(tzinfo=datetime.timezone.utc)
W1=datetime.datetime.fromisoformat(mu["window_end_utc"]).replace(tzinfo=datetime.timezone.utc)+datetime.timedelta(days=1)
WB=W0-datetime.timedelta(days=mu["lookback_days"])
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)
expected={a["id"]:a for a in json.load(open("ann_raw.json")) if WB<=f_(a["releaseDate"])<W1}
buckets=collections.Counter(); raw=[]; per={}; gen_hits=collections.Counter(); blocklen=[]
for i,meta in expected.items():
    r=json.load(open(f"ann_body/{i}.json")); x=norm(r["text"]); title=meta["title"]
    matched=[]
    for k in ("OPERATIONAL_UPDATE","FUTURES_ONLY","PREMARKET_TO_SPOT","SPOT_COPY_TRADING"):
        if k in EX and excluded(k,x,title): matched.append(k)
    if all(p.search(x) for p in GA): matched.append("A")
    if C1.search(x): matched.append("C_LAUNCH_THEN_LIST")
    if C2T.search(title) and (C2A.search(x) or C2B.search(x)): matched.append("C_PROGRAM_LIST_OPEN")
    if GB.search(x): matched.append("B")
    # v1.8.10:全部未命中时,以 rules.A_LISTING_HEAD 兜底(引用已编译模式,不复制正则)
    if not matched and AH.search(x): matched.append("A"); gen_hits["A_FALLBACK"]+=1
    for g in matched: gen_hits[g]+=1
    kind=next((g for g in R["PRIORITY"] if g in matched),"OTHER"); evs=[]
    if kind in ("OPERATIONAL_UPDATE","FUTURES_ONLY","PREMARKET_TO_SPOT","SPOT_COPY_TRADING"):
        pass
    elif kind=="A":
        m=AH.search(x)
        if m:
            assets={s.group('sym').upper() for s in SEG_P.finditer(m.group('asset_segment'))}
            if not assets:
                bare=m.group('asset_segment').strip()
                if bare and ' ' not in bare: assets={bare.upper()}
            blk=pair_block(x,m.end()); blocklen.append(len(blk))
            allp=pairs_from(m.group('tail'),assets)+pairs_from(blk,assets)
            tm=TIME.search(m.group('time'))
            if tm and assets:
                for A_ in sorted(assets):
                    if any(A_==b or A_==q for b,q,_ in allp): evs.append((A_,parse_time(tm),"A",None))
    elif kind=="C_LAUNCH_THEN_LIST":
        for m in C1.finditer(x):
            sym=m.group('sym').upper(); prep=(m.group('prep') or '').lower()
            tm=TIME.search(x[m.start():m.start()+300])
            if not tm: continue
            ok=(any(sym==b or sym==q for b,q,_ in pairs_from(x[m.start():m.start()+300],{sym}))) if prep=="with" else (sym in title.upper())
            if ok: evs.append((sym,parse_time(tm),"C_LAUNCH_THEN_LIST",prep))
    elif kind=="C_PROGRAM_LIST_OPEN":
        for P in (C2A,C2B):
            for m in P.finditer(x):
                sym=m.group('sym').upper(); tm=TIME.search(x[m.start():m.end()+120])
                if tm and any(sym==b or sym==q for b,q,_ in pairs_from(x[m.start():m.end()+200],{sym})):
                    evs.append((sym,parse_time(tm),"C_PROGRAM_LIST_OPEN",None))
    elif kind=="B":
        cand="B_FIRST_CANDIDATE" if BFIRST.search(x) else "B_NEW_PAIR_CANDIDATE"
        for cm in OPB.finditer(x):
            tm=TIME.search(cm.group(0))
            if not tm: continue
            assets={s.group('sym').upper() for s in SEG_P.finditer(cm.group(0))}
            for b,q,_ in pairs_from(cm.group('clause'),assets):
                evs.append((b,parse_time(tm),cand,None))
            break
        kind=cand
    seen=set(); uniq=[]
    for s_,t_,g_,pp_ in evs:
        if (s_,t_) in seen: continue
        seen.add((s_,t_)); uniq.append((s_,t_,g_,pp_))
    if kind in ("OTHER",) : buckets["OTHER"]+=1; per[i]={"kind":"OTHER","matched":matched}; continue
    if not uniq and kind not in ("OPERATIONAL_UPDATE","FUTURES_ONLY","PREMARKET_TO_SPOT","SPOT_COPY_TRADING"):
        buckets["PARSE_FAIL"]+=1; per[i]={"kind":"PARSE_FAIL","matched":matched}; continue
    buckets[kind]+=1; per[i]={"kind":kind,"matched":matched,"n_events":len(uniq)}
    for s_,t_,g_,pp_ in uniq:
        raw.append({"article_id":i,"base_asset":s_,"T_scheduled":t_.isoformat(),"generator":g_,"prep":pp_,
                    "candidate_kind":kind,"matched_generators":matched,"title":title[:110]})
tot=sum(buckets.values())
print(f"\n桶: {dict(buckets)}   求和={tot} / {len(expected)}")
assert tot==len(expected)
print("  [断言] 各桶互斥且求和 == expected  ✅")
print(f"生成器命中(可重叠): {dict(gen_hits)}")
print(f"三态: {dict(TRI)}")
FAIL=[]
def check(name,ok,got=None,want=None):
    """fail-closed:登记失败,最终统一以非零退出码终止并拒绝写产物。"""
    print(f"[断言] {name}: got={got} want={want}  {'✅' if ok else '❌'}")
    if not ok: FAIL.append({"check":name,"got":got,"want":want})
    return ok
n_full=sum(1 for l in blocklen if l==PB_MAX)
check("PAIR_BLOCK 恰好截满上限的块数",n_full==0,n_full,0)
groups={}
for e in raw:
    k=(e["base_asset"],e["T_scheduled"])
    g=groups.setdefault(k,{"base_asset":e["base_asset"],"T_scheduled":e["T_scheduled"],"source_records":[]})
    g["source_records"].append({"article_id":e["article_id"],"generator":e["generator"],"matched_generators":e["matched_generators"]})
GR=sorted(groups.values(),key=lambda z:z["T_scheduled"])
for g in GR: g["source_generators"]=sorted({s["generator"] for s in g["source_records"]})
print(f"\nraw_events={len(raw)}  candidate_groups={len(GR)}(未合并、未删除)")
print(f"  按 generator(raw): {dict(collections.Counter(e['generator'] for e in raw))}")
EC=mu["expected_counts"]
c1a={e["article_id"] for e in raw if e["generator"]=="C_LAUNCH_THEN_LIST"}
c1r=[e for e in raw if e["generator"]=="C_LAUNCH_THEN_LIST"]
c2a={e["article_id"] for e in raw if e["generator"]=="C_PROGRAM_LIST_OPEN"}
c2g=[g for g in GR if "C_PROGRAM_LIST_OPEN" in g["source_generators"]]
check("C1 篇数",len(c1a)==EC["C1_raw_articles"],len(c1a),EC["C1_raw_articles"])
check("C1 事件数",len(c1r)==EC["C1_raw_events"],len(c1r),EC["C1_raw_events"])
w=sum(1 for e in c1r if e.get("prep")=="with"); ag=sum(1 for e in c1r if e.get("prep")=="against")
check("C1 with 分支",w==EC["C1_with"],w,EC["C1_with"])
check("C1 against 分支",ag==EC["C1_against"],ag,EC["C1_against"])
check("C2 来源篇数",len(c2a)==EC["C2_raw_articles"],len(c2a),EC["C2_raw_articles"])
check("C2 分组数",len(c2g)==EC["C2_groups"],len(c2g),EC["C2_groups"])
me=EC["MEME_group"]; mg=[g for g in GR if g["base_asset"]=="MEME" and g["T_scheduled"].startswith(me["T_scheduled"][:16])]
check("MEME 分组数",len(mg)==me["groups"],len(mg),me["groups"])
if mg:
    check("MEME 来源数",len(mg[0]["source_records"])==me["sources"],len(mg[0]["source_records"]),me["sources"])
    check("MEME source_generators",mg[0]["source_generators"]==sorted(me["source_generators"]),
          mg[0]["source_generators"],sorted(me["source_generators"]))
    check("MEME 来源 article_ids",sorted(r["article_id"] for r in mg[0]["source_records"])==sorted(me["articles"]),
          sorted(r["article_id"] for r in mg[0]["source_records"]),sorted(me["articles"]))
bad=[e for e in raw if e["base_asset"] in PX]
check("伪资产出现在事件中",len(bad)==0,sorted({b["base_asset"] for b in bad}),[])
mb=[e for e in raw if e["base_asset"]=="1MBABYDOGE"]
check("1MBABYDOGE 事件数",len(mb)==1,len(mb),1)

# ---------- config 中 24 条结构化回归样本(stage=L03_CLASSIFY)----------
byart=collections.defaultdict(list)
for e in raw: byart[e["article_id"]].append(e)
rs=[s for s in mu["regression_samples"] if s.get("stage","L03_CLASSIFY")=="L03_CLASSIFY"]
print(f"\n--- 结构化回归样本(stage=L03_CLASSIFY,{len(rs)} 条)---")
for s in rs:
    aid=s["article_id"]; got=byart.get(aid,[]); k=per.get(aid,{}).get("kind")
    if "expect_events" in s:
        check(f"regr {aid} 事件数",len(got)==s["expect_events"],len(got),s["expect_events"])
    ek=s.get("expect_candidate_kind") or s.get("expect_generator")
    if ek: check(f"regr {aid} kind/generator",k==ek or any(e["generator"]==ek for e in got),
                 k or [e['generator'] for e in got],ek)
    if "expect_base" in s and s.get("expect_events",1)>0:
        check(f"regr {aid} base",any(e["base_asset"]==s["expect_base"] for e in got),
              sorted({e["base_asset"] for e in got}),s["expect_base"])
    if "expect_bases" in s and s.get("expect_events",0)>0:
        check(f"regr {aid} bases",sorted({e["base_asset"] for e in got})==sorted(s["expect_bases"]),
              sorted({e["base_asset"] for e in got}),sorted(s["expect_bases"]))
    if "expect_time" in s and s.get("expect_events",1)>0:
        want=s["expect_time"].replace("Z","+00:00")
        check(f"regr {aid} time",any(e["T_scheduled"]==want for e in got),
              sorted({e["T_scheduled"] for e in got}),want)
    if "expect_times" in s:
        want={t.replace("Z","+00:00") for t in s["expect_times"]}
        check(f"regr {aid} times",{e["T_scheduled"] for e in got}==want,
              sorted({e["T_scheduled"] for e in got}),sorted(want))
out={"config_sha256":H["L_config.json"],"ann_body_combined_root_sha256":BM["combined_root_sha256"],
     "stage":"L03_CLASSIFY","buckets":dict(buckets),"generator_hits":dict(gen_hits),
     "pair_tristate":dict(TRI),"n_raw_events":len(raw),"raw_events":raw,"candidate_groups":GR,
     "per_article":{str(k):v for k,v in per.items()}}
out["checks_failed"]=FAIL
# ---------- fail-closed 闸门 ----------
print(f"\n{'='*70}\n检查失败 {len(FAIL)} 项")
if FAIL:
    for f in FAIL: print(f"  ❌ {f['check']}  got={f['got']}  want={f['want']}")
    sys.exit(f"FAIL-CLOSED:{len(FAIL)} 项检查未通过 ⟹ **拒绝写出母表**(既有正式产物未被覆盖)")
print("全部检查通过 ✅")
if not DRY:
    json.dump(out,open("L_mother_events.json","w"),ensure_ascii=False,indent=1); record_outputs(["L_mother_events.json"])
else: print("\n[DRYRUN] 未写母表")
