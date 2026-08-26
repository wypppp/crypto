#!/usr/bin/env python3
"""Build slot- and point-day timing evidence for the frozen public wave."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SHANGHAI = timezone(timedelta(hours=8))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


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


def canonical_hash(value: Any) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parsed(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    return result if result.tzinfo else result.replace(tzinfo=SHANGHAI)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schedule_csv", type=Path)
    parser.add_argument("poll_root", type=Path)
    parser.add_argument("slot_output", type=Path)
    parser.add_argument("point_slot_output", type=Path)
    parser.add_argument("point_day_output", type=Path)
    args = parser.parse_args()
    schedule = read_csv(args.schedule_csv)
    slot_rows: list[dict[str, Any]] = []
    point_slot_rows: list[dict[str, Any]] = []

    for slot in schedule:
        if slot["status"] != "completed":
            continue
        run_id = slot["actual_run_id"]
        run = args.poll_root / run_id
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        target_time = parsed(
            "{}T{}:00+08:00".format(slot["measurement_date"], slot["target_hour_label"])
        )
        request_times = [parsed(record["fetched_at"]) for record in manifest.get("files") or []]
        observations = {
            (row["candidate_id"], row["port_id"]): row
            for row in read_csv(run / "observations.csv")
        }
        visible_count = 0
        for key, observation in sorted(observations.items()):
            point_key = "{}-{}".format(*key)
            payload = json.loads(
                (run / "raw" / point_key / "data.json").read_text(encoding="utf-8")
            )
            target_label = target_time.strftime("%Y-%m-%d %H:%M:%S")
            matches = [
                row
                for row in (payload.get("data") or [])
                if isinstance(row, dict) and str(row.get("time")) == target_label
            ]
            target_row = matches[0] if len(matches) == 1 else {}
            visible = is_numeric_row(target_row)
            visible_count += int(visible)
            seen_at = parsed(observation["Tseen_public"])
            point_slot_rows.append(
                {
                    "study_day": slot["study_day"],
                    "measurement_date": slot["measurement_date"],
                    "target_hour_label": slot["target_hour_label"],
                    "poll_offset_minutes": slot[
                        "poll_offset_from_hour_start_minutes"
                    ],
                    "run_id": run_id,
                    "candidate_id": observation["candidate_id"],
                    "ps_id": observation["ps_id"],
                    "port_id": observation["port_id"],
                    "Tseen_public": observation["Tseen_public"],
                    "actual_seen_offset_minutes": "{:.3f}".format(
                        (seen_at - target_time).total_seconds() / 60
                    ),
                    "target_row_found": int(len(matches) == 1),
                    "target_numeric_visible": int(visible),
                    "target_row_sha256": canonical_hash(target_row) if matches else "",
                    "latest_numeric_measurement_time": observation[
                        "latest_numeric_measurement_time"
                    ],
                    "data_response_sha256": observation["data_response_sha256"],
                }
            )
        scheduled = parsed(slot["scheduled_poll_at"])
        slot_rows.append(
            {
                "study_day": slot["study_day"],
                "measurement_date": slot["measurement_date"],
                "target_hour_label": slot["target_hour_label"],
                "poll_offset_minutes": slot["poll_offset_from_hour_start_minutes"],
                "scheduled_poll_at": slot["scheduled_poll_at"],
                "run_id": run_id,
                "actual_first_response_at": min(request_times).isoformat(),
                "actual_last_response_at": max(request_times).isoformat(),
                "first_response_deviation_seconds": "{:.3f}".format(
                    (min(request_times) - scheduled).total_seconds()
                ),
                "point_count": len(observations),
                "target_numeric_visible_point_count": visible_count,
                "target_no_numeric_point_count": len(observations) - visible_count,
                "manifest_sha256": file_hash(run / "manifest.json"),
            }
        )

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in point_slot_rows:
        grouped[
            (
                row["measurement_date"],
                row["candidate_id"],
                row["ps_id"],
                row["port_id"],
            )
        ].append(row)
    point_day_rows: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: int(row["poll_offset_minutes"]))
        visible_rows = [row for row in rows if row["target_numeric_visible"] == 1]
        first_visible = visible_rows[0] if visible_rows else None
        prior_nonvisible = [
            row
            for row in rows
            if row["target_numeric_visible"] == 0
            and (
                first_visible is None
                or int(row["poll_offset_minutes"])
                < int(first_visible["poll_offset_minutes"])
            )
        ]
        cutoff_offset = (
            int(first_visible["poll_offset_minutes"])
            if first_visible
            else max(int(row["poll_offset_minutes"]) for row in rows) + 1
        )
        scheduled_earlier = [
            slot
            for slot in schedule
            if slot["measurement_date"] == key[0]
            and int(slot["poll_offset_from_hour_start_minutes"]) < cutoff_offset
        ]
        incomplete_earlier = any(slot["status"] != "completed" for slot in scheduled_earlier)
        visible_hashes = [row["target_row_sha256"] for row in visible_rows]
        revision_count = sum(
            left != right for left, right in zip(visible_hashes, visible_hashes[1:])
        )
        point_day_rows.append(
            {
                "measurement_date": key[0],
                "candidate_id": key[1],
                "ps_id": key[2],
                "port_id": key[3],
                "completed_poll_count": len(rows),
                "first_observed_numeric_offset_minutes": (
                    first_visible["poll_offset_minutes"] if first_visible else "not_observed"
                ),
                "first_observed_numeric_at": (
                    first_visible["Tseen_public"] if first_visible else "not_observed"
                ),
                "last_completed_nonvisible_offset_before_first": (
                    max(int(row["poll_offset_minutes"]) for row in prior_nonvisible)
                    if prior_nonvisible
                    else "none"
                ),
                "earlier_scheduled_slot_incomplete": int(incomplete_earlier),
                "numeric_target_row_hash_change_count": revision_count,
                "timing_bound_status": (
                    "upper_bound_only_earlier_slot_incomplete"
                    if first_visible and incomplete_earlier
                    else "interval_bound"
                    if first_visible and prior_nonvisible
                    else "upper_bound_only_first_completed_poll"
                    if first_visible
                    else "not_visible_through_latest_completed_poll"
                ),
                "s5_revision_status": (
                    "revision_observed"
                    if revision_count
                    else "no_revision_observed_in_completed_slots"
                ),
            }
        )

    write_csv(
        args.slot_output,
        slot_rows,
        [
            "study_day",
            "measurement_date",
            "target_hour_label",
            "poll_offset_minutes",
            "scheduled_poll_at",
            "run_id",
            "actual_first_response_at",
            "actual_last_response_at",
            "first_response_deviation_seconds",
            "point_count",
            "target_numeric_visible_point_count",
            "target_no_numeric_point_count",
            "manifest_sha256",
        ],
    )
    write_csv(
        args.point_slot_output,
        point_slot_rows,
        [
            "study_day",
            "measurement_date",
            "target_hour_label",
            "poll_offset_minutes",
            "run_id",
            "candidate_id",
            "ps_id",
            "port_id",
            "Tseen_public",
            "actual_seen_offset_minutes",
            "target_row_found",
            "target_numeric_visible",
            "target_row_sha256",
            "latest_numeric_measurement_time",
            "data_response_sha256",
        ],
    )
    write_csv(
        args.point_day_output,
        point_day_rows,
        [
            "measurement_date",
            "candidate_id",
            "ps_id",
            "port_id",
            "completed_poll_count",
            "first_observed_numeric_offset_minutes",
            "first_observed_numeric_at",
            "last_completed_nonvisible_offset_before_first",
            "earlier_scheduled_slot_incomplete",
            "numeric_target_row_hash_change_count",
            "timing_bound_status",
            "s5_revision_status",
        ],
    )
    print(
        json.dumps(
            {
                "completed_slot_count": len(slot_rows),
                "point_slot_count": len(point_slot_rows),
                "point_day_count": len(point_day_rows),
                "target_visible_point_days": sum(
                    row["first_observed_numeric_offset_minutes"] != "not_observed"
                    for row in point_day_rows
                ),
                "target_row_revision_count": sum(
                    row["numeric_target_row_hash_change_count"] for row in point_day_rows
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
