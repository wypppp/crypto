"""Exercise the delivered shell driver in a temporary tree; launch is a failing stub."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W=Path('/home/ancillary/rightTail/baseline_work_20260910')
with tempfile.TemporaryDirectory(prefix='rta-driver-audit-') as td:
    root=Path(td);r=root/'runs/realchain2_20260911';r.mkdir(parents=True)
    shutil.copyfile(W/'runs/realchain2_20260911/run_compare.sh',r/'run_compare.sh')
    # No credentials read and no measurement command executed.
    (r/'launch.py').write_text("import sys\nprint('CONTROLLED_PRECONDITION_FAILURE')\nsys.exit(2)\n")
    prior={'tag':'prior_attempt','exit':1,'note':'preserve this historical execution'}
    (r/'runs.jsonl').write_text(json.dumps(prior)+'\n')
    (r/'serial.stdout.log').write_text('HISTORICAL_STDOUT\n')
    (r/'serial.stderr.log').write_text('HISTORICAL_STDERR\n')
    bindir=root/'bin';bindir.mkdir()
    # Remove only deliberate inter-run waiting; the delivered driver bytes are unchanged.
    (bindir/'sleep').write_text('#!/bin/sh\nexit 0\n');(bindir/'sleep').chmod(0o755)
    env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'])
    p=subprocess.run(['bash',str(r/'run_compare.sh')],env=env,capture_output=True,text=True,timeout=15)
    runs=[json.loads(x) for x in (r/'runs.jsonl').read_text().splitlines()]
    obs=dict(driver_exit=p.returncode,child_exits=[x['exit'] for x in runs],
        prior_run_retained=any(x.get('tag')=='prior_attempt' for x in runs),
        historical_stdout_retained='HISTORICAL_STDOUT' in (r/'serial.stdout.log').read_text(),
        historical_stderr_retained='HISTORICAL_STDERR' in (r/'serial.stderr.log').read_text(),
        stdout=p.stdout,stderr=p.stderr)
    assert p.returncode==0 and obs['child_exits']==[2,2,2]
    assert not obs['prior_run_retained'] and not obs['historical_stdout_retained'] and not obs['historical_stderr_retained']
out=Path(__file__).resolve().parent
(out/'driver_observations.json').write_text(json.dumps(obs,indent=2))
print(json.dumps(obs,indent=2))
