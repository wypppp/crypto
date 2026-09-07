"""Replay ACE parser impact in an isolated directory. Does not publish a release."""
from pathlib import Path
import argparse,collections,hashlib,json,os,shutil,subprocess,sys,tempfile
here=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=here.parents[1]/'.probe_L_work');p.add_argument('--out',type=Path,required=True);a=p.parse_args();w=a.work.resolve();out=a.out.resolve()
assert not out.exists(),'Use a new output directory; preserve previous experiments'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((here/'baseline_manifest.json').read_text())
for n,digest in m['inputs'].items():assert sha(w/n)==digest,(n,'INPUT_CHANGED')
out.mkdir(parents=True)
with tempfile.TemporaryDirectory(prefix='ace_impact_') as t:
 tmp=Path(t)
 for n in ['L_config.json','L_00_bootstrap.py','L_03_classify.py','ann_raw.json','crawl_report.json','ann_body_manifest.json','u_trade_candidates.json','spot_exchangeinfo.json']:shutil.copy2(w/n,tmp/n)
 shutil.copytree(w/'ann_body',tmp/'ann_body');c=json.loads((tmp/'L_config.json').read_text());mu=c['mother_universe'];g=mu['rules']['GEN']['C_LAUNCH_THEN_LIST'];old=g['require'];assert old.startswith('will then list');g['require']=old.replace('will then list','(?:will then list|tentatively set to list)',1)
 # Expectations derived from article 185740 before parsing.
 for k in ['C1_raw_articles','C1_raw_events','C1_with']:mu['expected_counts'][k]+=1
 mu['regression_samples'].append({'article_id':185740,'stage':'L03_CLASSIFY','expect_events':1,'expect_candidate_kind':'C_LAUNCH_THEN_LIST','expect_records':[['ACE','2023-12-18T06:00:00+00:00','C_LAUNCH_THEN_LIST']]})
 (tmp/'L_config.json').write_text(json.dumps(c,ensure_ascii=False,indent=1)+'\n')
 for n in ['L_config.json','L_03_classify.py']:shutil.copy2(tmp/n,out/n)
 env={k:v for k,v in os.environ.items() if k!='L_CONFIG' and not k.startswith('NEG_')}
 r=subprocess.run([sys.executable,'-B','L_03_classify.py'],cwd=tmp,env=env,capture_output=True,text=True);(out/'run.log').write_text(r.stdout+r.stderr)
 if r.returncode:sys.exit(r.returncode)
 d=json.loads((tmp/'L_mother_events.json').read_text());base=json.loads((w/'L_mother_events.json').read_text());key=lambda e:(e['article_id'],e['base_asset'],e['T_scheduled'],e['generator']);bc=collections.Counter(map(key,base['raw_events']));dc=collections.Counter(map(key,d['raw_events']));add=list((dc-bc).elements());rem=list((bc-dc).elements());assert add==[(185740,'ACE','2023-12-18T06:00:00+00:00','C_LAUNCH_THEN_LIST')] and not rem
 before={key(e):e for e in base['raw_events']};after={key(e):e for e in d['raw_events']};assert len(before)==len(base['raw_events']);assert all(after[k]==e for k,e in before.items())
 assert after[add[0]]['announced_pairs']==['ACEBNB','ACEBTC','ACEFDUSD','ACETRY','ACEUSDT']
 s={'status':'ISOLATED_IMPACT_ONLY_NOT_PUBLISHED','baseline_config_sha256':sha(w/'L_config.json'),'baseline_raw':len(base['raw_events']),'experimental_raw':len(d['raw_events']),'added':add,'removed':rem,'checks_failed':d['checks_failed'],'unchanged_full_records':len(before),'announced_pairs':after[add[0]]['announced_pairs'],'scope':'Active config, production outputs and fixed 37-event sample unchanged'}
 (out/'impact.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n');shutil.copy2(tmp/'L_mother_events.json',out/'L_mother_events.json');print(json.dumps(s,ensure_ascii=False))
