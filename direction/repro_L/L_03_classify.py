"""Probe L · 分类与提取(config v1.4.1)。
⚠ 门控:抓取完整性断言(success_ids == expected_ids)未通过时,**拒绝产出母表**,只允许 --dryrun 验证解析器。
桶:SPOT_LISTING / OPERATIONAL_UPDATE / PARSE_FAIL / FETCH_FAIL / OTHER,五者互斥且求和 == expected。"""
import json,os,re,sys,datetime,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load
DRY="--dryrun" in sys.argv
cfg,H=load([__file__,"L_00_bootstrap.py"])
mu=cfg["mother_universe"]
W0=datetime.datetime.fromisoformat(mu["window_start_utc"]).replace(tzinfo=datetime.timezone.utc)
W1=datetime.datetime.fromisoformat(mu["window_end_utc"]).replace(tzinfo=datetime.timezone.utc)+datetime.timedelta(days=1)
WB=W0-datetime.timedelta(days=mu["lookback_days"])
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)

# ---- v1.3 提取规则 ----
ENT=re.compile(r'&nbsp;|&#160;|\u00a0')
def norm(t):                      # v1.4 step0:实体与空白规范化
    return re.sub(r'\s+',' ',ENT.sub(' ',t).replace('&amp;','&'))
CAND=lambda t: bool(re.search(r'will list',t,re.I) and re.search(r'spot trading pair',t,re.I))
SPAN=re.compile(r'will list(.*?)(?:open trading|and open)',re.I|re.S)
ASSET=re.compile(r'([A-Za-z0-9 .\-]{2,40}?)\s*\(([A-Za-z0-9]{1,15})\)')   # v1.4:允许小写与单字符
BARE=re.compile(r'\b([A-Za-z0-9]{1,15})\b')
# v1.4.1:本文自身动作为暂停/恢复/推迟者 = OPERATIONAL_UPDATE(不得误用 'cancel',会命中 cancel all pending orders)
OPS=re.compile(r'we will (halt|suspend|pause)|listing will be postponed|will be postponed|will restart|resume trading',re.I)
TIME=re.compile(r'(\d{4}-\d{2}-\d{2})\s*(\d{1,2}:\d{2})\s*\(?UTC\)?')
STRUCT=re.compile(r'will list(.{0,1200}?open trading.{0,300})',re.I|re.S)   # 时间必须落在该结构内
def pairs_in(text):
    """正文中列出的现货交易对(大小写不敏感),用于交叉验证代号"""
    s=set()
    for m in re.finditer(r'\b([A-Za-z0-9]{1,15})\s*/\s*([A-Za-z0-9]{2,10})\b',text): s.add(m.group(1).upper())
    for m in re.finditer(r'\b([A-Za-z0-9]{1,15})(USDT|USDC|FDUSD|BNB|BTC|TRY|EUR)\b',text): s.add(m.group(1).upper())
    return s
