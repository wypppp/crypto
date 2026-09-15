import sys,json,hashlib,copy
from pathlib import Path
sys.dont_write_bytecode=True
W=Path('/home/ancillary/rightTail/baseline_work_20260910');D=Path(__file__).resolve().parent
sys.path.insert(0,str(W));import evidence as E
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old_pairs={
 (sha(W/'audit_v116_20260911/pilot_measure.audited.py'),sha(W/'MEASUREMENT_SPEC.v1.16.md')):'v1.16',
 (sha(W/'audit_v117_20260911/pilot_measure.audited.py'),sha(W/'MEASUREMENT_SPEC.v1.17.md')):'v1.17'}
assert E.LEGACY_BINDING_RULES==old_pairs
r=W/'runs/realchain2_20260911';rows=[json.loads(x) for x in (r/'serial.evidence.jsonl').read_text().splitlines()]
doc=json.loads((r/'serial.json').read_text());binding=json.loads((r/'serial.checkpoint.jsonl').read_text().splitlines()[0])
obs=[]
for mode in ['real_v116','no_legacy_result_doc','wrong_result_primitives','current_script_old_spec','mixed_legacy_pair']:
 rr=copy.deepcopy(rows);dd=copy.deepcopy(doc);b=copy.deepcopy(binding)
 h=next(x for x in rr if x['kind']=='run_header')
 if mode=='no_legacy_result_doc':dd=None
 if mode=='wrong_result_primitives':dd['package_script_sha256']='0'*64
 if mode=='current_script_old_spec':h['script_sha256']=sha(W/'pilot_measure.py')
 if mode=='mixed_legacy_pair':h['spec_sha256']=sha(W/'MEASUREMENT_SPEC.v1.17.md')
 problems,rule=E.verify_run_binding(rr,doc['run_id'],b,result_doc=dd)
 item=dict(mode=mode,problems=problems,rule=rule);obs.append(item)
 assert bool(problems) is (mode!='real_v116')
 if mode in ['current_script_old_spec','mixed_legacy_pair']:assert problems[0]['reason']=='evidence_run_binding_missing'
(D/'legacy_verification.json').write_text(json.dumps(dict(constants_match=True,cases=obs),indent=2))
print('Legacy exact-pair constants and five positive/negative cases verified.')
