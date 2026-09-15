"""复用审查方 reproduce.py 的受控 flow()，用于断言【修复后】行为。"""
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

def flow(d,tag,parallel=1,checkpoint=None,slot_limit=2,no_mint=False,worker_crash=False,max_calls=99999,scan_error=False,pin_finalized=None,
         max_rss_mb=None,max_cpu_s=None,max_wall_s=None,governor_poll_s=0.02,chain_id=1,
         hard_rss_mb=None,hard_cpu_s=None,stop_grace_calls=16,stop_grace_seconds=15.0,faults=()):
    sample=d/'sample.json'
    if not sample.exists():
        sample.write_text(json.dumps(dict(universe_sha256=E.sha256_file(P.UNIVERSE),n=2,
             sample=[dict(index=i,pair=PAIR,token=TOKEN,created_block=MINT-10) for i in [1,2]])))
    cfg=dict(head=25900000,genesis_ts=0,entry_block=MINT+1,pair=PAIR,token=TOKEN,chain_id=chain_id,
             received=10**18,cash=10**15,slot=0,faults=faults,
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
        checkpoint=str(checkpoint or d/(tag+'.ck')),spec='MEASUREMENT_SPEC.v1.19.md',
        parallel=parallel,slot_limit=slot_limit,max_calls=max_calls,max_seconds=9999,rps=10000,diagnostics=False,
        pin_finalized=pin_finalized,
        max_rss_mb=max_rss_mb,max_cpu_s=max_cpu_s,max_wall_s=max_wall_s,
        governor_poll_s=governor_poll_s,hard_rss_mb=hard_rss_mb,hard_cpu_s=hard_cpu_s,
        stop_grace_calls=stop_grace_calls,stop_grace_seconds=stop_grace_seconds)
    with patch.object(P.V,'RPC',side_effect=factory),patch.object(P,'etherscan',side_effect=scan), \
         patch.dict(os.environ,ETH_RPC_URL='https://x.invalid/test/FAKE_ONLY_KEY',ETHERSCAN_API_KEY='FAKE_ONLY_SCAN_KEY'), \
         contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        rc=P.measure(a)
    doc=json.loads(Path(a.out).read_text())
    rows,diag=E.read_evidence(a.evidence,report=True)
    return rc,doc,rows,instances

