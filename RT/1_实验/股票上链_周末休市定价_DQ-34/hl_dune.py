#!/usr/bin/env python3
"""DQ-34：执行一条已入库的 Dune SQL（公开查询）→ 台账 → 流式下载（10-02）。
python hl_dune.py <标签> <sql 文件>；结果 raw/dune/<标签>.csv.gz，费用记 runs/dune_ledger.csv。
单条费用 >100 credits 时打印警告（审批阈值；预计 >100 的查询须先经用户批准，不在这里跑）。
"""

import subprocess
import sys
import time
from pathlib import Path

from dune_get import get
from xs_dune import H, call, ledger


def main() -> None:
    label, sql_file = sys.argv[1], sys.argv[2]
    sql = (H / sql_file).read_text()
    qid = call(
        "POST",
        "/query",
        {"name": f"DQ-34 {label}", "query_sql": sql, "is_private": False},
    )["query_id"]
    eid = call("POST", f"/query/{qid}/execute", {"performance": "large"})[
        "execution_id"
    ]
    while True:
        st = get(f"/execution/{eid}/status")
        if st["state"] not in ("QUERY_STATE_PENDING", "QUERY_STATE_EXECUTING"):
            break
        time.sleep(10)
    cost = st.get("execution_cost_credits")
    ledger([qid, str(Path(sql_file)), eid, st["state"], cost, "", "公开查询"])
    print(label, qid, st["state"], cost, flush=True)
    if st["state"] != "QUERY_STATE_COMPLETED":
        print(st, flush=True)
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
