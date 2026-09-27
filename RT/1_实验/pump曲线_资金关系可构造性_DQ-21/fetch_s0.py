#!/usr/bin/env python3
"""Inspect a finished Dune S0 execution and download it only below the frozen size cap."""
from __future__ import annotations

import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
ROOT = H.parents[2]
API = "https://api.dune.com/api/v1"
m = re.search(r"^\s*DUNE_API_KEY\s*=\s*['\"]?([^'\"\s]+)", (ROOT / ".env").read_text(), re.M)
if not m:
    raise RuntimeError("DUNE_API_KEY not found")
KEY = m.group(1)
MAX_BYTES = 5_000_000


def get(path):
    req = urllib.request.Request(API + path, headers={"X-Dune-API-Key": KEY})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.read()
        except OSError:
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: fetch_s0.py EXECUTION_ID")
    eid = sys.argv[1]
    raw = H / "raw" / "s0"
    raw.mkdir(parents=True, exist_ok=True)
    status = json.loads(get(f"/execution/{eid}/status"))
    (raw / "S0_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2))
    meta = status.get("result_metadata") or {}
    rows = int(meta.get("total_row_count") or meta.get("row_count") or 0)
    size = int(meta.get("result_set_bytes") or 0)
    print("state", status.get("state"), "rows", rows, "bytes", size,
          "credits", status.get("execution_cost_credits"))
    if status.get("state") != "QUERY_STATE_COMPLETED":
        return
    if not size or size > MAX_BYTES:
        raise RuntimeError(f"result {size} bytes exceeds frozen 5 MB download cap")

    out = raw / "S0_AB.csv.gz"
    header = None
    actual = 0
    with gzip.open(out, "wt", newline="") as dst:
        writer = None
        for offset in range(0, rows, 1000):
            q = urllib.parse.urlencode({"limit": 1000, "offset": offset})
            page = get(f"/execution/{eid}/results/csv?{q}").decode()
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
    print("saved", out, "rows", actual)


if __name__ == "__main__":
    main()

