"""Probe L · B_RESOLVE(层 2 裁定)。
只对 L03 产出的 B 候选做首次/新增裁定;证据源 = agg_earliest_day.json(日粒度元数据)。
**不读 t0_exact.json / t0_manifest.json**,不触碰留出行情正文。
比较基准 = UTC-date(T_scheduled),**禁止使用 releaseDate**。
证据不足者保留 PENDING_ADJUDICATION,不为清零强行归类。
用法: [--dryrun]"""
import json,os,re,sys,collections,hashlib
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
DRY="--dryrun" in sys.argv
REQ=["L_mother_events.json","agg_earliest_day.json","u_trade_candidates.json","ann_raw.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
mu=cfg["mother_universe"]; BS=mu["rules"]["B_SPLIT"]; L2=BS["layer2_join_evidence"]

# ---------- 分类阶段隔离:B_RESOLVE 允许读日粒度元数据,仍禁止 T0 ----------
FORBID=["t0_exact.json","t0_manifest.json"]
_open=open
def guarded(p,*a,**k):
    if os.path.basename(str(p)) in FORBID: sys.exit(f"ISOLATION VIOLATION: B_RESOLVE 读取了 {p}")
    return _open(p,*a,**k)
open=guarded

FAIL=[]
def check(name,ok,got=None,want=None):
    print(f"[断言] {name}: got={got} want={want}  {'✅' if ok else '❌'}")
    if not ok: FAIL.append({"check":name,"got":got,"want":want})
    return ok

M=json.load(open("L_mother_events.json"))
check("上游母表 config 与本次一致",M["config_sha256"]==H["L_config.json"],
      M["config_sha256"][:16],H["L_config.json"][:16])
raw=M["raw_events"]
UC=json.load(open("u_trade_candidates.json")); AG=json.load(open("agg_earliest_day.json"))
sym2base={r["symbol"]:r["base"] for r in UC["pairs"]}
earliest={}                                    # base -> 该 base 全部交易对的最早成交日
for s,v in AG.items():
    b=sym2base.get(s)
    if b and v.get("status")=="OK" and v.get("earliest_trade_day"):
        d=v["earliest_trade_day"]
        if b not in earliest or d<earliest[b]: earliest[b]=d
print(f"[证据源] agg_earliest_day 覆盖 base = {len(earliest)}  (不含 T0 精确时刻)")

# v1.8.19:首次上市声明**直接读用 L03 写入的 first_marker_source**,两阶段口径必须一致,
# 不在本阶段重算 —— 重算会重新引入"标题无条件全文匹配"的风险。
NEG=os.environ.get("NEG_BR","")
out=[]; kinds=collections.Counter()
for e in raw:
    if e["generator"] not in ("B_FIRST_CANDIDATE","B_NEW_PAIR_CANDIDATE"): continue
    b=e["base_asset"]; sd=e["T_scheduled"][:10]; ed=earliest.get(b)
    fm=e.get("first_marker_source")                        # BODY / TITLE / None
    if NEG=="NO_ARCH" and b in ("GMX","BDOT"): ed=None      # 无证据反例
    if ed is None:
        k="ANNOUNCEMENT_ONLY" if fm else "PENDING_NO_ARCHIVE_EVIDENCE"
    elif ed< sd:                         k="NEW_QUOTE_PAIR_EXISTING_ASSET"
    elif ed==sd and fm:                  k="FIRST_SPOT_LISTING"
    elif ed==sd:                         k="PENDING_ADJUDICATION"   # SAME_DAY_OPEN_ONLY
    else:                                k="AMBIGUOUS"              # 归档晚于开盘日 = 证据冲突
    kinds[k]+=1
    out.append({**e,"final_kind":k,"evidence_earliest_trade_day":ed,
                "compared_against":sd,"first_marker_source":fm,
                "evidence_source":L2["evidence_source"]})
print(f"\n裁定分布: {dict(kinds)}")

# ---------- 分支覆盖断言(实测值,非预注册目标)----------
COV=mu["b_resolve_branch_coverage"]
for k,v in COV.items():
    if k.startswith("_"): continue
    check(f"分支 {k} 记录数",kinds.get(k,0)==v["expected_records"],kinds.get(k,0),v["expected_records"])

# ---------- 结构化回归样本(stage=B_RESOLVE)----------
byart=collections.defaultdict(list)
for e in out: byart[e["article_id"]].append(e)
rs=[s for s in mu["regression_samples"] if s.get("stage")=="B_RESOLVE"]
print(f"\n--- B_RESOLVE 回归样本({len(rs)} 条)---")
for s in rs:
    aid=s["article_id"]; got=byart.get(aid,[])
    check(f"regr {aid} 候选存在",len(got)>0,len(got),">0")
    if not got: continue
    check(f"regr {aid} bases",sorted({x['base_asset'] for x in got})==sorted(s["expect_bases"]),
          sorted({x['base_asset'] for x in got}),sorted(s["expect_bases"]))
    check(f"regr {aid} candidate_kind",{x['generator'] for x in got}=={s["expect_candidate_kind"]},
          sorted({x['generator'] for x in got}),s["expect_candidate_kind"])
    km={x['base_asset']:x['final_kind'] for x in got}          # v1.8.18:完整 base→裁定映射
    check(f"regr {aid} 裁定映射",km==dict(s["expect_kind_map"]),km,dict(s["expect_kind_map"]))
    if "expect_first_marker_source" in s:
        check(f"regr {aid} first_marker_source",
              {x['first_marker_source'] for x in got}=={s["expect_first_marker_source"]},
              sorted({str(x['first_marker_source']) for x in got}),s["expect_first_marker_source"])
    ev={x['base_asset']:x['evidence_earliest_trade_day'] for x in got}
    check(f"regr {aid} 证据留存",ev==s["evidence"],ev,s["evidence"])
    check(f"regr {aid} 比较基准=UTC-date(T_scheduled)",
          {x['compared_against'] for x in got}=={s["T_scheduled_date"]},
          sorted({x['compared_against'] for x in got}),s["T_scheduled_date"])

# ---------- 待裁定纪律:不得消失、不得强行归类 ----------
G=mu["b_resolve_semantics_gap"]["SAME_DAY_OPEN_ONLY"]
want={(i["article_id"],i["base"]) for i in G["all_instances"]}
gotp={(x["article_id"],x["base_asset"]) for x in out if x["final_kind"]=="PENDING_ADJUDICATION"}
check("SAME_DAY_OPEN_ONLY 实例集合",gotp==want,sorted(gotp),sorted(want))
check("待裁定实例数与 config 一致",len(gotp)==G["instances_measured"],len(gotp),G["instances_measured"])
noev=[x for x in out if x["final_kind"]=="PENDING_ADJUDICATION" and not x["evidence_earliest_trade_day"]]
check("待裁定记录均留存证据",not noev,len(noev),0)
# 事件守恒:B 候选一条不少
nb=sum(1 for e in raw if e["generator"] in ("B_FIRST_CANDIDATE","B_NEW_PAIR_CANDIDATE"))
check("B 候选守恒(裁定不删除记录)",len(out)==nb,len(out),nb)

if FAIL:
    for f in FAIL: print(f"  ❌ {f['check']}  got={f['got']}  want={f['want']}")
    sys.exit(f"FAIL-CLOSED:{len(FAIL)} 项检查未通过 ⟹ **拒绝写出 B_RESOLVE 产物**")
print("\n全部检查通过 ✅")
res={"config_sha256":H["L_config.json"],"stage":"B_RESOLVE",
     "evidence_source":L2["evidence_source"],"forbidden_inputs":FORBID,
     "kinds":dict(kinds),"n_records":len(out),"records":out}
if not DRY:
    json.dump(res,_open("L_b_resolve.json","w"),ensure_ascii=False,indent=1)
    record_outputs(["L_b_resolve.json"])
else: print("[dryrun] 未写出")
