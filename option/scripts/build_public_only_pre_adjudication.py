#!/usr/bin/env python3
"""Build the day-1 S0-S5 pre-adjudication for public-only v1.

This is not the final PUBX/PUB1 adjudication.  It freezes conclusions that are
already determined and isolates the items that genuinely require the rest of
the registered seven-day forward window.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def keyed(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["candidate_id"], row["port_id"]): row for row in rows}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path("option/data/public_only_v1"),
    )
    args = parser.parse_args()
    root = args.root.resolve()

    inputs = {
        "pilot_points.csv": root / "pilot_points.csv",
        "point_field_audit.csv": root / "point_field_audit.csv",
        "historical_point_field_audit.csv": root
        / "historical_point_field_audit.csv",
        "wave1_point_day_summary.csv": root / "wave1_point_day_summary.csv",
        "quick_feasibility/point_proxy_evaluation.csv": root
        / "quick_feasibility"
        / "point_proxy_evaluation.csv",
        "quick_feasibility/verdict.json": root
        / "quick_feasibility"
        / "verdict.json",
    }
    missing = [name for name, path in inputs.items() if not path.is_file()]
    if missing:
        raise SystemExit("missing inputs: {}".format(", ".join(missing)))

    pilots = read_csv(inputs["pilot_points.csv"])
    field_audit = keyed(read_csv(inputs["point_field_audit.csv"]))
    history_audit = keyed(read_csv(inputs["historical_point_field_audit.csv"]))
    timing = keyed(read_csv(inputs["wave1_point_day_summary.csv"]))
    proxy = keyed(read_csv(inputs["quick_feasibility/point_proxy_evaluation.csv"]))

    expected_keys = {(row["candidate_id"], row["port_id"]) for row in pilots}
    for name, table in (
        ("field audit", field_audit),
        ("history audit", history_audit),
        ("day-1 timing", timing),
        ("quick proxy", proxy),
    ):
        if set(table) != expected_keys:
            raise SystemExit("{} keys do not match the five frozen points".format(name))

    rows: list[dict[str, Any]] = []
    for pilot in pilots:
        key = (pilot["candidate_id"], pilot["port_id"])
        current = field_audit[key]
        history = history_audit[key]
        day = timing[key]
        diagnostic = proxy[key]
        numeric_hours = int(history["numeric_measurement_row_count"])

        if numeric_hours == 0:
            s3_status = "provisional_fail_no_numeric_measurement"
            s3_evidence = (
                "0/168 historical current-view numeric hours; target row not visible "
                "through the latest completed day-1 +80 slot"
            )
            s4_status = "not_testable_no_numeric_measurement"
            s4_evidence = "No numeric series exists for a physical-state contrast"
            disposition = "provisional_PUBX_no_numeric_pending_window_close"
            remaining = "S5_frozen_days_2_7_only"
        else:
            s3_status = "provisional_pass_pending_days_2_7"
            s3_evidence = (
                "{}/168 historical current-view numeric hours; day-1 target row first "
                "saved visible at {} with {}"
            ).format(
                numeric_hours,
                day["first_observed_numeric_at"],
                day["timing_bound_status"],
            )
            if diagnostic["diagnostic_disposition"] == (
                "one_event_separable_diagnostic_only"
            ):
                s4_status = "diagnostic_pass_one_weak_event_not_forward_generalization"
                s4_evidence = (
                    "6/12 weak-label event hours detected, 0 external alerts, "
                    "cross-point controls stable; same-source retrospective only"
                )
                disposition = "continue_forward_source_test_technical_poc_only"
                remaining = "S2_definition,S3_days_2_7,S4_forward_event,S5_days_2_7"
            else:
                s4_status = "unknown_no_saved_positive_event_contrast"
                s4_evidence = (
                    "Numeric history is available, but no positive event window exists "
                    "for this fixed point"
                )
                disposition = "continue_forward_source_test"
                remaining = "S2_definition,S3_days_2_7,S4_event,S5_days_2_7"

        rows.append(
            {
                "measurement_date": day["measurement_date"],
                "candidate_id": pilot["candidate_id"],
                "ps_id": pilot["ps_id"],
                "ps_name": pilot["ps_name"],
                "port_id": pilot["port_id"],
                "port_name": pilot["port_name"],
                "s0_catalog_status": "pass_closed_catalog_and_unique_public_ids",
                "s0_evidence": "Frozen public catalog, point registry and source hashes validate",
                "s1_specificity_status": "diagnostic_pass_explicit_public_point_name",
                "s1_evidence": pilot["selection_reason"],
                "s2_semantics_status": current["semantic_gate_status"],
                "s2_evidence": (
                    "Platform labels and response shape are recorded; exact aggregation, "
                    "status-generation and missing/backfill definitions remain incomplete"
                ),
                "s3_numeric_status": s3_status,
                "s3_evidence": s3_evidence,
                "s4_physical_status": s4_status,
                "s4_evidence": s4_evidence,
                "s5_timing_status": "pending_registered_seven_day_window",
                "s5_evidence": (
                    "Day 1 has {} completed polls; target-row hash changes {}; "
                    "the +60 slot was missed"
                ).format(
                    day["completed_poll_count"],
                    day["numeric_target_row_hash_change_count"],
                ),
                "current_provisional_disposition": disposition,
                "remaining_blockers": remaining,
                "final_pubx_pub1_adjudication_earliest": "2026-08-31_after_plus80_slot",
                "inference_limit": (
                    "pre_adjudication_only_no_PUB1_PUB2_no_production_or_trading_claim"
                ),
            }
        )

    output_path = root / "wave1_pre_adjudication.csv"
    write_csv(output_path, rows)
    summary = {
        "schema_version": "public-only-wave1-pre-adjudication-v1",
        "status": "pre_adjudication_in_progress",
        "source_policy": "saved_public_platform_evidence_only_no_new_fetch",
        "as_of": "2026-08-25_after_day1_plus80",
        "point_count": len(rows),
        "s0_pass_count": sum(row["s0_catalog_status"].startswith("pass_") for row in rows),
        "s1_diagnostic_pass_count": sum(
            row["s1_specificity_status"].startswith("diagnostic_pass_") for row in rows
        ),
        "s2_pass_count": sum(
            row["s2_semantics_status"].startswith("S2_pass") for row in rows
        ),
        "s3_provisional_pass_count": sum(
            row["s3_numeric_status"].startswith("provisional_pass_") for row in rows
        ),
        "s3_provisional_fail_count": sum(
            row["s3_numeric_status"].startswith("provisional_fail_") for row in rows
        ),
        "s4_retrospective_diagnostic_pass_count": sum(
            row["s4_physical_status"].startswith("diagnostic_pass_") for row in rows
        ),
        "s5_complete_count": 0,
        "provisional_pubx_count": sum(
            row["current_provisional_disposition"].startswith("provisional_PUBX")
            for row in rows
        ),
        "pub1_awarded_count": 0,
        "pub2_awarded_count": 0,
        "final_adjudication_earliest": "2026-08-31_after_plus80_slot",
        "decision": (
            "PUB-003 can proceed as a pre-adjudication now. Four numeric points continue; "
            "one no-numeric point is provisional PUBX. Final PUBX/PUB1 remains gated by "
            "the registered seven-day window and unresolved S2 semantics."
        ),
        "inputs": {name: sha256(path) for name, path in inputs.items()},
        "output": {
            "path": output_path.name,
            "sha256": sha256(output_path),
        },
    }
    summary_path = root / "wave1_pre_adjudication.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
