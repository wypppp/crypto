#!/usr/bin/env python3
"""DQ-35：执行一条已入库的 Dune SQL（公开查询）→ 台账 → 流式下载（10-02；同 DQ-34 hl_dune.py）。
python run_dune.py <标签> <sql 文件>；结果 raw/dune/<标签>.csv.gz，费用记 runs/dune_ledger.csv。
单条预计 >100 credits 的查询须先经用户批准，不在这里跑；实际费用 >100 时打印警告。
"""

import csv
import json
import subprocess
import sys
import time
import urllib.request

from dune_get import API, H, KEY, get


def call(method: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        method=method,
        headers={"X-Dune-API-Key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def main() -> None:
    label, sql_file = sys.argv[1], sys.argv[2]
    sql = (H / sql_file).read_text()
    qid = call(
        "POST",
        "/query",
        {"name": f"DQ-35 {label}", "query_sql": sql, "is_private": False},
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
        csv.writer(f).writerow([qid, sql_file, eid, st["state"], cost, "", "公开查询"])
    print(label, qid, st["state"], cost, flush=True)
    if st["state"] != "QUERY_STATE_COMPLETED":
        print(json.dumps(st.get("error"), ensure_ascii=False), flush=True)
        sys.exit(1)
    if cost is not None and float(cost) > 100:
        print("警告：单条费用超过审批阈值 100", flush=True)
    subprocess.run(
        [sys.executable, "dune_get_stream.py", str(qid), label, sql_file],
        cwd=H,
        check=True,
    )


if __name__ == "__main__":
    main()
