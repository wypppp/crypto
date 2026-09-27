#!/usr/bin/env python3
"""Inspect S0 v1.1 first; download only under an explicit data-point budget."""
from __future__ import annotations

import argparse
import csv
import gzip
import io
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
    env = ROOT / ".env"
    m = re.search(r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)", env.read_text(), re.M)
    if not m:
        raise RuntimeError("DUNE_API_KEY not found")
    return m.group(1)


def get(path: str, key: str) -> bytes:
    req = urllib.request.Request(API + path, headers={"X-Dune-API-Key": key})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.read()
        except OSError:
            if attempt == 5:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def column_count(meta: dict) -> int:
    for name in ("column_names", "columns"):
        value = meta.get(name)
        if isinstance(value, list):
            return len(value)
    value = meta.get("column_count")
    return int(value or 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("execution_id")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--datapoints-per-credit", type=float)
    ap.add_argument("--max-export-credits", type=float, default=100.0)
    ap.add_argument("--out", type=Path, default=H / "raw" / "s0" / "S0_AB_v1_1.csv.gz")
    args = ap.parse_args()
    key = api_key()
    raw_dir = H / "raw" / "s0"
    raw_dir.mkdir(parents=True, exist_ok=True)
    status = json.loads(get(f"/execution/{args.execution_id}/status", key))
    (raw_dir / "S0_v1_1_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2))
    meta = status.get("result_metadata") or {}
    rows = int(meta.get("total_row_count") or meta.get("row_count") or 0)
    size = int(meta.get("total_result_set_bytes") or meta.get("result_set_bytes") or 0)
    cols = column_count(meta)
    direct_points = int(meta.get("datapoint_count") or 0)
    point_bounds = [direct_points]
    if rows and cols:
        point_bounds.append(rows * cols)
    if size:
        point_bounds.append(math.ceil(size / 100))
    points = max(point_bounds)
    report = {
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
        print("metadata only; pass --download and the console's current --datapoints-per-credit to fetch")
        return
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise RuntimeError("execution not completed")
    if not args.datapoints_per_credit or args.datapoints_per_credit <= 0:
        raise RuntimeError("download requires the current plan's positive --datapoints-per-credit")
    if not points:
        raise RuntimeError("status lacks rows/columns/bytes; cannot bound export cost")
    projected = points / args.datapoints_per_credit
    # 10% headroom covers page/header rounding; the hard comparison stays conservative.
    if projected * 1.10 > args.max_export_credits:
        raise RuntimeError(
            f"projected export {projected:.3f} credits (+10% buffer) exceeds "
            f"cap {args.max_export_credits}; no result page requested"
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    header = None
    actual = 0
    with gzip.open(args.out, "wt", newline="") as dst:
        writer = None
        for offset in range(0, rows, 1000):
            query = urllib.parse.urlencode({"limit": 1000, "offset": offset})
            page = get(f"/execution/{args.execution_id}/results/csv?{query}", key).decode()
            reader = csv.DictReader(io.StringIO(page))
            if header is None:
                header = reader.fieldnames
                writer = csv.DictWriter(dst, fieldnames=header)
                writer.writeheader()
            elif reader.fieldnames != header:
                raise RuntimeError("CSV header changed between pages")
            batch = list(reader)
            writer.writerows(batch)
            actual += len(batch)
    if actual != rows:
        raise RuntimeError(f"expected {rows} rows, downloaded {actual}")
    print("saved", args.out, "rows", actual)


if __name__ == "__main__":
    main()
