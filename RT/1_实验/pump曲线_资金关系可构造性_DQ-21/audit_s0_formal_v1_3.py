#!/usr/bin/env python3
"""Independent identity, pilot-retention, and pre-existing R0 checks for S0."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path


H = Path(__file__).resolve().parent
R = H / "raw/s0"
FORMAL = R / "S0_AB_v1_3_audit_columns.csv.gz"
TWO_DAY = R / "S0_SMOKE_cost_2day_30d_v1_3_audit_columns.csv.gz"


def read(path: Path) -> dict[str, dict[str, str]]:
    with gzip.open(path, "rt", newline="") as src:
        rows = list(csv.DictReader(src))
    out = {row["mint"]: row for row in rows}
    assert len(out) == len(rows), f"duplicate mints in {path}"
    return out


def yes(value: str) -> bool:
    return value.lower() in ("true", "1")


def main() -> None:
    full = read(FORMAL)
    pilot = read(TWO_DAY)
    assert len(full) == 10565, len(full)
    assert len(pilot) == 1312, len(pilot)
    assert set(pilot) <= set(full), "two-day pilot mints missing"
    assert {int(r["n_all"]) for r in full.values()} == {371312}
    assert {int(r["n_all_week"]) for r in full.values() if r["cohort_week"] == "A"} == {183962}
    assert {int(r["n_all_week"]) for r in full.values() if r["cohort_week"] == "B"} == {187350}
    # 183,962 and 187,350 were computed in the older DQ-1F pipeline, not S0.
    # Thirty-day outcomes and event-time state for pilot mints must be invariant
    # when the larger creation cohort is added to the same 30-day path.
    fields = (
        "mint_hash_exact", "r0_seen", "eligible", "tail10_exec",
        "tail420_candidate", "t3_s", "e5_x", "e5_y", "e5_fee_bps",
    )
    for mint, old in pilot.items():
        new = full[mint]
        for field in fields:
            assert old[field] == new[field], (mint, field, old[field], new[field])

    for mint, row in full.items():
        if yes(row["r0_seen"]):
            continue  # QA inclusion is deliberate; its probability is not a sampling weight.
        case = yes(row["tail420_candidate"]) or yes(row["tail10_exec"])
        assert float(row["objective_inclusion_probability"]) == (1.0 if case else 0.02), (
            mint, row["objective_inclusion_probability"]
        )

    pre_s0_t3 = {
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
    for mint, seconds in pre_s0_t3.items():
        assert mint in full and yes(full[mint]["r0_seen"])
        assert int(full[mint]["t3_s"]) == seconds, mint

    out = {
        "formal_rows": len(full),
        "creation_counts_match_DQ1F": {"A": 183962, "B": 187350},
        "two_day_rows_retained": len(pilot),
        "two_day_fields_unchanged": fields,
        "non_QA_inclusion_probabilities_checked": len(full) - sum(yes(r["r0_seen"]) for r in full.values()),
        "pre_s0_t3_checks": len(pre_s0_t3),
        "verdict": "PASS_PILOT_RETENTION_AND_PRIOR_R0_TIMES",
    }
    (R / "S0_AB_v1_3_independent_audit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
