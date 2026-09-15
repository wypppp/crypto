import subprocess,json,re,hashlib,time
from pathlib import Path
D=Path(__file__).resolve().parent
W=Path('/home/ancillary/rightTail/baseline_work_20260910')
results=[]
for name in ['evidence','first_mint','step3','step4','e2e_blocking','resume','parallel','audit_fixes','audit_followup','realchain_tools']:
 t=time.monotonic();cmd=['python3','test_'+name+'.py']
 try:
  p=subprocess.run(cmd,cwd=W,capture_output=True,text=True,timeout=420)
  out=p.stdout+p.stderr;rc=p.returncode
 except subprocess.TimeoutExpired as e:
  out='AUDIT TIMEOUT\n'+str(e.stdout or '')+str(e.stderr or '');rc=124
 (D/('test_'+name+'.log')).write_text(out)
 matches=re.findall(r'通过\s*(\d+)\s*/\s*失败\s*(\d+)',out)
 row=dict(entry=name,cmd=cmd,exit=rc,elapsed_s=round(time.monotonic()-t,2),counts=list(map(int,matches[-1])) if matches else None)
 results.append(row);(D/'tests.json').write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)
start=json.loads((D/'hashes_start.json').read_text());end={n:hashlib.sha256((W/n).read_bytes()).hexdigest() for n in start}
(D/'hashes_end.json').write_text(json.dumps(end,indent=2));assert start==end
print('DONE',flush=True)
