#!/usr/bin/env python3
"""Fetch a narrow projection of the frozen S0 result; no query execution."""
from __future__ import annotations

import csv
import gzip
import json
import urllib.parse
from pathlib import Path

from fetch_s0_v1_2 import api_key, get


QUERY_ID = 8844536
EXECUTION_ID = "01M3JFX2HT1ZJJ25S4TDKAFC2J"
EXPECTED_ROWS = 10565
PAGE_SIZE = 100
# Conservative legacy proxy; actual API debit must be checked in Dune console.
MAX_BYTES = 1_500_000
COLS = [
    "mint", "price_pm_30s", "price_pm_120s", "buy_sol_t3",
    "dev_buy_sol_t3", "qbuyers_5s", "qbuyers_30s",
]
HERE = Path(__file__).resolve().parent
OUT = HERE / "raw/s0/S0_AB_v1_3_spot_drift.csv.gz"


def main() -> None:
    key = api_key()
    rows: list[dict] = []
    total_bytes = 0
    for offset in range(0, EXPECTED_ROWS, PAGE_SIZE):
        limit = min(PAGE_SIZE, EXPECTED_ROWS - offset)
        params = urllib.parse.urlencode({
            "limit": limit, "offset": offset, "columns": ",".join(COLS),
        })
        page = get(f"/query/{QUERY_ID}/results?{params}", key)
        if page.get("execution_id") != EXECUTION_ID:
            raise RuntimeError("saved Dune query was overwritten")
        result = page.get("result") or {}
        batch = result.get("rows") or []
        if len(batch) != limit or any(set(row) != set(COLS) for row in batch):
            raise RuntimeError(f"unexpected result shape at offset {offset}")
        page_bytes = int((result.get("metadata") or {}).get("result_set_bytes") or 0)
        if page_bytes <= 0 or total_bytes + page_bytes > MAX_BYTES:
            raise RuntimeError(f"projection cap reached at offset {offset}: {total_bytes + page_bytes}")
        total_bytes += page_bytes
        rows.extend(batch)
        if len(rows) % 1000 == 0 or len(rows) == EXPECTED_ROWS:
            print(f"rows={len(rows)} bytes={total_bytes}", flush=True)

    if len({row["mint"] for row in rows}) != EXPECTED_ROWS:
        raise RuntimeError("duplicate or missing mints")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(rows)
    meta = {
        "query_id": QUERY_ID, "execution_id": EXECUTION_ID,
        "rows": len(rows), "columns": COLS, "sum_result_set_bytes": total_bytes,
        "conservative_legacy_export_proxy_credits": total_bytes * 20 / 1_000_000,
        "interpretation": "Pool spot-price ratios, not model sale proceeds or net returns",
    }
    OUT.with_name("S0_AB_v1_3_spot_drift_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
