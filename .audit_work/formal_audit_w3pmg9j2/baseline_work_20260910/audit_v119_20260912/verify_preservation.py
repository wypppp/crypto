import json
from pathlib import Path
D=Path(__file__).resolve().parent;R=D/'probes';out=[]
for mode in ['control','runtime_changed','primitives_changed','binding_removed']:
 d=R/('resume_'+mode)
 first=json.loads((d/'first.json').read_text());res=json.loads((d/'resume.json').read_text())
 rr=[json.loads(x) for x in (d/'resume.jsonl').read_text().splitlines()]
 ck=[json.loads(x) for x in (d/'shared.ck').read_text().splitlines()]
 raw=lambda xs:{c['index']:{k:v for k,v in c.items() if k!='carried_from_checkpoint'} for c in xs}
 assert raw(first['results'])==raw(res['results'])
 att=[c for c in ck if c['kind']=='attempt'];assert len(att)==2 and sorted(c['candidate'] for c in att)==[1,2]
 assert all(c['evidence_run_id']==first['run_id'] for c in att)
 assert not [x for x in rr if x['kind']=='candidate_start']
 acc=res['acceptance'];assert acc['measurement_semantics_verified'] is False and acc['economic_results_eligible'] is False
 comp=json.loads((d/'full_comparator_report.json').read_text())
 problems=acc['evidence_chain_problems']
 if mode!='control':
  assert 'new checkpoint' in acc['evidence_chain_action']
  cp=comp['checks']['final_results_traced:serial']['detail']
  assert sorted(problems,key=lambda x:x['candidate'])==sorted(cp,key=lambda x:x['candidate'])
 else:assert not problems and acc['evidence_chain_action']=='none'
 out.append(dict(mode=mode,results_preserved=True,attempts_preserved=len(att),remeasured_candidates=0,
                 evidence_chain_action=acc['evidence_chain_action'],same_per_candidate_reasons=True,
                 economic_eligible=False))
(D/'preservation_verification.json').write_text(json.dumps(out,indent=2));print('Results/history kept; no remeasurement; exact per-candidate reasons agree in all four cases.')
