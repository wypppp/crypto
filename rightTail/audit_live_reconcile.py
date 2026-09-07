"""Read-only small-window reconciliation using existing credentials, with public RPC evidence."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

p=argparse.ArgumentParser()
p.add_argument('--env-file',default=str(Path(__file__).resolve().parents[1]/'.env'))
p.add_argument('--from-block',type=int,required=True)
p.add_argument('--to-block',type=int,required=True)
p.add_argument('--out',required=True)
a=p.parse_args()
if not 1<=a.from_block<=a.to_block or a.to_block-a.from_block>10000:
    p.error('small reconciliation requires 1..10001 explicitly selected blocks')
values={}
for line in Path(a.env_file).read_text().splitlines():
    match=re.match(r'\s*(?:export\s+)?([^:=]+?)\s*[:=]\s*(.*?)\s*$',line)
    if match: values[match[1].strip().lower()]=match[2].strip().strip('\"\'')
for env, label in [('RTA_RPC_ETH','alchemy endpoint url'),('ETHERSCAN_API_KEY','etherscan key')]:
    if not os.environ.get(env):
        os.environ[env]=values.get(env.lower(),values.get(label,''))
    if not os.environ[env]: raise SystemExit('Missing '+env)
out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
os.environ.update(RTA_CHAIN='ethereum',RTA_PAIR_LOGS='etherscan',RTA_OUT=str(out),
                  RTA_FROM_BLOCK=str(a.from_block),RTA_TO_BLOCK=str(a.to_block))
source=Path(__file__).with_name('rt_a_attribution.py')
spec=importlib.util.spec_from_file_location('R',source)
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
records=[]
secrets=[os.environ['RTA_RPC_ETH'],os.environ['ETHERSCAN_API_KEY'],values.get('alchemy key','')]
def sanitize(value):
    text=json.dumps(value,ensure_ascii=False)
    for secret in secrets:
        if secret: text=text.replace(secret,'[REDACTED]')
    return json.loads(text)
def wrap(fn,kind):
    def call(*args,**kw):
        result=fn(*args,**kw)
        records.append(sanitize({'kind':kind,'args':args,'kwargs':kw,'response':result}))
        return result
    return call
R.rpc=wrap(R.rpc,'rpc');R.etherscan=wrap(R.etherscan,'etherscan')
rc=1
try:
    chain,error=R.rpc('eth_chainId',[])
    if error or R.hex_int(chain)!=1: raise RuntimeError('RPC chain ID verification failed')
    sys.argv=['rt_a_attribution.py','reconcile']
    try: R.main()
    except SystemExit as e: rc=e.code
finally:
    (out/'requests.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    (out/'execution.json').write_text(json.dumps({'source':str(source),'exit':rc,
      'candidate_range':[a.from_block,a.to_block],'history_lookback_blocks':0,
      'request_count':len(records),'attribution':False,'report':False},indent=2))
sys.exit(rc)
