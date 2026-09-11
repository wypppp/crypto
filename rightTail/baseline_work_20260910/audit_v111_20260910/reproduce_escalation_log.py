"""Unit test of actual measure escalation callback; os._exit is mocked throughout."""
import sys,tempfile,threading,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
P,E=A.P,A.E
captured=[]
def capture(*a,**kw):captured.append(kw['on_escalate']);raise RuntimeError('capture callback before any real governor work')
with tempfile.TemporaryDirectory(prefix='rta-escalation-') as td:
 with patch.object(E,'ResourceGovernor',side_effect=capture):
  try:A.flow(Path(td),'run')
  except RuntimeError:pass
 cb=captured[0]
 log=dict(zip(cb.__code__.co_freevars,[c.cell_contents for c in cb.__closure__]))['log']
 entered=threading.Event();exit_codes=[];original_write=E.EvidenceLog.write
 def write(self,*a,**kw):entered.set();return original_write(self,*a,**kw)
 with patch.object(P.os,'_exit',side_effect=lambda code:exit_codes.append(code)),patch.object(E.EvidenceLog,'write',write):
  log._lock.acquire()
  t=threading.Thread(target=cb,args=({'stuck_inflight':1},),daemon=True)
  try:
   t.start();assert entered.wait(1)
   t.join(.1)
   assert t.is_alive() and exit_codes==[]
   result=dict(callback_entered=True,writer_lock_held=True,exit_attempted_while_lock_held=False,callback_blocked=True)
  finally:log._lock.release();t.join(1)
  assert exit_codes==[3] and not t.is_alive()
  result['exit_after_lock_released']=exit_codes
 log.close()
 print(json.dumps(result))
 Path(__file__).with_name('escalation_log_observation.json').write_text(json.dumps(result,indent=2))
