"""Read-only verification of supplied artifacts; no network, no original writes."""
import collections
import hashlib
import json
import sys
from pathlib import Path

W = Path('/home/ancillary/rightTail/baseline_work_20260910')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(W))
import evidence as E
import pilot_measure as P

R = W / 'runs/realchain2_20260911'
tags = ['serial', 'parallel', 'resume_serial', 'resume_parallel', 'resume_parallel2']
load = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
docs = {t: load(R / (t + '.json')) for t in tags}
rows = {}
report = {'runs': {}, 'candidates': [], 'evidence_support_checks': 0, 'raw_probe_checks': 0}
sample = load(W / 'pilot/dev_sample.json')
expected = {c['index']: c for c in sample['sample']}
assert len(expected) == sample['n'] == 8
pin = docs['serial']['finalized_snapshot']
headers = []
for t, d in docs.items():
    rr, diag = E.read_evidence(R / (t + '.evidence.jsonl'), report=True)
    rows[t] = rr
    assert diag['complete']
    hh = [x for x in rr if x['kind'] == 'run_header']
    assert len(hh) == 1 and hh[0]['run_id'] == d['run_id']
    h = hh[0]; headers.append(h)
    assert h['script_sha256'] == sha(W / 'pilot_measure.py')
    assert h['evidence_module_sha256'] == sha(W / 'evidence.py')
    assert h['spec_sha256'] == sha(W / 'MEASUREMENT_SPEC.v1.16.md')
    assert h['sample_sha256'] == d['sample_sha256'] == sha(W / 'pilot/dev_sample.json')
    assert h['universe_sha256_now'] == sample['universe_sha256'] == sha(P.UNIVERSE)
    assert h['finalized_snapshot'] == d['finalized_snapshot'] == pin
    assert len(d['results']) == len({c['index'] for c in d['results']}) == 8
    for c in d['results']:
        for k, v in expected[c['index']].items():
            assert c[k] == v, (t, c['index'], k)
        assert c['economic_eligible'] is False
    assert d['acceptance']['economic_results_eligible'] is False
    assert d['acceptance']['measurement_semantics_verified'] is False
    counts = collections.Counter(x['kind'] for x in rr)
    assert counts['rpc'] == d['rpc_calls']
    assert counts['rpc'] + counts['etherscan'] == d['gate_stats']['http_sent']
    assert d['gate_stats']['http_sent'] == d['gate_stats']['http_reserved']
    gov = next(x for x in rr if x['kind'] == 'governor_report')
    assert not gov['stopped'] and not gov['limits']['hard_problems']
    hard = gov['limits']['hard_backstop']['applied']
    assert set(hard) == {'RLIMIT_AS', 'RLIMIT_CPU'}
    assert all(v['verified'] is True for v in hard.values())
    assert hard['RLIMIT_AS']['readback'] == hard['RLIMIT_AS']['bytes'] == 8589934592
    assert hard['RLIMIT_CPU']['readback'] == [3600, 3605]
    report['runs'][t] = dict(rpc=counts['rpc'], etherscan=counts['etherscan'],
        http=d['gate_stats']['http_sent'], evidence_complete=diag['complete'],
        new_candidates=[x['candidate'] for x in rr if x['kind'] == 'candidate_start'],
        skipped=d['acceptance']['skipped_already_completed'],
        rss_peak_kb=gov['final']['rss_peak_kb'], cpu_s=gov['final']['cpu_s'],
        transport_errors=sum(x['kind']=='rpc' and x['record'].get('error',{}).get('kind')=='transport' for x in rr))
assert all(h['params'] == headers[0]['params'] for h in headers)

def normalized(c):
    return {k: v for k, v in c.items() if k not in {'elapsed_s', 'rpc_calls', 'carried_from_checkpoint'}}

