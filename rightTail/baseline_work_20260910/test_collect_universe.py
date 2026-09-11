"""Offline end-to-end process/artifact assertions; all outputs are temporary."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect_universe as C


class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = C.load(C.ROOT/'rt_a_attribution.py','test_universe_rta')
        cls.B = C.load(C.ROOT/'baseline_20260909/verify_capabilities.py','test_universe_abi')

    def events(self):
        R=self.R
        return [dict(address=R.chain_cfg()['factory'],blockNumber=hex(C.START+j),
                     transactionHash='0x'+format(j+1,'064x'),logIndex='0x0',
                     topics=[R.TOPIC_PAIR_CREATED,'0x'+format(j+1,'064x'),
                             '0x'+(C.WETH[2:].zfill(64) if j!=1 else format(99,'064x'))],
                     data='0x'+format(1000+j,'064x')+format(C.I0+j+1,'064x'))
                for j in range(3)]

    def test_categories_and_zero_based_indices(self):
        rows=C.ledger(self.events(),self.R,C.I0,C.I0+3)
        self.assertEqual([r['category'] for r in rows],['weth','non_weth','weth'])
        self.assertEqual([r['index'] for r in rows],list(range(C.I0,C.I0+3)))

    def test_missing_retained_as_unknown(self):
        rows=C.ledger(self.events()[:-1],self.R,C.I0,C.I0+3)
        self.assertEqual(rows[-1]['reason'],'missing_event')

    def test_duplicates(self):
        logs=self.events();logs.append(copy.deepcopy(logs[0]))
        self.assertEqual(len(C.ledger(logs,self.R,C.I0,C.I0+3)),3)
        logs[-1]['data']='0x'+format(8888,'064x')+format(C.I0+1,'064x')
        with self.assertRaisesRegex(ValueError,'conflicting duplicate'):
            C.ledger(logs,self.R,C.I0,C.I0+3)

    def test_invalid_token_retained_unknown(self):
        logs=self.events();logs[0]['topics'][1]='0x'+'0'*64
        self.assertEqual(C.ledger(logs,self.R,C.I0,C.I0+3)[0]['category'],'unknown')

    def flow(self, missing=False, budget=400):
        R,B=self.R,self.B
        logs=self.events()
        class Response:
            status_code=200
            def __init__(self,obj): self.obj=obj;self.text=json.dumps(obj)
            def json(self): return self.obj
        def request(method,url,**kw):
            if 'params' in kw:
                return Response(dict(status='1',message='OK',result=logs[:-1] if missing else logs))
            req=kw['json'];m=req['method'];p=req['params']
            if m=='eth_chainId': value='0x1'
            elif m=='eth_getBlockByNumber':
                n=C.END+20 if p[0]=='finalized' else int(p[0],16)
                ts={C.START-1:1767225599,C.START:1767225600,C.END:1775001599,C.END+1:1775001600}.get(n,1775001900)
                value=dict(number=hex(n),timestamp=hex(ts),hash='0x'+format(n,'064x'))
            elif m=='eth_getCode': value='0x6000'
            elif m=='eth_call':
                data=p[0]['data'];sel=data[:10]
                if sel=='0x574f2ba3':
                    value='0x'+B.pad(C.I0 if int(p[1],16)==C.START-1 else C.I0+3)
                elif sel=='0x1e3dd18b': value='0x'+B.pad(1000+int(data[10:],16)-C.I0)
                elif sel in ('0x0dfe1681','0xd21220a7'):
                    j=int(p[0]['to'],16)-1000
                    value=logs[j]['topics'][1 if sel=='0x0dfe1681' else 2]
                elif sel=='0xe6a43905':value='0x'+B.pad(999+int(data[10:74],16))
                else: raise AssertionError('unexpected call')
            else: raise AssertionError('unexpected method')
            return Response(dict(jsonrpc='2.0',id=req['id'],result=value))
        class NoWait:
            def __init__(self,*a):pass
            def wait(self):pass
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run'
            with patch.object(C,'I1',C.I0+3),patch.object(C,'load',side_effect=[R,B]), \
                 patch.object(R._session,'request',side_effect=request), \
                 patch.object(R,'Limiter',NoWait), \
                 patch.object(R,'ETHERSCAN_KEY','offline-test-key'), \
                 patch.object(C.resource,'setrlimit'),patch.object(C.os,'nice'), \
                 patch('sys.argv',['collect','--out',str(out),'--max-http',str(budget)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                rc=C.main()
            summary=json.loads((out/'execution.json').read_text())
            self.assertEqual(rc,summary['exit'])
            self.assertFalse(summary['baseline_ready'])
            if missing or budget<20:
                self.assertEqual(rc,1)
                self.assertEqual(summary['state'],'incomplete')
                self.assertIsNone(summary.get('N'))
            else:
                self.assertEqual(rc,0,summary)
                self.assertEqual(summary['N'],2)
                self.assertEqual(summary['categories'],{'weth':2,'non_weth':1})
                self.assertTrue((out/'registry_checks.json').exists())
            self.assertFalse((out/'sample.csv').exists())
            self.assertTrue((out/'requests.jsonl').stat().st_size>0)

    def test_success_exit_and_artifacts(self): self.flow()
    def test_missing_event_blocks_complete_result(self): self.flow(missing=True)
    def test_budget_blocks_complete_result(self): self.flow(budget=2)


if __name__=='__main__': unittest.main()
