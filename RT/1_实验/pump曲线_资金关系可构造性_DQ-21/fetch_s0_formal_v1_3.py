#!/usr/bin/env python3
"""Fetch the frozen S0 formal result with a conservative 100-credit export cap."""
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
PAGE_SIZE = 100  # 41 columns × 100 rows stays below the API's per-request datapoint gate.
MAX_BYTES = 5_000_000  # 100 credits at conservative legacy 20 credits/MB.
HERE = Path(__file__).resolve().parent
OUT = HERE / "raw/s0/S0_AB_v1_3_audit_columns.csv.gz"
COLS = """mint created_at eligible tail10_exec early_crash r0_seen
mint_hash_exact objective_inclusion_probability n_all n_eligible n_tail10_exec
tail420_candidate n_tail420_candidate n_tail10_outside_tail420 n_early_crash
n_random_2pct has_migration_event amm_mapped n_migration_event n_amm_mapped
n_migration_unmapped n_mapped_reverse_pool t3_s e5_x e5_y e5_fee_bps
cohort_week t3_bucket n_all_week n_eligible_week n_eligible_week_t3_bucket
max_sell_30d max_sell_30d_e30 max_sell_30d_e120 e5_venue trades_t3
n_post_entry_trades mapped_pool_reversed max_price_pm_30d first_dd50_s
max_sell_24h""".split()


def main() -> None:
    key = api_key()
    rows = []
    total_bytes = 0
    for offset in range(0, EXPECTED_ROWS, PAGE_SIZE):
        limit = min(PAGE_SIZE, EXPECTED_ROWS - offset)
        params = urllib.parse.urlencode({
            "limit": limit, "offset": offset, "columns": ",".join(COLS)
        })
        page = get(f"/query/{QUERY_ID}/results?{params}", key)
        if page.get("execution_id") != EXECUTION_ID:
            raise RuntimeError("Dune query was overwritten; stop export")
        result = page.get("result") or {}
        batch = result.get("rows") or []
        if len(batch) != limit or any(set(row) != set(COLS) for row in batch):
            raise RuntimeError(f"unexpected result shape at offset {offset}")
        page_bytes = int((result.get("metadata") or {}).get("result_set_bytes") or 0)
        if page_bytes <= 0 or total_bytes + page_bytes > MAX_BYTES:
            raise RuntimeError(f"conservative export cap reached at {offset}: {total_bytes + page_bytes}")
        total_bytes += page_bytes
        rows.extend(batch)
        print(f"rows={len(rows)} bytes={total_bytes}", flush=True)

    if len(rows) != EXPECTED_ROWS or len({row["mint"] for row in rows}) != EXPECTED_ROWS:
        raise RuntimeError("missing or duplicate mints")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "query_id": QUERY_ID,
        "execution_id": EXECUTION_ID,
        "rows": len(rows),
        "columns": COLS,
        "sum_result_set_bytes": total_bytes,
        "conservative_export_upper_bound_credits": total_bytes * 20 / 1_000_000,
    }
    OUT.with_name("S0_AB_v1_3_audit_columns_meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )
    print("saved", OUT, flush=True)


if __name__ == "__main__":
    main()
