"""Offline audit probes: output only in this new audit directory; no live launch."""
import collections
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
A=Path(__file__).resolve().parent; W=A.parent
sys.path.insert(0,str(W))
import evidence as E
load=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    with Path(p).open('x') as f:f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rewrite(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False)+'\n')
def rewrite_lines(p,rs):Path(p).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs))
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('ETH_RPC_URL',None);env.pop('ETHERSCAN_API_KEY',None)
commands=[]
def run(cmd,cwd=W,name='command',env_=None):
    p=subprocess.run(cmd,cwd=cwd,env=env_ or env,capture_output=True,text=True,timeout=300)
    commands.append(dict(name=name,argv=cmd,cwd=str(cwd),exit=p.returncode,stdout=p.stdout,stderr=p.stderr))
    save(A/(name+'_execution.json'),commands[-1]);return p

S=W/'pilot/formal_20260912'; sm=load(S/'formal_sample_300.json'); mf=load(S/'MANIFEST.json')
dev=load(W/'pilot/dev_sample.json');dev_ids={x['index'] for x in dev['sample']}
assert sha(S/'formal_sample_300.json')==mf['formal_sample_300.json']== '38d685ed8842c5335855defaa8caa1f56a4ad59d998f74ad38b5fbd03335e93a'
assert sha(W/'universe_run/universe.csv')==sm['universe_sha256']==dev['universe_sha256']
with (W/'universe_run/universe.csv').open() as f:universe=[r for r in csv.DictReader(f) if r['category']=='weth']
picked=random.Random(sm['seed']).sample(universe,308)
ids={int(r['index']) for r in picked}-dev_ids
assert ids=={r['index'] for r in sm['sample']} and len(ids)==sm['n']==300 and not ids & dev_ids
for r in sm['sample']:
    row=next(x for x in universe if int(x['index'])==r['index'])
    assert r['pair']==row['pair'] and r['created_block']==int(row['block'])
    assert r['token'] in {row['token0'],row['token1']} and r['token'].lower()!='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
    assert r['created_block']<=24781026
main_ids=[]; sub_ids=[]
for group,dest in [('batches',main_ids),('subset_batches',sub_ids)]:
    for b in mf[group]:
        doc=load(S/b['file']);assert sha(S/b['file'])==b['sha256']
        assert doc['parent_sample_sha256']==mf['formal_sample_300.json']
        assert doc['n']==b['n']==len(doc['sample'])
        assert [c['index'] for c in doc['sample']]==b['indices']
        for c in doc['sample']:assert c==next(r for r in sm['sample'] if r['index']==c['index'])
        dest.extend(b['indices'])
assert set(main_ids)==ids and len(main_ids)==len(set(main_ids))==300
assert set(sub_ids)<=ids and len(sub_ids)==len(set(sub_ids))==30
assert len(mf['batches'])==15 and {x['n'] for x in mf['batches']}=={20}
assert [x['n'] for x in mf['subset_batches']]==[15,15]
declared=A/'declared_again'
p=run([sys.executable,'-B',str(W/'runs/freeze_plan_20260912/declare_formal.py'),str(declared)],name='declare_again')
assert p.returncode==0
assert load(declared/'formal_sample_300.json')['sample']==sm['sample']
assert all(load(declared/b['file'])['sample']==load(S/b['file'])['sample'] for b in mf['batches']+mf['subset_batches'])
save(A/'sample_verification.json',dict(passed=True,n=300,excluded=sorted(dev_ids),batches=15,subset_n=30,
    note='Candidate membership and partition reproduced; declared_at and dependent parent hash are intentionally not identical across regeneration.'))

R=W/'runs/formal_sub01_20260912T003750Z-f0c3ee'
man=rows(R/'runs.jsonl');tags=[r['tag'] for r in man if r['kind']=='run']
meta=load(R/'driver.json');allserial=[t for t in tags if t.startswith('serial')];allparallel=[t for t in tags if t.startswith('parallel')]
def compare(d,label,single=False):
    cs=meta['code_sha256'];cmd=[sys.executable,'-B',str(W/'realchain_tools/compare_runs.py'),
        '--dir',str(d),'--parallel',','.join(allparallel),'--sample',str(W/meta['sample']),
        '--pin',meta['pin'],'--expect-script-sha',cs['pilot_measure.py'],
        '--expect-evidence-sha',cs['evidence.py'],'--expect-spec-sha',cs['spec'],
        '--expect-primitives-sha',cs['primitives'],'--expect-runtime-params',json.dumps(meta['runtime_params']),
        '--out',str(A/(label+'.json'))]
    if single:
        for t in allserial:cmd.extend(['--ignore-tag',t])
    else:cmd.extend(['--serial',','.join(allserial)])
    p=run(cmd,name=label);return p.returncode,load(A/(label+'.json'))
