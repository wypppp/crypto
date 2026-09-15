#!/usr/bin/env python3
"""Read-only re-count and hash verification. Writes only this audit's verification JSON."""
import collections
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
W=OUT.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
old=load(W/'audit_v116_20260911/delivery_artifact_hashes.json')
old_bad={n:dict(expected=h,actual=sha(W/n) if (W/n).is_file() else None)
         for n,h in old.items() if not (W/n).is_file() or sha(W/n)!=h}
decl=load(W/'runs/classify_20260911/source_hashes.json')
decl_bad={n:dict(expected=h,actual=sha(W/n) if (W/n).is_file() else None)
          for n,h in decl.items() if not (W/n).is_file() or sha(W/n)!=h}
assert not old_bad and not decl_bad,(old_bad,decl_bad)
inventory=[]
for dirname in ['realchain_20260911','realchain2_20260911']:
    root=W/'runs'/dirname
    for p in sorted(root.glob('*.evidence.jsonl')):
        rows=[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        rr=[x for x in rows if x['kind']=='rpc']
        errors=[x for x in rr if x['record'].get('error')]
        inventory.append(dict(path=str(p.relative_to(W)),rpc=len(rr),
           etherscan=sum(x['kind']=='etherscan' for x in rows),
           errors=[dict(stage=x.get('stage'),candidate=x.get('candidate'),
                        error_kind=x['record']['error'].get('kind')) for x in errors]))
nrpc=sum(x['rpc'] for x in inventory); nerr=sum(len(x['errors']) for x in inventory)
assert (nerr,nrpc)==(8,2292)
manifest=[json.loads(x) for x in (W/'runs/realchain2_20260911/runs.jsonl').read_text().splitlines() if x.strip()]
runs={x['tag']:x for x in manifest}
serial_s=sum(runs[t]['wall_s'] for t in ['serial','resume_serial'])
parallel_s=sum(runs[t]['wall_s'] for t in ['parallel','resume_parallel','resume_parallel2'])
assert abs(serial_s-902.2)<1e-8 and abs(parallel_s-715.0)<1e-8
prior=[json.loads(x) for x in (W/'runs/realchain_20260911/runs.jsonl').read_text().splitlines() if x.strip()]
startup={r['tag']:r['exit'] for r in prior if r['tag'] in ['parallel','resume_serial']}
assert startup=={'parallel':1,'resume_serial':1}
finals=[load(W/'runs/realchain2_20260911'/f'{n}.json') for n in ['resume_serial','resume_parallel2']]
for doc in finals:
    assert len(doc['results'])==8
    for c in doc['results']:
        assert c['validation_passed'] is True and c['economic_eligible'] is False
        for k in ('state_validation','state_validation_exit','restore_check'):
            if c.get(k):assert c[k]['passed'] is True,(c['index'],k)
    assert doc['acceptance']['measurement_semantics_verified'] is False
    assert doc['acceptance']['economic_results_eligible'] is False
assert len(old)==74
rep=dict(historical_manifest_count=len(old),historical_manifest_directories=dict(collections.Counter(str(Path(n).parent) for n in old)),
         historical_hash_problems=old_bad,declared_hash_count=len(decl),declared_hash_problems=decl_bad,
         spec_sha256=sha(W/'MEASUREMENT_SPEC.v1.17.md'),
         audited_source_unchanged=load(OUT/'hashes_start.json')==load(OUT/'hashes_end.json'),
         rpc_error_inventory=inventory,rpc_records=nrpc,rpc_errors=nerr,rpc_error_fraction=nerr/nrpc,
         etherscan_records=sum(x['etherscan'] for x in inventory),
         subrun_wall_s=dict(serial=serial_s,parallel=parallel_s,ratio=parallel_s/serial_s),
         first_round_startup_exits=startup,final_results_with_complete_validation=16,
         economic_eligible=False,measurement_semantics_verified=False,passed=True)
(OUT/'delivery_verification.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in rep.items() if k not in ('rpc_error_inventory',)},ensure_ascii=False))
