#!/usr/bin/env python3
"""Build a reproducible field-semantics audit from one saved public snapshot.

The output deliberately separates labels exposed by the public platform from
interpretations that the platform does not define.  In particular, status text
on a row without numeric measurements is never treated as observed production
state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PHYSICAL_CODES = {
    "a19001": "oxygen_content",
    "a01011": "flue_gas_velocity",
    "a01012": "flue_gas_temperature",
    "a01014": "flue_gas_humidity",
    "a01013": "flue_gas_pressure",
}
MISSING_MARKERS = {"", "-", "--", "null", "none"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalized_value(value: Any) -> str:
    return str(value).split("_", 1)[0].strip()


def is_numeric(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    normalized = normalized_value(value)
    if normalized.lower() in MISSING_MARKERS:
        return False
    try:
        float(normalized)
        return True
    except ValueError:
        return False


def is_numeric_measurement_row(row: dict[str, Any]) -> bool:
    return any(
        key.endswith(("-avg", "-zsavg", "-cou")) and is_numeric(value)
        for key, value in row.items()
    )


def classify_field(field_id: str) -> str:
    if field_id == "time":
        return "time"
    if field_id.startswith("stop-"):
        return "facility_status_text"
    if field_id.endswith("-rt"):
        return "reported_update_timestamp"
    code, _, suffix = field_id.partition("-")
    if code in PHYSICAL_CODES and suffix == "avg":
        return PHYSICAL_CODES[code]
    if suffix == "avg":
        return "pollutant_actual_concentration"
    if suffix == "zsavg":
        return "pollutant_converted_concentration"
    if suffix == "cou" and code == "a00000":
        return "flue_gas_volume"
    if suffix == "cou":
        return "mass_emission"
    if suffix == "flag":
        return "automatic_maintenance_flag"
    if suffix == "otherFlag":
        return "manual_maintenance_flag"
    return "unknown"


def unit_from_path(path: str) -> str:
    matches = re.findall(r"[（(]([^()（）]+)[）)]", path)
    return matches[-1].strip() if matches else "not_exposed"


def joined_values(rows: Iterable[dict[str, Any]], field: str) -> str:
    values = {
        str(row.get(field)).strip()
        for row in rows
        if row.get(field) not in (None, "", "-", "--")
    }
    return "|".join(sorted(values)) if values else "none_observed"


def conflict_count(rows: Iterable[dict[str, Any]]) -> int:
    result = 0
    for row in rows:
        left = str(row.get("stop-rt") or "").strip()
        right = str(row.get("stop-stopDcsType") or "").strip()
        if left not in MISSING_MARKERS and right not in MISSING_MARKERS and left != right:
            result += 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "public_only_v1",
    )
    parser.add_argument("--field-output", type=Path)
    parser.add_argument("--point-output", type=Path)
    args = parser.parse_args()
    snapshot = args.snapshot_dir.resolve()
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dictionary_rows = read_csv(snapshot / "field_dictionary.csv")
    observations = read_csv(snapshot / "observations.csv")
    dictionary_by_point: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in dictionary_rows:
        dictionary_by_point[(row["candidate_id"], row["port_id"])].append(row)

    semantic_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for observation in observations:
        point = (observation["candidate_id"], observation["port_id"])
        point_key = "{}-{}".format(*point)
        data_path = snapshot / "raw" / point_key / "data.json"
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        data_rows = [row for row in (payload.get("data") or []) if isinstance(row, dict)]
        numeric_rows = [row for row in data_rows if is_numeric_measurement_row(row)]
        nonnumeric_rows = [row for row in data_rows if not is_numeric_measurement_row(row)]
        latest_numeric = max(
            (str(row.get("time")) for row in numeric_rows if row.get("time")),
            default="",
        )
        later_nonnumeric = [
            row
            for row in data_rows
            if latest_numeric
            and str(row.get("time") or "") > latest_numeric
            and not is_numeric_measurement_row(row)
        ]

        definitions = {
            row["id"]: row
            for row in dictionary_by_point[point]
            if row.get("checked") == "True" and row.get("is_leaf") == "True"
        }
        observed_ids = {field for row in data_rows for field in row}
        for field_id in sorted(set(definitions) | observed_ids):
            definition = definitions.get(field_id, {})
            values = [row.get(field_id) for row in data_rows if field_id in row]
            numeric_count = sum(is_numeric(value) for value in values)
            dash_count = sum(
                normalized_value(value).lower() in MISSING_MARKERS for value in values
            )
            decorated_count = sum(
                isinstance(value, str) and "_" in value for value in values
            )
            category = classify_field(field_id)
            semantic_rows.append(
                {
                    "run_id": manifest.get("run_id", snapshot.name),
                    "candidate_id": observation["candidate_id"],
                    "ps_id": observation["ps_id"],
                    "port_id": observation["port_id"],
                    "field_id": field_id,
                    "platform_name": definition.get("name", "not_in_column_dictionary"),
                    "platform_path": definition.get("path", "not_in_column_dictionary"),
                    "pollutant_code": definition.get("pollutant_code", ""),
                    "field_category": category,
                    "unit_as_exposed": unit_from_path(definition.get("path", "")),
                    "definition_evidence": (
                        "checked_leaf_in_column_response"
                        if definition
                        else "response_only_not_in_checked_column_dictionary"
                    ),
                    "aggregation_semantics": (
                        "hourly_row_shape_observed_exact_definition_unconfirmed"
                        if category
                        not in {
                            "time",
                            "facility_status_text",
                            "reported_update_timestamp",
                            "automatic_maintenance_flag",
                            "manual_maintenance_flag",
                        }
                        else "not_applicable_or_unconfirmed"
                    ),
                    "response_row_count": len(values),
                    "numeric_value_count": numeric_count,
                    "dash_missing_count": dash_count,
                    "decorated_value_count": decorated_count,
                    "semantics_status": (
                        "platform_label_recorded_definition_incomplete"
                        if definition
                        else "undocumented_response_field"
                    ),
                }
            )

        numeric_conflicts = conflict_count(numeric_rows)
        template_conflicts = conflict_count(later_nonnumeric)
        semantic_status = (
            "S2_blocked_no_numeric_measurement"
            if not numeric_rows
            else "S2_blocked_status_and_aggregation_definition_incomplete"
        )
        audit_rows.append(
            {
                "run_id": manifest.get("run_id", snapshot.name),
                "candidate_id": observation["candidate_id"],
                "ps_id": observation["ps_id"],
                "ps_name": observation["ps_name"],
                "port_id": observation["port_id"],
                "port_name": observation["port_name"],
                "checked_leaf_count": len(definitions),
                "response_field_count": len(observed_ids),
                "response_row_count": len(data_rows),
                "numeric_measurement_row_count": len(numeric_rows),
                "latest_numeric_measurement_time": latest_numeric or "none_observed",
                "nonnumeric_row_count": len(nonnumeric_rows),
                "later_nonnumeric_template_row_count": len(later_nonnumeric),
                "numeric_stop_rt_values": joined_values(numeric_rows, "stop-rt"),
                "numeric_stop_dcs_values": joined_values(numeric_rows, "stop-stopDcsType"),
                "later_template_stop_rt_values": joined_values(later_nonnumeric, "stop-rt"),
                "later_template_stop_dcs_values": joined_values(
                    later_nonnumeric, "stop-stopDcsType"
                ),
                "numeric_status_conflict_count": numeric_conflicts,
                "nonnumeric_status_conflict_count": conflict_count(nonnumeric_rows),
                "later_template_status_conflict_count": template_conflicts,
                "scss_event_count": len(payload.get("scssList") or []),
                "alarm_count": len(payload.get("alarmList") or []),
                "abnormal_count": len(payload.get("abnormalList") or []),
                "data_anomaly_entry_count": len(payload.get("dataAnomalMap") or {}),
                "semantic_gate_status": semantic_status,
                "status_interpretation": (
                    "Only status text on numeric rows is retained as a co-observation; "
                    "it is not production truth. Status on later nonnumeric rows is a "
                    "template value and is excluded from actual-state evidence."
                ),
                "data_response_sha256": sha256(data_path),
                "snapshot_manifest_sha256": sha256(manifest_path),
            }
        )

    semantic_fields = list(semantic_rows[0]) if semantic_rows else []
    audit_fields = list(audit_rows[0]) if audit_rows else []
    field_output = args.field_output or args.output_root / "field_semantics.csv"
    point_output = args.point_output or args.output_root / "point_field_audit.csv"
    write_csv(field_output, semantic_fields, semantic_rows)
    write_csv(point_output, audit_fields, audit_rows)
    print(
        json.dumps(
            {
                "run_id": manifest.get("run_id", snapshot.name),
                "point_count": len(audit_rows),
                "field_point_rows": len(semantic_rows),
                "points_with_numeric_rows": sum(
                    int(row["numeric_measurement_row_count"] > 0) for row in audit_rows
                ),
                "template_status_conflict_rows": sum(
                    row["later_template_status_conflict_count"] for row in audit_rows
                ),
                "all_nonnumeric_status_conflict_rows": sum(
                    row["nonnumeric_status_conflict_count"] for row in audit_rows
                ),
                "s2_pass_count": 0,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
