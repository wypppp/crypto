"""Read-only/controlled audit. Only the fake launcher may execute measurement.
All output goes to this new audit directory, never to delivered run directories.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
A=Path(__file__).resolve().parent;W=A.parent
sys.path.insert(0,str(W/'realchain_tools'))
import run_compare as RC
load=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with Path(p).open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('ETH_RPC_URL',None);env.pop('ETHERSCAN_API_KEY',None)
def run(cmd,label,cwd=W,env_=None):
    p=subprocess.run(cmd,cwd=cwd,env=env_ or env,capture_output=True,text=True,timeout=300)
    save(A/(label+'.execution.json'),dict(argv=cmd,cwd=str(cwd),exit=p.returncode,stdout=p.stdout,stderr=p.stderr))
    return p
R1=W/'runs/formal_sub01_20260912T003750Z-f0c3ee'
R2=W/'runs/formal_sub02_20260912T011723Z-17018c'
R3=W/'runs/v119_20260911T233131Z-546793'

def compare(d,label,meta_source=None,one=False):
    meta=load((meta_source or d)/'driver.json');cs=meta['code_sha256']
    rr=[r for r in rows(d/'runs.jsonl') if r['kind']=='run']
    serial=[r['tag'] for r in rr if r['parallel']==1];parallel=[r['tag'] for r in rr if r['parallel']>=2]
    cmd=[sys.executable,'-B',str(W/'realchain_tools/compare_runs.py'),
         '--dir',str(d),'--parallel',','.join(parallel),'--sample',str(W/meta['sample']),
         '--pin',meta['pin'],'--expect-script-sha',cs['pilot_measure.py'],
         '--expect-evidence-sha',cs['evidence.py'],'--expect-spec-sha',cs['spec'],
         '--expect-primitives-sha',cs['primitives'],'--expect-runtime-params',json.dumps(meta['runtime_params']),
         '--out',str(A/(label+'.json'))]
    if one:
        for tag in serial:cmd.extend(['--ignore-tag',tag])
    else:cmd.extend(['--serial',','.join(serial)])
    p=run(cmd,label);return p,load(A/(label+'.json'))

# Previously reproduced counter defect: actual same-byte counterexample, read-only.
old_case=W/'audit_formal_20260912/counter_case'
positive=[]
for one in [False,True]:
    label='counter_'+('single' if one else 'pair')
    p,r=compare(old_case,label,meta_source=R1,one=one)
    assert p.returncode==1 and 'candidate_usage_matches_evidence:parallel' in r['verdict']['failed']
    p,r=compare(R1,'clean_'+label,one=one)
    assert p.returncode==0 and r['verdict']['passed']
    positive.append(dict(mode=one,broken_exit=1,clean_exit=0))
p,r=compare(R3,'round3_current')
assert p.returncode==0 and r['verdict']['n_checks']==60
save(A/'previous_counter_closed.json',{'cases':positive,'round3_checks':60})

# Existing partial group, copied before any attempted resume.
partial=A/'partial_copy';shutil.copytree(R2,partial)
sp=RC.spent(partial)
records=rows(partial/'parallel.evidence.jsonl')
max_mono=max(r.get('mono_s',0) for r in records)
save(A/'partial_accounting.json',dict(spent=sp,partial_max_mono_s=max_mono,
    incomplete_parallel_rpc=sum(r['kind']=='rpc' for r in records),
    incomplete_parallel_etherscan=sum(r['kind']=='etherscan' for r in records)))
assert sp['rpc']==2464 and sp['etherscan']==29 and 'parallel.evidence.jsonl' in sp['incomplete_evidence']
assert max_mono>17000
old_bytes={p.name:sha(p) for p in partial.iterdir() if p.is_file()}
resume=run([sys.executable,'-B',str(W/'realchain_tools/run_compare.py'),
    '--continue-dir',str(partial),'--resume','parallel','--compare',
    '--launch',str(W/'realchain_tools/fake_launch.py'),'--gap-s','0',
    '--budget-rpc','4000','--budget-etherscan','40','--budget-wall-s','4500'],'partial_resume')
assert resume.returncode==1 and '没有先前运行' in resume.stderr
assert not list(partial.glob('parallel_resume*.stdout.log'))
assert all(sha(partial/n)==h for n,h in old_bytes.items() if n!='runs.jsonl')
save(A/'resume_observation.json',dict(exit=resume.returncode,no_child_launched=True,
    reason=resume.stderr.strip(),completed_checkpoint_records=sum(x.get('completed') is True for x in rows(partial/'parallel.checkpoint.jsonl')),
    old_evidence_unchanged=True))

# Stopping after a threshold has already been crossed does not cap the next child.
fake_runs=A/'fake_runs';fake_runs.mkdir()
sample=A/'fake_sample.json'
save(sample,dict(universe_sha256=sha(W/'universe_run/universe.csv'),n=2,sample=[dict(
    index=i,pair='0x'+'ab'*20,token='0x'+'cd'*20,created_block=24140000) for i in [1,2]]))
def drive(name,opts,plan=None):
    before=set(fake_runs.iterdir())
    p=run([sys.executable,'-B',str(W/'realchain_tools/run_compare.py'),
        '--name',name,'--runs-root',str(fake_runs),'--sample',str(sample),
        '--pin','25900000:0x'+format(25900000,'064x'),
        '--launch',str(W/'realchain_tools/fake_launch.py'),'--sides','parallel','--gap-s','0',
        '--compare',*opts],name,env_=dict(env,RT_FAKE_PLAN=json.dumps(plan or {})))
    new=set(fake_runs.iterdir())-before;assert len(new)==1
    return p,next(iter(new))
obs=[]
for name,opts,key,limit in [('rpc_cap_one',['--budget-rpc','1'],'rpc',1),
                           ('wall_cap_tiny',['--budget-wall-s','0.001'],'wall_s',0.001)]:
    p,d=drive(name,opts);spent=RC.spent(d)
    assert p.returncode==0 and spent[key]>limit
    obs.append(dict(case=name,exit=p.returncode,limit=limit,key=key,spent=spent))
p,d=drive('zero_budget',['--budget-rpc','0'])
assert p.returncode==1 and not list(d.glob('*.evidence.jsonl'))
p,d=drive('stop_not_retried',['--max-resumes','2'],{'parallel':'exit:3','parallel_resume1':'exit:3'})
assert p.returncode==1 and [x['exit'] for x in rows(d/'runs.jsonl') if x['kind']=='run']==[3]
save(A/'budget_observations.json',dict(overshoots=obs,zero_prelaunch_limit_blocks=True,exit3_not_retried=True))

# The ledger must verify that a registered-tool report actually supports this group.
spec=importlib.util.spec_from_file_location('ledger_audit',W/'runs/formal_20260912/update_state.py')
U=importlib.util.module_from_spec(spec);spec.loader.exec_module(U)
camp=load(W/'runs/formal_20260912/campaign.json');U.batch_pin=camp['pin']
batch=next(b for b in camp['batches'] if b['id']=='sub01')
baseline=U.scan_dir(R1,camp);assert U.judge(batch,[baseline])[0] is True
foreign=A/'foreign_report_case';shutil.copytree(R1,foreign)
# Remove only new-tool rechecks in this isolated copy. The old auto-report is retained.
for f in foreign.glob('recompare_*.json'):f.unlink()
shutil.copy2(A/'round3_current.json',foreign/'recompare_foreign.json')
# Alter a value in the latest result: membership and top-level acceptance stay the same.
doc=load(foreign/'parallel_resume1.json')
c=next(c for c in doc['results'] if c.get('exit') and c['state']=='measured_exit')
idx=c['index'];original_cash=c['exit']['cash_in'];c['exit']['cash_in']+=1
(foreign/'parallel_resume1.json').write_text(json.dumps(doc)+'\n')
o=U.scan_dir(foreign,camp);done,problems=U.judge(batch,[o])
fresh,rep=compare(foreign,'fresh_foreign_case',meta_source=R1)
assert done is True and not problems and o['compare_report']=='recompare_foreign.json'
assert fresh.returncode==1 and not rep['verdict']['passed']
save(A/'foreign_report_observation.json',dict(ledger_done=done,ledger_problems=problems,
    report_selected=o['compare_report'],report_actual_group=str(R3),target_group=str(R1),
    candidate=idx,old_cash_in=original_cash,new_cash_in=original_cash+1,
    fresh_comparator_exit=fresh.returncode,fresh_comparator_failed=rep['verdict']['failed']))

# The campaign registers measurement code hashes but the ledger never compares them.
badcode=A/'campaign_code_case';shutil.copytree(R1,badcode)
d=load(badcode/'driver.json');d['code_sha256']['pilot_measure.py']='0'*64
(badcode/'driver.json').write_text(json.dumps(d)+'\n')
o=U.scan_dir(badcode,camp);done,problems=U.judge(batch,[o])
assert done is True and not problems
save(A/'campaign_code_observation.json',dict(ledger_done=done,registered_script=camp['code_sha256']['pilot_measure.py'],
    directory_script=d['code_sha256']['pilot_measure.py'],problems=problems))

# Do not overwrite the delivered state when independently re-running the ledger.
state_dir=A/'state_recheck';state_dir.mkdir();shutil.copy2(W/'runs/formal_20260912/campaign.json',state_dir/'campaign.json')
p=run([sys.executable,'-B',str(W/'runs/formal_20260912/update_state.py'),'--state-dir',str(state_dir)],'ledger_recheck')
assert p.returncode==0
state=load(state_dir/'collection_state.json')
assert state['cost_so_far']=={'rpc':5133,'etherscan':62,'wall_s':4588.0,'unmatched_rpc_begin':1}
assert state['progress']['subset_done']==1 and state['progress']['main_done']==0
save(A/'summary.json',dict(previous_counter_closed=True,interrupted_rpc_now_counted=True,exit3_retry_closed=True,
    remaining=['budget permits full-child overshoot and omits interrupted wall time',
        'partial parallel group cannot be resumed via current driver',
        'campaign accepts unrelated/stale registered-tool report and ignores registered measurement code'],
    existing_campaign_progress=state['progress']))
print('AUDIT OBSERVATIONS REPRODUCED; previous targeted fixes independently checked')