def latest_completed(which):
    rr = [json.loads(x) for x in (R / (which + '.checkpoint.jsonl')).read_text().splitlines()]
    binding = rr[0]
    assert binding['kind'] == 'binding'
    assert binding['primitives_sha256'] == sha(W / '../baseline_20260909/verify_capabilities.py')
    latest = {}
    for x in rr[1:]:
        if x['completed']: latest[x['candidate']] = x
    assert set(latest) == set(expected)
    return binding, latest

sources = {}
for side, tag in [('serial', 'resume_serial'), ('parallel', 'resume_parallel2')]:
    binding, ck = latest_completed(side)
    for c in docs[tag]['results']:
        x = ck[c['index']]
        bare = {k:v for k,v in c.items() if k != 'carried_from_checkpoint'}
        assert bare == x['result']
        assert E.result_sha256_of(bare) == x['result_sha256']
        problems = E.verify_evidence_supports(x['evidence_file'], run_id=x['evidence_run_id'],
            candidate=c['index'], result_sha256=x['result_sha256'], binding=binding)
        assert not problems, problems
        report['evidence_support_checks'] += 1
        rr = [json.loads(z) for z in Path(x['evidence_file']).read_text().splitlines()]
        # Cache rows have worker but no candidate. Attribute only within an explicit
        # candidate_start/end span for that worker, rather than using global deltas.
        active = {}
        annotated = []
        for z in rr:
            if z['run_id'] != x['evidence_run_id']:
                continue
            worker = z.get('worker')
            if z['kind'] == 'candidate_start':
                assert worker not in active
                active[worker] = z['candidate']
            if z['kind'] == 'block_cache_hit':
                assert worker in active
                z = dict(z, candidate=active[worker])
            annotated.append(z)
            if z['kind'] == 'candidate_end':
                assert active.pop(worker) == z['candidate']
        assert not active
        mine = [z for z in annotated if z.get('candidate') == c['index']]
        sources[(side, c['index'])] = (c, mine)
        rpc = [z for z in mine if z['kind'] == 'rpc']
        assert len(rpc) == c['rpc_calls']
        # Independently decode primary probe returns into the delivered amounts.
        for stage, field in [('entry_buy','entry'), ('exit_sell','exit')]:
            calls = [z['record'] for z in rpc if z['stage'] == stage]
            if not c.get(field):
                assert not calls
                continue
            assert len(calls) == 1
            value = P.V.parse_probe(calls[0]['response']['result'])
            rec = c[field]
            assert rec['stage'] == value['stage']
            if field == 'entry':
                assert rec['received'] == value['token_after'] - value['token_before']
                assert rec['eth_debit'] == value['eth_before'] - value['eth_after']
            else:
                assert rec['cash_in'] == value['eth_after'] - value['eth_before']
                assert rec['token_before'] == value['token_before']
                assert rec['token_after'] == value['token_after']
            report['raw_probe_checks'] += 1

for idx in sorted(expected):
    a, ar = sources[('serial', idx)]; b, br = sources[('parallel', idx)]
    assert normalized(a) == normalized(b), idx
    ac = sum(r['kind'] == 'block_cache_hit' for r in ar)
    bc = sum(r['kind'] == 'block_cache_hit' for r in br)
    print('CACHE_CHECK', idx, a['rpc_calls'], ac, b['rpc_calls'], bc, flush=True)
    report['candidates'].append(dict(index=idx,state=a['state'],same_fields=True,
        rpc=[a['rpc_calls'],b['rpc_calls']],cache=[ac,bc],
        cash_in=(a.get('exit') or {}).get('cash_in')))
report['snapshot'] = pin
report['cache_accounting_matches'] = all(c['rpc'][0] + c['cache'][0] == c['rpc'][1] + c['cache'][1] for c in report['candidates'])
report['result_fields_and_provenance_passed'] = True
report['passed'] = report['cache_accounting_matches']
(OUT / 'realchain_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))

assert report['passed'], 'cache accounting mismatch; see complete saved observations'
