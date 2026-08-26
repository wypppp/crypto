#!/usr/bin/env python3
"""Compare consecutive public-only polls without treating template fill as revision."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


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


def measurement_fields(row: dict[str, Any]) -> set[str]:
    return {
        key
        for key in row
        if key != "time"
        and (
            key.endswith(("-avg", "-zsavg", "-cou", "-flag", "-otherFlag"))
            or key.startswith("stop-")
        )
    }


def normalized(value: Any) -> str:
    return "" if value is None else str(value)


def load_run(run: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], dict[str, str]]]:
    observations: dict[tuple[str, str], dict[str, str]] = {}
    with (run / "observations.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            observations[(row["candidate_id"], row["port_id"])] = row
    payloads = {}
    for key in observations:
        point_key = "{}-{}".format(*key)
        path = run / "raw" / point_key / "data.json"
        payloads[key] = json.loads(path.read_text(encoding="utf-8"))
    return payloads, observations


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("poll_root", type=Path)
    parser.add_argument("events_csv", type=Path)
    parser.add_argument("summary_csv", type=Path)
    args = parser.parse_args()
    runs = sorted(
        path for path in args.poll_root.iterdir() if (path / "manifest.json").is_file()
    )
    if len(runs) < 2:
        raise SystemExit("at least two saved polls are required")
    loaded = {run.name: load_run(run) for run in runs}
    events: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for prior_run, current_run in zip(runs, runs[1:]):
        prior_payloads, prior_observations = loaded[prior_run.name]
        current_payloads, current_observations = loaded[current_run.name]
        for key in sorted(set(prior_payloads) & set(current_payloads)):
            if (
                prior_observations[key].get("measurement_date")
                != current_observations[key].get("measurement_date")
            ):
                continue
            prior_rows = {
                str(row.get("time")): row
                for row in (prior_payloads[key].get("data") or [])
                if isinstance(row, dict) and row.get("time")
            }
            current_rows = {
                str(row.get("time")): row
                for row in (current_payloads[key].get("data") or [])
                if isinstance(row, dict) and row.get("time")
            }
            pair_counts = {
                "new_numeric_visibility_count": 0,
                "revised_existing_numeric_count": 0,
                "unchanged_existing_numeric_count": 0,
                "numeric_disappeared_count": 0,
                "template_change_count": 0,
            }
            for measured_at in sorted(set(prior_rows) | set(current_rows)):
                left = prior_rows.get(measured_at, {})
                right = current_rows.get(measured_at, {})
                left_numeric = is_numeric_row(left)
                right_numeric = is_numeric_row(right)
                fields = sorted(measurement_fields(left) | measurement_fields(right))
                changed = [
                    field for field in fields if normalized(left.get(field)) != normalized(right.get(field))
                ]
                if not left_numeric and right_numeric:
                    kind = "new_numeric_visibility"
                elif left_numeric and not right_numeric:
                    kind = "numeric_disappeared"
                elif left_numeric and right_numeric and changed:
                    kind = "revision_existing_numeric"
                elif left_numeric and right_numeric:
                    kind = "unchanged_existing_numeric"
                elif changed:
                    kind = "template_change"
                else:
                    continue
                count_field = {
                    "new_numeric_visibility": "new_numeric_visibility_count",
                    "revision_existing_numeric": "revised_existing_numeric_count",
                    "unchanged_existing_numeric": "unchanged_existing_numeric_count",
                    "numeric_disappeared": "numeric_disappeared_count",
                    "template_change": "template_change_count",
                }[kind]
                pair_counts[count_field] += 1
                if kind != "unchanged_existing_numeric":
                    observation = current_observations[key]
                    events.append(
                        {
                            "candidate_id": key[0],
                            "ps_id": observation["ps_id"],
                            "port_id": key[1],
                            "measurement_time": measured_at,
                            "prior_run_id": prior_run.name,
                            "current_run_id": current_run.name,
                            "prior_seen_at": prior_observations[key]["Tseen_public"],
                            "current_seen_at": observation["Tseen_public"],
                            "change_kind": kind,
                            "changed_field_count": len(changed),
                            "changed_fields": "|".join(changed),
                            "interpretation": (
                                "Existing numeric row changed after prior observation"
                                if kind == "revision_existing_numeric"
                                else "Not evidence of revision to a previously numeric row"
                            ),
                        }
                    )
            observation = current_observations[key]
            summaries.append(
                {
                    "candidate_id": key[0],
                    "ps_id": observation["ps_id"],
                    "port_id": key[1],
                    "prior_run_id": prior_run.name,
                    "current_run_id": current_run.name,
                    **pair_counts,
                    "s5_interpretation": (
                        "revision_observed"
                        if pair_counts["revised_existing_numeric_count"]
                        else "no_revision_observed_in_this_bounded_pair"
                    ),
                }
            )

    write_csv(
        args.events_csv,
        events,
        [
            "candidate_id",
            "ps_id",
            "port_id",
            "measurement_time",
            "prior_run_id",
            "current_run_id",
            "prior_seen_at",
            "current_seen_at",
            "change_kind",
            "changed_field_count",
            "changed_fields",
            "interpretation",
        ],
    )
    write_csv(
        args.summary_csv,
        summaries,
        [
            "candidate_id",
            "ps_id",
            "port_id",
            "prior_run_id",
            "current_run_id",
            "new_numeric_visibility_count",
            "revised_existing_numeric_count",
            "unchanged_existing_numeric_count",
            "numeric_disappeared_count",
            "template_change_count",
            "s5_interpretation",
        ],
    )
    print(
        json.dumps(
            {
                "run_count": len(runs),
                "point_pair_count": len(summaries),
                "event_count": len(events),
                "new_numeric_visibility_count": sum(
                    row["new_numeric_visibility_count"] for row in summaries
                ),
                "revised_existing_numeric_count": sum(
                    row["revised_existing_numeric_count"] for row in summaries
                ),
                "numeric_disappeared_count": sum(
                    row["numeric_disappeared_count"] for row in summaries
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
