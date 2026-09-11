#!/usr/bin/env python3
"""Independent read-only/copy-only comparator probes; driver uses a fully fake launch.

rc=0 means controls passed and the documented remaining counterexamples reproduced.
All output paths are exclusive or within a newly created --out-root.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

W=Path(__file__).resolve().parent.parent
T=W/'realchain_tools'
R2=W/'runs/realchain2_20260911'
PIN='25950799:0xe7e5d3e8b2be05e6e1c537f1a8ea534121c5defc9b6e7ea8edc54d01dd446e82'
EXPECT=[line.split()[0] for line in (R2/'code_hashes_at_launch.txt').read_text().splitlines()]

def run(cmd,d,env=None):
    p=subprocess.run(cmd,cwd=W,env=env,capture_output=True,text=True,timeout=180)
    (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    (d/'stdout.log').write_text(p.stdout);(d/'stderr.log').write_text(p.stderr)
    (d/'exit.json').write_text(json.dumps(p.returncode)+'\n')
    return p


def comparator(root,mode):
    d=root/mode;d.mkdir();inp=d/'inputs';inp.mkdir()
    for p in R2.iterdir():
        if p.is_file(): (inp/p.name).symlink_to(p)
    manifest=[json.loads(l) for l in (inp/'runs.jsonl').read_text().splitlines() if l.strip()]
    cp=inp/Path(next(r['checkpoint'] for r in manifest if r.get('tag')=='serial')).name
    rows=[json.loads(l) for l in cp.read_text().splitlines() if l.strip()]
    before=json.loads(json.dumps(rows[0]))
    if mode=='primitives_changed':rows[0]['primitives_sha256']='0'*64
    if mode=='runtime_changed':rows[0]['runtime_params']['slot_limit']=0
    if mode=='bindings_deleted':
        del rows[0]['primitives_sha256'];del rows[0]['runtime_params']
    if mode=='known_field_control':rows[0]['script_sha256']='0'*64
    if mode!='baseline':
        cp.unlink();cp.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (d/'binding_before_after.json').write_text(json.dumps(dict(before=before,after=rows[0]),indent=2)+'\n')
    cmd=[sys.executable,str(T/'compare_runs.py'),'--dir',str(inp),
         '--serial','serial,resume_serial','--parallel','parallel,resume_parallel,resume_parallel2',
         '--sample',str(W/'pilot/dev_sample.json'),'--pin',PIN,
         '--expect-script-sha',EXPECT[0],'--expect-evidence-sha',EXPECT[1],
         '--expect-spec-sha',EXPECT[2],'--out',str(d/'report.json')]
    p=run(cmd,d);rep=json.loads((d/'report.json').read_text())
    obs=dict(case=mode,exit=p.returncode,verdict=rep['verdict'])
    print(json.dumps(obs));return obs


def compare_without_initial(d, run_dir, sample):
    """Positive/negative controls: exclude only the initial attempt from the declared chain.
    This is safe only when no final candidate inherits evidence from that attempt.
    """
    out=d/'exclude_initial_control';out.mkdir()
    meta=json.loads((run_dir/'driver.json').read_text()); cs=meta['code_sha256']
    cmd=[sys.executable,str(T/'compare_runs.py'),'--dir',str(run_dir),
         '--serial','serial_resume1','--parallel','parallel','--ignore-tag','serial',
         '--sample',str(sample),'--pin',meta['pin'],
         '--expect-script-sha',cs['pilot_measure.py'],'--expect-evidence-sha',cs['evidence.py'],
         '--expect-spec-sha',cs['spec'],'--out',str(out/'report.json')]
    p=run(cmd,out);rep=json.loads((out/'report.json').read_text())
    return dict(exit=p.returncode,verdict=rep['verdict'])


def driver(root,mode):
    d=root/mode;d.mkdir();(d/'runs').mkdir()
    sys.path.insert(0,str(W))
    import pilot_measure as P
    import evidence as E
    sample=d/'sample.json'
    sample.write_text(json.dumps(dict(universe_sha256=E.sha256_file(P.UNIVERSE),n=2,
             sample=[dict(index=i,pair='0x'+'ab'*20,token='0x'+'cd'*20,created_block=24140000) for i in [1,2]])))
    launch=d/'launch.py'
    # The normal fake launcher patches BOTH real endpoint implementations. This wrapper
    # adds only the startup transport fault, below RpcTap, to the initial serial run.
    launch.write_text('''import sys, runpy
from pathlib import Path
from unittest.mock import patch
W=Path('''+repr(str(W))+''')
sys.path.insert(0,str(W))
import pilot_measure as P
from fake_chain import FakeRpc
tag=Path(sys.argv[sys.argv.index('--out')+1]).stem
orig=FakeRpc.request
def request(self,method,params):
    if tag=='serial' and method=='eth_chainId':
        self.records.append(dict(method=method,params=params,error=dict(kind='transport',message='controlled startup EOF')))
        raise P.V.RpcFailure('transport','controlled startup EOF')
    return orig(self,method,params)
with patch.object(FakeRpc,'request',request):
    runpy.run_path(str(W/'realchain_tools/fake_launch.py'),run_name='__main__')
''')
    env=dict(os.environ);env['RT_FAKE_PLAN']=json.dumps({'serial':'flaky'} if mode=='candidate_failure_recovery' else {})
    chosen=launch if mode=='startup_failure_recovery' else T/'fake_launch.py'
    cmd=[sys.executable,str(T/'run_compare.py'),'--name','offline','--runs-root',str(d/'runs'),
         '--sample',str(sample),'--pin','25900000:0x'+f'{25900000:064x}',
         '--launch',str(chosen),'--gap-s','0','--max-resumes','1','--compare',
         '--extra=--rps','--extra=10000','--extra=--slot-limit','--extra=2']
    p=run(cmd,d,env)
    run_dir=next((d/'runs').iterdir())
    manifest=[json.loads(l) for l in (run_dir/'runs.jsonl').read_text().splitlines() if l.strip()]
    end=manifest[-1]
    attempts=[dict(tag=r['tag'],exit=r['exit']) for r in manifest if r.get('kind')=='run']
    report=json.loads(next(run_dir.glob('compare_*.json')).read_text())
    obs=dict(case=mode,exit=p.returncode,attempts=attempts,driver_end=end,verdict=report['verdict'])
    obs['exclude_initial_control']=compare_without_initial(d,run_dir,sample)
    if mode=='startup_failure_recovery':
        ev=[json.loads(l) for l in (run_dir/'serial.evidence.jsonl').read_text().splitlines() if l.strip()]
        obs['startup_aborts']=[r for r in ev if r.get('kind')=='abort']
    (d/'observation.json').write_text(json.dumps(obs,indent=2)+'\n')
    print(json.dumps(obs));return obs


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out-root',required=True);a=ap.parse_args()
    root=Path(a.out_root);root.mkdir(exist_ok=False)
    results={n:comparator(root,n) for n in ['baseline','primitives_changed','runtime_changed','bindings_deleted','known_field_control']}
    assert results['baseline']['exit']==0 and results['baseline']['verdict']['n_checks']==53
    assert results['known_field_control']['exit']==1
    for n in ['primitives_changed','runtime_changed','bindings_deleted']:
        assert results[n]['exit']==0 and results[n]['verdict']['passed'] and not results[n]['verdict']['failed']
    for n in ['candidate_failure_recovery','startup_failure_recovery']:
        results[n]=driver(root,n)
    assert results['candidate_failure_recovery']['exit']==0
    assert results['candidate_failure_recovery']['exclude_initial_control']['exit']==1
    s=results['startup_failure_recovery']
    assert s['exit']==1 and s['attempts']==[dict(tag='serial',exit=2),dict(tag='serial_resume1',exit=0),dict(tag='parallel',exit=0)]
    assert s['driver_end']['last_exit_per_side']==dict(serial=0,parallel=0)
    assert s['startup_aborts'] and s['startup_aborts'][0]['reason']=='endpoint_unreachable'
    assert s['exclude_initial_control']['exit']==0
    assert s['verdict']['failed'] and all(':serial' in v or v=='binding_consistent' for v in s['verdict']['failed'])
    (root/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    print('Controls and remaining comparator-binding/driver-recovery gaps reproduced.')

if __name__=='__main__': main()
