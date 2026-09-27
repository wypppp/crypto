#!/usr/bin/env python3
"""Verify and safely fetch an S0 v1.2 result through Dune's query endpoint."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
ROOT = H.parents[2]
API = "https://api.dune.com/api/v1"


def api_key() -> str:
    m = re.search(
        r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)",
        (ROOT / ".env").read_text(), re.M,
    )
    if not m:
        raise RuntimeError("DUNE_API_KEY not found")
    return m.group(1)


def get(path: str, key: str) -> dict:
    req = urllib.request.Request(API + path, headers={"X-Dune-API-Key": key})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.load(response)
        except OSError:
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def normalized_sql(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(";")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query_id", type=int)
    ap.add_argument("execution_id")
    ap.add_argument("--sql", type=Path, required=True)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--datapoints-per-credit", type=float)
    ap.add_argument("--max-export-credits", type=float, default=100.0)
    ap.add_argument("--out", type=Path, default=H / "raw/s0/S0_AB_v1_2.csv.gz")
    args = ap.parse_args()
    key = api_key()
    raw_dir = H / "raw/s0"
    raw_dir.mkdir(parents=True, exist_ok=True)

    query = get(f"/query/{args.query_id}", key)
    saved_sql = query.get("query_sql") or query.get("sql") or ""
    if normalized_sql(saved_sql) != normalized_sql(args.sql.read_text()):
        raise RuntimeError("Dune saved SQL differs from the specified frozen file")

    status = get(f"/execution/{args.execution_id}/status", key)
    label = args.out.name
    for suffix in (".gz", ".csv"):
        if label.endswith(suffix):
            label = label[:-len(suffix)]
    (raw_dir / f"{label}_query.json").write_text(json.dumps(query, ensure_ascii=False, indent=2))
    (raw_dir / f"{label}_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2))
    meta = status.get("result_metadata") or {}
    rows = int(meta.get("total_row_count") or meta.get("row_count") or 0)
    size = int(meta.get("total_result_set_bytes") or meta.get("result_set_bytes") or 0)
    cols = len(meta.get("column_names") or meta.get("columns") or [])
    direct_points = int(meta.get("datapoint_count") or 0)
    points = max(direct_points, rows * cols if rows and cols else 0, math.ceil(size / 100) if size else 0)
    report = {
        "query_id": args.query_id,
        "execution_id": args.execution_id,
        "state": status.get("state"),
        "rows": rows,
        "columns": cols,
        "bytes": size,
        "estimated_datapoints": points,
        "execution_cost_credits": status.get("execution_cost_credits"),
    }
    if args.datapoints_per_credit and points:
        report["estimated_export_credits"] = points / args.datapoints_per_credit
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.download:
        print("metadata only; download requires the current plan's data-points/credit rate")
        return
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise RuntimeError("execution not completed")
    if not args.datapoints_per_credit or args.datapoints_per_credit <= 0:
        raise RuntimeError("download requires --datapoints-per-credit")
    projected = points / args.datapoints_per_credit
    if projected * 1.10 > args.max_export_credits:
        raise RuntimeError(
            f"projected export {projected:.3f} credits (+10% buffer) exceeds cap "
            f"{args.max_export_credits}; no result page requested"
        )

    header = None
    actual = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", newline="") as dst:
        writer = None
        for offset in range(0, rows, 1000):
            qs = urllib.parse.urlencode({"limit": 1000, "offset": offset})
            page = get(f"/query/{args.query_id}/results?{qs}", key)
            if page.get("execution_id") != args.execution_id:
                raise RuntimeError("query endpoint no longer points to the requested execution")
            batch = (page.get("result") or {}).get("rows") or []
            if batch and header is None:
                header = list(batch[0])
                writer = csv.DictWriter(dst, fieldnames=header)
                writer.writeheader()
            if batch and list(batch[0]) != header:
                raise RuntimeError("result columns changed between pages")
            writer.writerows(batch)
            actual += len(batch)
    if actual != rows:
        raise RuntimeError(f"expected {rows} rows, downloaded {actual}")
    print("saved", args.out, "rows", actual)


if __name__ == "__main__":
    main()
