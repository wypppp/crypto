#!/usr/bin/env python3
"""Audit and summarize the frozen DQ-21 S0 case-cohort output (stdlib only)."""
from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from pathlib import Path


def open_text(path: Path):
    return gzip.open(path, "rt", newline="") if path.suffix == ".gz" else path.open(newline="")


def f(row, name):
    v = row.get(name, "")
    return None if v in (None, "") else float(v)


def b(row, name):
    return str(row.get(name, "")).lower() in {"true", "1"}


def weighted_quantile(pairs, q):
    pairs = sorted((x, w) for x, w in pairs if x is not None and math.isfinite(x) and w > 0)
    total = sum(w for _, w in pairs)
    if not pairs or total <= 0:
        return None
    target = q * total
    acc = 0.0
    for x, w in pairs:
        acc += w
        if acc >= target:
            return x
    return pairs[-1][0]


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: analyze_s0.py PATH.csv[.gz]")
    path = Path(sys.argv[1])
    with open_text(path) as src:
        rows = list(csv.DictReader(src))
    if not rows:
        raise RuntimeError("empty S0 result")
    required = {
        "mint", "created_at", "eligible", "tail10_exec", "early_crash", "r0_seen",
        "mint_hash", "inclusion_probability", "n_all", "n_eligible", "n_tail10_exec",
        "n_early_crash", "n_random_2pct", "t3_s", "e5_x", "e5_y", "max_sell_30d",
    }
    missing = required - set(rows[0])
    if missing:
        raise RuntimeError(f"missing columns: {sorted(missing)}")
    if len({r["mint"] for r in rows}) != len(rows):
        raise RuntimeError("duplicate mint rows")

    constants = {}
    for name in ("n_all", "n_eligible", "n_tail10_exec", "n_early_crash", "n_random_2pct"):
        vals = {int(float(r[name])) for r in rows}
        if len(vals) != 1:
            raise RuntimeError(f"nonconstant {name}: {vals}")
        constants[name] = vals.pop()

    bad_selection = []
    for r in rows:
        selected = b(r, "r0_seen") or (b(r, "eligible") and b(r, "tail10_exec")) or (
            b(r, "eligible") and int(r["mint_hash"]) % 10000 < 200
        )
        if not selected:
            bad_selection.append(r["mint"])
    if bad_selection:
        raise RuntimeError(f"rows outside frozen selection: {bad_selection[:5]}")

    tail_rows = sum(b(r, "eligible") and b(r, "tail10_exec") for r in rows)
    random_rows = sum(b(r, "eligible") and int(r["mint_hash"]) % 10000 < 200 for r in rows)
    if tail_rows != constants["n_tail10_exec"]:
        raise RuntimeError(f"tail census incomplete: downloaded {tail_rows}, expected {constants['n_tail10_exec']}")
    if random_rows != constants["n_random_2pct"]:
        raise RuntimeError(f"random cohort incomplete: downloaded {random_rows}, expected {constants['n_random_2pct']}")

    # R0-only QA rows were selected deliberately and have no sampling weight.
    # R0 rows that independently enter the all-tail census or fixed hash cohort
    # retain those objective inclusion probabilities.
    r0_only_eligible = sum(
        b(r, "r0_seen") and b(r, "eligible") and not b(r, "tail10_exec")
        and int(r["mint_hash"]) % 10000 >= 200 for r in rows
    )
    eligible_denominator = constants["n_eligible"] - r0_only_eligible
    primary = [
        r for r in rows
        if b(r, "eligible") and (b(r, "tail10_exec") or int(r["mint_hash"]) % 10000 < 200)
    ]
    weighted = []
    for r in primary:
        if not b(r, "eligible"):
            continue
        # All tails have p=1; non-tails enter via the fixed 2% cohort.
        w = 1.0 if b(r, "tail10_exec") else 50.0
        weighted.append((r, w))

    def ht_mean(name):
        vals = [(f(r, name), w) for r, w in weighted if f(r, name) is not None]
        return None if not vals else sum(x * w for x, w in vals) / eligible_denominator

    def ht_share(pred):
        return sum(w for r, w in weighted if pred(r)) / eligible_denominator

    t3 = [(f(r, "t3_s"), w) for r, w in weighted]
    cap = []
    for r, w in weighted:
        x, fee = f(r, "e5_x"), f(r, "e5_fee_bps")
        if x is not None and fee is not None and fee < 10000:
            cap.append((x * (math.sqrt(1.05) - 1) / (1 - fee / 10000), w))

    by_week = {}
    by_week_t3 = {}
    for r in rows:
        week = r.get("cohort_week")
        if week:
            pair = (int(float(r["n_all_week"])), int(float(r["n_eligible_week"])))
            if week in by_week and by_week[week] != pair:
                raise RuntimeError(f"inconsistent exact week counts for {week}")
            by_week[week] = pair
            key = (week, r.get("t3_bucket"))
            n = int(float(r["n_eligible_week_t3_bucket"]))
            if key in by_week_t3 and by_week_t3[key] != n:
                raise RuntimeError(f"inconsistent t3 stratum count for {key}")
            by_week_t3[key] = n

    anomalies = {
        "eligible_without_t3": sum(b(r, "eligible") and f(r, "t3_s") is None for r in rows),
        "eligible_bad_t3": sum(b(r, "eligible") and not (0 <= f(r, "t3_s") <= 300) for r in rows),
        "eligible_missing_entry_state": sum(
            b(r, "eligible") and (f(r, "e5_x") is None or f(r, "e5_y") is None) for r in rows
        ),
        "nonpositive_entry_reserve": sum(
            b(r, "eligible") and ((f(r, "e5_x") or 0) <= 0 or (f(r, "e5_y") or 0) <= 0) for r in rows
        ),
        "tail_missing_recovery": sum(b(r, "tail10_exec") and f(r, "max_sell_30d") is None for r in rows),
    }
    out = {
        "source": str(path),
        "downloaded_rows": len(rows),
        "exact_counts": constants,
        "r0_qa_rows": sum(b(r, "r0_seen") for r in rows),
        "r0_only_eligible_excluded_from_weighted_estimates": r0_only_eligible,
        "weighted_target_n": eligible_denominator,
        "downloaded_tail_rows": tail_rows,
        "downloaded_random_rows": random_rows,
        "anomalies": anomalies,
        "weighted_estimates": {
            "exact_week_n_all_n_eligible": by_week,
            "exact_observed_t3_strata": {"/".join(k): v for k, v in by_week_t3.items()},
            "tail_share": ht_share(lambda r: b(r, "tail10_exec")),
            "early_crash_share": ht_share(lambda r: b(r, "early_crash")),
            "t3_s_p10_p50_p90": [weighted_quantile(t3, q) for q in (0.1, 0.5, 0.9)],
            "capacity_5pct_sol_p10_p50_p90": [weighted_quantile(cap, q) for q in (0.1, 0.5, 0.9)],
            "mean_max_sell_30d": ht_mean("max_sell_30d"),
        },
    }
    if any(anomalies.values()):
        out["verdict"] = "FAIL_DATA_INVARIANTS"
    elif out["r0_qa_rows"] < 100:
        out["verdict"] = "REVIEW_R0_COVERAGE"
    else:
        out["verdict"] = "READY_FOR_MANUAL_QA"
    target = path.with_name("S0_analysis.json")
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
