#!/usr/bin/env python3
"""Build bounded public-visibility timing tables from immutable T-026 polls."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


POINT_KEY = Tuple[str, str, str]


def parse_time(value: str) -> Optional[datetime]:
    value = value.strip()
    if not value:
        return None
    return datetime.fromisoformat(value)


def minutes(later: datetime, earlier: datetime) -> str:
    if later.tzinfo is not None and earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=later.tzinfo)
    elif later.tzinfo is None and earlier.tzinfo is not None:
        later = later.replace(tzinfo=earlier.tzinfo)
    return "{:.3f}".format((later - earlier).total_seconds() / 60.0)


def load_polls(root: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for path in sorted(root.glob("*/observations.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                row["source_run"] = path.parent.name
                rows.append(row)
    rows.sort(key=lambda row: row["Tseen_public"])
    return rows


def build(
    rows: List[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    previous: Dict[POINT_KEY, Dict[str, str]] = {}
    ledger: List[Dict[str, str]] = []
    latest: Dict[POINT_KEY, Dict[str, str]] = {}

    for row in rows:
        key = (row["candidate_id"], row["ps_id"], row["port_id"])
        seen = parse_time(row["Tseen_public"])
        measured = parse_time(row["latest_numeric_measurement_time"])
        if seen is None:
            raise ValueError("Tseen_public is empty for {}".format(key))
        prior = previous.get(key)
        prior_measured = (
            parse_time(prior["latest_numeric_measurement_time"]) if prior else None
        )
        if measured is not None and (prior_measured is None or measured > prior_measured):
            if prior is None:
                kind = "already_available_at_first_observed_poll"
                lower_poll = ""
                lower_lag = ""
            else:
                kind = "new_latest_between_consecutive_polls"
                lower_poll = prior["Tseen_public"]
                prior_seen = parse_time(lower_poll)
                lower_lag = minutes(prior_seen, measured) if prior_seen else ""
            ledger.append(
                {
                    "candidate_id": row["candidate_id"],
                    "ps_id": row["ps_id"],
                    "ps_name": row["ps_name"],
                    "port_id": row["port_id"],
                    "port_name": row["port_name"],
                    "measurement_time": row["latest_numeric_measurement_time"],
                    "not_yet_visible_at": lower_poll,
                    "first_observed_visible_at": row["Tseen_public"],
                    "lag_lower_minutes_exclusive": lower_lag,
                    "lag_upper_minutes_inclusive": minutes(seen, measured),
                    "evidence_kind": kind,
                    "source_run": row["source_run"],
                    "data_response_sha256": row["data_response_sha256"],
                }
            )
        previous[key] = row
        latest[key] = row

    state: List[Dict[str, str]] = []
    for key in sorted(latest):
        row = latest[key]
        measured = parse_time(row["latest_numeric_measurement_time"])
        seen = parse_time(row["Tseen_public"])
        state.append(
            {
                "candidate_id": row["candidate_id"],
                "ps_id": row["ps_id"],
                "ps_name": row["ps_name"],
                "port_id": row["port_id"],
                "port_name": row["port_name"],
                "latest_poll_at": row["Tseen_public"],
                "latest_numeric_measurement_time": row[
                    "latest_numeric_measurement_time"
                ],
                "latest_observed_lag_minutes": (
                    minutes(seen, measured) if seen and measured else ""
                ),
                "rows_with_numeric_measurement": row["rows_with_numeric_measurement"],
                "state": "numeric_visible" if measured else "no_numeric_visible",
                "source_run": row["source_run"],
                "data_response_sha256": row["data_response_sha256"],
            }
        )
    return ledger, state


def write_csv(path: Path, rows: List[Dict[str, str]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    option_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--poll-root", type=Path, default=option_root / "data" / "t026"
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=option_root / "data" / "t026_public_visibility.csv",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=option_root / "data" / "t026_public_state.csv",
    )
    args = parser.parse_args()
    rows = load_polls(args.poll_root)
    if not rows:
        raise SystemExit("no observations.csv files found")
    ledger, state = build(rows)
    write_csv(
        args.ledger,
        ledger,
        [
            "candidate_id",
            "ps_id",
            "ps_name",
            "port_id",
            "port_name",
            "measurement_time",
            "not_yet_visible_at",
            "first_observed_visible_at",
            "lag_lower_minutes_exclusive",
            "lag_upper_minutes_inclusive",
            "evidence_kind",
            "source_run",
            "data_response_sha256",
        ],
    )
    write_csv(
        args.state,
        state,
        [
            "candidate_id",
            "ps_id",
            "ps_name",
            "port_id",
            "port_name",
            "latest_poll_at",
            "latest_numeric_measurement_time",
            "latest_observed_lag_minutes",
            "rows_with_numeric_measurement",
            "state",
            "source_run",
            "data_response_sha256",
        ],
    )
    print(
        "poll rows: {}; visibility transitions: {}; point states: {}".format(
            len(rows), len(ledger), len(state)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
