"""Bounded semantic checks with concrete counterexamples, no network calls."""
from pathlib import Path
from datetime import datetime, timedelta
import json
import re
import csv
import io
import zipfile
import hashlib

HERE = Path(__file__).resolve().parent
RT = HERE / "snapshot/RT"
out = {}

# The source uses a cohort-wide fixed lower date and unbounded cumulative sums.
# Its name/card says prior 30 days. Demonstrate difference without claiming how
# many actual records were affected; that needs unexported creation events.
sql = (RT / "dq1f/sql/F1_val.sql").read_text()
hist = sql.split("dev_hist AS (", 1)[1].split("\ncomp AS (", 1)[0]
assert "DATE '2026-05-09'" in hist
assert "UNBOUNDED PRECEDING AND 1 PRECEDING" in hist
target = datetime(2026, 6, 14, 12)
prior = [datetime(2026, 5, 10, 12), datetime(2026, 6, 1, 12)]
fixed = [x for x in prior if datetime(2026, 5, 9) <= x < target]
rolling = [x for x in prior if target-timedelta(days=30) <= x < target]
assert len(fixed) == 2 and len(rolling) == 1
out["creator_history_counterexample"] = {
    "source": "dq1f/sql/F1_val.sql:31-68", "target_creation": target.isoformat(),
    "previous_launches": [x.isoformat() for x in prior],
    "sql_fixed_lower_boundary_count": len(fixed), "intended_rolling30_count": len(rolling),
    "actual_affected_tokens": "unknown: creation history is not in exported F1/F2 CSVs",
    "additional_note": "SQL counts at creation, not entry +30m; same-second launches lack a complete ordering key."
}

# Peak occurs late does not mean it failed the threshold earlier.
path = [(20, 12), (40, 20)]
ms60 = max(x[1] for x in path); peakday = max(path, key=lambda x:x[1])[0]
ms30 = max(x[1] for x in path if x[0] <= 30)
assert (ms60 >= 10 and peakday <= 30) is False and ms30 >= 10
out["label_counterexample"] = {"path_day_multiple": path, "peak_filter_winner": False,
                                "actual30_winner": True}

# Prospective protocol issue: service identity derived from all buyers that
# week is not necessarily available to an early-week trading decision.
early = {"S": 1, "other": 199}
later = {"S": 21, "other": 199}
out["weekly_service_exclusion_counterexample"] = {
    "source": "dq10/DQ10M_卡_草案.md service exclusion rule 3",
    "early_share": early["S"] / sum(early.values()),
    "end_week_share": later["S"] / sum(later.values()),
    "threshold": .01,
    "early_excluded": early["S"] / sum(early.values()) >= .01,
    "end_week_excluded": later["S"] / sum(later.values()) >= .01,
    "scope": "Design defect if current-week totals are used retrospectively; no executed economic result asserted."
}

# Independently check the three-valued CEX tail counts, preserving unknowns.
with (RT / "dq2/runs/20260915T013907Z-full/results.csv").open() as f:
    rows = list(csv.DictReader(f))
tail = {}
for field in ["a30_H180_mstar", "a30_H180_mstar_close"]:
    for threshold in [10, 50, 100]:
        counts = {"yes": 0, "no": 0, "unknown": 0}
        for row in rows:
            val = float(row[field]) if row.get(field) else None
            if val is not None and val >= threshold: label = "yes"
            elif row["a30_H180_status"] == "complete": label = "no"
            else: label = "unknown"
            counts[label] += 1
        tail[f"{field}>={threshold}"] = counts
out["dq2_three_valued_counts"] = tail

# Raw price check for the two decisive CEX examples. No original helper import.
rawchecks = []
for base in ["GMT", "GALA"]:
    row = next(r for r in rows if r["base"] == base)
    rawdir = RT / "dq2/raw"
    price = float(row["a30_price"])
    start = datetime.fromisoformat(row["a30_time_utc"]).date()
    end = datetime.fromisoformat(row["T0_day"]).date() + timedelta(days=180)
    daily = []
    files = sorted(rawdir.rglob(f"{base}USDT-1d-*.zip"))
    for p in files:
        with zipfile.ZipFile(p) as z:
            for r in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))):
                if not r or not r[0].isdigit(): continue
                t = int(r[0]); t = t/1e6 if t > 1e14 else t/1e3
                from datetime import timezone
                day = datetime.fromtimestamp(t, timezone.utc).date()
                if start <= day <= end: daily.append((day, float(r[2]), float(r[4])))
    rec = {"base": base, "stored_entry_price": price, "daily_file_count": len(files), "days": len(daily)}
    if daily:
        rec.update({"high_multiple": max(r[1] for r in daily)/price,
                    "close_multiple": max(r[2] for r in daily)/price,
                    "recorded_high_multiple": float(row["a30_H180_mstar"]),
                    "recorded_close_multiple": float(row["a30_H180_mstar_close"]),
                    "scope": "Raw daily-bar reconstruction with saved entry denominator, not orderbook execution or independent entry-price reconstruction."})
    rawchecks.append(rec)
out["cex_raw_daily_checks"] = rawchecks
(HERE / "checks/semantic_results.json").write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))
