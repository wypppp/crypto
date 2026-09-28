#!/usr/bin/env python3
"""Independent same-state check of the historical S1 curve-sell formula."""
from __future__ import annotations

import csv
import gzip
import json
import statistics
from pathlib import Path

from evt_decode import iter_events

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "raw/s1/S1_SMOKE_20260601.csv.gz"
OUT = HERE / "raw/s1/S1_curve_sell_direction_audit.json"
HELIUS = HERE / "raw/helius"


def audit_landed_sells(limit: int = 1000) -> dict[str, int | float]:
    """Check the reserve direction against landed Pump TradeEvents.

    TradeEvent reserves are post-trade.  On a sell, reconstructing
    pre_y=post_y+? is unnecessary guesswork: official semantics imply
    post_y=pre_y+q and post_x=pre_x-sol_amount.  The corrected integer quote
    must therefore reproduce the event's gross sol_amount exactly.
    """
    correct_errors: list[int] = []
    old_errors: list[int] = []
    files = 0
    for path in sorted(HELIUS.glob("*.jsonl.gz")):
        files += 1
        with gzip.open(path, "rt") as f:
            for line in f:
                tx = json.loads(line)
                for event in iter_events(tx):
                    if event["name"] != "TradeEvent" or event["is_buy"]:
                        continue
                    q = event["token_amount"]
                    post_x = event["virtual_sol_reserves"]
                    post_y = event["virtual_token_reserves"]
                    observed = event["sol_amount"]
                    if q <= 0 or post_y <= q:
                        continue
                    pre_x = post_x + observed
                    pre_y = post_y - q
                    corrected = pre_x * q // (pre_y + q)
                    correct_errors.append(abs(corrected - observed))
                    if pre_y > q:
                        old = pre_x * pre_y // (pre_y - q) - pre_x
                        old_errors.append(abs(old - observed))
                    if len(correct_errors) >= limit:
                        return {
                            "cached_files_read": files,
                            "landed_sell_events": len(correct_errors),
                            "correct_formula_exact_events": sum(x == 0 for x in correct_errors),
                            "correct_formula_max_abs_lamport_error": max(correct_errors),
                            "old_formula_exact_events": sum(x == 0 for x in old_errors),
                            "old_formula_median_abs_lamport_error": statistics.median(old_errors),
                        }
    raise AssertionError(f"only found {len(correct_errors)} landed sells")


def main() -> None:
    with gzip.open(SOURCE, "rt", newline="") as f:
        rows = list(csv.DictReader(f))
    curve = []
    same_state = []
    for row in rows:
        if row["eligible"] != "True" or row["e5_venue"] != "0":
            continue
        x, y = float(row["e5_x"]), float(row["e5_y"])
        xr = float(row["e5_xr"])
        fee = float(row["e5_fee_bps"]) / 10000
        tokens = y - x * y / (x + 0.5 * (1 - fee))
        old_sell = (x * y / (y - tokens) - x) * (1 - fee)
        correct_sell = (x - x * y / (y + tokens)) * (1 - fee)
        cap = xr + 0.5 * (1 - fee)
        old_ret = min(old_sell, cap) / 0.5
        correct_ret = min(correct_sell, cap) / 0.5
        curve.append({"mint": row["mint"], "old_roundtrip": old_ret,
                      "correct_roundtrip": correct_ret, "difference": old_ret - correct_ret})
        age = row["state_age_d5_30s"]
        if age and float(age) > 30 and row["ret_d5_30s"]:
            observed = float(row["ret_d5_30s"])
            if abs(observed - old_ret) > 1e-9:
                raise AssertionError(f"historical SQL is not the old same-state formula: {row['mint']}")
            same_state.append({"mint": row["mint"], "observed_old": observed,
                               "correct": correct_ret, "overstatement": observed - correct_ret})
    if len(same_state) < 20:
        raise AssertionError("too few unchanged-pool observations")
    diffs = sorted(x["difference"] for x in curve)
    result = {
        "source": str(SOURCE),
        "curve_eligible": len(curve),
        "same_state_30s_count": len(same_state),
        "same_state_overstatement_median": statistics.median(x["overstatement"] for x in same_state),
        "same_state_overstatement_min": min(x["overstatement"] for x in same_state),
        "same_state_overstatement_max": max(x["overstatement"] for x in same_state),
        "counterfactual_roundtrip_overstatement_median": statistics.median(diffs),
        "counterfactual_roundtrip_overstatement_p95": diffs[int(0.95 * (len(diffs) - 1))],
        "counterfactual_roundtrip_overstatement_max": max(diffs),
        "same_state_examples_first_5": same_state[:5],
        "note": "This diagnoses the direction error. It does not estimate the full-path strategy-return correction.",
        "landed_trade_event_check": audit_landed_sells(),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("same_state_examples_first_5", "source")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
