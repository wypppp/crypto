"""Build a metadata-only evidence overlay; does not change eligibility or fetch prices."""
from pathlib import Path
import argparse, collections, csv, hashlib, json
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=Path(__file__).resolve().parents[2]/'.probe_L_work');a=p.parse_args()
here=Path(__file__).resolve().parent; w=a.work
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
u=read(w/'L_u_master.json'); pairs=read(w/'u_trade_candidates.json')['pairs']; days=read(w/'agg_earliest_day.json')
source_path=here/'identity_sources.json'; sources={b:(old,url) for b,old,url in read(source_path)}
pending={r['base_asset']:r for r in u['trade_only_eligibility'] if r['verdict']=='PENDING_EVIDENCE'}
assert len(pending)==42 and len(sources)==38 and set(pending)==set(sources)|{'ACE','BDOT','WBETH','NBT'}
manifest_path=here/'baseline_manifest.json'
assert manifest_path.exists(), 'Freeze baseline_manifest.json before building'
manifest=read(manifest_path)
for name,digest in manifest['inputs'].items(): assert sha(w/name)==digest,(name,'INPUT_CHANGED')
assert sha(source_path)==manifest['identity_sources_sha256']
notes={
 'OOKI':'换币入口停用通知证明 BZRX→OOKI 关联；本条未独立确认换币完成日与首开时间。',
 'REI':'来源为币安官方中文公告频道；记录 GXS→REI 关联，不使用跳转后已失效的支持页作为证据。',
 'NOM':'Binance Academy 回顾性身份说明；不是历史时点可交易信号。',
 'T':'NU 与 KEEP 合并为 T；不可当作单一旧币 1:1 改名。',
 'LUNC':'旧 LUNA→LUNC；不与后来的新 LUNA 按字符串合并。',
 'FRAX':'此处为 FXS→FRAX；必须区分历史同名稳定币。',
 'KAIA':'来源证明 KLAY→KAIA；不把该关系当成对全部合并参与方的完整描述。'
}
rows=[]
for base,original in sorted(pending.items()):
 r={'base_asset':base,'T0_day':original['T0_day'],'embargo':original['embargo'],'baseline_attribution':original['attribution'],'baseline_eligibility':original['verdict'],'eligibility_action':'RETAIN_PENDING_NO_EXCLUSION','retrieved_on':'2026-09-07','evidence_use':'IDENTITY_AND_CATALOG_AUDIT_ONLY_NOT_TRADING_SIGNAL','legacy_symbols':None,'article_ids':[],'source_urls':[],'notes':None}
 assert r['embargo']==('EMBARGOED' if hashlib.sha256(base.encode()).digest()[0]%5==0 else 'FETCHABLE')
 if base in sources:
  old,url=sources[base];r.update(evidence_class='LEGACY_IDENTITY_DOCUMENTED',legacy_symbols=old,source_urls=[url],finding=f'一手来源明确关联 {old} → {base}。',next_requirement='补齐相关换币事件、合约/比例/生效时间；分别裁定首次经济资产上市与 U_trade 收益口径。',notes=notes.get(base,'本条仅确认身份关联；未宣称所有换币执行细节均已核验。'))
 elif base=='ACE':
  d=read(w/'ann_body/185740.json');r.update(evidence_class='MISSED_LISTING_CONFIRMED',article_ids=[185740],source_urls=['https://www.binance.com/en/support/announcement/detail/'+d['code']],finding='本地 Launchpool 公告明确列出 ACE 2023-12-18 06:00 UTC 与五个交易对；C1 模板漏掉 tentatively set to list。',next_requirement='将隔离修复纳入新版本并重跑裁定、时间链与联合表，再冻结新增取数清单。',notes='当前正式 1134 行、206 条取数清单及固定 37 条核验样本均未改写；没有新下载 ACE 行情。')
 elif base in {'BDOT','WBETH'}:
  aid=81389 if base=='BDOT' else 161233;d=read(w/f'ann_body/{aid}.json');r.update(evidence_class='STAKING_WRAPPER_DOCUMENTED',article_ids=[aid],source_urls=['https://www.binance.com/en/support/announcement/detail/'+d['code']],finding=('BDOT 为已质押 DOT 的代币化凭证。' if base=='BDOT' else 'WBETH 为含质押收益的流动性质押凭证；同篇 CVC 不适用相同裁定。'),next_requirement='为包装/质押凭证明确上市资格；保留 SAME_DAY_OPEN_ONLY 证据与未裁定状态。',notes='身份事实不能替代资产类别资格规则。')
 else:
  r.update(evidence_class='VENUE_EVIDENCE_PENDING',source_urls=['https://support.tokocrypto.com/hc/en-us/articles/4693749255309-NBT-is-going-to-be-Listed-on-Tokocrypto','https://support.tokocrypto.com/hc/en-us/articles/4722887851405-Join-TKO-x-NBT-Trading-Competition-to-win-more-than-IDR-1-Billion'],finding='Tokocrypto 官方列出 NanoByte NBT/BIDR 与 NBT/USDT 于 2022-03-11 13:00 UTC+7 开盘；与本地两对及日期一致。',next_requirement='核实本地归档对应的交易场所与 Binance Global 历史交易资格。',notes='此一致性提出场所疑点；既不能证明本地污染，也不能证明 Binance 从未上市 NBT。')
 r['local_pairs']=[dict(x,earliest_trade_day=days.get(x['symbol'],{}).get('earliest_trade_day')) for x in pairs if x['base']==base]
 r['local_article_sha256']={str(i):sha(w/f'ann_body/{i}.json') for i in r['article_ids']}
 rows.append(r)
counts=dict(collections.Counter(r['evidence_class'] for r in rows));assert counts=={'LEGACY_IDENTITY_DOCUMENTED':38,'MISSED_LISTING_CONFIRMED':1,'STAKING_WRAPPER_DOCUMENTED':2,'VENUE_EVIDENCE_PENDING':1}
assert all(r['eligibility_action']=='RETAIN_PENDING_NO_EXCLUSION' for r in rows)
out={'status':'EVIDENCE_OVERLAY_NOT_A_NEW_UNIVERSE','baseline_manifest':manifest,'script_sha256':sha(Path(__file__)),'n_rows':42,'evidence_counts':counts,'new_market_downloads':0,'eligibility_changes':0,'rows':rows}
(here/'qualification_evidence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
fields=['base_asset','T0_day','embargo','evidence_class','legacy_symbols','finding','next_requirement','notes','source_urls']
with (here/'qualification_evidence.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
 for r in rows:writer.writerow({k:' ; '.join(r[k]) if isinstance(r[k],list) else r[k] for k in fields})
print(json.dumps({'rows':42,'evidence_counts':counts,'eligibility_changes':0,'new_market_downloads':0},ensure_ascii=False))
