#!/usr/bin/env python3
"""Technical audit of the June 1 S1 cost pilot; never infers two-week returns."""
from __future__ import annotations

import json
import math
from pathlib import Path

from analyze_s0_v1_2 import b, f
from analyze_s1_baseline import HERE, STRATEGIES, read_rows, summarize

S0 = HERE / "raw/s0/S0_AB_v1_3_audit_columns.csv.gz"
S1 = HERE / "raw/s1/S1_SMOKE_20260601.csv.gz"


def main() -> None:
    old, new = read_rows(S0), read_rows(S1)
    expected = {mint for mint, r in old.items() if r["created_at"][:10] == "2026-06-01"}
    if set(new) != expected or len(new) != 695:
        raise AssertionError("June 1 frozen mint set changed")
    audit_cols = ("eligible", "r0_seen", "tail420_candidate", "tail10_exec", "mint_hash_exact",
                  "t3_s", "e5_x", "e5_y")
    for mint, row in new.items():
        prior = old[mint]
        for col in audit_cols:
            a, z = row[col], prior[col]
            if a != z:
                try:
                    same = math.isclose(float(a), float(z), rel_tol=1e-12, abs_tol=1e-12)
                except (TypeError, ValueError):
                    same = False
                if not same:
                    raise AssertionError(f"frozen field mismatch: {mint} {col}")
    rows = [r for r in new.values() if b(r, "eligible") and not b(r, "r0_seen")]
    denominator = int(float(next(iter(new.values()))["n_eligible"])) - sum(
        b(r, "eligible") and b(r, "r0_seen") for r in new.values()
    )
    result: dict = {
        "label": "ONE-DAY COST/TECHNICAL PILOT ONLY; do not infer two-week population return",
        "n_frozen_sample": len(new),
        "n_primary_sample": len(rows),
        "june1_exact_eligible_excluding_r0": denominator,
        "strategies": {},
        "state_age_over_hold_count": {},
    }
    for key in STRATEGIES:
        z = summarize(rows, key, denominator)
        result["strategies"][key] = {
            k: z[k] for k in (
                "observed_rows", "missing_rows", "observed_weight", "missing_weight",
                "population_mean_if_no_missing_HT", "observed_only_ratio_mean_diagnostic",
                "weighted_median_observed_diagnostic", "top_positive_profit_weighted_1_3_10"
            )
        }
    for delay in (5, 30, 120):
        for label, hold in (("30s", 30), ("2m", 120), ("10m", 600), ("1h", 3600)):
            col = f"state_age_d{delay}_{label}"
            ages = [f(r, col) for r in rows]
            result["state_age_over_hold_count"][col] = sum(v is not None and v > hold for v in ages)
    out = HERE / "raw/s1/S1_SMOKE_20260601_audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": True, "sample_rows": len(new), "primary": len(rows),
                      "target": denominator, "saved": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
