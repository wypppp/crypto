"""Independent, offline audit of direction/. Writes only to its temporary folder."""
import ast
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(tempfile.mkdtemp(prefix='direction_review_20260906_'))
RESULT = {'artifact_dir': str(OUT), 'scope': 'offline file checks and synthetic counterexamples; no full market replay'}

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def extract_function(path, name, namespace):
    tree = ast.parse(Path(path).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]

versions = {}
for rel in ['L_config.json', '.probe_L_work/L_config.json', 'repro_L/L_config.json', 'archive/v1.8.8/L_config.json']:
    p = ROOT / rel
    versions[rel] = {'version': json.loads(p.read_text())['_meta']['version'], 'sha256': sha(p)}
RESULT['l_versions'] = versions

hash_results = {}
for rel in ['repro_F', 'repro_L', 'repro_C1BN', 'archive/v1.8.8']:
    folder = ROOT / rel
    if rel == 'repro_C1BN':
        expected = json.loads((folder / 'HASHES.json').read_text())
    else:
        expected = {}
        for line in (folder / 'SHA256SUMS.txt').read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            digest, filename = line.split(maxsplit=1)
            expected[filename.lstrip('*')] = digest
    checks = {'ok': [], 'mismatch': [], 'missing': [], 'digest_lengths': sorted({len(h) for h in expected.values()})}
    for name, h in expected.items():
        p = folder / name
        key = 'missing' if not p.is_file() else 'ok' if sha(p).startswith(h) else 'mismatch'
        checks[key].append(name)
    hash_results[rel] = checks
RESULT['package_hashes'] = hash_results

work = ROOT / '.probe_L_work'
body_manifest = json.loads((work / 'ann_body_manifest.json').read_text())
entries = body_manifest['entries']
body_mismatch = [e['article_id'] for e in entries if sha(work / 'ann_body' / f"{e['article_id']}.json") != e['sha256']]
RESULT['l_body_integrity'] = {'recorded_count': len(entries), 'actual_files': len(list((work / 'ann_body').glob('*.json'))), 'hash_mismatch': body_mismatch, 'complete': body_manifest['complete']}

t0 = json.loads((work / 't0_exact.json').read_text())
manifest = json.loads((work / 't0_manifest.json').read_text())
blocked = {r['base'] for r in manifest['embargoed']}
planned = {(r['base'], s, r['earliest_trade_day']) for r in manifest['download_manifest'] for s in r['tied_pairs']}
actual = {(base, r['symbol'], r['day']) for base, data in t0['t0'].items() for r in data['files']}
t0_inconsistent = [base for base, data in t0['t0'].items() if data['T0_us'] != min(r['min_ts_us'] for r in data['files'])]
RESULT['l_t0_integrity'] = {'bases': len(t0['t0']), 'files': len(actual), 'planned': len(planned), 'missing': len(planned - actual), 'extra': len(actual - planned), 'failures': t0['failures'], 'overlap_with_holdout': sorted(set(t0['t0']) & blocked), 'inconsistent_minima': t0_inconsistent, 'checksum_fields_equal': all(r['official_checksum'] == r['local_sha256'] and r['checksum_verified'] for v in t0['t0'].values() for r in v['files']), 'limitation': 'checks stored metadata, not redownloaded official ZIP contents'}

f_events = list(csv.DictReader((ROOT / 'repro_F/F_lambda_events.csv').open()))
classification = collections.Counter()
for e in f_events:
    gap = (dt.datetime.fromisoformat(e['t_first_1h']) - dt.datetime.fromisoformat(e['t_touch'])).total_seconds() / 3600
    funding = float(e['pre_switch_funding'])
    automatic = .5 <= gap <= 1.5 and min(abs(abs(funding)-.02), abs(abs(funding)-.03)) <= 2e-5
    label = 'positive' if automatic and funding > 0 else 'negative' if automatic else 'administrative'
    classification[label] += 1
years = (dt.datetime(2026,9,1) - dt.datetime(2025,5,2)).days / 365.25
def poisson_cdf(k, mean):
    return math.exp(-mean) * sum(mean**j / math.factorial(j) for j in range(k+1))
