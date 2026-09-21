"""Reproduce the newly reported concentration and oracle tables.

This reproduces a static, hindsight, linear-sizing calculation. It does NOT
validate executable capacity, an optimal oracle, or a multi-year wealth path.
Run from any directory using the project's .venv/bin/python.
"""
import csv
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOL_USD = 69.76
USD_CNY = 7.1
FIXED_RETURN_DEDUCTION = 0.004


def allocation(rows, budget, key, allow_partial):
    """No recycling: total allocated principal is bounded by budget."""
    cash = budget
    selected = []
    for row in sorted(rows, key=lambda r: r[key], reverse=True):
        if cash <= 0:
            break
        q = min(cash, row["capacity_cny"])
        if not allow_partial and q < row["capacity_cny"]:
            break
        selected.append((row, q))
        cash -= q
    return {
        "budget_cny": budget,
        "n": len(selected),
        "allocated_cny": sum(q for _, q in selected),
        "linear_profit_cny": sum(q * (r["recovery"] - 1) for r, q in selected),
        "maximum_holding_days": max((r["holding_seconds"] / 86400 for r, _ in selected), default=0),
        "positions_held_over_seven_days": sum(r["holding_seconds"] > 7 * 86400 for r, _ in selected),
    }


def check(relative_path, recovery_column):
    source = ROOT / relative_path
    rows = []
    for raw in csv.DictReader(source.open()):
        if raw["mint"] == "__SUMMARY__" or not raw[recovery_column]:
            continue
        recovery = float(raw[recovery_column]) - FIXED_RETURN_DEDUCTION
        entry_x = float(raw["entry_x_sol"])
        # This 0.025 approximation reproduces all six quoted numbers.
        capacity = entry_x * 0.025 * SOL_USD * USD_CNY
        rows.append({
            "mint": raw["mint"], "recovery": recovery,
            "entry_x_sol": entry_x, "capacity_cny": capacity,
            "linear_full_capacity_profit_cny": capacity * (recovery - 1),
            "holding_seconds": float(raw[recovery_column + "_dt"]),
        })
    positive = [r for r in rows if r["recovery"] > 1]
    gain = sum(max(r["recovery"] - 1, 0) for r in rows)
    loss = sum(max(1 - r["recovery"], 0) for r in rows)
    ranked = sorted(rows, key=lambda r: r["recovery"], reverse=True)
    result = {
        "input": relative_path, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "return_column": recovery_column, "n": len(rows), "positive_n": len(positive),
        "positive_excess_return_sum": gain, "negative_excess_return_sum": loss,
        "net_excess_return_sum": gain - loss,
        "mean_recovery": 1 + (gain - loss) / len(rows),
        "concentration": {
            str(k): {"population_share": k / len(rows),
                     "positive_profit_share": sum(r["recovery"] - 1 for r in ranked[:k]) / gain}
            for k in (5, 50)
        },
        "quoted_table_reconstruction": [
            allocation(positive, b, "linear_full_capacity_profit_cny", False)
            for b in (10000, 30000, 1000000)
        ],
        "fractional_optimum_in_same_static_linear_relaxation": [
            allocation(positive, b, "recovery", True) for b in (10000, 30000, 1000000)
        ],
        "unconstrained_single_coin_hindsight_profit_at_10000_cny":
            10000 * (ranked[0]["recovery"] - 1),
    }
    return result


def main():
    out = {
        "scope": "Arithmetic reproduction only; original new oracle script not located.",
        "constants": {"sol_usd": SOL_USD, "usd_cny": USD_CNY,
                      "fixed_return_deduction": FIXED_RETURN_DEDUCTION,
                      "quoted_capacity_multiplier": 0.025,
                      "existing_project_capacity_multiplier": math.sqrt(1.05) - 1},
        "A": check("RT/dq7/raw/F2_dev.csv", "b50"),
        "B": check("RT/dq1f/raw/F1_val.csv", "x50_24h"),
    }
    out["source_of_three_year_claim"] = {
        label: data["quoted_table_reconstruction"][-1]["linear_profit_cny"] * 156
        for label, data in (("A", out["A"]), ("B", out["B"]))
    }
    (HERE / "claims_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
