#!/usr/bin/env python3
"""Compare corrected S1 pilot with old June 1 execution and independent quotes."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from analyze_s1_baseline import HERE, read_rows

ORIGINAL = HERE / "raw/s1/S1_SMOKE_20260601.csv.gz"


def same(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-12)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("optimized")
    args = ap.parse_args()
    old, new = read_rows(ORIGINAL), read_rows(Path(args.optimized))
    if set(old) != set(new) or len(old) != 695:
        raise AssertionError(f"mint set changed: old={len(old)} new={len(new)} intersection={len(set(old)&set(new))}")
    unchanged = {
        "mint_hash_exact", "created_at", "cohort_week", "t3_s", "t3_bucket", "eligible",
        "tail420_candidate", "r0_seen", "has_migration_event", "amm_mapped",
        "e5_x", "e5_y", "e5_xr", "e5_fee_bps", "e5_venue", "e5_ts", "e30_ts", "e120_ts",
        *{f"state_age_d{d}_{h}" for d in (5, 30, 120) for h in ("30s", "2m", "10m", "1h")},
        *{f"stop_time_d{d}" for d in (5, 30, 120)},
    }
    if unchanged - set(next(iter(new.values()))):
        raise AssertionError(f"corrected output lacks invariants: {unchanged - set(next(iter(new.values())))}")
    failures = []
    for mint in sorted(old):
        for col in unchanged:
            if not same(old[mint][col], new[mint][col]):
                failures.append((mint, col, old[mint][col], new[mint][col]))
                if len(failures) == 20:
                    break
        if len(failures) == 20:
            break
    if failures:
        raise AssertionError(f"sample-first changed non-return fields: {failures}")
    no_trade = 0
    for mint, row in new.items():
        age = row["state_age_d5_30s"]
        if not age or float(age) <= 30:
            continue
        x, y = float(row["e5_x"]), float(row["e5_y"])
        fee = float(row["e5_fee_bps"]) / 10000
        tokens = y - x * y / (x + 0.5 * (1 - fee))
        gross = x * tokens / (y + tokens) if row["e5_venue"] == "0" else x - x * y / (y + tokens)
        received = gross * (1 - fee)
        if row["e5_venue"] == "0":
            received = min(received, float(row["e5_xr"]) + 0.5 * (1 - fee))
        expected = received / 0.5
        actual = float(row["ret_d5_30s"])
        if not math.isclose(expected, actual, rel_tol=1e-10, abs_tol=1e-10):
            raise AssertionError(f"same-state curve quote mismatch: {mint} {expected} != {actual}")
        no_trade += 1
    if no_trade < 20:
        raise AssertionError(f"too few independent same-state sell checks: {no_trade}")
    old_10 = sum(r["tail10_exec"] == "True" for r in old.values())
    new_10 = sum(r["tail10_exec"] == "True" for r in new.values())
    print(f"PASS: 695 identical mints, {len(unchanged)} invariant columns, "
          f"{no_trade} independent same-state sell quotes; old10={old_10} corrected10={new_10}")


if __name__ == "__main__":
    main()