def invert_cdf(k, target):
    lo, hi = 0., 100.
    for _ in range(100):
        mid = (lo+hi)/2
        if poisson_cdf(k, mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2
RESULT['f_counts'] = {'rows': len(f_events), 'counts': dict(classification), 'positive_per_year': classification['positive']/years, 'garwood_two_sided_95': [invert_cdf(3, .975)/years, invert_cdf(4, .025)/years], 'published_interval': json.loads((ROOT/'repro_F/F_final.json').read_text())['poisson95_pos'], 'limitation': 'reclassifies stored event table; does not reconstruct all funding histories'}

c1_events = list(csv.DictReader((ROOT/'repro_C1BN/events.csv').open()))
c1_counts = {}
for variant in sorted({e['variant'] for e in c1_events}):
    rows = [e for e in c1_events if e['variant'] == variant]
    by_symbol = collections.defaultdict(list)
    for e in rows:
        by_symbol[e['symbol']].append(dt.datetime.fromisoformat(e['utc']).timestamp())
    episode_count = 0
    for times in by_symbol.values():
        previous = None
        for t in sorted(times):
            if previous is None or t-previous >= 8*3600:
                episode_count += 1
            previous = t
    c1_counts[variant] = {'rows': len(rows), 'episodes': episode_count}
RESULT['c1_stored_counts'] = c1_counts

# Run the actual funding crossing function on a 17-day synthetic history.
hour = 3600000
start_ms = int(dt.datetime(2022,1,1,tzinfo=dt.timezone.utc).timestamp()*1000)
series = [(start_ms+i*8*hour, 1e-5) for i in range(50)] + [(start_ms+50*8*hour, 0.), (start_ms+51*8*hour, 1e-3)]
ns = {'DAY': 24*hour, 'H': hour, 'norm_series': lambda symbol: series}
crossings = extract_function(ROOT/'repro_C1BN/rerun_c1.py', 'crossings', ns)
hits = crossings('SYNTHETIC', 365, 'settle')
RESULT['c1_warmup_counterexample'] = {'history_days': 17, 'window_days_requested': 365, 'emitted_triggers': len(hits), 'trigger_days_since_first': [(t-start_ms)/(24*hour) for t,v in hits], 'expected_under_frozen_rule': 0}

# Actual top-20 builder: alter only the final day's future daily volume.
def top20_run(final_volume, dirname):
    folder = OUT / dirname
    data = folder / 'daily_klines'
    data.mkdir(parents=True)
    base = dt.datetime(2021,8,3,tzinfo=dt.timezone.utc)
    day_ms = [int((base+dt.timedelta(days=i)).timestamp()*1000) for i in range(30)]
    for index in range(21):
        name = f'INCUMBENT{index:02d}' if index < 20 else 'FUTURE_SURGE'
        rows = [[t, 1., 100. if index < 20 else (final_volume if i==29 else 1.)] for i,t in enumerate(day_ms)]
        (data/(name+'.json')).write_text(json.dumps(rows))
    proc = subprocess.run([sys.executable, '-B', str(ROOT/'repro_C1BN/build_top20.py')], cwd=folder, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    result = json.loads((folder/'top20_universe.json').read_text())['top20'][str(day_ms[-1])]
    return result
low, high = top20_run(1., 'top20_low'), top20_run(4000., 'top20_high')
RESULT['c1_top20_lookahead_counterexample'] = {'timestamp': '2021-09-01T00:00:00Z', 'all_prior_data_equal': True, 'surge_member_with_low_future_daily_volume': 'FUTURE_SURGE' in low, 'surge_member_with_high_future_daily_volume': 'FUTURE_SURGE' in high, 'expected': 'membership at day start must be unchanged when only that future day volume is changed'}

# Actual OI loader overwrites hour-start with a later 5-minute observation.
oi_folder = OUT/'oi'
(oi_folder/'metrics').mkdir(parents=True)
(oi_folder/'metrics/SYNTHETIC_2022-01-01.json').write_text(json.dumps([['2022-01-01 16:00:00',100.], ['2022-01-01 16:55:00',200.]]))
old_cwd = Path.cwd()
os.chdir(oi_folder)
try:
    ns = {'H':hour, 'os':os, 'json':json, 'datetime':dt}
    loader = extract_function(ROOT/'repro_C1BN/rerun_c1.py', 'load_oi', ns)
    values = loader('SYNTHETIC',['2022-01-01'])
finally:
    os.chdir(old_cwd)
oi_key = int(dt.datetime(2022,1,1,16,tzinfo=dt.timezone.utc).timestamp()*1000)
RESULT['c1_oi_lookahead_counterexample'] = {'decision_time':'2022-01-01T16:00:00Z','available_value':100.,'future_16_55_value':200.,'loader_value_at_16_00':values[oi_key]}

# Classifier in a temporary copy; no edits to project inputs or outputs.
stage = OUT/'l_classifier'
stage.mkdir()
for name in ['L_03_classify.py','L_00_bootstrap.py']:
    shutil.copyfile(work/name, stage/name)
for name in ['ann_raw.json','crawl_report.json','ann_body_manifest.json','u_trade_candidates.json','spot_exchangeinfo.json','ann_body']:
    (stage/name).symlink_to(work/name, target_is_directory=name=='ann_body')
env = os.environ.copy()
env['L_CONFIG'] = str(ROOT/'L_config.json')
dry = subprocess.run([sys.executable,'-B','L_03_classify.py','--dryrun'], cwd=stage, env=env, text=True, capture_output=True)
(OUT/'l_dryrun.log').write_text(dry.stdout+dry.stderr)
RESULT['l_current_dryrun'] = {'exit_code':dry.returncode, 'selected_output':[s for s in dry.stdout.splitlines() if s.startswith(('桶:', 'raw_events=', '[断言]', '[复现门]', '[来源断言]'))], 'stderr':dry.stderr}

cfg = json.loads((ROOT/'L_config.json').read_text())
before = cfg['mother_universe']['expected_counts']['C1_raw_articles']
cfg['mother_universe']['expected_counts']['C1_raw_articles'] = before + 1
mutated = stage/'mutated_expected_config.json'
mutated.write_text(json.dumps(cfg,ensure_ascii=False))
env['L_CONFIG'] = str(mutated)
proc = subprocess.run([sys.executable,'-B','L_03_classify.py'], cwd=stage, env=env, text=True, capture_output=True)
(OUT/'l_invalid_expectation.log').write_text(proc.stdout+proc.stderr)
RESULT['l_nonblocking_assertion_counterexample'] = {'mutation':'C1_raw_articles expectation increased by one in temporary config only', 'original_expected':before,'mutated_expected':before+1,'failed_checks':[s for s in proc.stdout.splitlines() if '❌' in s], 'exit_code':proc.returncode,'mother_file_written':(stage/'L_mother_events.json').is_file(),'stderr':proc.stderr}

(OUT/'results.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2))
print(json.dumps(RESULT,ensure_ascii=False,indent=2))
