#!/usr/bin/env python3
"""Compare the v1.3 full-horizon cost pilot with its one-day-path smoke."""
import csv
import gzip
import json
from pathlib import Path

from audit_s0_smoke_projection import EXPECTED_T3, yes
from xxhash64_local import dune_mint_hash

H = Path(__file__).resolve().parent


def read(label):
    path = H / f"raw/s0/S0_SMOKE_{label}_audit_columns.csv.gz"
    with gzip.open(path, "rt", newline="") as src:
        rows = list(csv.DictReader(src))
    by_mint = {r["mint"]: r for r in rows}
    assert len(rows) == len(by_mint)
    return by_mint


def main():
    short = read("v1_3")
    full = read("cost_30d_v1_3")
    assert len(short) == 685 and len(full) == 695
    expected = {
        "n_all": 28845, "n_eligible": 11068,
        "n_tail10_exec": 138, "n_tail420_candidate": 478,
        "n_tail10_outside_tail420": 0, "n_random_2pct": 220,
        "n_migration_event": 220, "n_amm_mapped": 220,
        "n_migration_unmapped": 0, "n_mapped_reverse_pool": 0,
    }
    for field, target in expected.items():
        assert {int(r[field]) for r in full.values()} == {target}, field
    for mint, r in full.items():
        h = int(r["mint_hash_exact"])
        assert h == dune_mint_hash(mint), mint
        assert yes(r["r0_seen"]) or (
            yes(r["eligible"]) and (
                yes(r["tail420_candidate"]) or yes(r["tail10_exec"]) or h % 10000 < 200
            )
        ), mint
    assert sum(yes(r["tail420_candidate"]) for r in full.values()) == 478
    assert sum(yes(r["tail10_exec"]) for r in full.values()) == 138
    assert sum(yes(r["eligible"]) and int(r["mint_hash_exact"]) % 10000 < 200 for r in full.values()) == 220
    for mint, t3 in EXPECTED_T3.items():
        assert int(full[mint]["t3_s"]) == t3
    overlap = set(short) & set(full)
    for mint in overlap:
        for field in ("t3_s", "trades_t3", "e5_x", "e5_y", "e5_fee_bps"):
            assert short[mint][field] == full[mint][field], (mint, field)
    short_cases = {m for m, r in short.items() if yes(r["tail420_candidate"])}
    full_cases = {m for m, r in full.items() if yes(r["tail420_candidate"])}
    assert short_cases <= full_cases and len(full_cases - short_cases) == 12
    result = {
        "short_rows": len(short), "full_rows": len(full),
        "exact_counts": expected, "hashes_checked": len(full),
        "prior_t3_checked": len(EXPECTED_T3),
        "shared_entry_states_checked": len(overlap),
        "new_30d_cases": len(full_cases - short_cases),
        "verdict": "PASS_TECHNICAL_COST_PILOT",
    }
    dest = H / "raw/s0/S0_COST_30D_v1_3_audit.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
