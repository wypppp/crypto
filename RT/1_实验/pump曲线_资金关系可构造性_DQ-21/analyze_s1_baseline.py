#!/usr/bin/env python3
"""Audit S1 fixed-exit output against frozen S0 and summarize model returns.

Only uses development-cohort rows. Missing exits are reported, never filled with
zero and never silently dropped from a population mean.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from analyze_s0_v1_2 import b, f, weighted_quantile

HERE = Path(__file__).resolve().parent
S0_DEFAULT = HERE / "raw/s0/S0_AB_v1_3_audit_columns.csv.gz"
STRATEGIES = [f"ret_d{d}_{h}" for d in (5, 30, 120)
              for h in ("30s", "2m", "10m", "1h")]
STRATEGIES += [f"b50_ret_d{d}" for d in (5, 30, 120)]


def read_rows(path: Path) -> dict[str, dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as src:
        rows = list(csv.DictReader(src))
    out = {r["mint"]: r for r in rows}
    if len(out) != len(rows):
        raise RuntimeError(f"duplicate mints in {path}")
    return out


def summarize(rows: list[dict], name: str, denominator: int) -> dict:
    present = []
    missing = []
    for r in rows:
        weight = 1 if b(r, "tail420_candidate") or b(r, "tail10_exec") else 50
        val = f(r, name)
        if val is None or not math.isfinite(val) or val < 0:
            missing.append((r["mint"], weight))
        else:
            present.append((r, weight, val))
    observed_w = sum(w for _, w, _ in present)
    missing_w = sum(w for _, w in missing)
    sum_wr = sum(w * val for _, w, val in present)
    by_day = defaultdict(lambda: [0.0, 0.0])
    for r, w, val in present:
        z = by_day[r["created_at"][:10]]
        z[0] += w
        z[1] += w * val
    days = sorted(by_day)
    boot = []
    if not missing and len(days) >= 7:
        rng = random.Random(210928)
        for _ in range(2000):
            sampled = [rng.choice(days) for _ in days]
            den = sum(by_day[day][0] for day in sampled)
            boot.append(sum(by_day[day][1] for day in sampled) / den)
        boot.sort()
    profits = sorted(((w * max(val - 1, 0), r["mint"]) for r, w, val in present), reverse=True)
    total_positive_profit = sum(x for x, _ in profits)
    return {
        "observed_rows": len(present), "missing_rows": len(missing),
        "observed_weight": observed_w, "missing_weight": missing_w,
        "weighted_sample_total": observed_w + missing_w,
        "exact_target_n": denominator,
        "missing_mints_first_10": [mint for mint, _ in missing[:10]],
        "population_mean_if_no_missing_HT": sum_wr / denominator if not missing else None,
        "observed_only_ratio_mean_diagnostic": sum_wr / observed_w if observed_w else None,
        "weighted_median_observed_diagnostic": weighted_quantile([(v, w) for _, w, v in present], 0.5),
        "weighted_loss_share_observed_diagnostic": (
            sum(w for _, w, v in present if v < 1) / observed_w if observed_w else None
        ),
        "weighted_realized_10x_share_observed_diagnostic": (
            sum(w for _, w, v in present if v >= 10) / observed_w if observed_w else None
        ),
        "top_positive_profit_weighted_1_3_10": [
            sum(x for x, _ in profits[:n]) / total_positive_profit if total_positive_profit > 0 else None
            for n in (1, 3, 10)
        ],
        "day_block_ratio_mean_p025_p975": [boot[int((len(boot) - 1) * q)] for q in (0.025, 0.975)] if boot else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("s1", type=Path)
    ap.add_argument("--s0", type=Path, default=S0_DEFAULT)
    args = ap.parse_args()
    s0 = read_rows(args.s0)
    s1 = read_rows(args.s1)
    if set(s0) != set(s1):
        raise RuntimeError(f"S0/S1 mint mismatch: lost={len(set(s0)-set(s1))}, new={len(set(s1)-set(s0))}")
    required = set(STRATEGIES) | {"mint", "created_at", "eligible", "r0_seen", "tail420_candidate",
                                  "tail10_exec", "mint_hash_exact", "t3_s", "e5_x", "e5_y"}
    if required - set(next(iter(s1.values()))):
        raise RuntimeError(f"S1 columns missing: {sorted(required - set(next(iter(s1.values()))))}")
    for mint, r in s1.items():
        old = s0[mint]
        for col in ("eligible", "r0_seen", "tail420_candidate", "tail10_exec"):
            if b(r, col) != b(old, col):
                raise RuntimeError(f"S1 changed frozen S0 field: {mint} {col}: {r[col]} != {old[col]}")
        if int(r["mint_hash_exact"]) != int(old["mint_hash_exact"]):
            raise RuntimeError(f"S1 changed mint hash: {mint}")
        for col in ("t3_s", "e5_x", "e5_y"):
            a, z = f(r, col), f(old, col)
            if (a is None) != (z is None) or (a is not None and not math.isclose(a, z, rel_tol=1e-12, abs_tol=1e-12)):
                raise RuntimeError(f"S1 changed frozen S0 field: {mint} {col}: {r[col]} != {old[col]}")
        for d in (5, 30, 120):
            for h, horizon in (("30s", 30), ("2m", 120), ("10m", 600), ("1h", 3600)):
                age = f(r, f"state_age_d{d}_{h}")
                if age is not None and not (0 <= age <= horizon + d):
                    raise RuntimeError(f"invalid state age: {mint} d{d} {h} {age}")
    target = int(float(next(iter(s0.values()))["n_eligible"])) - sum(
        b(r, "r0_seen") and b(r, "eligible") for r in s0.values()
    )
    primary = [r for r in s1.values() if b(r, "eligible") and not b(r, "r0_seen")]
    summary = {
        "s0": str(args.s0), "s1": str(args.s1), "same_mints": len(s1),
        "target_eligible_excluding_r0": target, "primary_sample_rows": len(primary),
        "note": "All returns are pool-model proceeds per 0.5 SOL purchase; extra priority fees, failed trades and MEV remain excluded. Missing outcome means population mean not reported.",
        "strategies": {name: summarize(primary, name, target) for name in STRATEGIES},
    }
    out = args.s1.with_suffix(".analysis.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"same_mints": len(s1), "primary_sample_rows": len(primary),
                      "missing_by_strategy": {k: v["missing_rows"] for k, v in summary["strategies"].items()},
                      "saved": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
