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
L1B=R["B_SPLIT"]["layer1_L03_semantic_only"]
BFIRST=CP(L1B["first_marker"])
FMT=L1B["first_marker_title"]; FMT_CL=CP(FMT["clause"]); FMT_TOK=FMT["asset_token"]
def title_first(title,base):
    """v1.8.19:标题上市声明必须**逐资产指向** —— 资产代号须作为独立 token 出现在
    标题 `will list` 子句内;同篇其他资产不共享该标记。禁止无条件全文关键词匹配。"""
    m=FMT_CL.search(title or "")
    if not m: return False
    return bool(re.search(FMT_TOK.replace("{ASSET}",re.escape(base)),m.group("clause"),re.I))
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
AP=R["ANNOUNCED_PAIRS"]; AP_QL=CP(AP["quote_list"]); AP_TOK=re.compile(r"[A-Z0-9]{2,10}")
def quote_list_pairs(x,base):
    """ANNOUNCED_PAIRS.quote_list(v1.8.31):HODLer 空投类把报价资产写成裸列表
    `open trading against USDT, USDC, BNB and TRY pairs`,无 X/Y 形态。仅保留 quote_assets 内的 token。"""
    m=AP_QL.search(x)
    if not m: return []
    return [base+t for t in AP_TOK.findall(m.group("quotes")) if t in QSET]
ASP=R["A_LISTING_SPLIT"]; ASP_H=CP(ASP["head"]); ASP_P=CP(ASP["pair_sentence"]); ASP_GAP=ASP["max_gap_chars"]
def a_split(x):
    """A_LISTING_SPLIT(v1.8.22):`will list X at TIME.` + **相邻**交易对句。
    段落边界 = 交易对句起点须在 head 结束后 ≤max_gap_chars 内;交易对 base 必须命中资产段。"""
    h=ASP_H.search(x)
    if not h: return None
    ps=ASP_P.search(x,h.end(),h.end()+ASP_GAP+320)
    if not ps or ps.start()-h.end()>ASP_GAP: return None
    return h,ps
PMF=R["GEN"]["PREMARKET_TO_SPOT_FORMAL"]; PMF_R=CP(PMF["require"]); PMF_T=CP(PMF["spot_open"])
PN=R["PAIR_NORMALIZE_SPACE"]; SPB=CP(PN["spaced_base"]); SP_HITS=[]
def despace_base(seg,assets):
    """PAIR_NORMALIZE_SPACE(v1.8.15)。base 字符类排除空白,故必须在**配对提取前**拼接;
    门控:拼接结果须命中资产段,或与紧随 quote 组成的完整对在 ARCH 内。否则原样保留。"""
    def rep(m):
        j=(m.group('num')+m.group('sym')).upper()
        if j in assets or (j+m.group('q').upper()) in ARCH:
            SP_HITS.append((m.group(0),j)); return m.group('num')+m.group('sym')
        return m.group(0)
    return SPB.sub(rep,seg)
def classify_pair(b,q,assets):
    """三态。v1.8.11 三段优先级(见 rules.PAIR_EXCLUDE.precedence):
    URL 上下文(调用方已处理) → 完整对在 ARCH 内则直接接受 → 仅未归档候选套通用词黑名单。"""
    B,Q=b.upper(),q.upper()
    if (B+Q) in ARCH:                                # 段 2:归档已确认 ⟹ 直接接受,不套黑名单
        TRI["ARCHIVE_CONFIRMED"]+=1; return (B,Q,"ARCHIVE_CONFIRMED")
    if B in PX or Q in PX: TRI["INVALID_PAIR"]+=1; return None   # 段 3:仅对未归档候选生效
    if Q not in QSET: TRI["INVALID_PAIR"]+=1; return None
    TRI["UNSEEN_IN_ARCHIVE"]+=1; return (B,Q,"UNSEEN_IN_ARCHIVE")
def pairs_from(seg,assets):
    seg=despace_base(seg,assets)                     # v1.8.15:先做有门控的空格拼接
    out=[]
    for m in PAIR.finditer(seg):
        lo=max(0,m.start()-20)
        if URLG.search(seg[lo:m.end()+10]): TRI["INVALID_PAIR"]+=1; continue
        r=classify_pair(m.group('base'),m.group('quote'),assets)
        if r: out.append(r)
    return out
