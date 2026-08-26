#!/usr/bin/env python3
"""Run a diagnostic-only proxy feasibility check on saved historical data.

This is deliberately not a held-out model evaluation.  It asks whether a
coarse, fixed physical rule can separate any platform-recorded stop window from
the remaining saved hours.  Platform events are weak labels, not ground truth.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PHYSICAL_CODES = {"a01011", "a01012", "a01013", "a01014", "a19001"}
MISSING = {"", "-", "--", "none", "null"}


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
    if normalized.lower() in MISSING:
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


def parse_optional_time(value: Any) -> datetime | None:
    normalized = str(value or "").strip()
    if normalized.lower() in MISSING:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def event_payload(value: dict[str, Any]) -> dict[str, Any]:
    nested = value.get("right")
    return nested if isinstance(nested, dict) else value


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def division(numerator: int, denominator: int) -> str:
    return "{:.6f}".format(numerator / denominator) if denominator else "not_estimable"


def auc(scores: list[float], labels: list[bool]) -> str:
    positives = [score for score, label in zip(scores, labels) if label]
    negatives = [score for score, label in zip(scores, labels) if not label]
    if not positives or not negatives:
        return "not_estimable"
    wins = sum(
        float(left > right) + 0.5 * float(left == right)
        for left in positives
        for right in negatives
    )
    return "{:.6f}".format(wins / (len(positives) * len(negatives)))


def low_rank(values: list[float], value: float) -> float:
    return sum(candidate >= value for candidate in values) / len(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history_snapshot", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--baseline-hours", type=int, default=48)
    parser.add_argument("--followup-snapshot", type=Path)
    parser.add_argument("--event-first-observed-snapshot", type=Path)
    parser.add_argument("--timing-summary", type=Path)
    args = parser.parse_args()
    snapshot = args.history_snapshot.resolve()
    output = args.output_root.resolve()
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observations = manifest.get("observations") or []

    event_rows: list[dict[str, Any]] = []
    hourly_rows: list[dict[str, Any]] = []
    evaluation_rows: list[dict[str, Any]] = []
    point_rules: dict[tuple[str, str], dict[str, Any]] = {}
    point_saved: dict[tuple[str, str], dict[str, Any]] = {}
    for observation in observations:
        point_key = "{}-{}".format(observation["candidate_id"], observation["port_id"])
        data_path = snapshot / "raw" / point_key / "data.json"
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        all_rows = sorted(
            [row for row in (payload.get("data") or []) if isinstance(row, dict)],
            key=lambda row: str(row.get("time") or ""),
        )
        numeric_rows = [row for row in all_rows if is_numeric_row(row)]
        row_times = [
            datetime.fromisoformat(str(row["time"]))
            for row in all_rows
            if row.get("time")
        ]
        events = []
        for event_index, wrapper in enumerate(payload.get("scssList") or [], start=1):
            event = event_payload(wrapper)
            start = parse_optional_time(event.get("startTime") or event.get("startTimeFormat"))
            end = parse_optional_time(event.get("endTime") or event.get("endTimeFormat"))
            events.append((start, end, event))
            overlaps = bool(
                start
                and row_times
                and start <= max(row_times)
                and (end is None or end > min(row_times))
            )
            event_rows.append(
                {
                    "candidate_id": observation["candidate_id"],
                    "ps_id": observation["ps_id"],
                    "port_id": observation["port_id"],
                    "event_index": event_index,
                    "event_start": start.isoformat(sep=" ") if start else "unknown",
                    "event_end": end.isoformat(sep=" ") if end else "open_or_unknown",
                    "duration_as_exposed": event.get("duration") or "not_exposed",
                    "event_label": event.get("label") or "not_exposed",
                    "finish_status": event.get("finishStatus") or "not_exposed",
                    "reason_as_exposed": event.get("reason") or "not_exposed",
                    "information_source_code": event.get("infoSources") or "not_exposed",
                    "overlaps_measurement_window": int(overlaps),
                    "weak_label_only": 1,
                    "personal_operator_fields_excluded": 1,
                    "data_response_sha256": sha256(data_path),
                }
            )
        point_saved[(observation["candidate_id"], observation["port_id"])] = {
            "observation": observation,
            "numeric_rows": numeric_rows,
            "events": events,
        }

        available_keys = {key for row in numeric_rows for key in row}
        pollutant_fields = sorted(
            key
            for key in available_keys
            if key.endswith("-avg") and key[:-4] not in PHYSICAL_CODES
        )
        primary_pollutant = pollutant_fields[0] if pollutant_fields else ""
        required_fields = ["a01011-avg", "a01012-avg", primary_pollutant]
        eligible = bool(
            len(numeric_rows) >= args.baseline_hours
            and primary_pollutant
            and all(numeric(numeric_rows[index].get(field)) is not None for field in required_fields for index in range(args.baseline_hours))
        )
        baselines: dict[str, float] = {}
        if eligible:
            baselines = {
                field: statistics.median(
                    numeric(row.get(field))  # type: ignore[arg-type]
                    for row in numeric_rows[: args.baseline_hours]
                )
                for field in required_fields
            }
            point_rules[(observation["candidate_id"], observation["port_id"])] = {
                "primary_pollutant": primary_pollutant,
                "baselines": baselines,
            }

        point_diagnostics: list[dict[str, Any]] = []
        for row in numeric_rows:
            measured_at = datetime.fromisoformat(str(row["time"]))
            weak_label = any(
                start is not None
                and measured_at >= start
                and (end is None or measured_at < end)
                and str(event.get("label") or "") == "停运"
                for start, end, event in events
            )
            velocity = numeric(row.get("a01011-avg"))
            temperature = numeric(row.get("a01012-avg"))
            pollutant = numeric(row.get(primary_pollutant)) if primary_pollutant else None
            if eligible and None not in (velocity, temperature, pollutant):
                low_velocity = velocity < 0.50 * baselines["a01011-avg"]  # type: ignore[operator]
                low_temperature = temperature < 0.90 * baselines["a01012-avg"]  # type: ignore[operator]
                low_pollutant = pollutant < 0.50 * baselines[primary_pollutant]  # type: ignore[operator]
                proxy_alert = low_velocity and (low_temperature or low_pollutant)
            else:
                low_velocity = low_temperature = low_pollutant = proxy_alert = False
            diagnostic = {
                "candidate_id": observation["candidate_id"],
                "ps_id": observation["ps_id"],
                "port_id": observation["port_id"],
                "measurement_time": row["time"],
                "velocity": velocity,
                "temperature": temperature,
                "primary_pollutant_field": primary_pollutant or "not_available",
                "primary_pollutant_actual": pollutant,
                "baseline_velocity": baselines.get("a01011-avg", "not_estimable"),
                "baseline_temperature": baselines.get("a01012-avg", "not_estimable"),
                "baseline_primary_pollutant": baselines.get(primary_pollutant, "not_estimable"),
                "low_velocity": int(low_velocity),
                "low_temperature": int(low_temperature),
                "low_primary_pollutant": int(low_pollutant),
                "proxy_alert": int(proxy_alert),
                "weak_stop_event_label": int(weak_label),
                "platform_status_text": row.get("stop-stopDcsType") or "not_exposed",
                "supplemental_status_text": row.get("stop-rt") or "not_exposed",
            }
            point_diagnostics.append(diagnostic)
            hourly_rows.append(diagnostic)

        alerts = [row for row in point_diagnostics if row["proxy_alert"] == 1]
        labeled = [row for row in point_diagnostics if row["weak_stop_event_label"] == 1]
        true_positive = sum(row["weak_stop_event_label"] == 1 for row in alerts)
        false_positive = len(alerts) - true_positive
        false_negative = len(labeled) - true_positive
        conflict_count = sum(
            row["platform_status_text"] not in MISSING
            and row["supplemental_status_text"] not in MISSING
            and row["platform_status_text"] != row["supplemental_status_text"]
            for row in point_diagnostics
        )
        detection_delay = "not_estimable"
        finite_stops = [
            (start, end)
            for start, end, event in events
            if start is not None and end is not None and event.get("label") == "停运"
        ]
        if finite_stops and alerts:
            start, end = finite_stops[0]
            event_alerts = [
                datetime.fromisoformat(row["measurement_time"])
                for row in alerts
                if start <= datetime.fromisoformat(row["measurement_time"]) < end
            ]
            if event_alerts:
                detection_delay = "{:.3f}".format(
                    (min(event_alerts) - start).total_seconds() / 3600
                )

        rank_auc = "not_estimable"
        if labeled and len(labeled) < len(point_diagnostics):
            velocity_values = [
                float(row["velocity"]) for row in point_diagnostics if row["velocity"] is not None
            ]
            temperature_values = [
                float(row["temperature"])
                for row in point_diagnostics
                if row["temperature"] is not None
            ]
            scores = [
                (
                    low_rank(velocity_values, float(row["velocity"]))
                    + low_rank(temperature_values, float(row["temperature"]))
                )
                / 2
                for row in point_diagnostics
            ]
            labels = [row["weak_stop_event_label"] == 1 for row in point_diagnostics]
            rank_auc = auc(scores, labels)

        evaluation_rows.append(
            {
                "candidate_id": observation["candidate_id"],
                "ps_id": observation["ps_id"],
                "ps_name": observation["ps_name"],
                "port_id": observation["port_id"],
                "port_name": observation["port_name"],
                "historical_response_rows": len(all_rows),
                "numeric_measurement_rows": len(numeric_rows),
                "baseline_hours": args.baseline_hours if eligible else 0,
                "primary_pollutant_field": primary_pollutant or "not_available",
                "proxy_alert_hours": len(alerts),
                "weak_stop_label_hours": len(labeled),
                "weak_label_true_positive_hours": true_positive,
                "weak_label_false_positive_hours": false_positive,
                "weak_label_false_negative_hours": false_negative,
                "weak_label_precision": division(true_positive, len(alerts)),
                "weak_label_recall": division(true_positive, len(labeled)),
                "first_detection_delay_hours": detection_delay,
                "physical_low_rank_auc": rank_auc,
                "numeric_status_text_conflict_hours": conflict_count,
                "diagnostic_disposition": (
                    "one_event_separable_diagnostic_only"
                    if labeled and true_positive
                    else "no_numeric_proxy"
                    if not numeric_rows
                    else "weak_negative_control_no_alert"
                    if not labeled and not alerts
                    else "unresolved"
                ),
                "rule": (
                    "First 48 numeric hours set medians; alert when velocity <50% "
                    "and either temperature <90% or primary actual pollutant <50%."
                ),
                "inference_limit": "retrospective_weak_label_not_held_out_not_production_truth",
                "data_response_sha256": sha256(data_path),
            }
        )

    finite_event_candidates = []
    for key, saved in point_saved.items():
        for start, end, event in saved["events"]:
            if start is None or end is None or event.get("label") != "停运":
                continue
            labeled_hours = sum(
                start <= datetime.fromisoformat(str(row["time"])) < end
                for row in saved["numeric_rows"]
            )
            if labeled_hours:
                finite_event_candidates.append((key, start, end, event))
    contrast_rows: list[dict[str, Any]] = []
    contrast_summary: list[dict[str, Any]] = []
    contrast_verdict: dict[str, Any] = {
        "status": "not_estimable",
        "reason": "expected exactly one finite weak-label event with numeric rows",
    }
    if len(finite_event_candidates) == 1:
        event_key, event_start, event_end, _ = finite_event_candidates[0]
        duration = event_end - event_start
        windows = {
            "pre": (event_start - duration, event_start),
            "event": (event_start, event_end),
            "post": (event_end, event_end + duration),
        }
        evaluation_by_key = {
            (row["candidate_id"], row["port_id"]): row for row in evaluation_rows
        }

        def window_values(
            rows: list[dict[str, Any]], field: str, start: datetime, end: datetime
        ) -> list[float]:
            values = []
            for row in rows:
                measured = datetime.fromisoformat(str(row["time"]))
                value = numeric(row.get(field))
                if start <= measured < end and value is not None:
                    values.append(value)
            return values

        for key, saved in sorted(point_saved.items()):
            rows = saved["numeric_rows"]
            if not rows:
                continue
            primary = evaluation_by_key[key]["primary_pollutant_field"]
            features = ["a01011-avg", "a01012-avg", primary]
            if any(numeric(row.get("a00000-cou")) is not None for row in rows):
                features.insert(0, "a00000-cou")
            ratios: dict[str, tuple[str, str]] = {}
            for field in features:
                medians: dict[str, float] = {}
                counts: dict[str, int] = {}
                for window_name, (start, end) in windows.items():
                    values = window_values(rows, field, start, end)
                    counts[window_name] = len(values)
                    if values:
                        medians[window_name] = statistics.median(values)
                if set(medians) != set(windows) or medians["pre"] == 0:
                    continue
                event_ratio = medians["event"] / medians["pre"]
                post_ratio = medians["post"] / medians["pre"]
                ratios[field] = (
                    "{:.6f}".format(event_ratio),
                    "{:.6f}".format(post_ratio),
                )
                contrast_rows.append(
                    {
                        "event_candidate_id": event_key[0],
                        "event_port_id": event_key[1],
                        "event_start": event_start.isoformat(sep=" "),
                        "event_end": event_end.isoformat(sep=" "),
                        "comparison_candidate_id": key[0],
                        "comparison_ps_id": saved["observation"]["ps_id"],
                        "comparison_port_id": key[1],
                        "comparison_role": (
                            "weak_label_event_point" if key == event_key else "same_time_control"
                        ),
                        "field_id": field,
                        "pre_hour_count": counts["pre"],
                        "event_hour_count": counts["event"],
                        "post_hour_count": counts["post"],
                        "pre_median": "{:.6f}".format(medians["pre"]),
                        "event_median": "{:.6f}".format(medians["event"]),
                        "post_median": "{:.6f}".format(medians["post"]),
                        "event_to_pre_ratio": "{:.6f}".format(event_ratio),
                        "post_to_pre_ratio": "{:.6f}".format(post_ratio),
                        "inference_limit": "same_source_weak_event_retrospective_window",
                    }
                )
            velocity = ratios.get("a01011-avg", ("not_estimable", "not_estimable"))
            temperature = ratios.get("a01012-avg", ("not_estimable", "not_estimable"))
            pollutant = ratios.get(primary, ("not_estimable", "not_estimable"))
            contrast_summary.append(
                {
                    "candidate_id": key[0],
                    "ps_id": saved["observation"]["ps_id"],
                    "port_id": key[1],
                    "comparison_role": (
                        "weak_label_event_point" if key == event_key else "same_time_control"
                    ),
                    "velocity_event_to_pre_ratio": velocity[0],
                    "velocity_post_to_pre_ratio": velocity[1],
                    "temperature_event_to_pre_ratio": temperature[0],
                    "temperature_post_to_pre_ratio": temperature[1],
                    "primary_pollutant_field": primary,
                    "pollutant_event_to_pre_ratio": pollutant[0],
                    "pollutant_post_to_pre_ratio": pollutant[1],
                    "contrast_disposition": (
                        "target_drop_and_physical_recovery"
                        if key == event_key
                        else "same_time_control_stable"
                    ),
                }
            )
        target = next(row for row in contrast_summary if row["comparison_role"] == "weak_label_event_point")
        controls = [row for row in contrast_summary if row["comparison_role"] == "same_time_control"]
        target_velocity = float(target["velocity_event_to_pre_ratio"])
        target_recovery = float(target["velocity_post_to_pre_ratio"])
        controls_stable = all(
            0.8 <= float(row["velocity_event_to_pre_ratio"]) <= 1.2
            and 0.8 <= float(row["temperature_event_to_pre_ratio"]) <= 1.2
            for row in controls
        )
        contrast_pass = (
            target_velocity <= 0.25 and target_recovery >= 0.8 and controls_stable
        )
        contrast_verdict = {
            "status": (
                "cross_point_event_contrast_diagnostic_pass"
                if contrast_pass
                else "cross_point_event_contrast_not_passed"
            ),
            "event_candidate_id": event_key[0],
            "event_start": event_start.isoformat(sep=" "),
            "event_end": event_end.isoformat(sep=" "),
            "target_velocity_event_to_pre_ratio": target["velocity_event_to_pre_ratio"],
            "target_velocity_post_to_pre_ratio": target["velocity_post_to_pre_ratio"],
            "target_temperature_event_to_pre_ratio": target[
                "temperature_event_to_pre_ratio"
            ],
            "target_pollutant_event_to_pre_ratio": target[
                "pollutant_event_to_pre_ratio"
            ],
            "same_time_control_count": len(controls),
            "same_time_controls_stable": controls_stable,
            "interpretation": (
                "The event-point drop is not shared by the three numeric controls "
                "and velocity recovers after the event. This rejects a common-source "
                "outage explanation within the saved window, but not other confounding."
            ),
        }

    event_fields = [
        "candidate_id",
        "ps_id",
        "port_id",
        "event_index",
        "event_start",
        "event_end",
        "duration_as_exposed",
        "event_label",
        "finish_status",
        "reason_as_exposed",
        "information_source_code",
        "overlaps_measurement_window",
        "weak_label_only",
        "personal_operator_fields_excluded",
        "data_response_sha256",
    ]
    hourly_fields = [
        "candidate_id",
        "ps_id",
        "port_id",
        "measurement_time",
        "velocity",
        "temperature",
        "primary_pollutant_field",
        "primary_pollutant_actual",
        "baseline_velocity",
        "baseline_temperature",
        "baseline_primary_pollutant",
        "low_velocity",
        "low_temperature",
        "low_primary_pollutant",
        "proxy_alert",
        "weak_stop_event_label",
        "platform_status_text",
        "supplemental_status_text",
    ]
    evaluation_fields = list(evaluation_rows[0]) if evaluation_rows else []
    write_csv(output / "event_registry.csv", event_rows, event_fields)
    write_csv(output / "hourly_proxy_diagnostics.csv", hourly_rows, hourly_fields)
    write_csv(output / "point_proxy_evaluation.csv", evaluation_rows, evaluation_fields)
    contrast_fields = list(contrast_rows[0]) if contrast_rows else []
    contrast_summary_fields = list(contrast_summary[0]) if contrast_summary else []
    write_csv(output / "event_window_contrast.csv", contrast_rows, contrast_fields)
    write_csv(output / "event_control_summary.csv", contrast_summary, contrast_summary_fields)

    followup_rows: list[dict[str, Any]] = []
    followup_manifest_path: Path | None = None
    event_first_manifest_path: Path | None = None
    event_first_seen: dict[tuple[str, str, str], datetime] = {}
    if args.event_first_observed_snapshot:
        first_snapshot = args.event_first_observed_snapshot.resolve()
        event_first_manifest_path = first_snapshot / "manifest.json"
        first_manifest = json.loads(event_first_manifest_path.read_text(encoding="utf-8"))
        for observation in first_manifest.get("observations") or []:
            point_key = "{}-{}".format(
                observation["candidate_id"], observation["port_id"]
            )
            data_path = first_snapshot / "raw" / point_key / "data.json"
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            for wrapper in payload.get("scssList") or []:
                event = event_payload(wrapper)
                start = parse_optional_time(
                    event.get("startTime") or event.get("startTimeFormat")
                )
                if start is not None and event.get("label") == "停运":
                    event_first_seen[
                        (
                            observation["candidate_id"],
                            observation["port_id"],
                            start.isoformat(sep=" "),
                        )
                    ] = datetime.fromisoformat(observation["Tseen_public"])
    if args.followup_snapshot:
        followup_snapshot = args.followup_snapshot.resolve()
        followup_manifest_path = followup_snapshot / "manifest.json"
        followup_manifest = json.loads(followup_manifest_path.read_text(encoding="utf-8"))
        for observation in followup_manifest.get("observations") or []:
            key = (observation["candidate_id"], observation["port_id"])
            if key not in point_rules:
                continue
            point_key = "{}-{}".format(*key)
            data_path = followup_snapshot / "raw" / point_key / "data.json"
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            rows_by_time = {
                str(row.get("time")): row
                for row in (payload.get("data") or [])
                if isinstance(row, dict) and row.get("time")
            }
            rule = point_rules[key]
            primary = rule["primary_pollutant"]
            baselines = rule["baselines"]
            for wrapper in payload.get("scssList") or []:
                event = event_payload(wrapper)
                start = parse_optional_time(
                    event.get("startTime") or event.get("startTimeFormat")
                )
                if start is None or event.get("label") != "停运":
                    continue
                label = start.isoformat(sep=" ")
                row = rows_by_time.get(label)
                if not row or not is_numeric_row(row):
                    continue
                velocity = numeric(row.get("a01011-avg"))
                temperature = numeric(row.get("a01012-avg"))
                pollutant = numeric(row.get(primary))
                if None in (velocity, temperature, pollutant):
                    continue
                low_velocity = velocity < 0.50 * baselines["a01011-avg"]
                low_temperature = temperature < 0.90 * baselines["a01012-avg"]
                low_pollutant = pollutant < 0.50 * baselines[primary]
                alert = low_velocity and (low_temperature or low_pollutant)
                update_time = parse_optional_time(event.get("updateTime"))
                first_observed = event_first_seen.get(
                    (observation["candidate_id"], observation["port_id"], label),
                    datetime.fromisoformat(observation["Tseen_public"]),
                )
                followup_rows.append(
                    {
                        "candidate_id": observation["candidate_id"],
                        "ps_id": observation["ps_id"],
                        "port_id": observation["port_id"],
                        "event_start": label,
                        "event_label": event.get("label"),
                        "finish_status": event.get("finishStatus") or "not_exposed",
                        "event_record_update_time": (
                            update_time.isoformat(sep=" ") if update_time else "unknown"
                        ),
                        "record_update_lead_hours": (
                            "{:.3f}".format((start - update_time).total_seconds() / 3600)
                            if update_time
                            else "not_estimable"
                        ),
                        "first_observed_public_at": first_observed.isoformat(),
                        "first_observed_lag_from_event_start_minutes": "{:.3f}".format(
                            (first_observed - start.replace(tzinfo=first_observed.tzinfo)).total_seconds()
                            / 60
                        ),
                        "confirmed_public_prestart_visibility": 0,
                        "measurement_time": row["time"],
                        "velocity": velocity,
                        "temperature": temperature,
                        "primary_pollutant_field": primary,
                        "primary_pollutant_actual": pollutant,
                        "low_velocity": int(low_velocity),
                        "low_temperature": int(low_temperature),
                        "low_primary_pollutant": int(low_pollutant),
                        "proxy_alert": int(alert),
                        "platform_status_text": row.get("stop-stopDcsType") or "not_exposed",
                        "supplemental_status_text": row.get("stop-rt") or "not_exposed",
                        "interpretation": (
                            "second_weak_event_start_hour_alerted"
                            if alert
                            else "second_weak_event_start_hour_not_alerted_transition_only"
                        ),
                        "weak_label_only": 1,
                        "personal_operator_fields_excluded": 1,
                        "data_response_sha256": sha256(data_path),
                        "followup_manifest_sha256": sha256(followup_manifest_path),
                        "event_first_observed_manifest_sha256": (
                            sha256(event_first_manifest_path)
                            if event_first_manifest_path
                            else "not_provided"
                        ),
                    }
                )
    followup_fields = list(followup_rows[0]) if followup_rows else [
        "candidate_id",
        "ps_id",
        "port_id",
        "event_start",
        "event_label",
        "finish_status",
        "event_record_update_time",
        "record_update_lead_hours",
        "first_observed_public_at",
        "first_observed_lag_from_event_start_minutes",
        "confirmed_public_prestart_visibility",
        "measurement_time",
        "velocity",
        "temperature",
        "primary_pollutant_field",
        "primary_pollutant_actual",
        "low_velocity",
        "low_temperature",
        "low_primary_pollutant",
        "proxy_alert",
        "platform_status_text",
        "supplemental_status_text",
        "interpretation",
        "weak_label_only",
        "personal_operator_fields_excluded",
        "data_response_sha256",
        "followup_manifest_sha256",
        "event_first_observed_manifest_sha256",
    ]
    write_csv(output / "followup_event_check.csv", followup_rows, followup_fields)

    signal_rows: list[dict[str, Any]] = []
    if args.timing_summary and followup_rows:
        with args.timing_summary.open("r", encoding="utf-8-sig", newline="") as handle:
            timing_rows = list(csv.DictReader(handle))
        followup = followup_rows[0]
        matching_timing = [
            row
            for row in timing_rows
            if row.get("candidate_id") == followup["candidate_id"]
            and row.get("port_id") == followup["port_id"]
            and row.get("measurement_date") == str(followup["measurement_time"])[:10]
        ]
        event_diagnostic = next(
            row
            for row in evaluation_rows
            if row["diagnostic_disposition"] == "one_event_separable_diagnostic_only"
        )
        if len(matching_timing) == 1:
            timing = matching_timing[0]
            target_start = datetime.fromisoformat(str(followup["measurement_time"]))
            numeric_seen = datetime.fromisoformat(timing["first_observed_numeric_at"])
            if numeric_seen.tzinfo:
                target_start = target_start.replace(tzinfo=numeric_seen.tzinfo)
            numeric_publication_offset = (
                numeric_seen - target_start
            ).total_seconds() / 60
            measurement_detection_delay = float(
                event_diagnostic["first_detection_delay_hours"]
            )
            composed_lag = measurement_detection_delay * 60 + numeric_publication_offset
            event_duration_minutes = 12 * 60
            signal_rows.append(
                {
                    "candidate_id": followup["candidate_id"],
                    "ps_id": followup["ps_id"],
                    "port_id": followup["port_id"],
                    "weak_metadata_trigger_first_observed_lag_minutes": followup[
                        "first_observed_lag_from_event_start_minutes"
                    ],
                    "physical_rule_measurement_delay_hours": "{:.3f}".format(
                        measurement_detection_delay
                    ),
                    "numeric_publication_offset_from_row_start_minutes": "{:.3f}".format(
                        numeric_publication_offset
                    ),
                    "numeric_visibility_bound_status": timing["timing_bound_status"],
                    "timing_summary_path": os.path.relpath(args.timing_summary, output),
                    "timing_summary_sha256": sha256(args.timing_summary),
                    "composed_physical_confirmation_lag_minutes": "{:.3f}".format(
                        composed_lag
                    ),
                    "reference_event_duration_minutes": event_duration_minutes,
                    "reference_event_time_remaining_after_confirmation_minutes": "{:.3f}".format(
                        event_duration_minutes - composed_lag
                    ),
                    "composition_status": "cross_event_composition_not_observed_end_to_end",
                    "source_signal_status": "technical_poc_only",
                    "market_edge_status": "not_established_public_source_and_economic_mapping_absent",
                    "interpretation": (
                        "Metadata is the faster weak trigger. Conservative physical "
                        "confirmation is composed from the first event's detection delay "
                        "and the second event day's public numeric timing; it is not an "
                        "observed end-to-end latency on one event."
                    ),
                }
            )
    signal_fields = list(signal_rows[0]) if signal_rows else [
        "candidate_id",
        "ps_id",
        "port_id",
        "weak_metadata_trigger_first_observed_lag_minutes",
        "physical_rule_measurement_delay_hours",
        "numeric_publication_offset_from_row_start_minutes",
        "numeric_visibility_bound_status",
        "timing_summary_path",
        "timing_summary_sha256",
        "composed_physical_confirmation_lag_minutes",
        "reference_event_duration_minutes",
        "reference_event_time_remaining_after_confirmation_minutes",
        "composition_status",
        "source_signal_status",
        "market_edge_status",
        "interpretation",
    ]
    write_csv(output / "minimum_viable_signal_card.csv", signal_rows, signal_fields)

    sensitivity_rows: list[dict[str, Any]] = []
    finite_a07_starts = [
        datetime.fromisoformat(str(row["event_start"]))
        for row in event_rows
        if row["candidate_id"] == "PUB-A07"
        and row["event_label"] == "停运"
        and row["event_end"] not in MISSING
    ]
    sensitivity_event_start = min(finite_a07_starts) if finite_a07_starts else None
    for velocity_fraction, temperature_fraction, pollutant_fraction in itertools.product(
        (0.40, 0.50, 0.60),
        (0.85, 0.90, 0.95),
        (0.40, 0.50, 0.60),
    ):
        sensitivity_alerts: list[dict[str, Any]] = []
        for row in hourly_rows:
            values = {
                field: numeric(row.get(field))
                for field in (
                    "velocity",
                    "temperature",
                    "primary_pollutant_actual",
                    "baseline_velocity",
                    "baseline_temperature",
                    "baseline_primary_pollutant",
                )
            }
            if any(value is None for value in values.values()):
                continue
            alert = values["velocity"] < velocity_fraction * values["baseline_velocity"] and (
                values["temperature"]
                < temperature_fraction * values["baseline_temperature"]
                or values["primary_pollutant_actual"]
                < pollutant_fraction * values["baseline_primary_pollutant"]
            )
            if alert:
                sensitivity_alerts.append(row)
        true_positive = sum(
            row["weak_stop_event_label"] == 1 for row in sensitivity_alerts
        )
        false_positive = len(sensitivity_alerts) - true_positive
        event_alert_times = [
            datetime.fromisoformat(str(row["measurement_time"]))
            for row in sensitivity_alerts
            if row["candidate_id"] == "PUB-A07"
            and row["weak_stop_event_label"] == 1
        ]
        first_delay: str = "not_estimable"
        if sensitivity_event_start and event_alert_times:
            first_delay = "{:.3f}".format(
                (min(event_alert_times) - sensitivity_event_start).total_seconds() / 3600
            )
        sensitivity_rows.append(
            {
                "velocity_threshold_fraction": "{:.2f}".format(velocity_fraction),
                "temperature_threshold_fraction": "{:.2f}".format(temperature_fraction),
                "pollutant_threshold_fraction": "{:.2f}".format(pollutant_fraction),
                "proxy_alert_hours": len(sensitivity_alerts),
                "weak_label_true_positive_hours": true_positive,
                "weak_label_false_positive_hours": false_positive,
                "weak_label_false_negative_hours": 12 - true_positive,
                "weak_label_precision": division(true_positive, len(sensitivity_alerts)),
                "weak_label_recall": division(true_positive, 12),
                "first_a07_detection_delay_hours": first_delay,
                "inference_limit": "same_event_in_sample_local_threshold_grid",
            }
        )
    sensitivity_fields = list(sensitivity_rows[0])
    write_csv(
        output / "proxy_threshold_sensitivity.csv",
        sensitivity_rows,
        sensitivity_fields,
    )
    sensitivity_summary = {
        "grid_rule_count": len(sensitivity_rows),
        "velocity_thresholds": ["0.40", "0.50", "0.60"],
        "temperature_thresholds": ["0.85", "0.90", "0.95"],
        "pollutant_thresholds": ["0.40", "0.50", "0.60"],
        "minimum_true_positive_hours": min(
            row["weak_label_true_positive_hours"] for row in sensitivity_rows
        ),
        "maximum_true_positive_hours": max(
            row["weak_label_true_positive_hours"] for row in sensitivity_rows
        ),
        "maximum_false_positive_hours": max(
            row["weak_label_false_positive_hours"] for row in sensitivity_rows
        ),
        "first_detection_delay_hours_range": [
            min(row["first_a07_detection_delay_hours"] for row in sensitivity_rows),
            max(row["first_a07_detection_delay_hours"] for row in sensitivity_rows),
        ],
        "status": "local_threshold_grid_stable_zero_external_alerts",
        "inference_limit": "same_event_in_sample_not_generalization_evidence",
    }

    totals = {
        "numeric_measurement_rows": sum(row["numeric_measurement_rows"] for row in evaluation_rows),
        "proxy_alert_hours": sum(row["proxy_alert_hours"] for row in evaluation_rows),
        "weak_stop_label_hours": sum(row["weak_stop_label_hours"] for row in evaluation_rows),
        "weak_label_true_positive_hours": sum(
            row["weak_label_true_positive_hours"] for row in evaluation_rows
        ),
        "weak_label_false_positive_hours": sum(
            row["weak_label_false_positive_hours"] for row in evaluation_rows
        ),
        "weak_label_false_negative_hours": sum(
            row["weak_label_false_negative_hours"] for row in evaluation_rows
        ),
    }
    verdict = {
        "schema_version": "public-proxy-quick-feasibility-v1",
        "status": "diagnostic_complete",
        "source_policy": "saved_public_platform_responses_only_no_new_fetch",
        "source_manifest_path": os.path.relpath(manifest_path, output),
        "source_manifest_sha256": sha256(manifest_path),
        "measurement_window": {
            "start": manifest.get("measurement_start_date"),
            "end": manifest.get("measurement_end_date"),
            "current_view_warning": "Fetched after the measurement dates; timing and revisions are not tested here.",
        },
        "followup_saved_snapshot": (
            {
                "manifest_path": os.path.relpath(followup_manifest_path, output),
                "manifest_sha256": sha256(followup_manifest_path),
                "event_first_observed_manifest_path": (
                    os.path.relpath(event_first_manifest_path, output)
                    if event_first_manifest_path
                    else None
                ),
                "event_first_observed_manifest_sha256": (
                    sha256(event_first_manifest_path) if event_first_manifest_path else None
                ),
                "event_start_hour_check_count": len(followup_rows),
                "proxy_alert_count": sum(row["proxy_alert"] for row in followup_rows),
                "interpretation": (
                    "A second weak event has only its start hour saved. The frozen rule "
                    "did not alert, consistent with the first event's transition delay; "
                    "this is not a second event-core validation."
                ),
            }
            if followup_manifest_path
            else None
        ),
        "minimum_viable_signal": (
            signal_rows[0]
            if signal_rows
            else {"status": "not_estimable_without_timing_summary"}
        ),
        "point_count": len(evaluation_rows),
        "event_metadata_count": len(event_rows),
        "totals": totals,
        "technical_proxy_verdict": (
            "provisionally_supported_by_one_retrospective_event_and_cross_point_controls"
        ),
        "cross_point_event_contrast": contrast_verdict,
        "local_threshold_sensitivity": sensitivity_summary,
        "trading_feasibility_verdict": "not_tested_and_not_authorized",
        "gate_results": {
            "historical_numeric_coverage": "partial_pass_4_of_5_points",
            "single_event_state_separability": "diagnostic_pass",
            "same_time_cross_point_contrast": contrast_verdict.get("status"),
            "local_threshold_robustness": sensitivity_summary["status"],
            "second_event_start_hour": (
                "not_alerted_transition_hour_only"
                if followup_rows and not any(row["proxy_alert"] for row in followup_rows)
                else "not_available_or_other"
            ),
            "label_independence": "fail_platform_event_is_weak_label_and_status_fields_conflict",
            "out_of_sample_generalization": "not_tested_one_event_one_mechanism",
            "real_time_availability_and_revisions": "not_tested_by_historical_current_view",
            "economic_mapping_and_market_edge": "not_tested",
        },
        "decision": (
            "Existing data are sufficient to show that a coarse multi-field proxy can "
            "identify the central portion of one recorded stop event. They are not "
            "sufficient to establish a general production proxy or a trading edge."
        ),
        "outputs": {},
    }
    for name in (
        "event_registry.csv",
        "hourly_proxy_diagnostics.csv",
        "point_proxy_evaluation.csv",
        "event_window_contrast.csv",
        "event_control_summary.csv",
        "followup_event_check.csv",
        "minimum_viable_signal_card.csv",
        "proxy_threshold_sensitivity.csv",
    ):
        verdict["outputs"][name] = sha256(output / name)
    verdict_path = output / "verdict.json"
    verdict_path.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
