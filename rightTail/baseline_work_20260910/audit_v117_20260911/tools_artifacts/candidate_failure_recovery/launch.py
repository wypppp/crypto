import sys, runpy
from pathlib import Path
from unittest.mock import patch
W=Path('/home/ancillary/rightTail/baseline_work_20260910')
sys.path.insert(0,str(W))
import pilot_measure as P
from fake_chain import FakeRpc
tag=Path(sys.argv[sys.argv.index('--out')+1]).stem
orig=FakeRpc.request
def request(self,method,params):
    if tag=='serial' and method=='eth_chainId':
        self.records.append(dict(method=method,params=params,error=dict(kind='transport',message='controlled startup EOF')))
        raise P.V.RpcFailure('transport','controlled startup EOF')
    return orig(self,method,params)
with patch.object(FakeRpc,'request',request):
    runpy.run_path(str(W/'realchain_tools/fake_launch.py'),run_name='__main__')
