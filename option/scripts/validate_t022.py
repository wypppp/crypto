#!/usr/bin/env python3
"""Validate first-round T-022 metadata exports without reading numeric histories."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


TABLES = {
    "metadata": {
        "required": {
            "enterprise_id",
            "plant_id",
            "universe_vintage",
            "as_of",
            "city",
            "county",
            "industry_raw",
            "production_facility_id",
            "production_facility_name_raw",
            "process_name_raw",
            "monitoring_point_id",
            "monitoring_point_name_raw",
            "medium",
            "topology",
            "operating_status_source",
            "first_visible_lag",
            "available_history",
            "field_set_id",
        },
        "enums": {
            "medium": {"waste_gas", "wastewater", "VOC", "ambient", "other"},
            "topology": {
                "one_to_one",
                "shared_outlet",
                "one_device_multi_outlet",
                "unknown",
            },
            "operating_status_source": {
                "PLC",
                "manual",
                "platform_derived",
                "monitoring_device",
                "unknown",
            },
        },
        "stable_ids": {
            "enterprise_id",
            "plant_id",
            "production_facility_id",
            "monitoring_point_id",
            "field_set_id",
        },
    },
    "capacity": {
        "required": {
            "capacity_record_id",
            "enterprise_id",
            "plant_id",
            "product_name",
            "specification",
            "pricing_market",
            "deliverable_grade",
            "production_line_id",
            "production_facility_id",
            "capacity_value",
            "capacity_unit",
            "capacity_basis",
            "operating_status",
            "effective_start",
            "effective_end",
            "source_type",
            "source_url",
            "published_at",
            "accessed_at",
            "snapshot_hash",
            "evidence_level",
            "last_verified_at",
            "crosswalk_status",
        },
        "enums": {
            "capacity_basis": {
                "design",
                "approved",
                "effective",
                "consumption_capacity",
                "unknown",
            },
            "operating_status": {
                "operating",
                "planned",
                "under_construction",
                "long_idle",
                "demolished",
                "replaced",
                "unknown",
            },
            "evidence_level": {"I0", "F", "M", "L", "H", "U", "X"},
            "crosswalk_status": {
                "unique",
                "shared",
                "known_unobservable",
                "capacity_unknown",
                "relation_unknown",
            },
        },
        "stable_ids": {"capacity_record_id", "enterprise_id", "plant_id"},
    },
    "field_dictionary": {
        "required": {
            "field_set_id",
            "source_field_name_raw",
            "normalized_concept",
            "pollutant_or_metric",
            "unit_raw",
            "measured_or_converted",
            "actual_or_standard_condition",
            "dry_or_wet_basis",
            "instant_or_hourly_aggregate",
            "calculation_rule",
            "valid_range_or_limit",
            "missing_zero_negative_semantics",
        },
        "enums": {
            "measured_or_converted": {"measured", "converted", "derived", "unknown"},
            "actual_or_standard_condition": {"actual", "standard", "unknown"},
            "dry_or_wet_basis": {"dry", "wet", "unknown"},
            "instant_or_hourly_aggregate": {
                "instant_mean",
                "hourly_mean",
                "hourly_total",
                "unknown",
            },
        },
        "stable_ids": {"field_set_id"},
    },
    "status_dictionary": {
        "required": {
            "code_set_id",
            "raw_code",
            "raw_label",
            "applies_to",
            "generated_by",
            "effective_start",
            "effective_end",
            "research_treatment",
            "definition_source",
        },
        "enums": {
            "applies_to": {
                "production_facility",
                "control_facility",
                "monitoring_device",
                "pollutant_channel",
                "platform_record",
                "unknown",
            },
            "generated_by": {
                "PLC",
                "enterprise_manual",
                "platform_rule",
                "monitoring_device",
                "unknown",
            },
            "research_treatment": {
                "valid",
                "maintenance",
                "calibration",
                "fault",
                "invalid",
                "unknown",
            },
        },
        "stable_ids": {"code_set_id"},
    },
}

EMPTY = {"", "null", "none", "na", "n/a"}


def nonempty(value: str | None) -> bool:
    return value is not None and value.strip().lower() not in EMPTY


def validate(table: str, path: Path) -> list[str]:
    spec = TABLES[table]
    errors: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing_headers = spec["required"] - headers
        if missing_headers:
            errors.append(f"missing columns: {', '.join(sorted(missing_headers))}")
            return errors
        rows = list(reader)

    if not rows:
        return ["file has a header but no data rows"]

    stable_values: dict[str, Counter[str]] = {
        field: Counter() for field in spec["stable_ids"]
    }
    for line_number, row in enumerate(rows, start=2):
        for field in spec["required"]:
            if not nonempty(row.get(field)):
                errors.append(f"line {line_number}: {field} is empty; use unknown/NA when allowed")
        for field, choices in spec["enums"].items():
            value = (row.get(field) or "").strip()
            if value and value not in choices:
                errors.append(
                    f"line {line_number}: {field}={value!r} is not one of {sorted(choices)}"
                )
        for field in spec["stable_ids"]:
            value = (row.get(field) or "").strip()
            if nonempty(value) and value not in {"unknown", "NA"}:
                stable_values[field][value] += 1

    if table == "capacity":
        duplicates = [value for value, count in stable_values["capacity_record_id"].items() if count > 1]
        if duplicates:
            errors.append(f"capacity_record_id is not unique: {', '.join(duplicates[:10])}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table", choices=sorted(TABLES))
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    errors = validate(args.table, args.csv_path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {args.table} {args.csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
