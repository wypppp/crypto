"""Independent offline integration counterexamples; never contacts real endpoints."""
import argparse
import collections
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import pilot_measure as P
import evidence as E
from fake_chain import FakeRpc

REAL_RPC=P.V.RPC
REAL_SCAN=P.etherscan
outputs=[]
def record(name, **data):
    item=dict(name=name,**data);outputs.append(item);print(json.dumps(item),flush=True)

PAIR='0x'+'ab'*20;TOKEN='0x'+'cd'*20;MINT=24140010

def flow(d,tag,parallel=1,checkpoint=None,slot_limit=2,no_mint=False,worker_crash=False,max_calls=99999,scan_error=False):
    sample=d/'sample.json'
    if not sample.exists():
        sample.write_text(json.dumps(dict(universe_sha256=E.sha256_file(P.UNIVERSE),n=2,
             sample=[dict(index=i,pair=PAIR,token=TOKEN,created_block=MINT-10) for i in [1,2]])))
    cfg=dict(head=25900000,genesis_ts=0,entry_block=MINT+1,pair=PAIR,token=TOKEN,
             received=10**18,cash=10**15,slot=0,
             supply=lambda b:0 if no_mint or int(b,16)<MINT else 10**6)
    instances=[]
    def factory(*a,**kw):
        if worker_crash and threading.current_thread() is not threading.main_thread():
            raise RuntimeError('injected worker initialization failure')
        r=FakeRpc(cfg);instances.append(r);return r
    def scan(*a,**kw):
        if scan_error:
            with patch.object(P.urllib.request,'urlopen',side_effect=ValueError('diagnostic apikey=FAKE_ONLY_SCAN_KEY')):
                return REAL_SCAN(*a,**kw)
        return dict(status='1',result=[] if no_mint else [dict(address=PAIR,blockNumber=hex(MINT),
           topics=[P.MINT_TOPIC,'0x'+'0'*64],data='0x'+'1'*128,
           transactionHash='0x'+'2'*64,logIndex='0x0')])
    a=argparse.Namespace(sample=str(sample),out=str(d/(tag+'.json')),evidence=str(d/(tag+'.jsonl')),
        checkpoint=str(checkpoint or d/(tag+'.ck')),spec='MEASUREMENT_SPEC.v1.4.md',
        parallel=parallel,slot_limit=slot_limit,max_calls=max_calls,max_seconds=9999,rps=10000,diagnostics=False)
    with patch.object(P.V,'RPC',side_effect=factory),patch.object(P,'etherscan',side_effect=scan), \
         patch.dict(os.environ,ETH_RPC_URL='https://x.invalid/test/FAKE_ONLY_KEY',ETHERSCAN_API_KEY='FAKE_ONLY_SCAN_KEY'), \
         contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        rc=P.measure(a)
    doc=json.loads(Path(a.out).read_text())
    rows,diag=E.read_evidence(a.evidence,report=True)
    return rc,doc,rows,instances

with tempfile.TemporaryDirectory() as t:
    d=Path(t)
    rc,doc,rows,_=flow(d,'redaction',scan_error=True)
    exposed='FAKE_ONLY_SCAN_KEY' in (d/'redaction.json').read_text()
    evidence_exposed='FAKE_ONLY_SCAN_KEY' in (d/'redaction.jsonl').read_text()
    record('summary_json_bypasses_redaction',exit=rc,fake_secret_in_summary=exposed,fake_secret_in_evidence=evidence_exposed)
    assert exposed and not evidence_exposed

with tempfile.TemporaryDirectory() as t:
    rc,doc,rows,_=flow(Path(t),'budget_crash',parallel=2,max_calls=100)
    record('worker_budget_exhaustion_success',exit=rc,expected_n=2,actual_n=len(doc['results']),acceptance=doc['acceptance'])
    assert rc==0 and len(doc['results'])<2

with tempfile.TemporaryDirectory() as t:
    d=Path(t)
    rc,doc,rows,inst=flow(d,'parallel',parallel=2)
    unowned=[r for r in rows if r['kind']=='rpc' and r.get('worker') is not None and r.get('candidate') is None]
    actual=sum(len(x.records) for x in inst)
    record('parallel_outer_rpc',exit=rc,reported_rpc=doc['rpc_calls'],actual_mock_rpc=actual,
           unowned_worker_requests=len(unowned),
           unowned_methods=sorted({r['record']['method'] for r in unowned}))
    assert unowned and doc['rpc_calls']<actual
    pending=collections.Counter((r['run_id'],r['worker'],r['pending_id']) for r in rows if r['kind']=='rpc_begin')
    record('duplicate_pending_identifiers',duplicate_keys=sum(n>1 for n in pending.values()))

