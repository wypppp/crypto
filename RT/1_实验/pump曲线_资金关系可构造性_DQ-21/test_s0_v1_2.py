#!/usr/bin/env python3
"""Semantic, sampling and DuneSQL compatibility checks for S0 v1.2."""
from pathlib import Path
import csv
import gzip
import re

from xxhash64_local import dune_mint_hash, xxh64

H = Path(__file__).resolve().parent


def main():
    # Published xxHash64 vectors and all exact hashes recovered from the v1.1 smoke.
    assert xxh64(b"") == 0xEF46DB3751D8E999
    assert xxh64(b"a") == 0xD24EC4F1A98C6E5B
    with gzip.open(H / "raw/s0/S0_SMOKE_v1_1_localhash.csv.gz", "rt", newline="") as src:
        rows = list(csv.DictReader(src))
    assert rows and all(dune_mint_hash(r["mint"]) == int(r["mint_hash"]) for r in rows)

    template = (H / "sql/S0_AB_事件时点机会普查_v1_2.sql").read_text()
    runtime = (H / "sql/S0_AB_事件时点机会普查_v1_2_运行版.sql").read_text()
    smoke = (H / "sql/S0_SMOKE_v1_2_20260601.sql").read_text()

    assert template.count("('__R0_MINT_PLACEHOLDER__')") == 1
    assert "('__R0_MINT_PLACEHOLDER__')" not in runtime
    assert "CAST(mint_hash AS varchar) AS mint_hash_exact" in template
    assert "ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING" in template
    assert "future_max_price / NULLIF(price, 0) >= 8" in template
    assert "created_at + INTERVAL '420' SECOND" in template
    assert "tail420_candidate OR tail10_exec" in template
    assert "n_tail10_outside_tail420" in template
    assert "has_migration_event" in template and "amm_mapped" in template
    assert "n_migration_unmapped" in template
    assert "base_mint = 'So11111111111111111111111111111111111111112' AS pool_reversed" in template
    assert "ORDER BY s.slot, s.txi, s.oix, s.iix, s.venue" in template
    assert "quote_amount_in_with_lp_fee" in template
    assert "COALESCE(IF(" not in template
    assert not re.search(r"FILTER\s*\([^)]*\)\s*OVER", template, re.S | re.I)
    assert template.count("\nstates AS (") == 1
    assert template.count("\namm_states AS (") == 1
    assert smoke.count("BETWEEN DATE '2026-06-01' AND DATE '2026-06-01'") == 1
    assert smoke.count("BETWEEN DATE '2026-06-01' AND DATE '2026-06-02'") == 5
    assert "INTERVAL '1' DAY" in smoke
    assert "Platform execution cap: 10 credits" in smoke
    print("S0 v1.2 invariants: OK")


if __name__ == "__main__":
    main()

