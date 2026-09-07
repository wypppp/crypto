"""Probe L · 公告正文清单。ann_body/ 是 L_03 的实际输入,必须可校验。
产出 ann_body_manifest.json:逐文件 SHA-256 + 组合根哈希(按 article_id 排序拼接后再哈希)。
组合根哈希是 ann_body/ 整体内容的单一指纹,写入 L_mother_events.json 以固定复现链。"""
import json,os,sys,hashlib,datetime
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
REQ=["ann_raw.json","crawl_report.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
mu=cfg["mother_universe"]; exp_n=mu["expected_count_in_window"]
W0=datetime.datetime.fromisoformat(mu["window_start_utc"]).replace(tzinfo=datetime.timezone.utc)-datetime.timedelta(days=mu["lookback_days"])
W1=datetime.datetime.fromisoformat(mu["window_end_utc"]).replace(tzinfo=datetime.timezone.utc)+datetime.timedelta(days=1)
f_=lambda ms: datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc)
expected={a["id"] for a in json.load(open("ann_raw.json")) if W0<=f_(a["releaseDate"])<W1}
assert len(expected)==exp_n, f"窗口内 {len(expected)} != config {exp_n}"
entries=[]; missing=[]; bad=[]
for i in sorted(expected):
    p=f"ann_body/{i}.json"
    if not os.path.exists(p): missing.append(i); continue
    raw=open(p,'rb').read()
    try: r=json.loads(raw)
    except Exception: bad.append({"id":i,"why":"JSON 不可解析"}); continue
    if r.get("http")!=200 or not r.get("text"): bad.append({"id":i,"why":f"http={r.get('http')} text={'有' if r.get('text') else '无'}"}); continue
    entries.append({"article_id":i,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)})
root=hashlib.sha256("\n".join(f"{e['article_id']}:{e['sha256']}" for e in entries).encode()).hexdigest()
complete = (len(entries)==exp_n)
out={"config_sha256":H["L_config.json"],"expected_count":exp_n,"present_count":len(entries),
     "complete":complete,"missing_ids":missing,"invalid":bad,
     "combined_root_sha256":root,"generated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "entries":entries}
json.dump(out,open("ann_body_manifest.json","w"),ensure_ascii=False)
print(f"expected={exp_n}  present={len(entries)}  missing={len(missing)}  invalid={len(bad)}")
print(f"组合根哈希 = {root}")
print(f"完整性: {'✅ complete' if complete else '⚠ INCOMPLETE —— L_03 将拒绝正式产出母表'}")
record_outputs(["ann_body_manifest.json"])
