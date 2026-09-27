#!/usr/bin/env python3
"""Derive the two-creation-day, full-horizon cost calibration from S0 v1.3."""
from pathlib import Path

H = Path(__file__).resolve().parent
src = H / "sql/S0_AB_事件时点机会普查_v1_3_运行版.sql"
text = src.read_text()
cohort = "BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'"
scan = "BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'"
assert text.count(cohort) == 1
assert text.count(scan) == 5
assert text.count("INTERVAL '30' DAY") == 1
text = text.replace(cohort, "BETWEEN DATE '2026-06-01' AND DATE '2026-06-02'")
text = text.replace(scan, "BETWEEN DATE '2026-06-01' AND DATE '2026-07-03'")
text = """/* COST CALIBRATION ONLY: S0 v1.3, coins created June 1-2, full 30-day path.
   Same logic/result shape as frozen production SQL. No relationship signal or
   strategy inference is authorized from this two-day cohort.
   Suggested platform execution cap: 40 credits; user maximum: 100. */
""" + text
out = H / "sql/S0_COST_2DAY_30D_v1_3_20260601_02.sql"
out.write_text(text)
print(out)
