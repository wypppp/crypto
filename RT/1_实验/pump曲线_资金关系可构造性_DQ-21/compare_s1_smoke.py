#!/usr/bin/env python3
"""Compare sample-first S1 pilot to the original June 1 execution, all shared columns."""
from __future__ import annotations

import argparse
import math

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
    old, new = read_rows(ORIGINAL), read_rows(args.optimized)
    if set(old) != set(new) or len(old) != 695:
        raise AssertionError(f"mint set changed: old={len(old)} new={len(new)} intersection={len(set(old)&set(new))}")
    shared = set(next(iter(old.values()))) & set(next(iter(new.values())))
    dropped = set(next(iter(old.values()))) - shared
    allowed_dropped = {"n_all", "n_eligible", "n_tail420_candidate", "n_random_2pct"}
    if dropped != allowed_dropped:
        raise AssertionError(f"unexpected dropped columns: {dropped}")
    failures = []
    for mint in sorted(old):
        for col in shared:
            if not same(old[mint][col], new[mint][col]):
                failures.append((mint, col, old[mint][col], new[mint][col]))
                if len(failures) == 20:
                    break
        if len(failures) == 20:
            break
    if failures:
        raise AssertionError(f"sample-first changed output: {failures}")
    print(f"PASS: 695 identical mints, {len(shared)} shared output columns numerically identical")


if __name__ == "__main__":
    main()
