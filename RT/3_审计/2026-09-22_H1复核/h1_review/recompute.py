"""Read existing S1 exports; no network, parameter search, or raw-path rerun."""
import hashlib
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
src = ROOT / 'RT/case_timing/raw/dune/H1_S1_A.csv'
events = pd.read_csv(ROOT / 'RT/case_timing/h1_events_A.csv')
data = pd.read_csv(src)
assert not data.duplicated(['mint', 'd']).any()
assert not events.mint.duplicated().any()
assert set(data.mint) == set(events.mint)
assert data.groupby('mint').d.apply(lambda x: set(x) == {30, 120, 300}).all()
data = data.merge(events[['mint', 'is_seed', 'cday']], on='mint', validate='many_to_one')
data['net'] = data.recovery - 0.004
rows = []
for delay, g in data.groupby('d'):
    rest = g[~g.is_seed]
    rows.append(dict(delay=int(delay), n=len(g), mean=float(g.net.mean()),
                     n_nonseed=len(rest), mean_nonseed=float(rest.net.mean()),
                     seed_pnl_sol=float(((g[g.is_seed].net-1)*0.5).sum()),
                     nonseed_pnl_sol=float(((rest.net-1)*0.5).sum())))
m = data[data.d == 120].copy()
for col in ['t_entry', 'exit_ts']:
    m[col] = pd.to_datetime(m[col].str.replace(' UTC', '+00:00'), utc=True)
m['exit_clock'] = m.exit_ts
idle, stop = m.exit_kind.eq('idle'), m.exit_kind.eq('stop')
# Under the stored execution convention, idle can only be known after 24h;
# stop valuation is already at trigger +5s. This changes timing, not valuation.
m.loc[idle, 'exit_clock'] = m.loc[idle, ['exit_ts', 't_entry']].max(axis=1) + pd.Timedelta(hours=24)
m.loc[stop, 'exit_clock'] = m.loc[stop, 'exit_ts'] + pd.Timedelta(seconds=5)
assert m.exit_kind.isin(['idle', 'stop']).all(), 'Handle horizon explicitly if present'
timing = {}
for col in ['exit_ts', 'exit_clock']:
    clocks = pd.concat([pd.DataFrame({'t': m.t_entry, 'k': 1}),
                        pd.DataFrame({'t': m[col], 'k': -1})]).sort_values(['t', 'k'])
    holds = (m[col] - m.t_entry).dt.total_seconds()/3600
    timing[col] = dict(peak_positions=int(clocks.k.cumsum().max()),
                       median_hold_h=float(holds.median()), p90_hold_h=float(holds.quantile(.9)),
                       negative_holds=int((holds < 0).sum()))
out = dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
           returns=rows, timing=timing, idle_events=int(idle.sum()),
           nonseed_daily_means=m[~m.is_seed].groupby('cday').net.mean().to_dict(),
           scope='CSV arithmetic and exit-clock correction only; not independent raw-event replay')
(HERE / 'checks.json').write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n')
m[['mint', 'exit_kind', 't_entry', 'exit_ts', 'exit_clock']].to_csv(HERE / 'exit_clock_check.csv', index=False)
print(json.dumps(out, ensure_ascii=False, indent=2))
