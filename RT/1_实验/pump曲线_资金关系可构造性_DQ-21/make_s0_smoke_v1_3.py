#!/usr/bin/env python3
"""Derive the one-day schema/cost smoke from S0 v1.3's runtime SQL."""
from pathlib import Path

H = Path(__file__).resolve().parent
src = H / "sql" / "S0_AB_事件时点机会普查_v1_3_运行版.sql"
text = src.read_text()
old_cohort = "BETWEEN DATE '2026-06-01' AND DATE '2026-06-14'"
old_scan = "BETWEEN DATE '2026-06-01' AND DATE '2026-07-15'"
old_horizon = "INTERVAL '30' DAY"
assert text.count(old_cohort) == 1
assert text.count(old_scan) == 5
assert text.count(old_horizon) == 1
text = text.replace(old_cohort, "BETWEEN DATE '2026-06-01' AND DATE '2026-06-01'")
text = text.replace(old_scan, "BETWEEN DATE '2026-06-01' AND DATE '2026-06-02'")
text = text.replace(old_horizon, "INTERVAL '1' DAY")
text = """/* DIAGNOSTIC ONLY: S0 v1.3, one creation day and one-day path.
   Column names ending 30d retain the production schema but contain only this
   smoke's one-day path. Do not use any outcome count as evidence.
   Platform execution cap: 10 credits. */\n""" + text
out = H / "sql" / "S0_SMOKE_v1_3_20260601.sql"
out.write_text(text)
print(out)
