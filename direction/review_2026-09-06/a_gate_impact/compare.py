"""Compare the current A gate with A_LISTING_HEAD without changing project sources."""
import collections
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
USE_FALLBACK = '--fallback' in sys.argv
WORK = ROOT / '.probe_L_work'
OUT = Path(tempfile.mkdtemp(prefix='direction_a_gate_impact_'))
sys.dont_write_bytecode = True

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

protected = [ROOT/'L_config.json', WORK/'L_config.json', WORK/'L_03_classify.py', WORK/'L_00_bootstrap.py', WORK/'L_mother_events.json']
before = {str(p): sha(p) for p in protected}
source = (WORK/'L_03_classify.py').read_text()
old_line = '    if all(p.search(x) for p in GA): matched.append("A")'
new_line = '    if AH.search(x): matched.append("A")'
assert source.count(old_line) == 1

def run_variant(label, code):
    folder = OUT/label
    folder.mkdir()
    (folder/'L_03_classify.py').write_text(code)
    for name in ['L_00_bootstrap.py','L_config.json']:
        shutil.copyfile(WORK/name, folder/name)
    for name in ['ann_raw.json','crawl_report.json','ann_body_manifest.json','u_trade_candidates.json','spot_exchangeinfo.json','ann_body']:
        (folder/name).symlink_to(WORK/name, target_is_directory=name=='ann_body')
    old_cwd, old_argv, old_path = Path.cwd(), sys.argv, sys.path[:]
    old_env = os.environ.get('L_CONFIG')
    os.environ['L_CONFIG'] = str(folder/'L_config.json')
    sys.argv = [str(folder/'L_03_classify.py'), '--dryrun']
    sys.modules.pop('L_00_bootstrap', None)
    ns = {'__name__':'__main__', '__file__':str(folder/'L_03_classify.py')}
    log = io.StringIO()
    exit_code, exit_message = 0, None
    os.chdir(folder)
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                exec(compile(code, ns['__file__'], 'exec'), ns)
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else 1 if exc.code else 0
                exit_message = str(exc.code)
    finally:
        os.chdir(old_cwd)
        sys.argv, sys.path = old_argv, old_path
        if old_env is None:
            os.environ.pop('L_CONFIG',None)
        else:
            os.environ['L_CONFIG'] = old_env
    (OUT/(label+'.log')).write_text(log.getvalue()+'\nEXIT: '+str(exit_message))
    data = ns.get('out')
    assert data is not None, exit_message
    capture = {'status':'DIAGNOSTIC_CAPTURE_ONLY', 'exit_code':exit_code, 'exit_message':exit_message,
               'temporary_code_sha256':sha(folder/'L_03_classify.py'), 'config_sha256':sha(folder/'L_config.json'),
               'checks_passed':sum(1 for s in log.getvalue().splitlines() if s.startswith('[断言]') and '✅' in s),
               'checks_failed':data['checks_failed'], 'mother_file_written':(folder/'L_mother_events.json').exists(), 'data':data}
    (OUT/(label+'.json')).write_text(json.dumps(capture,ensure_ascii=False,indent=2))
    return capture, ns

baseline, old_ns = run_variant('baseline_v189',source)
candidate_code = source.replace(old_line,new_line)
if USE_FALLBACK:
    anchor = '    if GB.search(x): matched.append("B")'
    assert source.count(anchor) == 1
    candidate_code = source.replace(anchor, anchor + '\n    if not matched and AH.search(x): matched.append("A")')
candidate, new_ns = run_variant('candidate_unmatched_fallback' if USE_FALLBACK else 'candidate_head_gate', candidate_code)
old, new = baseline['data'], candidate['data']
by_old, by_new = collections.defaultdict(list), collections.defaultdict(list)
for e in old['raw_events']: by_old[e['article_id']].append(e)
for e in new['raw_events']: by_new[e['article_id']].append(e)

changed = []
gate_changes = []
for aid, meta in old_ns['expected'].items():
    text = old_ns['norm'](json.loads((WORK/'ann_body'/f'{aid}.json').read_text())['text'])
    old_gate = all(p.search(text) for p in old_ns['GA'])
    head = old_ns['AH'].search(text)
    old_kind = old['per_article'][str(aid)]['kind']
    new_kind = new['per_article'][str(aid)]['kind']
    if old_gate != bool(head):
        gate_changes.append({'article_id':aid,'old_gate':old_gate,'new_gate':bool(head),'old_kind':old_kind,'new_kind':new_kind})
    old_semantic = {(e['base_asset'],e['T_scheduled'],e['generator']) for e in by_old[aid]}
    new_semantic = {(e['base_asset'],e['T_scheduled'],e['generator']) for e in by_new[aid]}
    if old_kind != new_kind or old_semantic != new_semantic:
        changed.append({'article_id':aid,'title':meta['title'],'old_kind':old_kind,'new_kind':new_kind,
                        'old_events':by_old[aid], 'new_events':by_new[aid],
                        'old_matches':old['per_article'][str(aid)]['matched'], 'new_matches':new['per_article'][str(aid)]['matched'],
                        'head_match':head.group(0) if head else None,
                        'operation_context':text[max(0,head.start()-80):head.end()+160] if head else text[:650]})

def event_key(e): return (e['article_id'], e['base_asset'], e['T_scheduled'])
old_ev = {event_key(e):e for e in old['raw_events']}
new_ev = {event_key(e):e for e in new['raw_events']}
old_only = [old_ev[k] for k in sorted(set(old_ev)-set(new_ev))]
new_only = [new_ev[k] for k in sorted(set(new_ev)-set(old_ev))]
relabeled = [{'article_id':k[0],'base':k[1],'time':k[2],'old_generator':old_ev[k]['generator'],'new_generator':new_ev[k]['generator']}
             for k in sorted(set(old_ev)&set(new_ev)) if old_ev[k]['generator']!=new_ev[k]['generator']]
summary = {'scope':('Unmatched-only A_LISTING_HEAD fallback' if USE_FALLBACK else 'Direct A predicate replacement') + '; temporary copy only; all source files and expected counts unchanged',
           'output_directory':str(OUT), 'source_sha256':before,
           'baseline':{k:v for k,v in baseline.items() if k!='data'},
           'candidate':{k:v for k,v in candidate.items() if k!='data'},
           'baseline_buckets':old['buckets'], 'candidate_buckets':new['buckets'],
           'baseline_raw_events':len(old['raw_events']),'candidate_raw_events':len(new['raw_events']),
           'baseline_groups':len(old['candidate_groups']),'candidate_groups':len(new['candidate_groups']),
           'gate_changes':gate_changes, 'changed_articles':changed,
           'transition_counts':dict(collections.Counter(r['old_kind']+' -> '+r['new_kind'] for r in changed)),
           'new_semantic_events':new_only,'removed_semantic_events':old_only,'relabeled_events':relabeled}
after = {str(p):sha(p) for p in protected}
summary['project_source_and_mother_unchanged'] = before==after
assert before==after
(OUT/'impact.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ['changed_articles','source_sha256','relabeled_events','gate_changes']},ensure_ascii=False,indent=2))
print('CHANGED ARTICLE TITLES:')
for r in changed:
    print(r['article_id'], r['old_kind'], '->', r['new_kind'], r['title'])
