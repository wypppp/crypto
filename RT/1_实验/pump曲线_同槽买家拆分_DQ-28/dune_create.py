#!/usr/bin/env python3
"""DQ-26（复制自 DQ-24）：把本地 SQL 文件原样建成 Dune 查询（不执行），并回读核对逐字节一致。

python dune_create.py SQL_FILE NAME [public] → 打印 query_id；记录追加到 raw/created_queries.jsonl
10-01 起新查询可建为公开（第三个参数 public）：SQL 本来就在公开 repo 里，公开查询不占私有查询名额。
DUNE_API_KEY 按键名从工作区 .env 读取，不打印、不写出。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
API = "https://api.dune.com/api/v1"
_m = re.search(
    r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)",
    (H.parents[2] / ".env").read_text(),
    re.M,
)
if _m is None:
    raise RuntimeError("DUNE_API_KEY not found")
KEY = _m.group(1)


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"X-Dune-API-Key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def main() -> None:
    path, name = Path(sys.argv[1]), sys.argv[2]
    private = not (len(sys.argv) > 3 and sys.argv[3] == "public")
    sql = path.read_text()
    sha = hashlib.sha256(sql.encode()).hexdigest()
    qid = call(
        "POST", "/query", {"name": name, "query_sql": sql, "is_private": private}
    )["query_id"]
    back = call("GET", f"/query/{qid}")
    same = hashlib.sha256(back["query_sql"].encode()).hexdigest() == sha
    rec = {
        "query_id": qid,
        "name": name,
        "file": path.name,
        "sha256": sha,
        "saved_equal": same,
        "is_private": back.get("is_private"),
    }
    (H / "raw").mkdir(exist_ok=True)
    with open(H / "raw" / "created_queries.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))
    assert same


if __name__ == "__main__":
    main()
