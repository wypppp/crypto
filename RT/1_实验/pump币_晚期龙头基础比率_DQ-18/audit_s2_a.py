"""Recompute DQ-18 A-stage signal-quality counts from saved Dune rows.

This diagnoses the original first-in-month signal; it does not define a new
first-crossing rule or compute any post-signal returns.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "raw" / "s2"
THRESHOLDS = (1_000_000, 5_000_000, 20_000_000, 100_000_000)


def month_rows(month):
    payload = json.loads((ROOT / ("A_" + month + ".json")).read_text())
    return payload["rows"]


def main():
    for month in ("202411", "202512"):
        rows = month_rows(month)
        print(month, "rows", len(rows), "mints", len({r["mint"] for r in rows}))
        for threshold in THRESHOLDS:
            selected = [r for r in rows if float(r["threshold_usd"]) == threshold]
            print(
                threshold,
                "candidates", len(selected),
                "all_trades_lt10", sum(r["n_all_trades"] < 10 for r in selected),
                "priced_trades_lt10", sum(r["n_price_trades"] < 10 for r in selected),
                "valid_usd_lt1", sum(r["valid_usd_volume"] < 1 for r in selected),
                "original_hour_quality50_10", sum(
                    r["valid_usd_volume"] >= 50 and r["n_price_trades"] >= 10
                    for r in selected
                ),
                "mayhem_unknown", sum(r["is_mayhem_mode"] is None for r in selected),
            )

    pnut = "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump"
    match = [
        r for r in month_rows("202411")
        if r["mint"] == pnut and float(r["threshold_usd"]) == 20_000_000
    ]
    assert len(match) == 1
    assert match[0]["hour_start"].startswith("2024-11-02 16:00:00")


if __name__ == "__main__":
    main()
