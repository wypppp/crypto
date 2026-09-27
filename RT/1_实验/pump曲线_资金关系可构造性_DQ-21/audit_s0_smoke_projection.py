#!/usr/bin/env python3
"""Audit the cost-bounded S0 v1.2 smoke projection without outcome inference."""
import csv
import gzip
import json
from pathlib import Path

from xxhash64_local import dune_mint_hash

H = Path(__file__).resolve().parent
SOURCE = H / "raw/s0/S0_SMOKE_v1_2_audit_columns.csv.gz"
EXPECTED_T3 = {
    "9RWbXv3hCdmEpkqwb659JCvnVes6XLhvpXB7oYxjpump": 0,
    "2r9x15QN6obFdUPGKmv98x99N4PAYKsL7xg8Ug2Spump": 0,
    "D826xNm4gC9L97UjnFjpbsZoUXAKdEWXukyfdA4Apump": 0,
    "YxUstMyYDyqPNz78auhYfhdUKrBQgg7uctnKNDEpump": 0,
    "57L67vSKy6fkDNjwncNx6UX1BQnWCsc1a4hcWYyhpump": 0,
    "B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump": 0,
    "GB2t2Hs2Awo4YAafTL7PzYafQJ75CkPCLCEnWoD8pump": 0,
    "DEAVE9fyfQDk3fDLspnEv7y7dTGErezq2FFrp6B2pump": 0,
    "ARYoDE9aaS4u7N3xfRysHwSAbY3bVFGHq5eGi3NuyYM6": 2,
    "35Ki5P8TWL6VwhCXJ3RZMQb1HKV3xfSfiqjtYBBapump": 2,
    "2cgAW8un1eE2xN99PTs4NJyFYXA4pzqUEQTJbiuowgcn": 3,
    "E2sHHwpzeVjhV3DjAMP8kYBeG27qT66xS3V9EBYVpump": 4,
    "EYEyyarU2mpWCTjEU5j2ezk2QEvCcr6SFMukc7Vjpump": 135,
}


def yes(value):
    return str(value).lower() in {"true", "1"}


def main():
    with gzip.open(SOURCE, "rt", newline="") as src:
        rows = list(csv.DictReader(src))
    by_mint = {r["mint"]: r for r in rows}
    assert len(rows) == len(by_mint) == 773
    counts = {}
    for key in (
        "n_all", "n_eligible", "n_tail10_exec", "n_tail420_candidate",
        "n_tail10_outside_tail420", "n_random_2pct", "n_migration_event",
        "n_amm_mapped", "n_migration_unmapped", "n_mapped_reverse_pool",
    ):
        values = {int(r[key]) for r in rows}
        assert len(values) == 1, (key, values)
        counts[key] = values.pop()
    assert counts == {
        "n_all": 28845, "n_eligible": 11068, "n_tail10_exec": 122,
        "n_tail420_candidate": 557, "n_tail10_outside_tail420": 0,
        "n_random_2pct": 220, "n_migration_event": 210,
        "n_amm_mapped": 210, "n_migration_unmapped": 0,
        "n_mapped_reverse_pool": 0,
    }
    assert sum(yes(r["tail420_candidate"]) for r in rows) == 557
    assert sum(yes(r["tail10_exec"]) for r in rows) == 122
    assert sum(yes(r["eligible"]) and int(r["mint_hash_exact"]) % 10000 < 200 for r in rows) == 220
    for r in rows:
        h = int(r["mint_hash_exact"])
        assert h == dune_mint_hash(r["mint"]), r["mint"]
        included = yes(r["r0_seen"]) or (
            yes(r["eligible"]) and (
                yes(r["tail420_candidate"]) or yes(r["tail10_exec"]) or h % 10000 < 200
            )
        )
        assert included, r["mint"]
        if yes(r["eligible"]):
            assert float(r["e5_x"]) > 0 and float(r["e5_y"]) > 0
    for mint, t3 in EXPECTED_T3.items():
        assert int(by_mint[mint]["t3_s"]) == t3, mint
    b1 = by_mint["B1C2xfcUajAAU8n3zfuXqXvvALRw8cB5sPzNB5ktpump"]
    b1_events = int(b1["trades_t3"]) + int(b1["n_post_entry_trades"])
    assert b1_events == 7771
    assert yes(b1["has_migration_event"]) and yes(b1["amm_mapped"])
    assert sum(yes(r["r0_seen"]) for r in rows) == 15
    result = {
        "source": str(SOURCE.relative_to(H)), "rows": len(rows),
        "counts": counts, "exact_hashes_checked": len(rows),
        "prior_t3_checked": len(EXPECTED_T3), "b1c2_events": b1_events,
        "r0_qa_rows": 15, "data_verdict": "PASS",
        "execution_cost_verdict": "FAIL_10_CREDIT_CAP",
    }
    dest = H / "raw/s0/S0_SMOKE_v1_2_projection_audit.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
