#!/usr/bin/env python3
"""Summarize a saved historical current-view window from the public platform.

This analysis can describe returned coverage and within-row arithmetic.  Because
the rows are fetched after the measurement dates, it cannot establish original
publication latency, absence of later revisions, or actual production state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PHYSICAL_CODES = {"a19001", "a01011", "a01012", "a01014", "a01013"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).split("_", 1)[0].strip()
    if normalized in {"", "-", "--"}:
        return None
    try:
        result = float(normalized)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def is_numeric_row(row: dict[str, Any]) -> bool:
    return any(
        key.endswith(("-avg", "-zsavg", "-cou")) and numeric(value) is not None
        for key, value in row.items()
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def count_positive(rows: Iterable[dict[str, Any]], field: str) -> int:
    return sum((value := numeric(row.get(field))) is not None and value > 0 for row in rows)


def status_values(rows: Iterable[dict[str, Any]]) -> str:
    values = {
        str(row.get("stop-stopDcsType")).strip()
        for row in rows
        if row.get("stop-stopDcsType") not in (None, "", "-", "--")
    }
    return "|".join(sorted(values)) if values else "none_observed"


def mass_formula_counts(rows: Iterable[dict[str, Any]]) -> tuple[int, int]:
    triplets = 0
    within = 0
    for row in rows:
        volume = numeric(row.get("a00000-cou"))
        if volume is None or volume <= 0:
            continue
        pollutant_codes = {
            key[: -len("-avg")]
            for key in row
            if key.endswith("-avg") and key[: -len("-avg")] not in PHYSICAL_CODES
        }
        for code in pollutant_codes:
            concentration = numeric(row.get(code + "-avg"))
            mass = numeric(row.get(code + "-cou"))
            if concentration is None or mass is None or concentration <= 0:
                continue
            expected_mass = concentration * volume / 1_000_000.0
            if expected_mass <= 0:
                continue
            triplets += 1
            if abs(mass / expected_mass - 1.0) <= 0.02:
                within += 1
    return triplets, within


def ratio_cv(rows: Iterable[dict[str, Any]]) -> tuple[int, str]:
    ratios = []
    for row in rows:
        volume = numeric(row.get("a00000-cou"))
        velocity = numeric(row.get("a01011-avg"))
        if volume is not None and velocity is not None and volume > 0 and velocity > 0:
            ratios.append(volume / velocity)
    if len(ratios) < 2 or statistics.mean(ratios) == 0:
        return len(ratios), "not_estimable"
    return len(ratios), "{:.6f}".format(
        statistics.pstdev(ratios) / abs(statistics.mean(ratios))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("point_output", type=Path)
    parser.add_argument("daily_output", type=Path)
    args = parser.parse_args()
    snapshot = args.snapshot_dir.resolve()
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observations = manifest.get("observations") or []
    daily_output: list[dict[str, Any]] = []
    point_output: list[dict[str, Any]] = []

    for observation in observations:
        point_key = "{}-{}".format(observation["candidate_id"], observation["port_id"])
        data_path = snapshot / "raw" / point_key / "data.json"
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        rows = [row for row in (payload.get("data") or []) if isinstance(row, dict)]
        by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            measured_at = str(row.get("time") or "")
            by_day[measured_at[:10] if len(measured_at) >= 10 else "unknown"].append(row)

        numeric_rows = [row for row in rows if is_numeric_row(row)]
        normal_positive = sum(
            str(row.get("stop-stopDcsType") or "").strip() == "正常生产"
            and (numeric(row.get("a00000-cou")) or 0) > 0
            and (numeric(row.get("a01011-avg")) or 0) > 0
            for row in numeric_rows
        )
        triplets, formula_matches = mass_formula_counts(numeric_rows)
        pair_count, flow_velocity_cv = ratio_cv(numeric_rows)

        for day in sorted(by_day):
            day_rows = by_day[day]
            day_numeric = [row for row in day_rows if is_numeric_row(row)]
            day_triplets, day_matches = mass_formula_counts(day_numeric)
            daily_output.append(
                {
                    "run_id": manifest.get("run_id", snapshot.name),
                    "candidate_id": observation["candidate_id"],
                    "ps_id": observation["ps_id"],
                    "port_id": observation["port_id"],
                    "measurement_date": day,
                    "response_row_count": len(day_rows),
                    "numeric_measurement_row_count": len(day_numeric),
                    "positive_volume_row_count": count_positive(day_numeric, "a00000-cou"),
                    "positive_velocity_row_count": count_positive(day_numeric, "a01011-avg"),
                    "positive_temperature_row_count": count_positive(
                        day_numeric, "a01012-avg"
                    ),
                    "numeric_status_values": status_values(day_numeric),
                    "mass_formula_triplet_count": day_triplets,
                    "mass_formula_within_2pct_count": day_matches,
                    "coverage_interpretation": "historical_current_view_not_original_availability",
                    "data_response_sha256": sha256(data_path),
                }
            )

        day_numeric_counts = [
            sum(is_numeric_row(row) for row in day_rows) for day_rows in by_day.values()
        ]
        numeric_count = len(numeric_rows)
        point_output.append(
            {
                "run_id": manifest.get("run_id", snapshot.name),
                "candidate_id": observation["candidate_id"],
                "ps_id": observation["ps_id"],
                "ps_name": observation["ps_name"],
                "port_id": observation["port_id"],
                "port_name": observation["port_name"],
                "measurement_start_date": manifest.get("measurement_start_date", ""),
                "measurement_end_date": manifest.get("measurement_end_date", ""),
                "calendar_day_count": len(by_day),
                "response_row_count": len(rows),
                "numeric_measurement_row_count": numeric_count,
                "numeric_coverage_share": (
                    "{:.6f}".format(numeric_count / len(rows)) if rows else "not_estimable"
                ),
                "days_with_any_numeric": sum(count > 0 for count in day_numeric_counts),
                "complete_24_numeric_days": sum(count == 24 for count in day_numeric_counts),
                "positive_volume_row_count": count_positive(numeric_rows, "a00000-cou"),
                "positive_velocity_row_count": count_positive(numeric_rows, "a01011-avg"),
                "positive_temperature_row_count": count_positive(
                    numeric_rows, "a01012-avg"
                ),
                "normal_status_positive_volume_velocity_rows": normal_positive,
                "numeric_status_values": status_values(numeric_rows),
                "volume_velocity_pair_count": pair_count,
                "volume_velocity_ratio_cv": flow_velocity_cv,
                "mass_formula_triplet_count": triplets,
                "mass_formula_within_2pct_count": formula_matches,
                "mass_formula_within_2pct_share": (
                    "{:.6f}".format(formula_matches / triplets)
                    if triplets
                    else "not_estimable"
                ),
                "scss_event_count": len(payload.get("scssList") or []),
                "alarm_count": len(payload.get("alarmList") or []),
                "s4_status": (
                    "S4_blocked_no_numeric_measurement"
                    if not numeric_rows
                    else "S4_not_adjudicated_current_view_only"
                ),
                "independence_warning": (
                    "Mass emission matching concentration times gas volume is arithmetic "
                    "dependence, not an independent corroborating signal."
                ),
                "availability_warning": (
                    "Fetched after the measurement window; completeness cannot prove "
                    "original publication timing or absence of revisions."
                ),
                "data_response_sha256": sha256(data_path),
                "snapshot_manifest_sha256": sha256(manifest_path),
            }
        )

    write_csv(args.point_output, point_output)
    write_csv(args.daily_output, daily_output)
    print(
        json.dumps(
            {
                "run_id": manifest.get("run_id", snapshot.name),
                "point_count": len(point_output),
                "daily_row_count": len(daily_output),
                "points_with_complete_current_view": sum(
                    row["complete_24_numeric_days"] == row["calendar_day_count"]
                    for row in point_output
                ),
                "s4_pass_count": 0,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
