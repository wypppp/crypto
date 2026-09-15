"""Independent offline acceptance from persisted transport responses and CSV; no collector import."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run',required=True)
    args=ap.parse_args()
    root=Path(args.run)
    report={'exit':1,'scope':'universe only; no execution or economic inference'}
    try:
        ex=json.loads((root/'execution.json').read_text())
        assert ex['state']=='complete' and ex['exit']==0 and ex['baseline_ready'] is False
        frozen=json.loads((root/'collection_frozen.json').read_text())
        p=frozen['payload']
        assert hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==frozen['payload_sha256']
        for path,h in ex['source_hashes'].items():
            assert hashlib.sha256((root/(Path(path).stem+'.snapshot.py')).read_bytes()).hexdigest()==h
        start,end=p['start_block'],p['end_block'];i0,i1=p['expected_index_range']
        weth=p['weth'];factory=p['factory'].lower()
        by_index={};counts=collections.Counter();rpc=[]
        for line in (root/'requests.jsonl').read_text().splitlines():
            record=json.loads(line);counts[record['kind']]+=1
            assert record['http_status']==200 and 'error' not in record
            response=json.loads(record['response']);request=record['request']
            if record['kind']=='rpc':
                assert response['id']==request['id'] and 'error' not in response
                rpc.append((request,response['result']))
                continue
            assert response['status']=='1'
            for event in response['result']:
                assert event['address'].lower()==factory
                assert start<=int(event['blockNumber'],16)<=end and not event.get('removed',False)
                topics=event['topics'];data=event['data'][2:]
                assert topics[0].lower()=='0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9'
                assert len(topics)==3 and len(data)==128 and data[:24]=='0'*24
                assert all(len(t)==66 and t[2:26]=='0'*24 for t in topics[1:])
                t0,t1=('0x'+t[-40:].lower() for t in topics[1:])
                assert 0<int(t0,16)<int(t1,16)
                idx=int(data[64:],16)-1
                row=dict(index=idx,pair='0x'+data[24:64].lower(),token0=t0,token1=t1,
                         category='weth' if weth in (t0,t1) else 'non_weth',
                         block=int(event['blockNumber'],16),tx=event['transactionHash'].lower(),
                         log_index=int(event['logIndex'] if event['logIndex']!='0x' else '0x0',16),reason='')
                assert i0<=idx<i1
                if idx in by_index: assert by_index[idx]==row
                by_index[idx]=row
        assert dict(counts)==ex['http_attempts']
        assert sorted(by_index)==list(range(i0,i1))
        assert len({r['pair'] for r in by_index.values()})==i1-i0
        assert len({(r['tx'],r['log_index']) for r in by_index.values()})==i1-i0
        csv_rows=list(csv.DictReader((root/'universe.csv').open()))
        assert len(csv_rows)==i1-i0
        for idx,row in zip(range(i0,i1),csv_rows):
            expected={k:str(v) for k,v in by_index[idx].items()}
            assert row==expected
        assert hashlib.sha256((root/'universe.csv').read_bytes()).hexdigest()==ex['universe_sha256']
        def values(method,params):
            return [v for r,v in rpc if r['method']==method and r['params']==params]
        for block_number,count in [(start-1,i0),(end,i1)]:
            got=values('eth_call',[{'to':p['factory'],'data':'0x574f2ba3'},hex(block_number)])
            assert got and all(int(v,16)==count for v in got)
        for n,b in p['boundaries'].items():
            got=values('eth_getBlockByNumber',[hex(int(n)),False])
            assert len(got)>=2 and all({k:v[k] for k in b}==b for v in got)
        checks=json.loads((root/'registry_checks.json').read_text())
        assert checks['ok'] and len(checks['indices'])==10
        for idx in checks['indices']:
            r=by_index[idx]
            for target,data,expected in [
                (p['factory'],'0x1e3dd18b'+format(idx,'064x'),r['pair']),
                (r['pair'],'0x0dfe1681',r['token0']),
                (r['pair'],'0xd21220a7',r['token1']),
                (p['factory'],'0xe6a43905'+r['token0'][2:].zfill(64)+r['token1'][2:].zfill(64),r['pair'])]:
                got=values('eth_call',[{'to':target,'data':data},hex(end)])
                assert got and all('0x'+v[-40:].lower()==expected for v in got)
        categories=collections.Counter(r['category'] for r in by_index.values())
        assert dict(categories)==ex['categories']
        resources=[json.loads(x) for x in (root/'resources.jsonl').read_text().splitlines()]
        report.update(exit=0,N_all=i1-i0,WETH=categories['weth'],non_WETH=categories['non_weth'],
                      unknown=0,raw_responses_match_every_csv_row=True,registry_indices_checked=10,
                      boundary_hashes_stable=True,peak_rss_kib=max(x['max_rss_kib'] for x in resources),
                      http_attempts=dict(counts),elapsed_seconds=ex['elapsed_seconds'])
    except Exception as e:
        report['error']=f'{type(e).__name__}: {e}'
    (root/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
    return report['exit']


if __name__=='__main__': raise SystemExit(main())
