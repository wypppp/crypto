#!/usr/bin/env python3
"""Audit frozen S0 pool-spot drift and sparse-stratum sample size.

These are neither executable fixed-horizon exits nor net strategy returns.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

from analyze_s0_v1_2 import weighted_quantile

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw/s0"


def read_csv(path: Path) -> list[dict]:
    with gzip.open(path, "rt", newline="") as src:
        return list(csv.DictReader(src))


def flag(v: str) -> bool:
    return v.lower() in {"true", "1"}


def f(v: str) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def summarize(rows: list[tuple[float | None, int]]) -> dict:
    pairs = [(x, w) for x, w in rows if x is not None and x > 0]
    w_valid = sum(w for _, w in pairs)
    w_total = sum(w for _, w in rows)
    return {
        "weighted_valid_n": w_valid,
        "weighted_total_n": w_total,
        "weighted_missing_n": w_total - w_valid,
        "weighted_p10": weighted_quantile(pairs, .1),
        "weighted_p50": weighted_quantile(pairs, .5),
        "weighted_p90": weighted_quantile(pairs, .9),
        "weighted_share_spot_ratio_gt_1": sum(w for x, w in pairs if x > 1) / w_valid if w_valid else None,
        "weighted_mean_spot_ratio": sum(x*w for x, w in pairs) / w_valid if w_valid else None,
    }


def main() -> None:
    core = read_csv(RAW / "S0_AB_v1_3_audit_columns.csv.gz")
    extra = read_csv(RAW / "S0_AB_v1_3_spot_drift.csv.gz")
    e = {r["mint"]: r for r in extra}
    if len(core) != 10565 or len(extra) != 10565 or len(e) != 10565:
        raise RuntimeError("wrong row count or duplicate mint")
    if set(e) != {r["mint"] for r in core}:
        raise RuntimeError("frozen S0 result projections differ in mint identities")
    primary = []
    for r in core:
        if not flag(r["eligible"]) or flag(r["r0_seen"]):
            continue
        case = flag(r["tail420_candidate"]) or flag(r["tail10_exec"])
        h = int(r["mint_hash_exact"])
        if not case and h % 10000 >= 200:
            continue
        w = 1 if case else 50
        primary.append((r, e[r["mint"]], w))

    out = {
        "definition": "S0 pool spot-price ratio at t3+30/120 seconds versus pool spot at t3+5 seconds. No hypothetical sale order, fees, landing delay, or fixed holding period is applied.",
        "source_execution_id": "01M3JFX2HT1ZJJ25S4TDKAFC2J",
        "primary_sample_rows": len(primary),
        "weighted_primary_rows": sum(w for _, _, w in primary),
        "ratios": {},
        "strata": [],
    }
    for name in ("price_pm_30s", "price_pm_120s"):
        out["ratios"][name] = summarize([(f(x[name]), w) for _, x, w in primary])

    strata = defaultdict(lambda: {"population_eligible": None, "r0_excluded": 0,
                                  "sample_noncase": 0, "sample_case": 0})
    for r in core:
        if not flag(r["eligible"]):
            continue
        key = (r["cohort_week"], r["t3_bucket"])
        z = strata[key]
        exact = int(float(r["n_eligible_week_t3_bucket"]))
        if z["population_eligible"] is not None and z["population_eligible"] != exact:
            raise RuntimeError(f"inconsistent population for {key}")
        z["population_eligible"] = exact
        if flag(r["r0_seen"]):
            z["r0_excluded"] += 1
            continue
        if flag(r["tail420_candidate"]) or flag(r["tail10_exec"]):
            z["sample_case"] += 1
        else:
            z["sample_noncase"] += 1
    for (week, bucket), z in sorted(strata.items()):
        noncase_population = z["population_eligible"] - z["r0_excluded"] - z["sample_case"]
        if noncase_population > 0 and z["sample_noncase"] == 0:
            raise RuntimeError(f"no sampled noncases in {week}/{bucket}")
        z.update({"week": week, "t3_bucket": bucket,
                  "ht_noncase": 50*z["sample_noncase"],
                  "sample_noncase_effective_n": z["sample_noncase"],
                  "noncase_population_exact_excluding_r0": noncase_population,
                  "calibrated_noncase_weight": noncase_population / z["sample_noncase"]})
        out["strata"].append(z)
    if sum(z["population_eligible"] - z["r0_excluded"] for z in strata.values()) != 137108:
        raise RuntimeError("calibrated target count differs from frozen S0")
    out["calibrated_ratios"] = {}
    for name in ("price_pm_30s", "price_pm_120s"):
        values = []
        for r, x, _ in primary:
            z = strata[(r["cohort_week"], r["t3_bucket"])]
            case = flag(r["tail420_candidate"]) or flag(r["tail10_exec"])
            w = 1.0 if case else z["calibrated_noncase_weight"]
            values.append((f(x[name]), w))
        out["calibrated_ratios"][name] = summarize(values)
    path = RAW / "S0_AB_v1_3_spot_drift_analysis.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "strata"}, ensure_ascii=False, indent=2))
    print("saved", path)


if __name__ == "__main__":
    main()
