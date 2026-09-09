"""Validate a completed forward run against its immutable backfill seed."""
import argparse,json,sqlite3
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--seed-db',required=True);a=p.parse_args()
root=Path(a.run);execution=json.loads((root/'execution.json').read_text())
assert execution.get('state')=='complete' and execution.get('exit')==0,execution.get('state')
assert execution['stages']=={'forward':0,'report':0},execution['stages']
assert not execution['cache_hits'], 'Forward requests must be live'
c=sqlite3.connect(root/'forward/rt_a.sqlite');s=sqlite3.connect(a.seed_db)
for table,where in [('attribution',"WHERE mode='backfill'"),('candidates','')]:
    old=s.execute('SELECT * FROM '+table+' '+where+' ORDER BY pair').fetchall()
    cols=[r[1] for r in s.execute('PRAGMA table_info('+table+')')]
    pair_index=cols.index('pair')
    for row in old:
        got=c.execute('SELECT * FROM '+table+' WHERE pair=?',(row[pair_index],)).fetchone()
        assert got==row,('seed row changed',table,row[pair_index])
runs=c.execute("SELECT batch,from_block,to_block,status FROM collection_runs WHERE mode='forward'").fetchall()
assert len(runs)==1 and runs[0][3]=='complete',runs
batch,start,end,_=runs[0]
checks=c.execute('SELECT from_block,to_block,ok,detail FROM batch_integrity WHERE batch=? ORDER BY from_block,to_block',(batch,)).fetchall()
cursor=start;expected=0
for lo,hi,ok,detail in checks:
    assert lo==cursor and hi>=lo and ok==1,(cursor,lo,hi,ok)
    cursor=hi+1;expected+=json.loads(detail)['n_expected']
assert cursor==end+1
assert c.execute('SELECT COUNT(*) FROM log_gaps WHERE resolved=0').fetchone()[0]==0
c.row_factory=sqlite3.Row
rows=[dict(r) for r in c.execute("SELECT * FROM attribution WHERE mode='forward'")]
assert len(rows)==expected,(len(rows),expected)
assert all(r['batch']==batch for r in rows)
assert all(r['lag_required_seconds'] is not None and r['lag_required_seconds']>=0 for r in rows)
qualified=[r for r in rows if r['l1_status']=='ok' and r['pair_created_tx_sender'] and r['creation_tx_sender'] and (r['l2a_status']=='ok' or r['l2b_status']=='ok') and r['creator_prior_activity_known'] in ('ok','no_history') and r['lag_required_seconds']<=execution['formal_spec']['decision_window_seconds']]
result={'exit':0,'range':[start,end],'blocks':end-start+1,'intervals':len(checks),'expected_events':expected,'attributed':len(rows),'joint_within_deadline':len(qualified),'lag_required_seconds':[r['lag_required_seconds'] for r in rows],'unchanged_backfill_rows':True,'unresolved_gaps':0,'cache_hits':0,'conclusion_scope':'This observation window only; no population-wide or trading conclusion.'}
(root/'acceptance.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
