"""DQ-29：流式下载大结果（10-02）。dune_get.py 把全部行放在内存里，388 万行时在 7 GB 机器上被系统结束；
这里每 5 万行写一次 gzip CSV，内存只保留一块。核对规则与 dune_get.py 相同（保存的 SQL 必须与本地一致）。

python dune_get_stream.py QUERY_ID LABEL SQL_FILE [EXECUTION_ID] → raw/dune/LABEL.csv.gz（先写 .part，完成后改名）
10-06（DQ-35，GPT 批 1a-i 增量复核④）：给了 EXECUTION_ID 就下载这一次执行，不再取查询的“最新一次执行”，
续传与首次下载都锁定冻结的执行号；没给时行为与旧版相同。
"""

import gzip
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from dune_get import H, get, norm, page

CHUNK, PS = 50_000, 1000


def main():
    qid, label, sql_file = sys.argv[1:4]
    eid_fixed = sys.argv[4] if len(sys.argv) > 4 else None
    q = get(f"/query/{qid}")
    if norm(q.get("query_sql", "")) != norm((H / sql_file).read_text()):
        raise SystemExit("Dune 上保存的 SQL 与本地冻结版本不一致，停止")
    eid = eid_fixed or get(f"/query/{qid}/results?limit=1")["execution_id"]
    st = get(f"/execution/{eid}/status")
    raw = H / "raw" / "dune"
    (raw / f"{label}_status.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2)
    )
    meta = st.get("result_metadata") or {}
    n, cols = meta.get("total_row_count"), meta.get("column_names")
    print(
        "execution",
        eid,
        "rows",
        n,
        "cost",
        st.get("execution_cost_credits"),
        flush=True,
    )
    if st.get("state") != "QUERY_STATE_COMPLETED" or not n or not cols:
        raise SystemExit("未完成或无列名")
    part = raw / f"{label}.csv.gz.part"
    done = 0
    with gzip.open(part, "wt", newline="") as fh, ThreadPoolExecutor(4) as ex:
        for c0 in range(0, n, CHUNK):
            offs = range(c0, min(c0 + CHUNK, n), PS)
            rows = [
                r
                for p in ex.map(lambda o: page(eid, o, min(PS, n - o)), offs)
                for r in p
            ]
            df = pd.DataFrame(rows, columns=cols)
            df.to_csv(fh, index=False, header=(c0 == 0))
            done += len(df)
            print(time.strftime("%H:%M:%S"), "rows", done, "/", n, flush=True)
    if done != n:
        raise RuntimeError(f"expected {n} rows, got {done}")
    part.rename(raw / f"{label}.csv.gz")
    print("saved", raw / f"{label}.csv.gz", done, flush=True)


if __name__ == "__main__":
    main()
