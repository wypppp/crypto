#!/usr/bin/env python3
"""DQ-35 v2.1 体量探针（10-04）：执行一条已入库的 Dune SQL，只记台账与执行状态（行数、结果字节、费用、耗时），不下载结果。

python run_dune_meta.py <标签> <sql 文件>  → runs/<标签>_status.json，费用记 runs/dune_ledger.csv（备注“体量探针，不下载”）
不读任何数据内容，所以可以对全量（含检验周的币）估体量与费用。
"""

import csv
import json
import sys
import time

from dune_get import H, get
from run_dune import call


def main():
    lab, sql_file = sys.argv[1], sys.argv[2]
    sql = (H / sql_file).read_text()
    qid = call(
        "POST",
        "/query",
        {"name": f"DQ-35 {lab}", "query_sql": sql, "is_private": False},
    )["query_id"]
    eid = call("POST", f"/query/{qid}/execute", {"performance": "large"})[
        "execution_id"
    ]
    while True:
        st = get(f"/execution/{eid}/status")
        if st["state"] not in ("QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING"):
            break
        time.sleep(15)
    cost = st.get("execution_cost_credits")
    with open(H / "runs" / "dune_ledger.csv", "a", newline="") as f:
        csv.writer(f).writerow(
            [qid, sql_file, eid, st["state"], cost, "", "公开查询；体量探针，不下载"]
        )
    (H / "runs" / f"{lab}_status.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2)
    )
    meta = st.get("result_metadata") or {}
    print(
        lab,
        qid,
        st["state"],
        cost,
        meta.get("total_row_count"),
        meta.get("result_set_bytes"),
        flush=True,
    )


if __name__ == "__main__":
    main()
