#!/usr/bin/env python3
"""Check that the two-day cost run preserves every one-day cohort result."""
import csv
import gzip
import json
from pathlib import Path

from xxhash64_local import dune_mint_hash

H = Path(__file__).resolve().parent


def read(label):
    p = H / f"raw/s0/S0_SMOKE_{label}_audit_columns.csv.gz"
    with gzip.open(p, "rt", newline="") as src:
        rows = list(csv.DictReader(src))
    by_mint = {r["mint"]: r for r in rows}
    assert len(rows) == len(by_mint)
    return by_mint


def yes(value):
    return str(value).lower() in ("true", "1")


def main():
    one = read("cost_30d_v1_3")
    two = read("cost_2day_30d_v1_3")
    assert len(one) == 695 and len(two) == 1312
    assert set(one) <= set(two)
    expected = {
        "n_all": 56134, "n_eligible": 21162,
        "n_tail10_exec": 248, "n_tail420_candidate": 898,
        "n_random_2pct": 420, "n_migration_event": 410,
        "n_amm_mapped": 410, "n_migration_unmapped": 0,
    }
    for field, target in expected.items():
        assert {int(r[field]) for r in two.values()} == {target}, field
    fields = (
        "mint_hash_exact", "r0_seen", "eligible", "tail10_exec",
        "tail420_candidate", "t3_s", "e5_x", "e5_y", "e5_fee_bps",
    )
    for mint, old in one.items():
        new = two[mint]
        for field in fields:
            assert old[field] == new[field], (mint, field)
    for mint, row in two.items():
        h = int(row["mint_hash_exact"])
        assert h == dune_mint_hash(mint), mint
        assert yes(row["r0_seen"]) or (
            yes(row["eligible"]) and (
                yes(row["tail10_exec"]) or yes(row["tail420_candidate"]) or h % 10000 < 200
            )
        ), mint
    assert sum(yes(r["tail10_exec"]) for r in two.values()) == 248
    assert sum(yes(r["tail420_candidate"]) for r in two.values()) == 898
    assert not any(yes(r["tail10_exec"]) and not yes(r["tail420_candidate"]) for r in two.values())
    assert sum(yes(r["eligible"]) and int(r["mint_hash_exact"]) % 10000 < 200 for r in two.values()) == 420
    result = {
        "one_day_rows_retained": len(one), "two_day_rows": len(two),
        "exact_counts": expected, "hashes_checked": len(two),
        "one_day_fields_unchanged": list(fields),
        "verdict": "PASS_TECHNICAL_COST_CALIBRATION",
    }
    target = H / "raw/s0/S0_COST_2DAY_30D_v1_3_audit.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
