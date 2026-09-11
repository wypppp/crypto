#!/usr/bin/env python3
"""Offline, isolated audit probes. rc=0 means the documented counterexamples reproduced.

No real RPC objects or Etherscan transport are constructed: audit_flow substitutes both.
Outputs go to a newly created directory; existing delivery bytes are never edited.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

W = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(W))
import audit_flow as A
P, E, F = A.P, A.E, A.FakeRpc
MARK, REQ, CALL = E.RpcTap.mark, F.request, F.call


def run_case(root, name, mode):
    d = root / name
    d.mkdir()
    fired = []

    def mark(self, *a, **kw):
        ret = MARK(self, *a, **kw)
        self.rpc._audit_stage, self.rpc._audit_candidate = self.stage, self.candidate
        return ret

    def event(raw, method, params, value=None, error=None):
        row = dict(stage=raw._audit_stage, candidate=raw._audit_candidate,
                   method=method, params=params, value=value, error=error)
        fired.append(row)
        raw.records.append(row)
        if error:
            raise P.V.RpcFailure(error, 'controlled follow-on ' + error)
        return value

    def call(self, to, data, block, overrides=None):
        stage, candidate = getattr(self, '_audit_stage', None), getattr(self, '_audit_candidate', None)
        sel = data[2:10]
        if candidate == 1 and stage == 'state_validation' and mode.startswith('sides'):
            if sel == P.V.selector('token0()'):
                return event(self, 'eth_call', [to, data, block], '0x' + '0'*24 + '99'*20)
            if mode == 'sides_then_transport' and sel == P.V.selector('getPair(address,address)'):
                return event(self, 'eth_call', [to, data, block], error='transport')
        return CALL(self, to, data, block, overrides)

    def request(self, method, params):
        stage, candidate = getattr(self, '_audit_stage', None), getattr(self, '_audit_candidate', None)
        target = 'restore_check' if mode.startswith('restore') else 'state_validation'
        if candidate == 1 and mode in ('restore_dirty', 'restore_dirty_then_budget', 'entry_dirty_then_budget') and stage == target:
            if params and params[0] == P.V.WALLET:
                if method == 'eth_getCode':
                    return event(self, method, params, '0x60')
                if method == 'eth_getBalance' and mode.endswith('budget'):
                    return event(self, method, params, error='budget')
        return REQ(self, method, params)

    with patch.object(E.RpcTap, 'mark', mark), patch.object(F, 'call', call), patch.object(F, 'request', request):
        rc, doc, rows, instances = A.flow(d, name)
    c = next(r for r in doc['results'] if r['index'] == 1)
    validation = c.get('state_validation') or {}
    restore = c.get('restore_check') or {}
    checks = [r for r in rows if r.get('kind') in ('state_validation', 'wallet_restore_check') and r.get('candidate') == 1]
    summary = dict(case=name, exit=rc, state=c['state'], validation_status=c.get('validation_status'),
                   validation_passed=c.get('validation_passed'), validation=validation, restore=restore,
                   validation_evidence=checks, fired=fired, acceptance=doc['acceptance'],
                   evidence_complete=E.read_evidence(d/(name+'.jsonl'), report=True)[1]['complete'])
    (d/'observation.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k: summary[k] for k in ('case','exit','state','validation_status','validation_passed','evidence_complete')}))
    return summary


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out-root', required=True); a=ap.parse_args()
    root=Path(a.out_root);root.mkdir(exist_ok=False)
    names=['baseline','sides_only','sides_then_transport','restore_dirty','restore_dirty_then_budget','entry_dirty_then_budget']
    results={n:run_case(root,n,n) for n in names}
    (root/'source_hashes.json').write_text(json.dumps({n:hashlib.sha256((W/n).read_bytes()).hexdigest() for n in ('pilot_measure.py','evidence.py','audit_flow.py','fake_chain.py')},indent=2)+'\n')
    assert results['baseline']['exit']==0 and results['baseline']['validation_passed'] is True
    assert results['sides_only']['state']=='state_validation_failed' and results['sides_only']['validation']['failures']
    x=results['sides_then_transport']
    assert len(x['fired'])==2 and x['fired'][0]['value'].endswith('99'*20)
    assert x['exit']==1 and x['state']=='data_missing' and x['validation_passed'] is None
    assert not x['validation']['failures'] and 'identity_closure' not in x['validation']
    assert results['restore_dirty']['restore']['failures'] and results['restore_dirty']['validation_passed'] is False
    for n in ('restore_dirty_then_budget','entry_dirty_then_budget'):
        x=results[n]; assert len(x['fired']) >= 2 and x['fired'][0]['value']=='0x60'
        part=x['restore'] if n.startswith('restore') else x['validation']
        assert x['exit']==1 and x['state']=='budget_exhausted' and not part['failures'] and x['validation_passed'] is None
    (root/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    print('All controls and three loss-of-known-mismatch counterexamples reproduced.')


if __name__=='__main__': main()