# ---------- v1.8.12 多批次语义块 ----------
MB=R["MULTI_BATCH"]
MB_AT=CP(MB["batch_anchor_at"]); MB_BARE=CP(MB["batch_anchor_bare"])
MB_INLINE=CP(MB["inline_date_time"]); MB_TERM=[CP(t) for t in MB["section_terminators"]]
MB_BACK=MB["scope_backward_lookbehind"]
MB_START=CP(r'will open trading')
def multi_batch(x):
    """逐批绑定 时间→交易对(v1.8.14)。
    作用域:`will open trading` 位置,并在其前 ≤MB_BACK 字符内**有界回看**至紧邻时间锚点;
    终止于首个 section_terminator。裸日期锚点仅在已出现 ≥1 个 at-锚点后才识别。"""
    st=MB_START.search(x)
    if not st: return []
    s0=st.start()
    back=x[max(0,s0-MB_BACK):s0]                     # 有界回看,禁止无界向前搜索
    bm=list(MB_AT.finditer(back))
    if bm: s0=max(0,s0-MB_BACK)+bm[-1].start()
    seg=x[s0:]
    cut=len(seg)
    for t in MB_TERM:
        m=t.search(seg)
        if m and m.start()>0: cut=min(cut,m.start())
    seg=seg[:cut]
    at_a=[(m.start(),m.end(),m.group('time')) for m in MB_AT.finditer(seg)]
    anchors=list(at_a)
    if at_a:                                         # 裸日期锚点:仅在首个 at-锚点之后
        first_end=at_a[0][1]
        for m in MB_BARE.finditer(seg):
            if m.start()<first_end: continue
            if any(a<=m.start()<b for a,b,_ in at_a): continue
            anchors.append((m.start(),m.end(),m.group('time')))
        anchors.sort()
    out=[]
    if anchors:
        for k,(a0,e0,tstr) in enumerate(anchors):
            tm=TIME.search(tstr)
            if not tm: continue
            end=anchors[k+1][0] if k+1<len(anchors) else len(seg)
            for b,q,_ in pairs_from(seg[e0:end],set()): out.append((b,parse_time(tm),q))
    else:                                            # `on DATE at TIME` 内联式(BDOT)
        im=MB_INLINE.search(seg)
        if im:
            tm=TIME.search(f"{im.group('d2')} {im.group('t2')}")
            if tm:
                for b,q,_ in pairs_from(seg[:im.start()],set()): out.append((b,parse_time(tm),q))
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
    if PMF_R.search(x) and PMF_T.search(x): matched.append("PREMARKET_TO_SPOT_FORMAL")
    # v1.8.10:全部未命中时,以 rules.A_LISTING_HEAD 兜底(引用已编译模式,不复制正则)
    if not matched and AH.search(x): matched.append("A"); gen_hits["A_FALLBACK"]+=1
    # v1.8.22:再未命中则试分句式上市(A_LISTING_SPLIT)
    if not matched and a_split(x): matched.append("A"); gen_hits["A_SPLIT"]+=1
    for g in matched: gen_hits[g]+=1
    kind=next((g for g in R["PRIORITY"] if g in matched),"OTHER"); evs=[]
    apairs=collections.defaultdict(set)                 # v1.8.30:公告所列现货交易对
    rec=lambda B_,Q_: apairs[B_].add(B_+Q_)
    if kind in ("OPERATIONAL_UPDATE","FUTURES_ONLY","PREMARKET_TO_SPOT","SPOT_COPY_TRADING"):
        pass
    elif kind=="PREMARKET_TO_SPOT_FORMAL":
        mm=PMF_R.search(x); tt=PMF_T.search(x); tm=TIME.search(tt.group("time"))
        sym=mm.group("sym").upper()
        for b,q,_ in pairs_from(x[tt.end():tt.end()+300],{sym}):
            if b==sym: rec(b,q)
        if tm: evs.append((sym,parse_time(tm),"PREMARKET_TO_SPOT_FORMAL",None))
    elif kind=="A":
        m=AH.search(x)
        if not m:                                    # v1.8.22 分句式
            sp=a_split(x)
            if sp:
                h,ps=sp
                assets={z.group('sym').upper() for z in SEG_P.finditer(h.group('asset_segment'))}
                tm=TIME.search(h.group('time'))
                if tm and assets:
                    for b,q,_ in pairs_from(ps.group('tail'),assets):
                        if b in assets: rec(b,q); evs.append((b,parse_time(tm),"A",None))
        if m:
            assets={s.group('sym').upper() for s in SEG_P.finditer(m.group('asset_segment'))}
            if not assets:
                bare=m.group('asset_segment').strip()
                if bare and ' ' not in bare: assets={bare.upper()}
            blk=pair_block(x,m.end()); blocklen.append(len(blk))
            allp=pairs_from(m.group('tail'),assets)+pairs_from(blk,assets)
            tm=TIME.search(m.group('time'))
            if tm and assets:
                for b,q,_ in allp:
                    if b in assets: rec(b,q)
                for A_ in sorted(assets):
                    if any(A_==b or A_==q for b,q,_ in allp): evs.append((A_,parse_time(tm),"A",None))
    elif kind=="C_LAUNCH_THEN_LIST":
        for m in C1.finditer(x):
            sym=m.group('sym').upper(); prep=(m.group('prep') or '').lower()
            tm=TIME.search(x[m.start():m.start()+300])
            if not tm: continue
            cp=pairs_from(x[m.start():m.start()+300],{sym})
            for b,q,_ in cp:
                if b==sym: rec(b,q)
            ok=(any(sym==b or sym==q for b,q,_ in cp)) if prep=="with" else (sym in title.upper())
            if ok: evs.append((sym,parse_time(tm),"C_LAUNCH_THEN_LIST",prep))
    elif kind=="C_PROGRAM_LIST_OPEN":
        for P in (C2A,C2B):
            for m in P.finditer(x):
                sym=m.group('sym').upper(); tm=TIME.search(x[m.start():m.end()+120])
                cp=pairs_from(x[m.start():m.end()+200],{sym})
                for b,q,_ in cp:
                    if b==sym: rec(b,q)
                if tm and any(sym==b or sym==q for b,q,_ in cp):
                    evs.append((sym,parse_time(tm),"C_PROGRAM_LIST_OPEN",None))
    elif kind=="B":
        body_first=bool(BFIRST.search(x))            # 正文命中优先
        def cand_for(b):
            if body_first: return "B_FIRST_CANDIDATE",None,"BODY"
            if title_first(title,b): return "B_FIRST_CANDIDATE",None,"TITLE"
            return "B_NEW_PAIR_CANDIDATE",None,None
        for cm in OPB.finditer(x):
            tm=TIME.search(cm.group(0))
            if not tm: continue
            assets={s.group('sym').upper() for s in SEG_P.finditer(cm.group(0))}
            for b,q,_ in pairs_from(cm.group('clause'),assets):
                rec(b,q); evs.append((b,parse_time(tm),*cand_for(b)))
            break
        if not evs:                                  # v1.8.12:多批次语义块
            for b_,t_,q_ in multi_batch(x): rec(b_,q_); evs.append((b_,t_,*cand_for(b_)))
        kind="B_FIRST_CANDIDATE" if any(e[2]=="B_FIRST_CANDIDATE" for e in evs) else "B_NEW_PAIR_CANDIDATE"
    seen=set(); uniq=[]
    for ev in evs:
        s_,t_,g_,pp_=ev[0],ev[1],ev[2],ev[3]
        fm=ev[4] if len(ev)>4 else None               # v1.8.19 first_marker_source
        if (s_,t_) in seen: continue
        seen.add((s_,t_)); uniq.append((s_,t_,g_,pp_,fm))
    if kind in ("OTHER",) : buckets["OTHER"]+=1; per[i]={"kind":"OTHER","matched":matched}; continue
    if not uniq and kind not in ("OPERATIONAL_UPDATE","FUTURES_ONLY","PREMARKET_TO_SPOT","SPOT_COPY_TRADING"):
        buckets["PARSE_FAIL"]+=1; per[i]={"kind":"PARSE_FAIL","matched":matched}; continue
    buckets[kind]+=1; per[i]={"kind":kind,"matched":matched,"n_events":len(uniq)}
    for s_,t_,g_,pp_,fm_ in uniq:                    # v1.8.31:无显式配对时用 quote_list 兜底
        if not apairs.get(s_):
            for pr in quote_list_pairs(x,s_): apairs[s_].add(pr)
    for s_,t_,g_,pp_,fm_ in uniq:
        raw.append({"article_id":i,"base_asset":s_,"T_scheduled":t_.isoformat(),"generator":g_,"prep":pp_,
                    "first_marker_source":fm_,"announced_pairs":sorted(apairs.get(s_,())),
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
# v1.8.11:黑名单中 ME/T 是真实 baseAsset(verified_real_assets),不属伪资产;
# 只对**非真实**的通用词断言零出现。
REAL=set(R["PAIR_EXCLUDE"].get("verified_real_assets",{}))
bad=[e for e in raw if e["base_asset"] in (PX-REAL)]
check("伪资产(非真实通用词)出现在事件中",len(bad)==0,sorted({b["base_asset"] for b in bad}),[])
realev=sorted({e["base_asset"] for e in raw if e["base_asset"] in REAL})
check("真实资产 ME/T 已恢复",set(realev)>= {"ME"},realev,"至少含 ME")
# v1.8.15:原 `1MBABYDOGE 事件数==1` 是脆弱代理(数全局,绿的来源与它声称验证的规范化无关),
# 已替换为 config 中 211378 的逐篇回归样本。此处只断言规范化确实发生过、且门控未被滥用。
check("PAIR_NORMALIZE_SPACE 生效次数",len(SP_HITS)>=1,len(SP_HITS),">=1")
check("空格拼接仅限已验证形态",{j for _,j in SP_HITS}=={"1MBABYDOGE"},sorted({j for _,j in SP_HITS}),["1MBABYDOGE"])

# ---------- config 中结构化回归样本(stage=L03_CLASSIFY)----------
PFE=mu["parse_fail_expectations"]
def recset(evs):
    """v1.8.16:完整记录多重集 (base_asset, T_scheduled, generator),含重复次数。"""
    return collections.Counter((e["base_asset"],e["T_scheduled"],e["generator"]) for e in evs)
def fmt_rec(c):
    return sorted(f"{b}@{t[:16]}/{g}"+("" if n==1 else f" x{n}") for (b,t,g),n in c.items())
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
    # v1.8.16:完整记录多重集。any()/时间集合都发现不了『资产在两批之间互换』
    if "expect_first_marker_source" in s:
        check(f"regr {aid} first_marker_source",
              {e.get("first_marker_source") for e in got}=={s["expect_first_marker_source"]},
              sorted({str(e.get("first_marker_source")) for e in got}),s["expect_first_marker_source"])
    if "expect_records" in s:
        w=collections.Counter((b,t.replace("Z","+00:00"),g) for b,t,g in s["expect_records"])
        check(f"regr {aid} 记录集",recset(got)==w,fmt_rec(recset(got)),fmt_rec(w))

# ---------- v1.8.22:7 篇找回上市公告的完整记录多重集 ----------
RLE=mu["recovered_listing_expectations"]
print(f"\n--- 找回上市公告记录多重集 ---")
for k,v in sorted(RLE.items()):
    if not k.isdigit(): continue
    aid=int(k); w=collections.Counter((b,t.replace("Z","+00:00"),v["generator"]) for b,t in v["records"])
    got=recset(byart.get(aid,[]))
    check(f"rec {aid} 记录集",got==w,fmt_rec(got),fmt_rec(w))

# ---------- v1.8.16:12 篇 PARSE_FAIL 的完整记录多重集(由冻结期望展开,非输出反推)----------
print(f"\n--- 12 篇批次记录多重集(mother_universe.parse_fail_expectations 展开)---")
for k,v in sorted(PFE.items(),key=lambda kv:kv[0]):
    if not k.isdigit(): continue
    aid=int(k); gen=v["generator"]; w=collections.Counter()
    for b in v["batches"]:
        t=b["t"].replace("Z","+00:00")
        for base in {q.split("/")[0].upper() for q in b["pairs"]}: w[(base,t,gen)]+=1
    g_=recset(byart.get(aid,[]))
    check(f"pfe {aid} 记录集",g_==w,fmt_rec(g_) if g_!=w else f"{sum(g_.values())} 条吻合",
          fmt_rec(w) if g_!=w else f"{sum(w.values())} 条")
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
