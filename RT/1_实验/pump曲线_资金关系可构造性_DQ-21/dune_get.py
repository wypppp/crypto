"""DQ-21：核对并下载一次已完成的 Dune 执行（基于 DQ-20 dune_get.py；加了 SQL 核对与并行分页）。

python dune_get.py QUERY_ID LABEL SQL_FILE [MAX_MB]
- 先取 Dune 上保存的 SQL，与本地 SQL_FILE 忽略空白后比较，不一致就停止；
- 取该查询最近一次执行的状态与费用；
- 每页 40 行，8 线程并行；402 时该页改用更小的页重取；
- 结果存 raw/dune/LABEL.csv.gz，状态存 raw/dune/LABEL_status.json。
DUNE_API_KEY 按键名从工作区 .env 读取，不打印、不写出。
"""
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
API = "https://api.dune.com/api/v1"
_m = re.search(r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)", (H.parents[2] / ".env").read_text(), re.M)
if _m is None:
    raise RuntimeError("DUNE_API_KEY not found")
KEY = _m.group(1)


def get(path):
    req = urllib.request.Request(API + path, headers={"X-Dune-API-Key": KEY})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (402, 403, 404) or attempt == 5:
                raise
            time.sleep(1 + 2 * attempt)
        except (ConnectionError, TimeoutError, OSError, http.client.HTTPException):
            if attempt == 5:
                raise
            time.sleep(1 + 2 * attempt)


def norm(sql):
    return re.sub(r"\s+", "", sql)


def page(eid, offset, n):
    try:
        return get(f"/execution/{eid}/results?limit={n}&offset={offset}")["result"]["rows"]
    except urllib.error.HTTPError as e:
        if e.code != 402 or n == 1:
            raise
        half = n // 2
        return page(eid, offset, half) + page(eid, offset + half, n - half)


def main():
    qid, label, sql_file = sys.argv[1:4]
    max_mb = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0
    q = get(f"/query/{qid}")
    same = norm(q.get("query_sql", "")) == norm((H / sql_file).read_text())
    print("saved SQL matches", sql_file, ":", same)
    if not same:
        raise SystemExit("Dune 上保存的 SQL 与本地冻结版本不一致，停止")
    eid = get(f"/query/{qid}/results?limit=1")["execution_id"]
    st = get(f"/execution/{eid}/status")
    raw = H / "raw" / "dune"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{label}_status.json").write_text(json.dumps(st, ensure_ascii=False, indent=2))
    meta = st.get("result_metadata") or {}
    n, nbytes = meta.get("total_row_count"), meta.get("result_set_bytes")
    print("execution", eid, "state", st.get("state"), "rows", n, "bytes", nbytes,
          "cost", st.get("execution_cost_credits"))
    if st.get("state") != "QUERY_STATE_COMPLETED" or n is None or nbytes is None or nbytes > max_mb * 1e6:
        raise SystemExit("未下载：未完成或超过大小上限")
    offsets = list(range(0, n, 40))
    with ThreadPoolExecutor(8) as ex:
        parts = list(ex.map(lambda o: page(eid, o, min(40, n - o)), offsets))
    rows = [r for p in parts for r in p]
    if len(rows) != n:
        raise RuntimeError(f"expected {n} rows, got {len(rows)}")
    df = pd.DataFrame(rows)
    df.to_csv(raw / f"{label}.csv.gz", index=False)
    print("saved", raw / f"{label}.csv.gz", df.shape)


if __name__ == "__main__":
    main()
