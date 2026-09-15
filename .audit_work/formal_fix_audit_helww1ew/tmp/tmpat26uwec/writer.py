
import sys, time
sys.path.insert(0, '/home/ancillary/.audit_work/formal_fix_audit_helww1ew/baseline_work_20260910')
import evidence as E
log = E.EvidenceLog('/home/ancillary/.audit_work/formal_fix_audit_helww1ew/tmp/tmpat26uwec/e2.jsonl')
log.write("run_header", note="before work")
i = 0
while True:
    log.write("rpc", candidate=i, stage="loop", record={"id": i})
    i += 1
    time.sleep(0.05)
