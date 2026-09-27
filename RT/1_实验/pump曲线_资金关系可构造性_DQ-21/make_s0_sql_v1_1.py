#!/usr/bin/env python3
"""Fill the frozen S0 v1.1 SQL's R0 QA mint list without changing its logic."""
from pathlib import Path
import csv

H = Path(__file__).resolve().parent
template = H / "sql" / "S0_AB_事件时点机会普查_v1_1.sql"
with (H / "sample.csv").open(newline="") as f:
    mints = sorted({row["mint"] for row in csv.DictReader(f) if row.get("mint")})
assert len(mints) == 105, len(mints)
values = ",\n        ".join("('%s')" % x.replace("'", "''") for x in mints)
text = template.read_text()
needle = "('__R0_MINT_PLACEHOLDER__')"
assert text.count(needle) == 1
out = H / "sql" / "S0_AB_事件时点机会普查_v1_1_运行版.sql"
out.write_text(text.replace(needle, values))
print(out)
print("r0_mints", len(mints))
