"""Read-only verification of audit-sample creation senders against fresh chain receipts."""
import argparse,csv,importlib.util,json,os,re,sqlite3,sys
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--run',required=True);args=p.parse_args()
root=Path(__file__).resolve().parent;run=Path(args.run).resolve()
values={}
for line in (root.parent/'.env').read_text().splitlines():
 m=re.match(r'\s*([^:=]+?)\s*[:=]\s*(.*?)\s*$',line)
 if m:values[m[1].lower()]=m[2].strip().strip('\"\'')
os.environ['RTA_RPC_ETH']=os.environ.get('RTA_RPC_ETH') or values['alchemy endpoint url']
os.environ['ETHERSCAN_API_KEY']=os.environ.get('ETHERSCAN_API_KEY') or values['etherscan key']
spec=importlib.util.spec_from_file_location('R',root/'rt_a_attribution.py');R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
R.SPEC.clear();R.SPEC.update(json.loads((run/'formal_frozen.json').read_text())['formal_spec'])
R.rpc_limiter.min_gap=1.0;R.scan_limiter.min_gap=1.0
con=sqlite3.connect('file:'+str(run/'backfill/rt_a.sqlite')+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
samples=list(csv.DictReader((run/'backfill/audit_sample.csv').open()))
evidence=[]
chain,error=R.rpc('eth_chainId',[]);assert error is None and R.hex_int(chain)==1
for sample in samples:
 row=dict(con.execute('SELECT a.*,c.new_token FROM attribution a JOIN candidates c ON c.pair=a.pair WHERE a.pair=?',(sample['pair'],)).fetchone())
 out={'pair':row['pair'],'deploy_kind':row['deploy_kind'],'token':row['new_token'],'creation_tx':row['creation_tx'],'expected_sender':row['creation_tx_sender']}
 if not row['creation_tx_sender']:
  out.update(result='undetermined',reason='No determinate creation sender in the frozen rule');evidence.append(out);continue
 tx,te=R.rpc('eth_getTransactionByHash',[row['creation_tx']]);rc,re_=R.rpc('eth_getTransactionReceipt',[row['creation_tx']])
 out.update(transaction=tx,receipt=rc,errors=[te,re_])
 checks={'outer_from_matches':bool(tx) and (tx.get('from') or '').lower()==row['creation_tx_sender'],
         'transaction_succeeded':bool(rc) and R.hex_int(rc.get('status'))==1,
         'creation_block_matches':bool(rc) and R.hex_int(rc.get('blockNumber'))==row['creation_block']}
 if row['deployment_factory']:
  traces,err=R.etherscan('account','txlistinternal',txhash=row['creation_tx'])
  out.update(internal_traces=traces,internal_error=err)
  traces=R.as_rows(traces) if not err else None
  checks['target_creation_confirmed']=bool(traces) and any(t.get('type','').lower() in ('create','create2') and (t.get('contractAddress') or '').lower()==row['new_token'] and str(t.get('isError','0'))=='0' for t in traces)
 else:
  checks['target_creation_confirmed']=bool(rc) and (rc.get('contractAddress') or '').lower()==row['new_token']
 out['checks']=checks;out['result']='verified' if all(checks.values()) else 'needs_review'
 evidence.append(out)
 print(out['pair'],out['result'],checks,flush=True)
 (run/'sample_receipt_audit.json').write_text(json.dumps({'chain_id':1,'checked_at':R.now_iso(),'rows':evidence},ensure_ascii=False,indent=2))
summary={result:sum(x['result']==result for x in evidence) for result in ('verified','undetermined','needs_review')}
(run/'sample_receipt_audit.json').write_text(json.dumps({'chain_id':1,'checked_at':R.now_iso(),'summary':summary,'rows':evidence},ensure_ascii=False,indent=2))
print(summary)
sys.exit(1 if summary['needs_review'] else 0)
