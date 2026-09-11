"""Run the delivered comparator against isolated copies, including negative controls."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

W = Path('/home/ancillary/rightTail/baseline_work_20260910')
R = W/'runs/realchain2_20260911'
sys.path.insert(0,str(W))
C = types.ModuleType('audited_comparator')
C.__file__ = str(R/'compare.py')
exec(compile((R/'compare.py').read_text(), C.__file__, 'exec'),C.__dict__)
chain = ('serial','resume_serial','parallel','resume_parallel','resume_parallel2')
outcomes=[]
for scene in ('baseline','one_wei','validation_flip','missing_footer','final_exit_1','missing_final_run_entries'):
    with tempfile.TemporaryDirectory(prefix='rta-compare-negative-') as td:
        dst = Path(td)
        for tag in chain:
            for suffix in ('.json','.evidence.jsonl'):
                shutil.copyfile(R/(tag+suffix),dst/(tag+suffix))
        shutil.copyfile(R/'runs.jsonl',dst/'runs.jsonl')
        if scene in ('one_wei','validation_flip'):
            p=dst/'resume_parallel2.json';d=json.loads(p.read_text())
            c=next(x for x in d['results'] if x['index']==478595)
            if scene=='one_wei': c['exit']['cash_in']+=1
            else: c['state_validation_exit']['passed']=not c['state_validation_exit']['passed']
            p.write_text(json.dumps(d))
        if scene=='missing_footer':
            p=dst/'serial.evidence.jsonl'
            rows=[json.loads(x) for x in p.read_text().splitlines()]
            assert sum(x['kind']=='run_footer' for x in rows)==1
            p.write_text(''.join(json.dumps(x)+'\n' for x in rows if x['kind']!='run_footer'))
        if scene in ('final_exit_1','missing_final_run_entries'):
            p=dst/'runs.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()]
            if scene=='final_exit_1':
                for x in rows:
                    if x['tag']=='resume_parallel2': x['exit']=1
            else: rows=[x for x in rows if x['tag'] not in ('resume_serial','resume_parallel2')]
            p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        C.R=dst
        with contextlib.redirect_stdout(io.StringIO()):rc=C.main('resume_serial','resume_parallel2',chain)
        report=json.loads((dst/'compare_report.json').read_text())
        outcomes.append(dict(scene=scene,exit=rc,verdict=report['verdict']))
        assert rc==(1 if scene in ('one_wei','validation_flip') else 0)
        if scene=='missing_footer':assert report['verdict']['both_evidence_complete'] is False
        if scene=='final_exit_1':assert report['verdict']['final_cumulative_exit_0'] is False
        if scene=='missing_final_run_entries':assert report['verdict']['final_cumulative_exit_0'] is True
out=Path(__file__).resolve().parent
(out/'comparator_observations.json').write_text(json.dumps(outcomes,indent=2))
print(json.dumps(outcomes,indent=2))
