"""Offline lifecycle audit; bounded mock transport and a child-owned full stderr pipe."""
import sys,json,tempfile,threading,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_flow as A
P,E=A.P,A.E
out=[]
def emit(name,**kw):out.append(dict(name=name,**kw));print(json.dumps(out[-1]),flush=True)
with tempfile.TemporaryDirectory(prefix='rta-v112-') as td:
 d=Path(td);release=threading.Event();started=threading.Event();holder={}
 class Response:
  def close(self):pass
 def transport():
  started.set();release.wait(2);return Response()
 def scan(rpc,*a,**kw):
  g=rpc.gate.governor;holder['gov']=g
  g.request_stop('controlled_stop')
  return E._supervised_open(transport,g,(),{})
 try:
  with patch.object(P,'find_slot',side_effect=scan):
   rc,doc,rows,_=A.flow(d,'run',stop_grace_seconds=.03)
  gov=holder['gov'];workers=[t for t in threading.enumerate() if t.name=='http-supervised']
  timers={k:getattr(gov,k) is None for k in ('_deadline_timer','_escalate_timer','_force_exit_timer')}
  assert rc==3 and started.is_set() and workers and all(timers.values()) and len(gov._inflight)==1
  emit('measure_returns_and_cancels_backstop_with_pending_transport',exit=rc,live_http_threads=len(workers),inflight=len(gov._inflight),timers_removed=timers,state=doc['results'][0]['state'])
 finally:
  release.set()
  for t in [t for t in threading.enumerate() if t.name=='http-supervised']:t.join(1)
  if 'gov' in holder:holder['gov'].close()
 assert not any(t.name=='http-supervised' for t in threading.enumerate()) and len(holder['gov']._inflight)==1
 emit('finished_abandoned_transport_still_registered',live_http_threads=0,inflight=len(holder['gov']._inflight))
# Real kernel pipe behavior in child only. A full blocking stderr stalls the "unconditional" exit.
code=r'''
import os,time,sys
import evidence as E
r,w=os.pipe()
os.set_blocking(w,False)
try:
 while True:os.write(w,b'x'*4096)
except BlockingIOError:pass
os.set_blocking(w,True)
os.dup2(w,2)
g=E.ResourceGovernor(grace_seconds=.02,escalate_after=.02,force_exit_after=.02,on_escalate=lambda x:None)
g.register_inflight(lambda:None)
g.request_stop('controlled_stuck')
time.sleep(.4)
print('SURVIVED_PAST_FORCED_EXIT',flush=True)
os._exit(9)
'''
p=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=3)
assert p.returncode==9 and 'SURVIVED_PAST_FORCED_EXIT' in p.stdout
emit('full_stderr_blocks_unconditional_hard_exit',child_exit=p.returncode,expected_governor_exit=3,output=p.stdout.strip(),governor_exit_deadline_s=.06,observed_survival_s=.4)
Path(__file__).with_name('observations.json').write_text(json.dumps(out,indent=2))