with tempfile.TemporaryDirectory() as t:
    rc,doc,rows,_=flow(Path(t),'worker_crash',parallel=2,worker_crash=True)
    record('worker_failure_success',exit=rc,expected_n=2,actual_n=len(doc['results']),acceptance=doc['acceptance'])
    assert rc==0 and not doc['results'] and doc['acceptance']['validation_passed']

with tempfile.TemporaryDirectory() as t:
    d=Path(t);ck=d/'shared.ck'
    rc,_,_,_=flow(d,'original',checkpoint=ck)
    rc2,doc,_,_=flow(d,'changed_slot',checkpoint=ck,slot_limit=0)
    record('changed_runtime_config_resumed',first_exit=rc,second_exit=rc2,slot_limit=0,
           skipped=doc['acceptance']['skipped_already_completed'],remaining_result_rows=len(doc['results']))
    assert rc==rc2==0 and doc['acceptance']['skipped_already_completed']==[1,2]

with tempfile.TemporaryDirectory() as t:
    rc,doc,_,_=flow(Path(t),'no_mint',no_mint=True)
    record('verified_no_mint_not_completable',exit=rc,states=[r['state'] for r in doc['results']],
           validation=[r['validation_passed'] for r in doc['results']])
    assert rc==1 and all(r['state']=='no_mint_by_cutoff' for r in doc['results'])

with tempfile.TemporaryDirectory() as t:
    p=Path(t)/'ck';c=E.Checkpoint(p);c.write_binding(sample_sha256='s');c.close()
    with p.open('a') as f:f.write('{"partial":')
    c=E.Checkpoint(p);c.record_attempt(1,'measured_exit',True);before=c.completed();c.close()
    c=E.Checkpoint(p);after=c.completed();c.close()
    record('checkpoint_partial_append_loses_success',before=sorted(before),after=sorted(after))
    assert before=={1} and after==set()

with tempfile.TemporaryDirectory() as t:
    p=Path(t)/'e';l=E.EvidenceLog(p);l.write('run_header');l.write('rpc_begin',pending_id=1)
    l.write('run_footer');l.close();_,diag=E.read_evidence(p,report=True)
    record('unmatched_begin_considered_complete',complete=diag['complete'])
    assert diag['complete'] is True

with tempfile.TemporaryDirectory() as t:
    log=E.EvidenceLog(Path(t)/'retry');gate=E.SharedGate(10000,1,30)
    rpc=REAL_RPC('https://x.invalid',max_calls=10,max_seconds=30,rps=10000)
    tap=E.RpcTap(rpc,log,gate=gate,worker=0);calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*a):return json.dumps(dict(jsonrpc='2.0',id=2,result='0x1')).encode()
    def urlopen(*a,**k):
        calls.append(1)
        if len(calls)==1:raise urllib.error.HTTPError('https://x.invalid',503,'temporary',{},None)
        return Response()
    with patch.object(P.V.urllib.request,'urlopen',side_effect=urlopen),patch.object(P.V.time,'sleep'):
        value=tap.request('eth_chainId',[])
    log.close()
    record('http_retry_exceeds_shared_budget',max_calls=1,gate_calls=gate.calls,http_attempts=len(calls),result=value)
    assert gate.calls==1 and len(calls)==2

record('zero_unexecuted_leg_erases_known_buy_cost',
       costs=P.gas_cost({'swap':1,'approve':0},{'swap':0,'approve':0},10**9,None))
assert all(v=='unknown' for v in outputs[-1]['costs'].values())
bad=dict(address=PAIR,topics=[P.MINT_TOPIC,'NOT_AN_ADDRESS'],data='0x'+'z'*128,
         transactionHash='0x',logIndex='0x0',blockNumber=hex(MINT),blockHash='WRONG')
record('malformed_mint_accepted',rejection=P._validate_log(bad,PAIR,MINT-1,MINT+1))
assert P._validate_log(bad,PAIR,MINT-1,MINT+1) is None
gate=E.SharedGate(20,10,0.01)
gate.acquire();gate.acquire()
record('request_admitted_after_time_budget',elapsed=gate.stats()['elapsed_s'],budget=0.01)
(Path(__file__).parent/'counterexamples.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2)+'\n')
