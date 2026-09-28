#!/usr/bin/env python3
"""Audit the corrected June 1 S1 pilot without treating one day as evidence."""
from __future__ import annotations

import json
import math

from analyze_s0_v1_2 import b, f
from analyze_s1_baseline import HERE, STRATEGIES, read_rows, summarize

S0 = HERE / "raw/s0/S0_AB_v1_3_audit_columns.csv.gz"
OLD = HERE / "raw/s1/S1_SMOKE_20260601.csv.gz"
NEW = HERE / "raw/s1/S1_SMOKE_20260601_corrected.csv.gz"


def same(a: str, z: str) -> bool:
    if a == z:
        return True
    try:
        return math.isclose(float(a), float(z), rel_tol=1e-12, abs_tol=1e-12)
    except (TypeError, ValueError):
        return False


def main() -> None:
    s0, old, new = read_rows(S0), read_rows(OLD), read_rows(NEW)
    expected = {mint for mint, row in s0.items() if row["created_at"][:10] == "2026-06-01"}
    if set(old) != expected or set(new) != expected or len(new) != 695:
        raise AssertionError("June 1 frozen mint set changed")

    invariant = (
        "mint_hash_exact", "created_at", "cohort_week", "t3_s", "t3_bucket",
        "eligible", "tail420_candidate", "r0_seen", "has_migration_event", "amm_mapped",
        "e5_x", "e5_y", "e5_xr", "e5_fee_bps", "e5_venue", "e5_ts", "e30_ts", "e120_ts",
    )
    for mint, row in new.items():
        for col in invariant:
            if not same(row[col], old[mint][col]):
                raise AssertionError(f"frozen field mismatch: {mint} {col}")
        prior = s0[mint]
        row["_frozen_case"] = b(prior, "tail420_candidate") or b(prior, "tail10_exec")
        old[mint]["_frozen_case"] = row["_frozen_case"]

    rows_new = [r for r in new.values() if b(r, "eligible") and not b(r, "r0_seen")]
    rows_old = [r for r in old.values() if b(r, "eligible") and not b(r, "r0_seen")]
    # These census counts are structural outputs of the old full-cohort query;
    # the return formula does not affect them. The corrected sample-first query
    # deliberately omits population-wide window functions.
    n_eligible = {int(float(r["n_eligible"])) for r in old.values()}
    if n_eligible != {11068}:
        raise AssertionError(f"unexpected June 1 eligible census: {n_eligible}")
    denominator = 11068 - sum(b(r, "eligible") and b(r, "r0_seen") for r in new.values())

    corrected = {key: summarize(rows_new, key, denominator) for key in STRATEGIES}
    previous = {key: summarize(rows_old, key, denominator) for key in STRATEGIES}
    deltas = {}
    for key in STRATEGIES:
        a = corrected[key]["population_mean_if_no_missing_HT"]
        z = previous[key]["population_mean_if_no_missing_HT"]
        deltas[key] = None if a is None or z is None else a - z

    result = {
        "scope": "technical/cost pilot for 2026-06-01 only; not A/B research evidence",
        "returns_valid": True,
        "source_query_id": 8848627,
        "source_execution_id": "01M3KHY8VKYNGJSHJY22WAQW3F",
        "execution_credits": 14.5594,
        "n_frozen_sample": len(new),
        "n_primary_sample": len(rows_new),
        "june1_exact_eligible_excluding_r0": denominator,
        "weighted_sample_total": corrected[STRATEGIES[0]]["weighted_sample_total"],
        "old_tail10_sample_count": sum(b(r, "tail10_exec") for r in old.values()),
        "corrected_tail10_sample_count": sum(b(r, "tail10_exec") for r in new.values()),
        "strategies": corrected,
        "old_minus_corrected_sign_convention": "delta values below are corrected minus old",
        "corrected_minus_old_population_mean_HT": deltas,
        "state_age_over_hold_count": {},
    }
    for delay in (5, 30, 120):
        for label, hold in (("30s", 30), ("2m", 120), ("10m", 600), ("1h", 3600)):
            col = f"state_age_d{delay}_{label}"
            ages = [f(r, col) for r in rows_new]
            result["state_age_over_hold_count"][col] = sum(v is not None and v > hold for v in ages)

    out = HERE / "raw/s1/S1_SMOKE_20260601_corrected.audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "pass": True,
        "sample_rows": len(new),
        "primary_rows": len(rows_new),
        "target": denominator,
        "weighted_sample_total": result["weighted_sample_total"],
        "tail10_old_new": [result["old_tail10_sample_count"], result["corrected_tail10_sample_count"]],
        "means_HT": {k: corrected[k]["population_mean_if_no_missing_HT"] for k in STRATEGIES},
        "saved": str(out),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
