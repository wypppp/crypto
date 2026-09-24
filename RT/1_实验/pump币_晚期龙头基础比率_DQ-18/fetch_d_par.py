"""并行、可续传地下载 D 段各块结果（分页缓存在 raw/s2/<label>_pages，完成后移到 raw/d/）。"""
import json, subprocess, shutil, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
eids = json.load(open("raw/d/eids.json"))
def job(label):
    for attempt in range(20):
        if Path(f"raw/d/{label}.json").exists():
            return label, "done"
        r = subprocess.run(["python3", "get_s2_dune.py", eids[label], label, "60"], capture_output=True, text=True)
        if Path(f"raw/s2/{label}.json").exists():
            shutil.move(f"raw/s2/{label}.json", f"raw/d/{label}.json")
            if Path(f"raw/s2/{label}_status.json").exists():
                shutil.move(f"raw/s2/{label}_status.json", f"raw/d/{label}_status.json")
            shutil.rmtree(f"raw/s2/{label}_pages", ignore_errors=True)
            return label, "ok"
        print(label, "retry", attempt, (r.stderr or r.stdout)[-160:], flush=True)
        time.sleep(10)
    return label, "fail"
todo = [l for l in eids if not Path(f"raw/d/{l}.json").exists()]
with ThreadPoolExecutor(6) as ex:
    for res in ex.map(job, todo):
        print(res, flush=True)
