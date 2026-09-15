import contextlib, json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, os.getcwd())
import audit_flow as A, evidence as E, pilot_measure as P
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
def tmp(): return Path(tempfile.mkdtemp(prefix="rta-s26-"))
def acc(m, k, default=None): return (m or {}).get(k, default)
exec(open(sys.argv[1]).read())
print(f"\n通过 {ok} / 失败 {fail}")
