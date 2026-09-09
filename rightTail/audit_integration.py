"""Independent process-level RT-A regressions. All artifacts live in --out."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def worker(source, case, out):
    spec = importlib.util.spec_from_file_location('R', source)
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    if case == 'etherscan_transient':
        R.ETHERSCAN_KEY='TEST_SECRET'
        R.scan_limiter.wait=lambda:None
        R.time.sleep=lambda _:None
        class Response:
            status_code=200
            def json(self):return {'status':'1','result':[]}
        class Session:
            calls=0
            def get(self,*a,**kw):
                self.calls+=1
                if self.calls==1:raise R.requests.exceptions.ProxyError('apikey=TEST_SECRET')
                return Response()
        R._session=Session()
        assert R.etherscan('logs','getLogs')==([],None) and R._session.calls==2
        class FailedSession:
            calls=0
            def get(self,*a,**kw):
                self.calls+=1
                raise R.requests.exceptions.ProxyError('apikey=TEST_SECRET')
        R._session=FailedSession()
        rows,error=R.etherscan('logs','getLogs')
        assert rows is None and R._session.calls==3 and 'TEST_SECRET' not in error
        Response.status_code=403
        R._session=Session();R._session.calls=1
        assert R.etherscan('logs','getLogs')==(None,'http 403') and R._session.calls==2
        print('Transient recovery=2 attempts; exhaustion=3; HTTP403=1; secrets redacted')
        return 0
    if case == 'transport_http':
        R.rpc_url=lambda:'https://mock.invalid'
        R.rpc_limiter.wait=lambda:None
        R.time.sleep=lambda _:None
        class Response:
            status_code=400
            text='rejected'
            def json(self):return {'error':{'message':'range limit'}}
        class Session:
            def __init__(self):self.calls=0
            def post(self,*a,**k):self.calls+=1;return Response()
        for status,expected in [(400,1),(429,3),(503,3)]:
            Response.status_code=status
            R._session=Session()
            result,error=R.rpc('eth_getLogs',[])
            assert result is None and error.startswith('http '+str(status))
            assert R._session.calls==expected,(status,R._session.calls)
            print('REAL_RPC_HTTP',status,'calls=',R._session.calls)
        return 0
    R.OUTDIR = str(out)
    R.DB_PATH = str(out / 'rt_a.sqlite')
    R.SPEC.update(candidate_from_block=1000, candidate_to_block=1040,
                  history_lookback_blocks=900, forward_lookback_blocks=900,
                  log_chunk_blocks=100, pair_logs_source='rpc', max_candidates=50)
    R.ETHERSCAN_KEY = 'MOCK'
    R.POLL_SLEEP = R.IDLE_SLEEP = 0
    P = R._std_pairs(100)
    R.rpc, R.etherscan = R._mk_mocks({'pairs': P, 'blocknum_sched': [1400]*12+[1403]})
    original = R.fetch_pair_created
    if case == 'scan_zero_index':
        R.SPEC['pair_logs_source']='etherscan'
        scan=R.etherscan
        raw=[]
        def etherscan(module,action,**kw):
            rows,error=scan(module,action,**kw)
            if action=='getLogs' and kw.get('topic0')==R.TOPIC_PAIR_CREATED:
                rows=[dict(row,logIndex='0x',transactionIndex='0x') for row in rows]
                raw.extend(rows)
            return rows,error
        R.etherscan=etherscan
        assert R.backfill()==0
        assert raw and all(row['logIndex']=='0x' for row in raw), 'raw response mutated'
        con=R.db()
        assert con.execute('SELECT DISTINCT log_index FROM candidates').fetchall()==[(0,)]
        assert R.report()==0
        assert R.normalize_etherscan_logs([{'logIndex':'bad'},{}])==[{'logIndex':'bad'},{}]
        return 0
    if case == 'strict_incomplete':
        def fetch(a,b):
            logs,gaps=original(a,b)
            return (logs[:-1] if a<1000 else logs),gaps
        R.fetch_pair_created=fetch
        R.attribute=lambda *a,**kw: (_ for _ in ()).throw(AssertionError('attribution must not run'))
        assert R.backfill(require_complete=True)==1
        con=R.db()
        assert con.execute('SELECT COUNT(*) FROM attribution').fetchone()[0]==0
        assert (out/'coverage_report_backfill.INCOMPLETE.md').exists()
        assert not (out/'coverage_report_backfill.md').exists()
        return 0
    if case == 'auto':
        R.SPEC.update(pair_logs_source='auto', log_chunk_blocks=2000)
        R.rpc, R.etherscan = R._mk_mocks({'pairs': P, 'getlogs_max_span': 10, 'blocknum_sched': [1400]})
        seen = []
        def fetch(a, b):
            seen.append((R.PAIR_LOGS_SOURCE, a, b))
            return original(a,b)
        R.fetch_pair_created = fetch
        rc = R.backfill()
        assert seen[0][0] == 'etherscan', seen
        print('FIRST_FETCH', seen[0])
        return 0
    if case in ('missing', 'empty_missing'):
        def fetch(a,b):
            logs,gaps=original(a,b)
            return (logs[:-1] if a>=1000 else logs),gaps
        R.fetch_pair_created=fetch
        if case == 'empty_missing':
            R.SPEC['candidate_to_block']=1000
        (out/'coverage_report_backfill.md').write_text('STALE')
        rc = R.backfill()
        report_rc=R.report()
        assert rc == 1, ('backfill exit',rc)
        assert report_rc == 1, ('report exit',report_rc)
        assert not (out/'coverage_report_backfill.md').exists()
        assert (out/'coverage_report_backfill.INCOMPLETE.md').exists()
        return 0
    if case == 'foreign_integrity':
        R.backfill()
        con=R.db()
        con.execute("UPDATE attribution SET spec_hash='foreign', batch='foreign'") if 'batch' in R.ATTR_COLS else con.execute("UPDATE attribution SET spec_hash='foreign'")
        con.commit()
        assert R.report()==1, 'unrelated successful integrity certified foreign rows'
        assert not (out/'coverage_report_backfill.md').exists()
        return 0
    if case == 'reconcile':
        requests=[]
        def fetch(a,b):
            requests.append((a,b))
            return original(a,b)
        R.fetch_pair_created=fetch
        R.attribute=lambda *a,**k: (_ for _ in ()).throw(AssertionError('attribution called'))
        sys.argv=['rt_a_attribution.py','reconcile']
        try: R.main()
        except SystemExit as e: assert e.code==0, e.code
        assert requests == [(1000,1040)], requests
        con=R.db()
        assert con.execute('SELECT COUNT(*) FROM attribution').fetchone()[0]==0
        assert con.execute("SELECT COUNT(*) FROM run_integrity WHERE mode='backfill'").fetchone()[0]==0
        assert not list(out.glob('coverage_report*'))
        return 0
    if case == 'forward_scope':
        R.backfill()
        con=R.db()
        hist=con.execute('SELECT pair FROM candidates WHERE in_candidate_range=0 LIMIT 1').fetchone()[0]
        R.upsert_attr(con, {'pair':hist,'mode':'backfill','spec_hash':R.spec_hash()})
        R.record_gaps(con,[{'from':195,'to':205}], 'history')
        R.record_gaps(con,[{'from':1404,'to':1406}], 'forward')
        con.commit()
        before=con.execute('SELECT * FROM attribution WHERE pair=?',(hist,)).fetchone()
        requests=[]
        def fetch(a,b):
            requests.append((a,b))
            return original(a,b)
        R.fetch_pair_created=fetch
        R.forward(.001)
        assert all(1401<=a<=b<=1403 for a,b in requests), requests
        assert con.execute('SELECT in_candidate_range FROM candidates WHERE pair=?',(hist,)).fetchone()[0]==0
        assert con.execute('SELECT * FROM attribution WHERE pair=?',(hist,)).fetchone()==before
        assert con.execute("SELECT resolved FROM log_gaps WHERE role='forward' AND from_block=1404").fetchone()[0]==0
        return 0
    if case == 'forward_retry':
        P=R._std_pairs(2,start=1401,step=1)
        R.rpc,R.etherscan=R._mk_mocks({'pairs':P,'blocknum_sched':[1400]*12+[1403,1404,1405]})
        attempts=[]
        def fetch(a,b):
            logs,gaps=original(a,b)
            attempts.append((a,b))
            if len(attempts)==1: return logs[:-1], []
            return logs,gaps
        R.fetch_pair_created=fetch
        assert R.forward(.01)==0
        con=R.db()
        assert attempts.count((1401,1403))==2,attempts
        assert con.execute('SELECT COUNT(*) FROM attribution').fetchone()[0]==2
        assert con.execute('SELECT COUNT(*) FROM log_gaps WHERE resolved=0').fetchone()[0]==0
        assert R.report()==0
        assert (out/'coverage_report_forward.md').exists()
        return 0
    if case == 'history_retry':
        def fetch(a,b):
            logs,gaps=original(a,b)
            return (logs[1:], [{'from':a,'to':b,'source':'rpc','err':'mock'}]) if a<1000 else (logs,gaps)
        R.fetch_pair_created=fetch
        assert R.backfill()==1
        con=R.db()
        assert con.execute("SELECT COUNT(*) FROM log_gaps WHERE resolved=0 AND role='history'").fetchone()[0]==1
        R.fetch_pair_created=original
        assert R.backfill()==0
        assert con.execute("SELECT COUNT(*) FROM log_gaps WHERE resolved=0 AND role='history'").fetchone()[0]==0
        assert con.execute('SELECT in_candidate_range FROM candidates ORDER BY block_number LIMIT 1').fetchone()[0]==0
        assert R.report()==0
        return 0
    if case == 'empty_success':
        R.rpc,R.etherscan=R._mk_mocks({'pairs':[],'blocknum_sched':[1400]})
        assert R.backfill()==0
        assert R.report()==0
        assert '候选数 N = 0' in (out/'coverage_report_backfill.md').read_text()
        return 0
    if case in ('cli_missing','cli_reconcile_missing'):
        def fetch(a,b):
            logs,gaps=original(a,b)
            return (logs[:-1] if a>=1000 else logs),gaps
        R.fetch_pair_created=fetch
        sys.argv=['rt_a_attribution.py','backfill' if case=='cli_missing' else 'reconcile']
        R.main()
        raise AssertionError('main did not exit')
    if case == 'gap_migration':
        import sqlite3
        con=sqlite3.connect(R.DB_PATH)
        con.execute('CREATE TABLE log_gaps(from_block INTEGER,to_block INTEGER,source TEXT,err TEXT,seen_at TEXT,resolved INTEGER DEFAULT 0, PRIMARY KEY(from_block,to_block))')
        con.execute("INSERT INTO log_gaps VALUES(1,2,'rpc','old','old',0)");con.commit();con.close()
        con=R.db()
        R.record_gaps(con,[{'from':1,'to':2}], 'history')
        R.record_gaps(con,[{'from':1,'to':2}], 'forward')
        assert con.execute('SELECT COUNT(*) FROM log_gaps').fetchone()[0]==3
        return 0
    raise AssertionError(case)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',default=str(Path(__file__).with_name('rt_a_attribution.py')));p.add_argument('--out',required=True);p.add_argument('--case');a=p.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    if a.case: sys.exit(worker(str(Path(a.source).resolve()),a.case,out))
    results={}
    for case in ['strict_incomplete','etherscan_transient','transport_http','scan_zero_index','auto','missing','empty_missing','foreign_integrity','reconcile','forward_scope','gap_migration','forward_retry','history_retry','empty_success','cli_missing','cli_reconcile_missing']:
        dest=out/case;dest.mkdir(exist_ok=True)
        r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--source',str(Path(a.source).resolve()),'--out',str(dest),'--case',case],capture_output=True,text=True,cwd=dest)
        (dest/'process.log').write_text(r.stdout+r.stderr)
        expected=1 if case.startswith('cli_') else 0
        results[case]={'exit':r.returncode,'expected':expected};print(case,'exit=',r.returncode,'expected=',expected)
        if case=='cli_missing':
            assert (dest/'coverage_report_backfill.INCOMPLETE.md').exists()
            assert not (dest/'coverage_report_backfill.md').exists()
        if case=='cli_reconcile_missing':
            assert not list(dest.glob('coverage_report*'))
    (out/'results.json').write_text(json.dumps(results,indent=2))
    sys.exit(int(any(v['exit']!=v['expected'] for v in results.values())))
