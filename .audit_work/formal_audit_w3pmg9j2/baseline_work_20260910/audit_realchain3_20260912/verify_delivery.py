"""Independent read-only audit of round 3. Outputs stay beside this script.
Run from baseline_work_20260910 with python3 -B. No endpoint requests.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
W = OUT.parent
R = W / 'runs/v119_20260911T233131Z-546793'
sys.path.insert(0, str(W))
import evidence as E

def deny_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        raise AssertionError('This audit must not access a network endpoint')
sys.addaudithook(deny_network)

load = lambda p: json.loads(p.read_text())
lines = lambda p: [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def save(name, value):
    with (OUT / name).open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def protected_snapshot():
    paths = set()
    for d in [W/'runs', *W.glob('audit_*')]:
        if d != OUT:
            paths.update(p for p in d.rglob('*') if p.is_file())
    paths.update(W/k for k in load(W/'runs/v119_20260911/source_hashes.json'))
    paths.add(W/'pilot/dev_sample.json')
    return {str(p.relative_to(W)): sha(p) for p in sorted(paths)}

before = protected_snapshot()
save('protected_before.json', before)
inventory = {}
for name, manifest, base in [
    ('historical', W/'audit_v116_20260911/delivery_artifact_hashes.json', W),
    ('sources', W/'runs/v119_20260911/source_hashes.json', W),
    ('round3_delivery', W/'runs/realchain3_20260912/artifact_hashes.json', W/'runs'),
]:
    declared = load(manifest)
    wrong = [p for p,h in declared.items() if not (base/p).is_file() or sha(base/p) != h]
    inventory[name] = {'files': len(declared), 'mismatches': wrong}
    assert not wrong, (name, wrong)
save('declared_hash_verification.json', inventory)

driver = load(R/'driver.json')
manifest = lines(R/'runs.jsonl')
attempts = [x for x in manifest if x['kind']=='run']
tags = ['serial','serial_resume1','serial_resume2','parallel','parallel_resume1']
assert [x['tag'] for x in attempts] == tags
assert [x['exit'] for x in attempts] == [1,1,0,1,0]
assert manifest[-1]['kind']=='driver_end' and manifest[-1]['driver_exit']==0
assert manifest[-1]['compare_exit']==0 and manifest[-1]['last_exit_per_side']=={'serial':0,'parallel':0}
assert len({x['run_id'] for x in [load(R/(t+'.json')) for t in tags]})==5
source_paths = {'pilot_measure.py':W/'pilot_measure.py', 'evidence.py':W/'evidence.py',
    'spec':W/'MEASUREMENT_SPEC.v1.19.md','sample':W/'pilot/dev_sample.json',
    'primitives':W.parent/'baseline_20260909/verify_capabilities.py'}
assert {k:sha(v) for k,v in source_paths.items()} == driver['code_sha256']
cmd = [sys.executable, '-B', str(W/'realchain_tools/compare_runs.py'),
    '--dir',str(R),'--serial',','.join(tags[:3]),'--parallel',','.join(tags[3:]),
    '--sample',str(source_paths['sample']),'--pin',driver['pin'],
    '--expect-script-sha',sha(source_paths['pilot_measure.py']),
    '--expect-evidence-sha',sha(source_paths['evidence.py']),
    '--expect-spec-sha',sha(source_paths['spec']),
    '--expect-primitives-sha',sha(source_paths['primitives']),
    '--expect-runtime-params',json.dumps(driver['runtime_params']),
    '--out',str(OUT/'comparator.json')]
cp = subprocess.run(cmd,cwd=W,text=True,capture_output=True,
                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
save('comparator_execution.json',dict(argv=cmd,exit=cp.returncode,stdout=cp.stdout,stderr=cp.stderr))
assert cp.returncode==0, cp.stderr
comparison = load(OUT/'comparator.json')
assert comparison['verdict']['passed'] and comparison['verdict']['n_checks']==58

docs={t:load(R/(t+'.json')) for t in tags}
rows={}; annotated={}; ck={}; report={'runs':{},'candidates':[],'errors':[],
    'raw_probe_checks':0, 'result_trace_checks':0, 'cost_scenarios_checked':0}
sample=load(source_paths['sample'])
expected={c['index']:c for c in sample['sample']}
assert len(expected)==sample['n']==8
assert sha(W/'universe_run/universe.csv')==sample['universe_sha256']
pin=docs['serial']['finalized_snapshot']
assert f"{pin['number']}:{pin['hash']}"==driver['pin']
assert pin['number']==25957369
for side in ['serial','parallel']:
    cr=lines(R/(side+'.checkpoint.jsonl'))
    binding=cr[0]
    assert binding['kind']=='binding'
    wanted={
        'sample_sha256':sha(source_paths['sample']), 'spec_sha256':sha(source_paths['spec']),
        'script_sha256':sha(source_paths['pilot_measure.py']),
        'evidence_module_sha256':sha(source_paths['evidence.py']),
        'primitives_sha256':sha(source_paths['primitives']),
        'universe_sha256':sample['universe_sha256'],
        'finalized_number':pin['number'],'finalized_hash':pin['hash'],
        'runtime_params':driver['runtime_params']}
    assert set(wanted)==set(E.Checkpoint.BINDING_KEYS)
    assert {k:binding[k] for k in wanted}==wanted
    ck[side]=(binding,cr[1:])

for t,d in docs.items():
    rr,diag=E.read_evidence(R/(t+'.evidence.jsonl'),report=True)
    assert diag['complete']
    assert len({x['run_id'] for x in rr})==1
    assert rr[0]['run_id']==d['run_id']
    hh=[x for x in rr if x['kind']=='run_header']; assert len(hh)==1
    h=hh[0]
    assert h['finalized_snapshot']==d['finalized_snapshot']==pin
    assert h['universe_sha256_now']==h['universe_sha256_declared']==sample['universe_sha256']
    assert h['universe_match'] and h['chain_id']==d['chain_id']==1
    assert h['script_sha256']==driver['code_sha256']['pilot_measure.py']
    assert h['evidence_module_sha256']==driver['code_sha256']['evidence.py']
    assert h['spec_sha256']==driver['code_sha256']['spec']
    assert h['sample_sha256']==driver['code_sha256']['sample']
    assert h['params']==next(x for x in lines(R/'serial.evidence.jsonl') if x['kind']=='run_header')['params']
    side='serial' if t.startswith('serial') else 'parallel'
    problems,rule=E.verify_run_binding(rr,d['run_id'],ck[side][0],result_doc=d)
    assert not problems and rule=='run_binding'
    assert len(d['results'])==len({c['index'] for c in d['results']})==8
    for c in d['results']:
        assert all(c[k]==v for k,v in expected[c['index']].items())
        assert c['economic_eligible'] is False
    acc=d['acceptance']
    assert acc['economic_results_eligible'] is False and acc['measurement_semantics_verified'] is False
    assert not acc['worker_errors'] and not acc['evidence_chain_problems']
    assert not acc['missing_candidates'] and not acc['duplicate_results']
    assert acc['process_completed']==(t in {'serial_resume2','parallel_resume1'})
    cnt=collections.Counter(x['kind'] for x in rr)
    assert cnt['rpc']==d['rpc_calls']
    assert cnt['rpc']+cnt['etherscan']==d['gate_stats']['http_sent']==d['gate_stats']['http_reserved']
    gov=next(x for x in rr if x['kind']=='governor_report')
    assert not gov['stopped'] and not gov['limits']['hard_problems']
    assert gov['escalations']==gov['absolute_deadline_closures']==gov['pending_inflight']==0
    hard=gov['limits']['hard_backstop']['applied']
    assert set(hard)=={'RLIMIT_AS','RLIMIT_CPU'} and all(v['verified'] for v in hard.values())
    assert hard['RLIMIT_AS']['readback']==8589934592 and hard['RLIMIT_CPU']['readback']==[3600,3605]
    active={}; ar=[]
    for z in rr:
        worker=z.get('worker')
        if z['kind']=='candidate_start':
            assert worker not in active
            active[worker]=z['candidate']
        if z['kind']=='block_cache_hit':
            assert worker in active
            z=dict(z,candidate=active[worker])
        ar.append(z)
        if z['kind']=='candidate_end': assert active.pop(worker)==z['candidate']
        if z['kind']=='rpc' and z['record'].get('error'):
            r=z['record']; assert r['error']['kind']=='transport'
            assert r['method']=='eth_getBlockByNumber' and r['attempt']==1
            report['errors'].append(dict(run=t,candidate=z['candidate'],stage=z['stage'],
                method=r['method'],params=r['params'],error=r['error']))
    assert not active
    starts=[x['candidate'] for x in rr if x['kind']=='candidate_start']
    assert set(starts).isdisjoint(acc['skipped_already_completed'])
    assert set(starts)|set(acc['skipped_already_completed'])==set(expected)
    rows[t]=rr;annotated[t]=ar
    report['runs'][t]=dict(rpc=cnt['rpc'],etherscan=cnt['etherscan'],http=d['gate_stats']['http_sent'],
        evidence_complete=diag['complete'],binding_rule=rule,new_candidates=starts,
        skipped=acc['skipped_already_completed'],incomplete=acc['incomplete'],
        rss_peak_kb=gov['final']['rss_peak_kb'],cpu_s=gov['final']['cpu_s'],
        transport_errors=sum(x['run']==t for x in report['errors']))

assert len(report['errors'])==5
assert collections.Counter(x['stage'] for x in report['errors'])=={'exit_locate':4,'restore_check':1}
for error in report['errors']:
    t=error['run']; idx=error['candidate']
    c=next(c for c in docs[t]['results'] if c['index']==idx)
    assert c['state']=='data_missing'
    assert idx in docs[t]['acceptance']['incomplete']
    if error['stage']=='restore_check':
        assert t=='serial_resume1' and idx==491410
        assert c['validation_status']=='unavailable' and c['validation_passed'] is None
        assert c['restore_check']['passed'] is None
        assert c['restore_check']['unavailable'][0]['error_kind']=='transport'
        assert docs[t]['acceptance']['validation_unavailable']==[491410]
        assert c['entry']['attempts']['swap']==1 and c['exit']['attempts']['swap']==1
        assert len(c['cost']['G_by_scenario'])==9
        assert report['runs']['serial_resume2']['new_candidates']==[491410]
    else:
        assert c['validation_status']=='passed' and c['validation_passed'] is True
        assert c['state_validation']['passed'] is True and c['restore_check']['passed'] is True
        assert 'state_validation_exit' not in c
    side='serial' if t.startswith('serial') else 'parallel'
    attempt=[x for x in ck[side][1] if x.get('evidence_run_id')==docs[t]['run_id'] and x.get('candidate')==idx]
    assert len(attempt)==1 and attempt[0]['completed'] is False

def probe_return(hexdata):
    # Decode directly from the saved ABI response, not from result JSON or P.parse_probe.
    assert hexdata.startswith('0x')
    raw=bytes.fromhex(hexdata[2:])
    assert len(raw)>=224 and len(raw)%32==0
    words=[int.from_bytes(raw[i:i+32],'big') for i in range(0,224,32)]
    assert words[5]==192 and len(raw)==224+32*((words[6]+31)//32)
    return dict(zip(['stage','token_before','token_after','eth_before','eth_after'],words[:5]))

sources={}
for side,t in [('serial','serial_resume2'),('parallel','parallel_resume1')]:
    binding,attempt_history=ck[side]
    latest={x['candidate']:x for x in attempt_history if x.get('completed')}
    assert set(latest)==set(expected)
    for c in docs[t]['results']:
        x=latest[c['index']];bare={k:v for k,v in c.items() if k!='carried_from_checkpoint'}
        assert x['result']==bare and E.result_sha256_of(bare)==x['result_sha256']
        origin=next(k for k,d in docs.items() if d['run_id']==x['evidence_run_id'])
        assert Path(x['evidence_file']).resolve()==(R/(origin+'.evidence.jsonl')).resolve()
        assert not E.verify_evidence_supports(x['evidence_file'],run_id=x['evidence_run_id'],
            candidate=c['index'],result_sha256=x['result_sha256'],binding=binding,result_doc=docs[origin])
        report['result_trace_checks']+=1
        mine=[z for z in annotated[origin] if z.get('candidate')==c['index']]
        rpc=[z for z in mine if z['kind']=='rpc']
        assert len(rpc)==c['rpc_calls']
        assert sum(z['kind']=='etherscan' for z in mine)==c['etherscan_calls']==1
        assert c['validation_passed'] is True
        sources[(side,c['index'])]=(c,mine)
        for stage,field in [('entry_buy','entry'),('exit_sell','exit')]:
            calls=[z['record'] for z in rpc if z['stage']==stage]
            if c[field] is None: assert not calls; continue
            assert len(calls)==1
            v=probe_return(calls[0]['response']['result']); rec=c[field]
            assert v['stage']==rec['stage']
            if field=='entry':
                assert rec['received']==v['token_after']-v['token_before']
                assert rec['eth_debit']==v['eth_before']-v['eth_after']
            else:
                assert rec['cash_in']==v['eth_after']-v['eth_before']
                assert (rec['token_before'],rec['token_after'])==(v['token_before'],v['token_after'])
            report['raw_probe_checks']+=1
        if c['entry']:
            assert c['model']['holding_state_basis']=='none_beyond_injection'
            assert c['state_validation']['passed'] and c['state_validation_exit']['passed'] and c['restore_check']['passed']
            for field,snap in c['blocks'].items():
                # Independently verify saved block responses and predecessor linkage.
                blocks=[z['record']['response']['result'] for z in annotated[origin]
                    if z['kind']=='rpc' and z['record']['method']=='eth_getBlockByNumber'
                    and not z['record'].get('error')]
                b=[b for b in blocks if int(b['number'],16)==snap['number']]
                prev=[b for b in blocks if int(b['number'],16)==snap['prev_number']]
                assert b and prev
                assert all(v['hash']==snap['hash'] and int(v['timestamp'],16)==snap['timestamp'] for v in b)
                assert all(v['hash']==snap['prev_hash'] and int(v['timestamp'],16)==snap['prev_timestamp'] for v in prev)
                assert snap['number']==snap['prev_number']+1
                assert snap['parent_hash']==snap['prev_hash'] and all(v['parentHash']==snap['prev_hash'] for v in b)
                if field=='exit':
                    assert snap['bracket_target']==c['blocks']['entry']['timestamp']+30*86400
                    assert snap['prev_timestamp']<snap['bracket_target']<=snap['timestamp']
                assert all(int(v['baseFeePerGas'],16)==c[field]['base_fee'] for v in b)
            cost=c['cost']
            assert len(cost['G_by_scenario'])==9
            for key,value in cost['G_by_scenario'].items():
                a,b=key.split('_'); assert a.startswith('swap') and b.startswith('tip')
                gas=int(a[4:]);tip=int(b[3:])
                total=sum((cost[leg+'_attempts']['swap']*gas+cost[leg+'_attempts']['approve']*50000)*
                          (cost['base_fee_'+leg]+tip) for leg in ['entry','exit'])
                assert value==total
                report['cost_scenarios_checked']+=1

ignore={'elapsed_s','rpc_calls','etherscan_calls','carried_from_checkpoint'}
for idx in sorted(expected):
    a,ar=sources[('serial',idx)];b,br=sources[('parallel',idx)]
    assert {k:v for k,v in a.items() if k not in ignore}=={k:v for k,v in b.items() if k not in ignore}
    hits=[sum(z['kind']=='block_cache_hit' for z in rr) for rr in [ar,br]]
    assert a['rpc_calls']+hits[0]==b['rpc_calls']+hits[1]
    report['candidates'].append(dict(index=idx,state=a['state'],validation_status=a['validation_status'],
        rpc=[a['rpc_calls'],b['rpc_calls']],cache=hits,fields_equal=True))
assert report['raw_probe_checks']==28 and report['result_trace_checks']==16

# Count historical rounds independently, including aborted startup evidence in round 1.
totals={}
for name,d in [('round1',W/'runs/realchain_20260911'),('round2',W/'runs/realchain2_20260911'),('round3',R)]:
    tally=collections.Counter();per={}
    for p in sorted(d.glob('*.evidence.jsonl')):
        counts=collections.Counter()
        for row in lines(p):
            if row['kind']=='rpc':
                counts['rpc']+=1
                if row['record'].get('error'): counts['errors']+=1
            if row['kind']=='etherscan': counts['etherscan']+=1
        tally.update(counts);per[p.name]=dict(counts)
    totals[name]={'totals':dict(tally),'per_file':per,'error_pct':100*tally['errors']/tally['rpc']}
assert totals['round3']['totals']=={'rpc':1755,'errors':5,'etherscan':21}
assert totals['round2']['totals']=={'rpc':1605,'errors':4,'etherscan':20}
assert totals['round1']['totals']['rpc']==687 and totals['round1']['totals']['errors']==4
serial_s=sum(x['wall_s'] for x in attempts if x['parallel']==1)
parallel_s=sum(x['wall_s'] for x in attempts if x['parallel']==2)
report['counts_by_round']=totals
report['wall_s']={'serial_including_resumes':serial_s,'parallel_including_resumes':parallel_s,
    'parallel_pct':100*parallel_s/serial_s,'basis':'sum of manifest child wall_s; excludes inter-run delays and driver/comparator overhead'}
report['snapshot']=pin
save('independent_verification.json',report)

# Cross-snapshot observation: list all schema additions with actual values.
old=load(W/'runs/realchain2_20260911/resume_serial.json')
assert old['finalized_snapshot']['number']==25950799
old_by={c['index']:c for c in old['results']}
assert set(old_by)==set(expected)
diffs=[];adds=[]
def walk(a,b,path):
    if isinstance(a,dict) and isinstance(b,dict):
        for k in sorted(set(a)|set(b)):
            p=path+'.'+k
            if k not in a: adds.append({'path':p,'value':b[k]})
            elif k not in b: diffs.append({'path':p,'removed':a[k]})
            else: walk(a[k],b[k],p)
    elif isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):diffs.append({'path':path,'old':a,'new':b})
        else:
            for i,(x,y) in enumerate(zip(a,b)):walk(x,y,f'{path}[{i}]')
    elif a!=b: diffs.append({'path':path,'old':a,'new':b})
for idx in sorted(expected):
    a={k:v for k,v in old_by[idx].items() if k not in ignore}
    b={k:v for k,v in sources[('serial',idx)][0].items() if k not in ignore}
    walk(a,b,str(idx))
assert not diffs,diffs
for add in adds:
    key=add['path'].split('.')[-1];v=add['value']
    assert (key in {'validation_status','status'} and v in {'passed','not_applicable'}) or (key in {'unavailable','failures'} and v==[]) or (key=='passed' and v is True) or (key=='interrupted_by' and v is None),add
def locate_requests(rr,idx):
    return [int(z['record']['params'][0],16) for z in rr if z['kind']=='rpc' and z.get('candidate')==idx and z.get('stage')=='exit_locate' and not z['record'].get('error')]
old_req=locate_requests(lines(W/'runs/realchain2_20260911/serial.evidence.jsonl'),478595)
new_req=locate_requests(rows['serial'],478595)
assert old_req and new_req and old_req!=new_req
save('cross_snapshot.json',dict(old_snapshot=old['finalized_snapshot'],new_snapshot=pin,
    unchanged_candidates=8,value_changes=diffs,schema_additions=adds,
    ignored_top_fields=sorted(ignore),exit_search_example={'index':478595,'round2_blocks':old_req,'round3_blocks':new_req},
    note='Historical entry/exit results agree; binary-search request blocks depend on the finalized upper bound.'))

# Scan existing configured values without printing them or putting them in outputs.
vals={}
for line in Path('/home/ancillary/.env').read_text().splitlines():
    if ':' in line:
        k,v=line.split(':',1);vals[k.strip().lower()]=v.strip()
url=next(v for k,v in vals.items() if 'endpoint' in k)
key=next(v for k,v in vals.items() if 'etherscan' in k)
secrets=[url.encode(),key.encode(),url.rsplit('/',1)[-1].encode()]
assert all(len(v)>=12 for v in secrets)
files=[p for p in R.rglob('*') if p.is_file()]
hits=[str(p.relative_to(R)) for p in files if any(s in p.read_bytes() for s in secrets)]
assert len(files)==25 and not hits
save('credential_scan.json',dict(files=25,hits=hits,scope='configured full RPC URL, final URL path component, Etherscan key; literal byte scan only'))
after=protected_snapshot()
changes={k:{'before':before.get(k),'after':after.get(k)} for k in set(before)|set(after) if before.get(k)!=after.get(k)}
save('protected_after.json',after)
save('preservation.json',{'files_before':len(before),'files_after':len(after),'changes':changes})
assert not changes
print(json.dumps(dict(passed=True,comparator=58,traced_results=16,decoded_probes=28,
    costs_checked=report['cost_scenarios_checked'],round_counts={k:v['totals'] for k,v in totals.items()},
    wall_s=report['wall_s'],historical_hashes=inventory['historical']['files'],
    source_hashes=inventory['sources']['files'],protected_files=len(before),schema_additions=len(adds)),ensure_ascii=False))
