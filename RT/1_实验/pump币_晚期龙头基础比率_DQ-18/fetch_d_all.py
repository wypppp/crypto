import json,re,urllib.request,subprocess,shutil
from pathlib import Path
KEY=re.search(r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)",Path('/home/ancillary/.env').read_text(),re.M).group(1)
jobs={"D_202406_202407":8827664,"D_202408_202409":8827667,"D_202411":8827671,"D_202412":8827677,"D_202501":8827684,
"D_202502":8827685,"D_202503":8827687,"D_202504":8827689,"D_202505":8827695,"D_202506":8827698,"D_202507_202508":8827700,
"D_202509_202510":8827708,"D_202511_202512":8827713,"D_202601_202602":8827716,"D_202603_202604":8827717,"D_202605_202606":8827718,"D_202607_202609":8827720}
ids={}
for label,q in jobs.items():
    if Path(f"raw/d/{label}.json").exists(): print(label,"have",flush=True); continue
    d=json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.dune.com/api/v1/query/{q}/results?limit=1",headers={"X-Dune-API-Key":KEY}),timeout=120))
    eid=d['execution_id']; ids[label]=[q,eid,d['result']['metadata']['total_row_count']]
    r=subprocess.run(['python3','get_s2_dune.py',eid,label,'60'],capture_output=True,text=True)
    print(label,(r.stdout or r.stderr).strip().splitlines()[:1],flush=True)
    for suf in ('.json','_status.json'):
        if Path(f"raw/s2/{label}{suf}").exists(): shutil.move(f"raw/s2/{label}{suf}",f"raw/d/{label}{suf}")
    shutil.rmtree(f"raw/s2/{label}_pages",ignore_errors=True)
json.dump(ids,open('raw/d/exec_ids.json','w'),indent=1)
