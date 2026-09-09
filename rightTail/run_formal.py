"""Execute the explicitly selected RT-A window; retain source and public request evidence."""
import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import threading
from replay_cache import ReplayCache
import shutil
import sqlite3
import sys
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    parser.add_argument('--from-block',required=True,type=int)
    parser.add_argument('--to-block',required=True,type=int)
    parser.add_argument('--lookback',required=True,type=int)
    parser.add_argument('--memory-mib',type=int,default=768)
    parser.add_argument('--reuse-evidence',action='append',default=[])
    parser.add_argument('--observe-minutes',type=float,default=0)
    parser.add_argument('--seed-db')
    args=parser.parse_args()
    if not 1<=args.from_block<=args.to_block or args.lookback<0:
        parser.error('invalid explicit range')
    root=Path(__file__).resolve().parent
    values={}
    for line in (root.parent/'.env').read_text().splitlines():
        match=re.match(r'\s*(?:export\s+)?([^:=]+?)\s*[:=]\s*(.*?)\s*$',line)
        if match: values[match[1].strip().lower()]=match[2].strip().strip('\"\'')
    for env,label in [('RTA_RPC_ETH','alchemy endpoint url'),('ETHERSCAN_API_KEY','etherscan key')]:
        if not os.environ.get(env):os.environ[env]=values.get(env.lower(),values.get(label,''))
        if not os.environ[env]:raise SystemExit('Missing '+env)
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False)
    if args.memory_mib < 256:
        parser.error('memory limit must be at least 256 MiB')
    limit=args.memory_mib*1024*1024
    resource.setrlimit(resource.RLIMIT_AS,(limit,limit))
    os.nice(10)
    # Durable logs survive WSL or terminal restart. No process arguments or credentials sampled.
    log_fd=os.open(out/'run.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    os.dup2(log_fd,1);os.dup2(log_fd,2);os.close(log_fd)
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    stopped=threading.Event()
    def resource_sample():
        with (out/'resources.jsonl').open('a',buffering=1) as log:
            while not stopped.is_set():
                usage=resource.getrusage(resource.RUSAGE_SELF)
                mem={line.split(':')[0]:line.split(':')[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:','VmSize:','VmPeak:'))}
                log.write(json.dumps({'at':time.time(),'pid':os.getpid(),'memory_limit_mib':args.memory_mib,
                    'max_rss_kib':usage.ru_maxrss,'cpu_seconds':usage.ru_utime+usage.ru_stime,**mem})+'\n')
                stopped.wait(5)
    threading.Thread(target=resource_sample,daemon=True).start()
    os.environ.update(RTA_CHAIN='ethereum',RTA_PAIR_LOGS='etherscan',RTA_FROM_BLOCK=str(args.from_block),
                      RTA_TO_BLOCK=str(args.to_block),RTA_LOOKBACK=str(args.lookback),RTA_FWD_LOOKBACK=str(args.lookback),
                      RTA_MAX='400',RTA_HIST_SENDERS='3000',RTA_OUT=str(out/'backfill'))
    source=root/'rt_a_attribution.py'
    shutil.copy(source,out/'rt_a_attribution.snapshot.py')
    spec=importlib.util.spec_from_file_location('R',source)
    R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
    frozen=dict(R.SPEC)
    for evidence_path in args.reuse_evidence:
        prior=json.loads((Path(evidence_path).parent/'formal_frozen.json').read_text())
        if prior['formal_spec_hash']!=R.spec_hash():
            raise RuntimeError('Refuse cached data from a different frozen specification')
    cache=ReplayCache(out/'replay-cache.sqlite',args.reuse_evidence)
    cache_hits=collections.Counter()
    summary={'started_at':R.now_iso(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'formal_spec':frozen,'formal_spec_hash':R.spec_hash(),'stages':{},'state':'preflight',
             'memory_limit_mib':args.memory_mib,'nice':os.nice(0),'require_complete':True,
             'reused_evidence':cache.sources}
    counts=collections.Counter();errors=collections.Counter();started=time.monotonic()
    http_attempts=collections.Counter()
    request=R._session.request
    def tracked_request(method,url,**kwargs):
        http_attempts['etherscan' if url.startswith(R.ETHERSCAN_V2) else 'rpc']+=1
        return request(method,url,**kwargs)
    R._session.request=tracked_request
    secrets=[os.environ['RTA_RPC_ETH'],os.environ['ETHERSCAN_API_KEY'],values.get('alchemy key','')]
    def redact(s):
        for secret in secrets:
            if secret:s=s.replace(secret,'[REDACTED]')
        return s
    last_save=[0.0]
    def save(force=True):
        if not force and time.monotonic()-last_save[0]<5:
            return
        last_save[0]=time.monotonic()
        summary.update(elapsed_seconds=round(time.monotonic()-started,1),calls=dict(counts),errors=dict(errors),http_attempts=dict(http_attempts),cache_hits=dict(cache_hits))
        tmp=out/'execution.tmp'
        tmp.write_text(json.dumps(summary,ensure_ascii=False,indent=2));tmp.replace(out/'execution.json')
    with gzip.open(out/'public_requests.jsonl.gz','at',encoding='utf-8') as evidence:
        def wrap(fn,kind):
            def call(*a,**kw):
                t=time.monotonic();cached=cache.get(kind,a,kw)
                result=cached[0] if cached else fn(*a,**kw)
                key=kind+':'+':'.join(str(x) for x in a[:2] if isinstance(x,str))
                counts[key]+=1
                if cached:cache_hits[key]+=1
                if result[1]:errors[key]+=1
                evidence.write(redact(json.dumps({'stage':summary['state'],'at':R.now_iso(),'kind':kind,
                    'args':a,'kwargs':kw,'cache_source':cached[1] if cached else None,'elapsed_s':round(time.monotonic()-t,3),'response':result},ensure_ascii=False))+'\n')
                evidence.flush()
                save(force=False)
                return result
            return call
        R.rpc=wrap(R.rpc,'rpc');R.etherscan=wrap(R.etherscan,'etherscan')
        rc=1
        try:
            chain,e=R.rpc('eth_chainId',[])
            head,he=R.rpc('eth_blockNumber',[])
            if e or he or R.hex_int(chain)!=1:raise RuntimeError('chain/head verification failed')
            summary['head_at_freeze']=R.hex_int(head)
            if args.to_block+frozen['l3_scan_blocks']>R.hex_int(head):
                raise RuntimeError('L3 upper bound is beyond observed chain head')
            (out/'formal_frozen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
            if args.observe_minutes:
                if args.observe_minutes < 0 or args.reuse_evidence or not args.seed_db:
                    raise RuntimeError('Forward observation requires a completed seed database and no replay cache')
                R.OUTDIR=str(out/'forward');R.DB_PATH=str(Path(R.OUTDIR)/'rt_a.sqlite')
                Path(R.OUTDIR).mkdir()
                source_db=sqlite3.connect('file:'+str(Path(args.seed_db).resolve())+'?mode=ro',uri=True)
                if R.integrity_of(source_db,'backfill')[0] is not True:
                    raise RuntimeError('Seed backfill integrity is not complete')
                if source_db.execute("SELECT COUNT(*) FROM attribution WHERE spec_hash<>?",(R.spec_hash(),)).fetchone()[0]:
                    raise RuntimeError('Seed specification mismatch')
                target_db=sqlite3.connect(R.DB_PATH);source_db.backup(target_db)
                source_db.close();target_db.close()
                summary['state']='forward';summary['observe_minutes']=args.observe_minutes;save()
                rc=R.forward(args.observe_minutes);summary['stages']['forward']=rc
                report_rc=R.report();summary['stages']['report']=report_rc
                rc=rc or report_rc
                summary['state']='complete' if rc==0 else 'incomplete'
                return rc
            # Reconcile is its own experiment with lookback zero; preserve the actual formal spec separately.
            summary['state']='reconcile';R.OUTDIR=str(out/'reconcile');R.DB_PATH=str(Path(R.OUTDIR)/'rt_a.sqlite')
            R.SPEC.update(reconcile_only=True,history_lookback_blocks=0)
            rc=R.backfill();summary['stages']['reconcile']=rc;save()
            if rc:
                summary['state']='incomplete'
                return rc
            R.SPEC.clear();R.SPEC.update(frozen)
            assert R.spec_hash()==summary['formal_spec_hash']
            summary['state']='backfill';R.OUTDIR=str(out/'backfill');R.DB_PATH=str(Path(R.OUTDIR)/'rt_a.sqlite')
            rc=R.backfill(require_complete=True);summary['stages']['backfill']=rc;save()
            summary['state']='report'
            report_rc=R.report();summary['stages']['report']=report_rc
            rc=rc or report_rc
            summary['state']='complete' if rc==0 else 'incomplete'
            return rc
        except BaseException as exc:
            rc=1
            summary['state']='failed';summary['exception']=redact(type(exc).__name__+': '+str(exc));raise
        finally:
            summary['exit']=rc;save();stopped.set()

if __name__=='__main__':sys.exit(main())
