"""Uses original RPC and gate; urlopen is fully mocked, no network."""
import sys,json,tempfile,time,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
E=A.E
with tempfile.TemporaryDirectory() as td:
    raw=A.REAL_RPC('https://offline.invalid',max_calls=10,max_seconds=10,rps=1000000)
    log=E.EvidenceLog(Path(td)/'e.jsonl')
    gate=E.SharedGate(0.1,2,10)
    tap=E.RpcTap(raw,log,gate=gate,worker=0)
    starts=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return json.dumps(dict(jsonrpc='2.0',id=2,result='0x1')).encode()
    def transport(*a,**kw):
        starts.append(time.monotonic()-gate.started)
        if len(starts)==1:raise urllib.error.HTTPError('https://offline.invalid',503,'mock',{},None)
        return Response()
    with patch.object(A.P.V.urllib.request,'urlopen',side_effect=transport):
        result=tap.request('eth_chainId',[])
    log.close()
    assert len(starts)==2 and starts[1]-starts[0]<gate.interval and result=='0x1'
    report=dict(required_http_interval_seconds=gate.interval,http_start_seconds=starts,result=result,gate=gate.stats())
    print(json.dumps(report))
    Path(__file__).with_name('retry.json').write_text(json.dumps(report,indent=2))
