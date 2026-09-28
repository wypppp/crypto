#!/usr/bin/env python3
"""Download only the verified S1 one-day execution; never execute SQL."""
from __future__ import annotations

import csv
import gzip
import argparse
import hashlib
import json
import urllib.parse
from pathlib import Path

from fetch_s0_v1_2 import api_key, get, normalized_sql

HERE = Path(__file__).resolve().parent
QUERY_ID = 8844536
EXECUTION_ID = "01M3K2Q7GZ38N0507QH57WPM5H"
SQL = HERE / "sql/S1_SMOKE_20260601_固定退出基础回收_待验.sql"
OUT = HERE / "raw/s1/S1_SMOKE_20260601.csv.gz"
MAX_RESULT_BYTES = 500_000
PAGE_SIZE = 50  # Keep each request below the account's per-request datapoint gate.


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query-id", type=int, default=QUERY_ID)
    ap.add_argument("--execution-id", default=EXECUTION_ID)
    ap.add_argument("--sql", type=Path, default=SQL)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--expected-rows", type=int, default=695)
    args = ap.parse_args()
    key = api_key()
    query = get(f"/query/{args.query_id}", key)
    if normalized_sql(query.get("query_sql") or "") != normalized_sql(args.sql.read_text()):
        raise RuntimeError("saved query SQL differs from local smoke file")
    status = get(f"/execution/{args.execution_id}/status", key)
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise RuntimeError(f"unexpected state {status.get('state')}")
    meta = status.get("result_metadata") or {}
    n = int(meta.get("total_row_count") or 0)
    columns = meta.get("column_names") or []
    size = int(meta.get("total_result_set_bytes") or 0)
    if n != args.expected_rows or not columns or size <= 0 or size > max(MAX_RESULT_BYTES, n * 1024):
        raise RuntimeError(f"unexpected result shape: {n} rows, {len(columns)} cols, {size} bytes")

    rows = []
    for offset in range(0, n, PAGE_SIZE):
        limit = min(PAGE_SIZE, n - offset)
        qs = urllib.parse.urlencode({"limit": limit, "offset": offset})
        print(f"fetching offset={offset} limit={limit}", flush=True)
        page = get(f"/query/{args.query_id}/results?{qs}", key)
        if page.get("execution_id") != args.execution_id:
            raise RuntimeError("latest result no longer points to verified smoke execution")
        batch = (page.get("result") or {}).get("rows") or []
        if len(batch) != limit:
            raise RuntimeError(f"incomplete page at {offset}")
        rows.extend(batch)
    if len({r["mint"] for r in rows}) != n:
        raise RuntimeError("duplicate or missing mint")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    audit = {
        "query_id": args.query_id, "execution_id": args.execution_id,
        "execution_cost_credits": status.get("execution_cost_credits"),
        "rows": n, "columns": len(columns), "result_bytes": size,
        "file": str(args.out),
        "download_sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
    }
    args.out.with_name(args.out.name.replace(".csv.gz", "_meta.json")).write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
