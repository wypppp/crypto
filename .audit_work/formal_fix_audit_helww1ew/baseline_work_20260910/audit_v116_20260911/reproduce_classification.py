"""Controlled full measure flows. Errors injected below RpcTap; no network."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

W = Path('/home/ancillary/rightTail/baseline_work_20260910')
sys.path.insert(0, str(W))
import audit_flow as A
P, E = A.P, A.E
mark0 = E.RpcTap.mark
request0 = A.FakeRpc.request
call0 = A.FakeRpc.call
observations = []

for scene, target_stage, target_op in [
    ('entry_code_transport', 'state_validation', 'request'),
    ('entry_identity_transport', 'state_validation', 'call'),
    ('exit_code_transport', 'state_validation_exit', 'request'),
    ('exit_identity_transport', 'state_validation_exit', 'call'),
    ('restore_transport', 'restore_check', 'request'),
]:
    fired = []
    def mark(self, *a, **kw):
        result = mark0(self, *a, **kw)
        self.rpc._audit_stage = self.stage
        self.rpc._audit_candidate = self.candidate
        return result
    def inject(raw, op, method, params):
        if (not fired and raw._audit_candidate == 1
                and raw._audit_stage == target_stage and op == target_op):
            fired.append(True)
            raw.records.append({'method': method, 'params': params,
                'error': {'kind': 'transport', 'message': 'controlled TLS EOF'}})
            raise P.V.RpcFailure('transport', 'controlled TLS EOF')
    def request(self, method, params):
        inject(self, 'request', method, params)
        return request0(self, method, params)
    def call(self, to, data, block, overrides=None):
        inject(self, 'call', 'eth_call', [to, data, block])
        return call0(self, to, data, block, overrides)
    with tempfile.TemporaryDirectory(prefix='rta-classification-') as tmp:
        with patch.object(E.RpcTap, 'mark', mark), patch.object(A.FakeRpc, 'request', request), patch.object(A.FakeRpc, 'call', call):
            rc, doc, rows, instances = A.flow(Path(tmp), scene)
        c = next(x for x in doc['results'] if x['index'] == 1)
        ck = [json.loads(x) for x in (Path(tmp)/(scene+'.ck')).read_text().splitlines()]
        attempt = next(x for x in ck if x.get('candidate') == 1)
        diag = E.read_evidence(Path(tmp)/(scene+'.jsonl'), report=True)[1]
        observation = dict(scene=scene, injected=bool(fired), exit=rc,
            state=c['state'], validation_passed=c['validation_passed'],
            checkpoint_completed=attempt['completed'], evidence_complete=diag['complete'],
            identity_failures=(c.get('state_validation_exit') or c.get('state_validation') or {}).get('failures'),
            restore=c.get('restore_check'), data=c.get('data'),
            entry_attempts=(c.get('cost') or {}).get('entry_attempts'),
            exit_attempts=(c.get('cost') or {}).get('exit_attempts'))
        observations.append(observation)
        assert fired and rc == 1 and attempt['completed'] is False and diag['complete']
        assert c['economic_eligible'] is False
        # This reproducer asserts current behavior, not desired repaired behavior.
        expected = 'data_missing' if scene == 'entry_code_transport' else 'state_validation_failed'
        assert c['state'] == expected

out = Path(__file__).resolve().parent
(out/'classification_observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2))
print(json.dumps(observations,ensure_ascii=False,indent=2))