def extract(text):
    """返回 (events, reason)。events=[(name,base)];reason 非空表示解析失败"""
    text=norm(text)
    sp=SPAN.search(text)
    if not sp: return [],"未找到 will list…open trading 片段"
    st=STRUCT.search(text)                       # v1.4.1:时间绑定到上市结构,禁止取全文首个
    if not st: return [],"未找到 will list…open trading 的完整结构"
    tm=TIME.search(st.group(1))
    if not tm: return [],"上市结构内未找到 UTC 时间(禁止回退到全文首个)"
    listed=pairs_in(text)
    got=[]
    for name,base in ASSET.findall(sp.group(1)):
        if base.upper() in listed: got.append((name.strip()[:60],base.upper()))
    if not got:                                        # v1.4 step2b:回退到裸 token,仍须交叉验证
        seen=set()
        for tok in BARE.findall(sp.group(1)):
            u=tok.upper()
            if u in listed and u not in seen: seen.add(u); got.append((tok,u))
    if not got: return [],f"片段内无通过交叉验证的代号(括号候选={[b for _,b in ASSET.findall(sp.group(1))][:6]})"
    try: ts=datetime.datetime.strptime(f"{tm.group(1)} {tm.group(2)}","%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
    except Exception: return [],"时间解析失败"
    return [(n,b,ts) for n,b in got],""

A=json.load(open("ann_raw.json"))
expected={a["id"]:a for a in A if WB<=f_(a["releaseDate"])<W1}
def read(i):
    p=f"ann_body/{i}.json"
    if not os.path.exists(p): return None
    try: return json.load(open(p))
    except Exception: return None
succ={i for i in expected if (r:=read(i)) and r.get("http")==200 and r.get("text")}
complete = (succ==set(expected))
print(f"抓取完整性: success={len(succ)} / expected={len(expected)}  -> {'✅ 通过' if complete else '⚠ 未通过'}")
if not complete and not DRY:
    sys.exit("抓取未完成且非 --dryrun ⟹ 按 config discipline 拒绝产出母表")

buckets=collections.Counter(); events=[]; pfail=[]; ffail=[]; opsu=[]
for i,a in expected.items():
    r=read(i)
    if not r or r.get("http")!=200 or not r.get("text"):
        buckets["FETCH_FAIL"]+=1; ffail.append({"id":i,"http":str(r.get("http")) if r else "no_file","title":a["title"][:80]}); continue
    t=r["text"]
    if not CAND(t): buckets["OTHER"]+=1; continue
    got,why=extract(t)
    if why:
        if OPS.search(norm(t)):                  # v1.4.1:自身动作是暂停/恢复/推迟 ⟹ 独立桶,不删除任何已有事件
            buckets["OPERATIONAL_UPDATE"]+=1
            opsu.append({"id":i,"title":a["title"][:90],"reason":why}); continue
        buckets["PARSE_FAIL"]+=1; pfail.append({"id":i,"reason":why,"title":a["title"][:90]}); continue
    buckets["SPOT_LISTING"]+=1
    for name,base,ts in got:
        events.append({"event_id":f"{i}::{base}","article_id":i,"base_asset":base,"asset_name":name,
                       "T_scheduled":ts.isoformat(),"release_date":f_(a["releaseDate"]).isoformat(),
                       "title":a["title"][:110],"n_assets_in_article":len(got)})
tot=sum(buckets.values())
print(f"\n桶:  SPOT_LISTING={buckets['SPOT_LISTING']}  OPERATIONAL_UPDATE={buckets['OPERATIONAL_UPDATE']}  "
      f"PARSE_FAIL={buckets['PARSE_FAIL']}  FETCH_FAIL={buckets['FETCH_FAIL']}  OTHER={buckets['OTHER']}   求和={tot} / {len(expected)}")
assert tot==len(expected), "断言失败:五桶求和 != expected"
print("  [断言] 五桶互斥且求和 == expected  ✅")
if opsu:
    print(f"\nOPERATIONAL_UPDATE {len(opsu)} 条(不产生事件,**不删除/替换任何已有上市事件**):")
    for x in opsu[:8]: print(f"    {x['id']}  {x['title'][:70]}")
inw=[e for e in events if W0<=datetime.datetime.fromisoformat(e["T_scheduled"])<W1]
print(f"\n按 T_scheduled 落窗的现货上市事件 = {len(inw)}   不同 baseAsset = {len({e['base_asset'] for e in inw})}")
multi=[e for e in inw if e["n_assets_in_article"]>1]
print(f"  来自多资产公告的事件 = {len(multi)}")
if pfail:
    print(f"\nPARSE_FAIL {len(pfail)} 条(逐条列出):")
    for x in pfail[:12]: print(f"    {x['id']}  {x['reason'][:70]}  | {x['title'][:60]}")
# ---- v1.4.1 召回率审计 ----
print("\n=== 召回率审计 ===")
byyr=collections.Counter(e["T_scheduled"][:4] for e in inw)
art=collections.Counter(datetime.datetime.fromisoformat(e["T_scheduled"]).strftime("%Y") for e in inw)
seen=set(); artyr=collections.Counter()
for e in inw:
    if e["article_id"] not in seen: seen.add(e["article_id"]); artyr[e["T_scheduled"][:4]]+=1
print("  年份 : 文章数 / 事件数")
for y in sorted(byyr): print(f"    {y} : {artyr[y]:>4} / {byyr[y]:>4}")
SUS=re.compile(r'list|listing|open trading|launchpool',re.I)
sus=[{"id":i,"title":expected[i]['title']} for i in expected
     if (r:=read(i)) and r.get("http")==200 and r.get("text") and not CAND(r["text"]) and SUS.search(expected[i]["title"])]
print(f"\n  OTHER 中标题含 list/listing/open trading/launchpool 的疑似漏项 = {len(sus)} 条(须逐条审阅)")
for x in sus[:15]: print(f"    {x['id']}  {x['title'][:88]}")
if not DRY: json.dump(sus,open("L_recall_suspects.json","w"),ensure_ascii=False,indent=1)
if DRY: print(f"\n[DRYRUN] 未写母表文件。")
else:
    json.dump({"config_sha256":H["L_config.json"],"buckets":dict(buckets),"events":sorted(inw,key=lambda x:x["T_scheduled"]),
               "parse_fail":pfail,"fetch_fail":ffail,"operational_update":opsu,"recall_suspects":sus},open("L_mother_events.json","w"),ensure_ascii=False,indent=1)
    print("\n-> L_mother_events.json")
