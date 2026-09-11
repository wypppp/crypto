"""Recheck actual hard exit with child-owned full stderr; never fills parent stderr."""
import sys,subprocess,json
from pathlib import Path
code=r'''
import os,time
import evidence as E
r,w=os.pipe();os.set_blocking(w,False)
try:
 while True:os.write(w,b'x'*4096)
except BlockingIOError:pass
os.set_blocking(w,True);os.dup2(w,2)
g=E.ResourceGovernor(grace_seconds=.02,escalate_after=.02,force_exit_after=.02,on_escalate=lambda x:None)
g.register_inflight(lambda:None);g.request_stop('controlled_stuck')
time.sleep(.4)
print('SURVIVED_PAST_FORCED_EXIT',flush=True)
os._exit(9)
'''
p=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=3)
assert p.returncode==3 and 'SURVIVED' not in p.stdout
r=dict(exit=p.returncode,survived=False);print(json.dumps(r));Path(__file__).with_name('exit_observation.json').write_text(json.dumps(r,indent=2))
