"""Offline audit: all network replaced by audit_flow mocks; temporary outputs only."""
import sys,json,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
P,E=A.P,A.E
out=[]
def emit(name,**kw):
    out.append(dict(name=name,**kw));print(json.dumps(out[-1]),flush=True)
with tempfile.TemporaryDirectory(prefix='rta-followup-') as td:
    root=Path(td)
    d=root/'resume';d.mkdir();ck=d/'shared.ck'
    rc,doc,rows,rs=A.flow(d,'first',checkpoint=ck)
    assert rc==0
    (d/'first.json').unlink();(d/'first.jsonl').unlink()
    rc,doc,rows,rs=A.flow(d,'second',checkpoint=ck)
    assert rc==0 and not doc['results']
    emit('missing_prior_results_accepted',exit=rc,results=doc['results'],acceptance=doc['acceptance'])
    lines=ck.read_text().splitlines();lines.insert(1,'BROKEN');ck.write_text('\n'.join(lines)+'\n')
    rc,doc,rows,rs=A.flow(d,'third',checkpoint=ck)
    assert rc==0
    emit('mid_checkpoint_corruption_accepted',exit=rc,acceptance=doc['acceptance'])
    d=root/'budget';d.mkdir()
    rc,doc,rows,rs=A.flow(d,'run',parallel=2,max_calls=2)
    count=sum(len(r.records) for r in rs)
    assert count>2
    emit('startup_outside_global_budget',exit=rc,max_calls=2,actual_mock_rpc=count)
    d=root/'cost';d.mkdir()
    with patch.object(P,'find_slot',side_effect=P.V.RpcFailure('transport','injected after buy')):
        rc,doc,rows,rs=A.flow(d,'run')
    rr=doc['results'][0]
    assert rr.get('entry') and not rr.get('cost')
    emit('buy_cost_lost_on_later_exception',exit=rc,state=rr['state'],entry=rr.get('entry'),cost=rr.get('cost'))
    d=root/'duplicates';d.mkdir()
    sample=dict(universe_sha256=E.sha256_file(P.UNIVERSE),n=2,sample=[dict(index=1,pair=A.PAIR,token=A.TOKEN,created_block=A.MINT-10)]*2)
    (d/'sample.json').write_text(json.dumps(sample))
    rc,doc,rows,rs=A.flow(d,'run')
    assert rc==0
    emit('duplicate_candidate_ids_accepted',exit=rc,indices=[r['index'] for r in doc['results']],acceptance=doc['acceptance'])
    f=root/'empty.jsonl';f.write_text('')
    _,diag=E.read_evidence(f,report=True)
    assert diag['complete']
    emit('empty_evidence_complete',diagnostic=diag)
    f.write_text(json.dumps(dict(run_id='r',seq=1,kind='rpc_end',pending_id=1))+'\n'+json.dumps(dict(run_id='r',seq=2,kind='run_footer'))+'\n')
    _,diag=E.read_evidence(f,report=True)
    assert diag['complete']
    emit('orphan_end_without_header_complete',diagnostic=diag)
    ev=dict(address=A.PAIR,blockNumber=hex(A.MINT),topics=[P.MINT_TOPIC,'0x'+'0'*64],data='0x'+'1'*128,transactionHash='0x',blockHash='WRONG',logIndex='garbage')
    rejected=P._validate_log(ev,A.PAIR,A.MINT-10,A.MINT+10)
    assert rejected is None
    emit('malformed_event_identity_accepted',validation=rejected,event=ev)
Path(__file__).with_name('remaining.json').write_text(json.dumps(out,indent=2))
