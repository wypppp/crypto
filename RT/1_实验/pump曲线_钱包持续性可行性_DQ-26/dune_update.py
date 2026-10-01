#!/usr/bin/env python3
"""DQ-26：复用一个已完成且结果已下载的私有查询槽位（试用账户私有查询数已满），把本地 SQL 原样写入并回读核对。

python dune_update.py QUERY_ID SQL_FILE NAME → 记录追加到 raw/created_queries.jsonl（reused_slot＝true）
DUNE_API_KEY 按键名从工作区 .env 读取，不打印、不写出。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from dune_create import H, call


def main() -> None:
    qid, path, name = int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    old = call("GET", f"/query/{qid}")
    assert old.get("is_private"), "只复用私有查询"
    sql = path.read_text()
    sha = hashlib.sha256(sql.encode()).hexdigest()
    call("PATCH", f"/query/{qid}", {"name": name, "query_sql": sql})
    back = call("GET", f"/query/{qid}")
    same = hashlib.sha256(back["query_sql"].encode()).hexdigest() == sha
    rec = {
        "query_id": qid,
        "name": name,
        "file": path.name,
        "sha256": sha,
        "saved_equal": same,
        "is_private": back.get("is_private"),
        "reused_slot": True,
        "previous_name": old.get("name"),
        "previous_sql_sha256": hashlib.sha256(old["query_sql"].encode()).hexdigest(),
    }
    with open(H / "raw" / "created_queries.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))
    assert same


if __name__ == "__main__":
    main()