rc,rep=compare(R,'subset01_recompare')
assert rc==0 and rep['verdict']['passed'] and rep['verdict']['n_checks']==51
save(A/'subset01_summary.json',dict(passed=True,checks=51,mode=rep['mode'],candidate_count=len(rep['candidates'])))

# A valid single-side result must still reconcile its own candidate RPC counter.
# Alter only the candidate counter and its result copies/hashes. Raw RPC rows and
# per-run counters remain untouched. Pair comparison used to check this invariant.
D=A/'counter_case';shutil.copytree(R,D)
rc,rep=compare(D,'single_counter_control',single=True);assert rc==0
doc=load(D/(allparallel[-1]+'.json'))
target=next(c for c in doc['results'] if c['state']=='measured_exit')['index']
ck=rows(D/'parallel.checkpoint.jsonl')
attempt=next(x for x in reversed(ck) if x.get('candidate')==target and x.get('completed'))
old_count=attempt['result']['rpc_calls'];attempt['result']['rpc_calls']+=7
attempt['rpc_calls']=attempt['result']['rpc_calls']
attempt['result_sha256']=E.result_sha256_of(attempt['result'])
for t in allparallel:
    d=load(D/(t+'.json'))
    for c in d['results']:
        if c['index']==target:
            c['rpc_calls']=old_count+7
            if c.get('carried_from_checkpoint'):c['carried_from_checkpoint']['result_sha256']=attempt['result_sha256']
    rewrite(D/(t+'.json'),d)
evname=Path(attempt['evidence_file']).name;rr=rows(D/evname)
for r in rr:
    if r['kind']=='candidate_result' and r.get('candidate')==target:r['record']['rpc_calls']=old_count+7
rewrite_lines(D/evname,rr);rewrite_lines(D/'parallel.checkpoint.jsonl',ck)
pair_rc,pair_rep=compare(D,'pair_counter_mismatch')
single_rc,single_rep=compare(D,'single_counter_mismatch',single=True)
assert pair_rc==1 and 'rpc_plus_cache_equal' in pair_rep['verdict']['failed']
assert single_rc==0 and single_rep['verdict']['passed']
save(A/'counter_observation.json',dict(candidate=target,raw_rpc_unchanged=True,old_count=old_count,reported_count=old_count+7,
    pair_exit=pair_rc,pair_failed=pair_rep['verdict']['failed'],single_exit=single_rc,single_failed=single_rep['verdict']['failed']))

# Cumulative budget: completed attempts are not the same thing as failed candidates.
budget_out=A/'budget_recomputed';budget_out.mkdir()
p=run([sys.executable,'-B',str(W/'runs/freeze_plan_20260912/budget_model.py')],cwd=budget_out,name='budget_model')
assert p.returncode==0
assert load(budget_out/'budget_model.json')==load(W/'runs/freeze_plan_20260912/budget_model.json')
rr3=W/'runs/v119_20260911T233131Z-546793'
errors_per={};new_starts={}
for t in ['serial','serial_resume1','serial_resume2','parallel','parallel_resume1']:
    rr=rows(rr3/(t+'.evidence.jsonl'))
    errors_per[t]=[x['candidate'] for x in rr if x['kind']=='rpc' and x['record'].get('error')]
    new_starts[t]=[x['candidate'] for x in rr if x['kind']=='candidate_start']
