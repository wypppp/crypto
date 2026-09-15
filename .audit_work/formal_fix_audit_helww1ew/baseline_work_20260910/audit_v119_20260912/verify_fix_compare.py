"""Compare the exact full-resume counterexample deliveries with a separate parallel run."""
import sys,json,subprocess
from pathlib import Path
sys.dont_write_bytecode=True
W=Path('/home/ancillary/rightTail/baseline_work_20260910');sys.path.insert(0,str(W))
import audit_flow as A
ROOT=Path(__file__).resolve().parent/'probes'; summary=[]
for mode in ['control','runtime_changed','primitives_changed','binding_removed']:
 d=ROOT/('resume_'+mode)
 rc,doc,rows,_=A.flow(d,'parallel',parallel=2,checkpoint=d/'parallel.ck');assert rc==0
 manifest=[]
 for tag,par,cp in [('first',1,'shared.ck'),('resume',1,'shared.ck'),('parallel',2,'parallel.ck')]:
  manifest.append(dict(kind='run',tag=tag,parallel=par,exit=(1 if tag=='resume' and mode!='control' else 0),checkpoint=str(d/cp),out=str(d/(tag+'.json')),evidence=str(d/(tag+'.jsonl'))))
 p=d/'audit_manifest.jsonl';assert not p.exists();p.write_text(''.join(json.dumps(x)+'\n' for x in manifest))
 b=json.loads((d/'shared.ck').read_text().splitlines()[0])
 cmd=[sys.executable,str(W/'realchain_tools/compare_runs.py'),'--dir',str(d),'--manifest',str(p),
 '--serial','first,resume','--parallel','parallel','--sample',str(d/'sample.json'),
 '--pin',str(b['finalized_number'])+':'+b['finalized_hash'],
 '--expect-script-sha',b['script_sha256'],'--expect-evidence-sha',b['evidence_module_sha256'],
 '--expect-spec-sha',b['spec_sha256'],'--expect-primitives-sha',b['primitives_sha256'],
 '--expect-runtime-params',json.dumps(b['runtime_params']),'--out',str(d/'full_comparator_report.json')]
 r=subprocess.run(cmd,cwd=W,capture_output=True,text=True,timeout=90)
 (d/'full_comparator_command.json').write_text(json.dumps(cmd,indent=2));(d/'full_comparator.log').write_text(r.stdout+r.stderr)
 rep=json.loads((d/'full_comparator_report.json').read_text());obs=dict(mode=mode,exit=r.returncode,verdict=rep['verdict']);summary.append(obs);print(json.dumps(obs),flush=True)
 assert r.returncode==(0 if mode=='control' else 1)
 if mode!='control':assert 'run_binding_matches:first' in rep['verdict']['failed']
(ROOT/'full_resume_compare.json').write_text(json.dumps(summary,indent=2)+'\n')
