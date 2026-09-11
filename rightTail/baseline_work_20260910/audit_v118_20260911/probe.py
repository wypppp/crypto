"""Independent offline probes. Source/delivery trees are read-only."""
import sys,types,json,hashlib,argparse,os,subprocess
from pathlib import Path
sys.dont_write_bytecode=True
W=Path('/home/ancillary/rightTail/baseline_work_20260910')
sys.path.insert(0,str(W));sys.path.insert(0,str(W/'realchain_tools'))
import audit_flow as A
import compare_runs as C
P,E=A.P,A.E
ROOT=Path(__file__).resolve().parent/'probes';ROOT.mkdir(exist_ok=False)
# Reuse the old fault injection, not its assertions that the old bugs exist.
f=W/'audit_v117_20260911/reproduce_remaining.py';m=types.ModuleType('old_faults');m.__file__=str(f)
exec(compile(f.read_text(),str(f),'exec'),m.__dict__)
closed={}
for n in ['baseline','sides_then_transport','restore_dirty_then_budget','entry_dirty_then_budget']:
 x=m.run_case(ROOT,n,n);closed[n]=x
 assert x['exit']==(0 if n=='baseline' else 1)
 assert x['validation_passed'] is (True if n=='baseline' else False)
 if n!='baseline':assert x['state']=='state_validation_failed'
(ROOT/'closed_classification.json').write_text(json.dumps(closed,indent=2)+'\n')
# Full resume entry point, varying only source evidence run_binding.
obs=[]
for mode in ['control','runtime_changed','primitives_changed','binding_removed']:
 d=ROOT/('resume_'+mode);d.mkdir();cp=d/'shared.ck'
 rc,doc,rows,_=A.flow(d,'first',checkpoint=cp);assert rc==0
 ev=d/'first.jsonl';before=ev.read_text(); rr=[json.loads(l) for l in before.splitlines()]
 rb=next(x for x in rr if x['kind']=='run_binding')
 original_rb=json.loads(json.dumps(rb))
 if mode=='runtime_changed':rb['runtime_params']['slot_limit']=999
 if mode=='primitives_changed':rb['primitives_sha256']='0'*64
 if mode=='binding_removed':rb['kind']='removed_run_binding'
 if mode!='control':ev.write_text(''.join(json.dumps(x)+'\n' for x in rr))
 assert E.read_evidence(ev,report=True)[1]['complete']
 rc2,doc2,rr2,_=A.flow(d,'resume',checkpoint=cp)
 h=next(x for x in rr if x['kind']=='run_header');binding=json.loads(cp.read_text().splitlines()[0])
 binding_ok,detail=C._run_binding_ok(rr,doc['run_id'],h,doc,binding)
 item=dict(mode=mode,exit=rc2,acceptance=doc2['acceptance'],skipped=doc2['acceptance']['skipped_already_completed'],
           comparator_binding_ok=binding_ok,comparator_binding_detail=detail,original_binding=original_rb,changed_binding=rb)
 obs.append(item);print(json.dumps(item),flush=True)
 assert rc2==0 and sorted(item['skipped'])==[1,2]
 assert not doc2['acceptance']['evidence_chain_problems']
 assert binding_ok is (mode=='control')
(ROOT/'resume_observations.json').write_text(json.dumps(obs,indent=2)+'\n')
# Comparator historical positive/three original negative controls, correct new CLI.
r2=W/'runs/realchain2_20260911'
exp=[line.split()[0] for line in (r2/'code_hashes_at_launch.txt').read_text().splitlines()]
binding=json.loads((r2/'serial.checkpoint.jsonl').read_text().splitlines()[0]);comps=[]
for mode in ['control','runtime_changed','primitives_changed','binding_removed']:
 d=ROOT/('compare_'+mode);d.mkdir();inp=d/'inputs';inp.mkdir()
 for p in r2.iterdir():
  if p.is_file():(inp/p.name).symlink_to(p)
 cp=inp/'serial.checkpoint.jsonl';rows=[json.loads(x) for x in cp.read_text().splitlines()]
 if mode=='runtime_changed':rows[0]['runtime_params']['slot_limit']=0
 if mode=='primitives_changed':rows[0]['primitives_sha256']='0'*64
 if mode=='binding_removed':
  del rows[0]['runtime_params'];del rows[0]['primitives_sha256']
 if mode!='control':cp.unlink();cp.write_text(''.join(json.dumps(x)+'\n' for x in rows))
 cmd=[sys.executable,str(W/'realchain_tools/compare_runs.py'),'--dir',str(inp),'--serial','serial,resume_serial',
      '--parallel','parallel,resume_parallel,resume_parallel2','--sample',str(W/'pilot/dev_sample.json'),
      '--pin',str(binding['finalized_number'])+':'+binding['finalized_hash'],
      '--expect-script-sha',exp[0],'--expect-evidence-sha',exp[1],'--expect-spec-sha',exp[2],
      '--expect-primitives-sha',binding['primitives_sha256'],'--expect-runtime-params',json.dumps(binding['runtime_params']),
      '--out',str(d/'report.json')]
 p=subprocess.run(cmd,cwd=W,capture_output=True,text=True,timeout=90)
 (d/'command.json').write_text(json.dumps(cmd,indent=2));(d/'stdout.log').write_text(p.stdout);(d/'stderr.log').write_text(p.stderr)
 report=json.loads((d/'report.json').read_text());item=dict(mode=mode,exit=p.returncode,verdict=report['verdict']);comps.append(item);print(json.dumps(item),flush=True)
 assert p.returncode==(0 if mode=='control' else 1)
(ROOT/'compare_observations.json').write_text(json.dumps(comps,indent=2)+'\n')
# True driver/measure entry point, fake endpoints. Startup failure then completed retry.
d=ROOT/'driver';d.mkdir();(d/'runs').mkdir()
sample=d/'sample.json'; sample.write_bytes((ROOT/'resume_control/sample.json').read_bytes())
cmd=[sys.executable,str(W/'realchain_tools/run_compare.py'),'--name','offline','--runs-root',str(d/'runs'),
 '--sample',str(sample),'--pin','25900000:0x'+f'{25900000:064x}',
 '--launch',str(W/'realchain_tools/fake_launch.py'),'--gap-s','0','--max-resumes','1','--compare',
 '--extra=--rps','--extra=10000','--extra=--slot-limit','--extra=2']
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',RT_FAKE_PLAN=json.dumps({'serial':'startup_fail'}))
p=subprocess.run(cmd,cwd=W,env=env,capture_output=True,text=True,timeout=120)
(d/'command.json').write_text(json.dumps(cmd,indent=2));(d/'stdout.log').write_text(p.stdout);(d/'stderr.log').write_text(p.stderr)
r=next((d/'runs').iterdir());manifest=[json.loads(x) for x in (r/'runs.jsonl').read_text().splitlines()]
print('driver exit',p.returncode,manifest[-1],flush=True);assert p.returncode==0
assert [(x['tag'],x['exit']) for x in manifest if x['kind']=='run']==[('serial',2),('serial_resume1',0),('parallel',0)]
(ROOT/'driver_observation.json').write_text(json.dumps(dict(exit=p.returncode,last=manifest[-1]),indent=2))
print('Independent closed-path checks and resume binding counterexamples complete.',flush=True)
