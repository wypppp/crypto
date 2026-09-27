#!/usr/bin/env python3
"""Derive a one-creation-day, full-30-day cost pilot from frozen S0 v1.3."""
from pathlib import Path

H = Path(__file__).resolve().parent
src = H / "sql/S0_AB_事件时点机会普查_v1_3_运行版.sql"
text = src.read_text()
cohort = "BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'"
scan = "BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'"
assert text.count(cohort) == 1
assert text.count(scan) == 5
assert text.count("INTERVAL '30' DAY") == 1
text = text.replace(cohort, "BETWEEN DATE '2026-06-01' AND DATE '2026-06-01'")
text = text.replace(scan, "BETWEEN DATE '2026-06-01' AND DATE '2026-07-02'")
text = """/* COST PILOT ONLY: S0 v1.3, coins created on 2026-06-01, full 30-day path.
   This query uses the production logic and result shape; only the creation
   cohort and table scan dates are reduced. No relationship signal or strategy
   result may be inferred from this deliberately selected single day.
   Suggested platform execution cap: 50 credits; user maximum: 100. */
""" + text
out = H / "sql/S0_COST_30D_v1_3_20260601.sql"
out.write_text(text)
print(out)
