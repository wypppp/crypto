#!/usr/bin/env python3
"""Fetch only S0 v1.2 smoke audit fields, within a 5-credit export cap."""
import csv
import gzip
import json
import urllib.parse
from pathlib import Path

from fetch_s0_v1_2 import api_key, get

QUERY_ID = 8844536
EXECUTION_ID = "01M3HD97S93VA2NYMN67NBRT0B"
ROW_COUNT = 773
MAX_BYTES = 250_000  # 5 credits at the conservative old rate of 20 credits/MB.
PAGE_SIZE = 50
COLS = [
    "mint", "mint_hash_exact", "eligible", "tail10_exec", "tail420_candidate",
    "r0_seen", "t3_s", "e5_x", "e5_y", "e5_fee_bps", "max_sell_30d",
    "has_migration_event", "amm_mapped", "mapped_pool_reversed", "trades_t3",
    "n_post_entry_trades", "n_all", "n_eligible", "n_tail10_exec",
    "n_tail420_candidate", "n_tail10_outside_tail420", "n_random_2pct",
    "n_migration_event", "n_amm_mapped", "n_migration_unmapped",
    "n_mapped_reverse_pool",
]


def main():
    key = api_key()
    rows = []
    bytes_fetched = 0
    for offset in range(0, ROW_COUNT, PAGE_SIZE):
        q = urllib.parse.urlencode({
            "limit": min(PAGE_SIZE, ROW_COUNT - offset),
            "offset": offset,
            "columns": ",".join(COLS),
        })
        response = get(f"/query/{QUERY_ID}/results?{q}", key)
        if response.get("execution_id") != EXECUTION_ID:
            raise RuntimeError("latest query execution changed; stop")
        result = response.get("result") or {}
        page = result.get("rows") or []
        if len(page) != min(PAGE_SIZE, ROW_COUNT - offset):
            raise RuntimeError(f"short page at {offset}: {len(page)}")
        if any(set(row) != set(COLS) for row in page):
            raise RuntimeError("column mismatch")
        page_bytes = int((result.get("metadata") or {}).get("result_set_bytes") or 0)
        if not page_bytes or bytes_fetched + page_bytes > MAX_BYTES:
            raise RuntimeError(f"export bound exceeded at {offset}: {bytes_fetched + page_bytes}")
        bytes_fetched += page_bytes
        rows.extend(page)
        print(f"offset={offset} fetched={len(rows)} bytes={bytes_fetched}", flush=True)

    if len(rows) != ROW_COUNT or len({row["mint"] for row in rows}) != ROW_COUNT:
        raise RuntimeError("missing or duplicate rows")
    out = Path(__file__).resolve().parent / "raw/s0/S0_SMOKE_v1_2_audit_columns.csv.gz"
    with gzip.open(out, "wt", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(rows)
    meta = {
        "query_id": QUERY_ID,
        "execution_id": EXECUTION_ID,
        "rows": len(rows),
        "columns": COLS,
        "sum_result_set_bytes": bytes_fetched,
        "conservative_export_upper_bound_credits": bytes_fetched * 20 / 1_000_000,
    }
    out.with_name("S0_SMOKE_v1_2_audit_columns_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    )
    print("saved", out, flush=True)


if __name__ == "__main__":
    main()