assert len(errors_per['serial'])==2 and len(errors_per['parallel'])==2
assert set(new_starts['parallel_resume1'])==set(errors_per['parallel'])
serial_rows=rows(rr3/'serial.evidence.jsonl')
first_error_seq=next(x['seq'] for x in serial_rows if x['kind']=='rpc' and x['record'].get('error'))
later_starts=[x['candidate'] for x in serial_rows if x['kind']=='candidate_start' and x['seq']>first_error_seq]
assert later_starts
save(A/'budget_control_flow.json',dict(errors_per_run=errors_per,new_candidates=new_starts,
    serial_candidates_started_after_first_error=later_starts,
    observed_rpc_errors=5,observed_resume_processes=3,
    plan_A_min_etherscan_without_any_resumes=300+2*30,
    note='This refutes one error == one process abort/resume. It does not estimate a population failure probability.'))

# The existing driver retries stop exit 3, too. All launches here are the fake one.
fake_root=A/'driver_fake';fake_root.mkdir()
fake_sample=A/'fake_sample.json'
save(fake_sample,dict(universe_sha256=sha(W/'universe_run/universe.csv'),n=2,sample=[dict(index=i,
    pair='0x'+'ab'*20,token='0x'+'cd'*20,created_block=24140000) for i in [1,2]]))
fake_plan={t:'exit:3' for t in ['parallel','parallel_resume1','parallel_resume2']}
p=run([sys.executable,'-B',str(W/'realchain_tools/run_compare.py'),
    '--name','stop','--runs-root',str(fake_root),'--sample',str(fake_sample),
    '--pin','25900000:0x'+format(25900000,'064x'),'--launch',str(W/'realchain_tools/fake_launch.py'),
    '--sides','parallel','--gap-s','0','--max-resumes','2','--compare'],
    name='driver_stop_retry',env_=dict(env,RT_FAKE_PLAN=json.dumps(fake_plan)))
dr=next(fake_root.iterdir());attempts=[x for x in rows(dr/'runs.jsonl') if x['kind']=='run']
assert p.returncode==1 and [x['exit'] for x in attempts]==[3,3,3]
save(A/'stop_retry_observation.json',dict(driver_exit=p.returncode,attempts=[{'tag':x['tag'],'exit':x['exit']} for x in attempts],
    max_resumes_200_per_side_max_attempts=201,each_attempt_gets_own_max_calls=4000,
    resulting_per_side_logical_budget_bound=201*4000))

# Read the campaign aggregator without executing its file-writing entry point.
sp=importlib.util.spec_from_file_location('campaign_audit',W/'runs/formal_20260912/update_state.py')
U=importlib.util.module_from_spec(sp);sp.loader.exec_module(U)
R2=W/'runs/formal_sub02_20260912T011723Z-17018c'
snap=A/'subset02_snapshot';shutil.copytree(R2,snap)
info=U.scan(snap)
actual=collections.Counter()
for f in snap.glob('*.evidence.jsonl'):
    for line in f.read_text().splitlines():
        try:r=json.loads(line)
        except ValueError:continue
        if r['kind'] in {'rpc','etherscan'}:actual[r['kind']]+=1
assert actual['rpc']>info['rpc_records']
save(A/'inflight_cost_observation.json',dict(aggregator_rpc=info['rpc_records'],evidence_rpc=actual['rpc'],
    missing_rpc=actual['rpc']-info['rpc_records'],aggregator_etherscan=info['etherscan_records'],evidence_etherscan=actual['etherscan'],
    manifest_rows=len(rows(snap/'runs.jsonl')),note='Evidence for a started, not yet manifest-recorded child is omitted from the cumulative total.'))

# Binding acceptance to folder names is insufficient: a completed 15-candidate
# subset can be counted as an approved 20-candidate main batch without checks.
campaign=A/'campaign_case';campaign.mkdir()
misnamed=campaign/'formal_main01_controlled';shutil.copytree(R,misnamed)
U.RUNS=campaign;U.SAMPLES=S
prev=Path.cwd();os.chdir(campaign)
try:U.main()
finally:os.chdir(prev)
state=load(campaign/'collection_state.json')
assert state['progress']['main_batches_passed']==1
assert state['batches']['01']['sample']=='subset_pair_01.json'
assert state['batches']['01']['finals']['parallel']['n_results']==15
save(A/'campaign_binding_observation.json',dict(main_batches_reported_passed=1,
    actual_sample=state['batches']['01']['sample'],actual_candidates=15,declared_main_batch_size=20,
    note='Controlled folder copy only; no original run or manifest was altered.'))
print('ALL AUDIT OBSERVATIONS REPRODUCED; sample and subset01 positive checks passed')
