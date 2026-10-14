"""DQ-29：流式下载大结果（10-02）。dune_get.py 把全部行放在内存里，388 万行时在 7 GB 机器上被系统结束；
这里每 5 万行写一次 gzip CSV，内存只保留一块。核对规则与 dune_get.py 相同（保存的 SQL 必须与本地一致）。

python dune_get_stream.py QUERY_ID LABEL SQL_FILE --approve=<批准编号> → raw/dune/LABEL.csv.gz（先写 .part，完成后改名）
10-14 总控第六轮：下载也付费（约 2.3 credits/MB）。单独下载须有批准、受同一把互斥锁；页面失败不自动重试，直接停下。
run_dune.py 在同一条批准与同一把锁里直接调用 fetch()。
"""

import gzip
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import paid_guard as PG
from dune_get import H, get, norm, page

CHUNK, PS = 50_000, 1000


def fetch(qid, label, sql_file, ticket):
    q = get(f"/query/{qid}")
    if norm(q.get("query_sql", "")) != norm((H / sql_file).read_text()):
        raise SystemExit("Dune 上保存的 SQL 与本地冻结版本不一致，停止")
    eid = get(f"/query/{qid}/results?limit=1", ticket)["execution_id"]
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
                for p in ex.map(lambda o: page(eid, o, min(PS, n - o), ticket), offs)
                for r in p
            ]
            # 可空整数列保留 Python int；默认 dtype 会转浮点，写成 .0 并可能丢低位。
            df = pd.DataFrame(rows, columns=cols, dtype=object)
            df.to_csv(fh, index=False, header=(c0 == 0))
            done += len(df)
            print(time.strftime("%H:%M:%S"), "rows", done, "/", n, flush=True)
    if done != n:
        raise RuntimeError(f"expected {n} rows, got {done}")
    part.rename(raw / f"{label}.csv.gz")
    print("saved", raw / f"{label}.csv.gz", done, flush=True)


def main():
    a = sys.argv[1:]
    opt = {
        x.split("=")[0]: x.split("=", 1)[1]
        for x in a
        if x.startswith("--") and "=" in x
    }
    qid, label, sql_file = [x for x in a if not x.startswith("--")][:3]
    if "--approve" not in opt:
        raise SystemExit("下载也付费：没有 --approve=<批准编号>，不下载")
    ticket = PG.check(opt["--approve"], sql_file)
    with PG.one_at_a_time(ticket):
        PG.mark_used(opt["--approve"], "下载 query %s" % qid, "下载")
        fetch(qid, label, sql_file, ticket)


if __name__ == "__main__":
    main()
