#!/usr/bin/env python3
"""Validate source-closed controls for the Hebei public-only v1 study.

A passing result verifies registries, counts and immutable-source hashes only.
It does not award PUB1/PUB2 or any trading status.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


VINTAGE_ID = "public-only-v1@2026-08-24T16:52:37+08:00"
EXPECTED_CANDIDATES = {"PUB-A{:02d}".format(i) for i in range(1, 14)}
EXPECTED_REGISTRIES = {
    "U-PUB-ENT-v1": (5951, 5951),
    "U-PUB-POINT-v1": (17412, 17408),
    "U-PUB-META-v1": (5, 5),
    "U-PUB-DISC-v1": (3177, 3177),
    "U-PUB-PILOT-v1": (5, 5),
}
ALLOWED_STAGES = {"catalog_discovery", "pilot_baseline_only"}
EXPECTED_PILOT_MANIFESTS = {
    "20260824T170000+0800": "88d59384b07e3dba76eacf7427710ce91b3f4c25ae8417a4aab2f567c60c0a15",
    "20260824T171500+0800": "4b1e374810a13865800c7dacd155a42f5c97ede476ac2da763446551a35191b8",
    "20260824T174912+0800": "4a1742da4285cda213a643bb18eab407d74d81b5b9f5c7954665059b2a77440a",
}
EXPECTED_HISTORY_MANIFESTS = {
    "20260825T083300+0800": "748b282ab950c5984d924a3a7a2ca019725c4a42cc1ffdd79a753627e644684f",
}
EXPECTED_DISCOVERY_REVIEW_COUNTS = {
    "mechanism_specific_name_evidence": 29,
    "ambiguous_name_evidence": 34,
    "false_positive_name_evidence": 59,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def duplicate_values(rows: Sequence[Dict[str, str]], field: str) -> List[str]:
    counts = Counter(row.get(field, "") for row in rows)
    return sorted(value for value, count in counts.items() if count > 1)


def validate(root: Path) -> Tuple[List[str], List[str], Dict[str, object]]:
    errors: List[str] = []
    warnings: List[str] = []
    summary: Dict[str, object] = {}

    with (root / "vintage.json").open("r", encoding="utf-8") as handle:
        vintage = json.load(handle)
    if vintage.get("vintage_id") != VINTAGE_ID:
        errors.append("unexpected vintage_id")
    if vintage.get("status") != "in_progress_wave_1":
        errors.append("public-only v1 must remain in_progress_wave_1 until gates are adjudicated")
    if set(vintage.get("closed_registries", [])) != set(EXPECTED_REGISTRIES):
        errors.append("closed registries do not match the five expected IDs")
    if vintage.get("source_url") != "https://111.62.218.180:9920/psIndex/":
        errors.append("unexpected observation source URL")

    data_root = root.parent
    catalog_root = (root / vintage.get("source_run", "")).resolve()
    catalog_manifest = catalog_root / "manifest.json"
    catalog_summary = catalog_root / "derived" / "summary.json"
    for path in (catalog_manifest, catalog_summary):
        if not path.exists():
            errors.append("missing immutable source: {}".format(path))
    if catalog_manifest.exists():
        actual = sha256(catalog_manifest)
        if actual != vintage.get("source_manifest_sha256"):
            errors.append("catalog manifest hash mismatch")
    if catalog_summary.exists():
        actual = sha256(catalog_summary)
        if actual != vintage.get("source_summary_sha256"):
            errors.append("catalog summary hash mismatch")
        with catalog_summary.open("r", encoding="utf-8") as handle:
            source_summary = json.load(handle)
        if source_summary.get("enterprise_count") != 5951:
            errors.append("catalog enterprise count changed")
        if source_summary.get("port_count") != 17408:
            errors.append("catalog unique point count changed")
        discovery_total = sum(
            item.get("total_hit_rows", 0)
            for item in source_summary.get("candidate_discovery", {}).values()
        )
        if discovery_total != 3177:
            errors.append("catalog discovery total changed")

    coverage_headers, coverage_rows = read_csv(root / "source_coverage.csv")
    required_coverage = {
        "universe_id",
        "member_type",
        "source_reported_rows",
        "unique_rows",
        "exact_duplicate_rows",
        "status",
        "source_path",
        "source_sha256",
        "limitations",
    }
    if not required_coverage.issubset(set(coverage_headers)):
        errors.append("source_coverage.csv schema mismatch")
    if duplicate_values(coverage_rows, "universe_id"):
        errors.append("duplicate source coverage universe IDs")
    coverage_by_id = {row.get("universe_id", ""): row for row in coverage_rows}
    if set(coverage_by_id) != set(EXPECTED_REGISTRIES):
        errors.append("source coverage rows do not match expected registries")
    for universe_id, (reported, unique) in EXPECTED_REGISTRIES.items():
        row = coverage_by_id.get(universe_id, {})
        try:
            actual_pair = (
                int(row.get("source_reported_rows", "")),
                int(row.get("unique_rows", "")),
            )
        except ValueError:
            errors.append("{} has non-integer counts".format(universe_id))
            continue
        if actual_pair != (reported, unique):
            errors.append("{} count mismatch".format(universe_id))
        source_path = (root / row.get("source_path", "")).resolve()
        if not source_path.is_file():
            errors.append("{} source path is not a file".format(universe_id))
        elif sha256(source_path) != row.get("source_sha256"):
            errors.append("{} source hash mismatch".format(universe_id))

    candidate_headers, candidates = read_csv(root / "candidate_registry.csv")
    required_candidates = {
        "public_study_id",
        "legacy_seed_id",
        "enterprise_name_hits",
        "point_process_hits",
        "total_hit_rows",
        "enterprises_with_point_hits",
        "pilot_point_count",
        "current_stage",
        "blocking_reason",
        "next_public_only_test",
        "s1_sample_rows",
        "s1_specific_name_rows",
        "s1_ambiguous_name_rows",
        "s1_false_positive_rows",
    }
    if not required_candidates.issubset(set(candidate_headers)):
        errors.append("candidate_registry.csv schema mismatch")
    candidate_ids = {row.get("public_study_id", "") for row in candidates}
    if candidate_ids != EXPECTED_CANDIDATES:
        errors.append("candidate registry must contain PUB-A01 through PUB-A13")
    if duplicate_values(candidates, "public_study_id"):
        errors.append("duplicate public study IDs")
    total_hits = 0
    total_pilot_count = 0
    for line_number, row in enumerate(candidates, start=2):
        try:
            enterprise_hits = int(row.get("enterprise_name_hits", ""))
            point_hits = int(row.get("point_process_hits", ""))
            row_total = int(row.get("total_hit_rows", ""))
            pilot_count = int(row.get("pilot_point_count", ""))
        except ValueError:
            errors.append("candidate line {} has non-integer counts".format(line_number))
            continue
        if enterprise_hits + point_hits != row_total:
            errors.append("candidate line {} hit counts do not add up".format(line_number))
        if row.get("current_stage") not in ALLOWED_STAGES:
            errors.append("candidate line {} has invalid stage".format(line_number))
        total_hits += row_total
        total_pilot_count += pilot_count
    if total_hits != 3177:
        errors.append("candidate hit total must be 3177")

    pilot_headers, pilot_points = read_csv(root / "pilot_points.csv")
    required_pilot = {
        "enabled",
        "candidate_id",
        "legacy_candidate_id",
        "ps_id",
        "port_id",
        "port_type_id",
        "data_type",
        "internal_point_id",
        "unique_mapping_status",
    }
    if not required_pilot.issubset(set(pilot_headers)):
        errors.append("pilot_points.csv schema mismatch")
    pilot_keys = [(row.get("ps_id", ""), row.get("port_id", "")) for row in pilot_points]
    if len(pilot_points) != 5 or len(set(pilot_keys)) != 5:
        errors.append("pilot registry must contain five unique points")
    if total_pilot_count != len(pilot_points):
        errors.append("candidate pilot counts do not match pilot_points.csv")
    for line_number, row in enumerate(pilot_points, start=2):
        if row.get("enabled") != "1":
            errors.append("pilot line {} is not enabled".format(line_number))
        if row.get("internal_point_id"):
            errors.append("pilot line {} improperly contains an internal point".format(line_number))
        if row.get("unique_mapping_status") != "not_applicable_public_only":
            errors.append("pilot line {} has an invalid public-only status".format(line_number))

    _, baseline = read_csv(root / "pilot_baseline.csv")
    baseline_keys = [(row.get("ps_id", ""), row.get("port_id", "")) for row in baseline]
    if set(baseline_keys) != set(pilot_keys):
        errors.append("pilot baseline does not match the five pilot points")
    if any(row.get("current_disposition") == "PUB2" for row in baseline):
        errors.append("baseline cannot award PUB2")

    poll_headers, poll_registry = read_csv(root / "poll_registry.csv")
    required_poll = {
        "run_id",
        "measurement_date",
        "study_id",
        "point_count",
        "raw_file_count",
        "manifest_path",
        "manifest_sha256",
        "hash_verified",
        "role",
    }
    if not required_poll.issubset(set(poll_headers)):
        errors.append("poll_registry.csv schema mismatch")
    if duplicate_values(poll_registry, "run_id"):
        errors.append("duplicate poll registry run IDs")
    for line_number, row in enumerate(poll_registry, start=2):
        path = (root / row.get("manifest_path", "")).resolve()
        if not path.exists():
            errors.append("poll line {} manifest is missing".format(line_number))
            continue
        if sha256(path) != row.get("manifest_sha256"):
            errors.append("poll line {} manifest hash mismatch".format(line_number))
        else:
            with path.open("r", encoding="utf-8") as handle:
                poll_manifest = json.load(handle)
            records = poll_manifest.get("files") or []
            for record in records:
                raw_path = path.parent / record.get("path", "")
                if not raw_path.is_file():
                    errors.append(
                        "poll line {} raw file is missing: {}".format(
                            line_number, record.get("path", "")
                        )
                    )
                elif sha256(raw_path) != record.get("sha256"):
                    errors.append(
                        "poll line {} raw file hash mismatch: {}".format(
                            line_number, record.get("path", "")
                        )
                    )
            try:
                expected_raw_count = int(row.get("raw_file_count", ""))
            except ValueError:
                expected_raw_count = -1
            if len(records) != expected_raw_count:
                errors.append("poll line {} manifest raw-file count mismatch".format(line_number))
        if row.get("hash_verified") != "1":
            errors.append("poll line {} is not marked hash-verified".format(line_number))
        try:
            point_count = int(row.get("point_count", ""))
            raw_file_count = int(row.get("raw_file_count", ""))
        except ValueError:
            errors.append("poll line {} has non-integer counts".format(line_number))
            continue
        if raw_file_count != point_count * 2:
            errors.append("poll line {} must have two raw responses per point".format(line_number))

    t026_root = data_root / "t026"
    listed_pilot_hashes = set(vintage.get("legacy_pilot_manifest_sha256", []))
    actual_pilot_hashes = set()
    for run_id, expected_hash in EXPECTED_PILOT_MANIFESTS.items():
        path = t026_root / run_id / "manifest.json"
        if not path.exists():
            errors.append("missing legacy pilot manifest {}".format(run_id))
            continue
        actual_hash = sha256(path)
        actual_pilot_hashes.add(actual_hash)
        if actual_hash != expected_hash:
            errors.append("legacy pilot manifest hash mismatch for {}".format(run_id))
    if actual_pilot_hashes != listed_pilot_hashes:
        errors.append("vintage legacy pilot hash set mismatch")

    history_headers, history_registry = read_csv(root / "history_registry.csv")
    required_history = {
        "run_id",
        "measurement_start_date",
        "measurement_end_date",
        "study_id",
        "point_count",
        "raw_file_count",
        "manifest_path",
        "manifest_sha256",
        "hash_verified",
        "role",
        "availability_limit",
    }
    if not required_history.issubset(set(history_headers)):
        errors.append("history_registry.csv schema mismatch")
    if duplicate_values(history_registry, "run_id"):
        errors.append("duplicate history registry run IDs")
    actual_history_hashes = set()
    for row in history_registry:
        expected_hash = EXPECTED_HISTORY_MANIFESTS.get(row.get("run_id", ""))
        if not expected_hash:
            errors.append("unregistered historical current-view run")
            continue
        path = (root / row.get("manifest_path", "")).resolve()
        if not path.exists():
            errors.append("history manifest is missing")
            continue
        actual_hash = sha256(path)
        actual_history_hashes.add(actual_hash)
        if actual_hash != expected_hash or actual_hash != row.get("manifest_sha256"):
            errors.append("history manifest hash mismatch")
        with path.open("r", encoding="utf-8") as handle:
            history_manifest = json.load(handle)
        history_records = history_manifest.get("files") or []
        for record in history_records:
            raw_path = path.parent / record.get("path", "")
            if not raw_path.is_file():
                errors.append("history raw file is missing: {}".format(record.get("path", "")))
            elif sha256(raw_path) != record.get("sha256"):
                errors.append(
                    "history raw file hash mismatch: {}".format(record.get("path", ""))
                )
        try:
            expected_history_raw = int(row.get("raw_file_count", ""))
        except ValueError:
            expected_history_raw = -1
        if len(history_records) != expected_history_raw:
            errors.append("history manifest raw-file count mismatch")
        if row.get("hash_verified") != "1":
            errors.append("history manifest is not marked hash-verified")
        if row.get("role") != "historical_current_view_shape_check":
            errors.append("history role cannot imply original-time availability")
    if actual_history_hashes != set(vintage.get("historical_current_view_manifest_sha256", [])):
        errors.append("vintage historical current-view hash set mismatch")

    _, field_audit = read_csv(root / "point_field_audit.csv")
    field_audit_keys = [(row.get("ps_id", ""), row.get("port_id", "")) for row in field_audit]
    if len(field_audit) != 5 or set(field_audit_keys) != set(pilot_keys):
        errors.append("point field audit must cover the five pilot points")
    if any(not row.get("semantic_gate_status", "").startswith("S2_blocked") for row in field_audit):
        errors.append("S2 cannot pass while exact field definitions remain incomplete")
    if sum(int(row.get("numeric_measurement_row_count", "0")) > 0 for row in field_audit) != 4:
        errors.append("unexpected numeric-point count in field audit")

    _, field_semantics = read_csv(root / "field_semantics.csv")
    semantics_keys = {(row.get("ps_id", ""), row.get("port_id", "")) for row in field_semantics}
    if len(field_semantics) != 147 or semantics_keys != set(pilot_keys):
        errors.append("field semantics must contain the frozen 147 point-field rows")
    if any(row.get("semantics_status") not in {
        "platform_label_recorded_definition_incomplete",
        "undocumented_response_field",
    } for row in field_semantics):
        errors.append("field semantics contain an unsupported adjudication")

    sample_headers, sample_rows = read_csv(root / "discovery_audit_sample.csv")
    required_sample = {
        "public_study_id",
        "candidate_id",
        "selection_hash",
        "sample_rank_within_candidate",
        "review_status",
    }
    if not required_sample.issubset(set(sample_headers)):
        errors.append("discovery audit sample schema mismatch")
    if len(sample_rows) != 122 or len({row.get("selection_hash", "") for row in sample_rows}) != 122:
        errors.append("discovery audit sample must contain 122 unique rows")
    sample_counts = Counter(row.get("candidate_id", "") for row in sample_rows)
    for candidate in ("A{:02d}".format(index) for index in range(1, 14)):
        expected = 2 if candidate == "A08" else 10
        if sample_counts[candidate] != expected:
            errors.append("unexpected sample count for {}".format(candidate))
    if any(row.get("review_status") != "unreviewed" for row in sample_rows):
        errors.append("mechanical sample must remain separate from review labels")
    sample_manifest_path = root / "discovery_audit_sample_manifest.json"
    with sample_manifest_path.open("r", encoding="utf-8") as handle:
        sample_manifest = json.load(handle)
    if sample_manifest.get("source_sha256") != coverage_by_id["U-PUB-DISC-v1"].get("source_sha256"):
        errors.append("discovery sample source hash mismatch")
    if sample_manifest.get("output_sha256") != sha256(root / "discovery_audit_sample.csv"):
        errors.append("discovery sample output hash mismatch")

    _, label_rows = read_csv(root / "discovery_audit_labels.csv")
    label_keys = {
        (row.get("candidate_id", ""), row.get("sample_rank_within_candidate", ""), row.get("selection_hash", ""))
        for row in label_rows
    }
    sample_keys = {
        (row.get("candidate_id", ""), row.get("sample_rank_within_candidate", ""), row.get("selection_hash", ""))
        for row in sample_rows
    }
    if len(label_rows) != 122 or label_keys != sample_keys:
        errors.append("discovery review labels do not match the frozen sample")
    review_counts = Counter(row.get("review_status", "") for row in label_rows)
    if dict(review_counts) != EXPECTED_DISCOVERY_REVIEW_COUNTS:
        errors.append("discovery review count mismatch")
    _, review_summary = read_csv(root / "discovery_audit_summary.csv")
    if len(review_summary) != 13:
        errors.append("discovery review summary must cover 13 mechanisms")
    review_summary_by_id = {row.get("public_study_id", ""): row for row in review_summary}
    for row in candidates:
        public_id = row.get("public_study_id", "")
        summary_row = review_summary_by_id.get(public_id, {})
        compared = (
            ("s1_sample_rows", "sample_row_count"),
            ("s1_specific_name_rows", "mechanism_specific_name_count"),
            ("s1_ambiguous_name_rows", "ambiguous_name_count"),
            ("s1_false_positive_rows", "false_positive_name_count"),
        )
        for candidate_field, summary_field in compared:
            if row.get(candidate_field, "") != summary_row.get(summary_field, ""):
                errors.append("{} review summary mismatch for {}".format(candidate_field, public_id))
    review_manifest_path = root / "discovery_audit_labels_manifest.json"
    with review_manifest_path.open("r", encoding="utf-8") as handle:
        review_manifest = json.load(handle)
    if review_manifest.get("labels_sha256") != sha256(root / "discovery_audit_labels.csv"):
        errors.append("discovery label hash mismatch")
    if review_manifest.get("summary_sha256") != sha256(root / "discovery_audit_summary.csv"):
        errors.append("discovery review summary hash mismatch")

    _, history_profile = read_csv(root / "historical_window_profile.csv")
    history_profile_keys = [(row.get("ps_id", ""), row.get("port_id", "")) for row in history_profile]
    if len(history_profile) != 5 or set(history_profile_keys) != set(pilot_keys):
        errors.append("historical window profile must cover five pilot points")
    historical_numeric_counts = sorted(
        int(row.get("numeric_measurement_row_count", "0")) for row in history_profile
    )
    if historical_numeric_counts != [0, 168, 168, 168, 168]:
        errors.append("unexpected historical current-view numeric coverage")
    if any(row.get("s4_status", "").startswith("S4_pass") for row in history_profile):
        errors.append("historical current-view data cannot pass S4")
    formula_total = sum(int(row.get("mass_formula_triplet_count", "0")) for row in history_profile)
    formula_matches = sum(
        int(row.get("mass_formula_within_2pct_count", "0")) for row in history_profile
    )
    if (formula_total, formula_matches) != (1344, 1344):
        errors.append("unexpected mass-emission arithmetic-dependence result")
    _, daily_coverage = read_csv(root / "historical_daily_coverage.csv")
    if len(daily_coverage) != 35:
        errors.append("historical daily coverage must contain 35 point-days")

    _, historical_field_audit = read_csv(root / "historical_point_field_audit.csv")
    if len(historical_field_audit) != 5:
        errors.append("historical field audit must contain five points")
    _, historical_semantics = read_csv(root / "historical_field_semantics.csv")
    if len(historical_semantics) != 147:
        errors.append("historical field semantics must contain 147 point-field rows")

    _, wave_schedule = read_csv(root / "wave1_schedule.csv")
    if len(wave_schedule) != 35:
        errors.append("wave-1 schedule must contain seven days times five polls")
    schedule_days = Counter(row.get("study_day", "") for row in wave_schedule)
    if schedule_days != Counter({str(index): 5 for index in range(1, 8)}):
        errors.append("wave-1 schedule day counts are invalid")
    expected_offsets = {"60", "62", "65", "70", "80"}
    for study_day in map(str, range(1, 8)):
        actual_offsets = {
            row.get("poll_offset_from_hour_start_minutes", "")
            for row in wave_schedule
            if row.get("study_day") == study_day
        }
        if actual_offsets != expected_offsets:
            errors.append("wave-1 schedule offsets are invalid for day {}".format(study_day))
    allowed_schedule_status = {"pending", "completed", "failed_query", "missed"}
    if any(row.get("status") not in allowed_schedule_status for row in wave_schedule):
        errors.append("wave-1 schedule has an invalid status")
    registered_run_ids = {row.get("run_id", "") for row in poll_registry}
    for row in wave_schedule:
        if row.get("status") == "completed" and row.get("actual_run_id") not in registered_run_ids:
            errors.append("completed schedule slot lacks a registered poll")

    _, change_summary = read_csv(root / "poll_change_summary.csv")
    public_poll_day_counts = Counter(
        row.get("measurement_date", "")
        for row in poll_registry
        if row.get("study_id") == "public-only-v1"
    )
    expected_point_pairs = 5 * sum(
        max(count - 1, 0) for count in public_poll_day_counts.values()
    )
    if len(change_summary) != expected_point_pairs:
        errors.append("poll change summary does not cover consecutive same-day point pairs")
    allowed_s5 = {
        "revision_observed",
        "no_revision_observed_in_this_bounded_pair",
    }
    if any(row.get("s5_interpretation") not in allowed_s5 for row in change_summary):
        errors.append("poll change summary has an invalid S5 interpretation")
    _, change_events = read_csv(root / "poll_change_events.csv")
    allowed_change_kinds = {
        "new_numeric_visibility",
        "revision_existing_numeric",
        "numeric_disappeared",
        "template_change",
    }
    if any(row.get("change_kind") not in allowed_change_kinds for row in change_events):
        errors.append("poll change events contain an invalid change kind")

    _, public_state = read_csv(root / "public_state.csv")
    public_state_keys = [(row.get("ps_id", ""), row.get("port_id", "")) for row in public_state]
    if len(public_state) != 5 or set(public_state_keys) != set(pilot_keys):
        errors.append("public state must cover the five fixed points")

    _, slot_timing = read_csv(root / "wave1_slot_timing.csv")
    completed_schedule = [row for row in wave_schedule if row.get("status") == "completed"]
    if len(slot_timing) != len(completed_schedule):
        errors.append("wave-1 slot timing does not match completed schedule slots")
    poll_hash_by_run = {
        row.get("run_id", ""): row.get("manifest_sha256", "") for row in poll_registry
    }
    for row in slot_timing:
        if row.get("manifest_sha256") != poll_hash_by_run.get(row.get("run_id", "")):
            errors.append("wave-1 timing manifest hash mismatch")
        if row.get("point_count") != "5":
            errors.append("wave-1 timing slot does not cover five points")
    _, point_slot_timing = read_csv(root / "wave1_point_slot_timing.csv")
    if len(point_slot_timing) != len(completed_schedule) * 5:
        errors.append("wave-1 point-slot timing row count mismatch")
    _, point_day_timing = read_csv(root / "wave1_point_day_summary.csv")
    completed_days = {
        row.get("measurement_date", "") for row in completed_schedule
    }
    if len(point_day_timing) != len(completed_days) * 5:
        errors.append("wave-1 point-day summary row count mismatch")
    allowed_timing_bounds = {
        "upper_bound_only_earlier_slot_incomplete",
        "interval_bound",
        "upper_bound_only_first_completed_poll",
        "not_visible_through_latest_completed_poll",
    }
    if any(row.get("timing_bound_status") not in allowed_timing_bounds for row in point_day_timing):
        errors.append("wave-1 point-day summary has an invalid timing bound")

    pre_path = root / "wave1_pre_adjudication.json"
    with pre_path.open("r", encoding="utf-8") as handle:
        pre_adjudication = json.load(handle)
    expected_pre_summary = {
        "schema_version": "public-only-wave1-pre-adjudication-v1",
        "status": "pre_adjudication_in_progress",
        "source_policy": "saved_public_platform_evidence_only_no_new_fetch",
        "point_count": 5,
        "s0_pass_count": 5,
        "s1_diagnostic_pass_count": 5,
        "s2_pass_count": 0,
        "s3_provisional_pass_count": 4,
        "s3_provisional_fail_count": 1,
        "s4_retrospective_diagnostic_pass_count": 1,
        "s5_complete_count": 0,
        "provisional_pubx_count": 1,
        "pub1_awarded_count": 0,
        "pub2_awarded_count": 0,
        "final_adjudication_earliest": "2026-08-31_after_plus80_slot",
    }
    if any(
        pre_adjudication.get(field) != value
        for field, value in expected_pre_summary.items()
    ):
        errors.append("wave-1 pre-adjudication summary changed")
    for name, expected_hash in (pre_adjudication.get("inputs") or {}).items():
        path = root / name
        if not path.is_file() or sha256(path) != expected_hash:
            errors.append("pre-adjudication input hash mismatch: {}".format(name))
    pre_output = pre_adjudication.get("output") or {}
    pre_csv_path = root / pre_output.get("path", "")
    if not pre_csv_path.is_file() or sha256(pre_csv_path) != pre_output.get("sha256"):
        errors.append("pre-adjudication output hash mismatch")
    _, pre_rows = read_csv(pre_csv_path)
    pre_keys = [(row.get("ps_id", ""), row.get("port_id", "")) for row in pre_rows]
    if len(pre_rows) != 5 or set(pre_keys) != set(pilot_keys):
        errors.append("pre-adjudication must cover the five frozen points")
    elif (
        any(
            row.get("s0_catalog_status")
            != "pass_closed_catalog_and_unique_public_ids"
            for row in pre_rows
        )
        or any(
            row.get("s1_specificity_status")
            != "diagnostic_pass_explicit_public_point_name"
            for row in pre_rows
        )
        or any(
            not row.get("s2_semantics_status", "").startswith("S2_blocked")
            for row in pre_rows
        )
        or Counter(row.get("s3_numeric_status") for row in pre_rows)
        != Counter(
            {
                "provisional_pass_pending_days_2_7": 4,
                "provisional_fail_no_numeric_measurement": 1,
            }
        )
        or Counter(row.get("current_provisional_disposition") for row in pre_rows)
        != Counter(
            {
                "continue_forward_source_test": 3,
                "continue_forward_source_test_technical_poc_only": 1,
                "provisional_PUBX_no_numeric_pending_window_close": 1,
            }
        )
    ):
        errors.append("unexpected wave-1 point pre-adjudication")

    quick_root = root / "quick_feasibility"
    quick_verdict_path = quick_root / "verdict.json"
    with quick_verdict_path.open("r", encoding="utf-8") as handle:
        quick_verdict = json.load(handle)
    if quick_verdict.get("schema_version") != "public-proxy-quick-feasibility-v1":
        errors.append("unexpected quick-feasibility schema")
    if quick_verdict.get("source_policy") != "saved_public_platform_responses_only_no_new_fetch":
        errors.append("quick feasibility used an invalid source policy")
    quick_source = (quick_root / quick_verdict.get("source_manifest_path", "")).resolve()
    if not quick_source.is_file() or sha256(quick_source) != quick_verdict.get(
        "source_manifest_sha256"
    ):
        errors.append("quick-feasibility source manifest hash mismatch")
    if quick_verdict.get("technical_proxy_verdict") != (
        "provisionally_supported_by_one_retrospective_event_and_cross_point_controls"
    ):
        errors.append("unexpected quick technical-proxy verdict")
    if quick_verdict.get("trading_feasibility_verdict") != "not_tested_and_not_authorized":
        errors.append("quick feasibility cannot authorize trading")
    for name, expected_hash in (quick_verdict.get("outputs") or {}).items():
        path = quick_root / name
        if not path.is_file() or sha256(path) != expected_hash:
            errors.append("quick-feasibility output hash mismatch: {}".format(name))
    quick_followup = quick_verdict.get("followup_saved_snapshot") or {}
    followup_manifest = (quick_root / quick_followup.get("manifest_path", "")).resolve()
    if not followup_manifest.is_file() or sha256(followup_manifest) != quick_followup.get(
        "manifest_sha256"
    ):
        errors.append("quick-feasibility follow-up manifest hash mismatch")
    event_first_manifest = (
        quick_root / quick_followup.get("event_first_observed_manifest_path", "")
    ).resolve()
    if not event_first_manifest.is_file() or sha256(event_first_manifest) != quick_followup.get(
        "event_first_observed_manifest_sha256"
    ):
        errors.append("quick-feasibility first-event-observation manifest hash mismatch")
    if quick_followup.get("event_start_hour_check_count") != 1 or quick_followup.get(
        "proxy_alert_count"
    ) != 0:
        errors.append("unexpected quick follow-up event-start result")
    quick_contrast = quick_verdict.get("cross_point_event_contrast") or {}
    expected_contrast = {
        "status": "cross_point_event_contrast_diagnostic_pass",
        "event_candidate_id": "PUB-A07",
        "target_velocity_event_to_pre_ratio": "0.065327",
        "target_velocity_post_to_pre_ratio": "0.976704",
        "target_temperature_event_to_pre_ratio": "0.903551",
        "target_pollutant_event_to_pre_ratio": "0.385253",
        "same_time_control_count": 3,
        "same_time_controls_stable": True,
    }
    if any(quick_contrast.get(field) != value for field, value in expected_contrast.items()):
        errors.append("quick cross-point event contrast changed")
    quick_sensitivity = quick_verdict.get("local_threshold_sensitivity") or {}
    expected_sensitivity = {
        "grid_rule_count": 27,
        "velocity_thresholds": ["0.40", "0.50", "0.60"],
        "temperature_thresholds": ["0.85", "0.90", "0.95"],
        "pollutant_thresholds": ["0.40", "0.50", "0.60"],
        "minimum_true_positive_hours": 6,
        "maximum_true_positive_hours": 7,
        "maximum_false_positive_hours": 0,
        "first_detection_delay_hours_range": ["3.000", "4.000"],
        "status": "local_threshold_grid_stable_zero_external_alerts",
        "inference_limit": "same_event_in_sample_not_generalization_evidence",
    }
    if quick_sensitivity != expected_sensitivity:
        errors.append("quick local threshold sensitivity changed")
    _, quick_sensitivity_rows = read_csv(
        quick_root / "proxy_threshold_sensitivity.csv"
    )
    if len(quick_sensitivity_rows) != 27:
        errors.append("quick threshold sensitivity must contain 27 local rules")
    elif (
        len(
            {
                (
                    row.get("velocity_threshold_fraction"),
                    row.get("temperature_threshold_fraction"),
                    row.get("pollutant_threshold_fraction"),
                )
                for row in quick_sensitivity_rows
            }
        )
        != 27
        or any(
            row.get("weak_label_false_positive_hours") != "0"
            for row in quick_sensitivity_rows
        )
        or Counter(
            row.get("weak_label_true_positive_hours")
            for row in quick_sensitivity_rows
        )
        != Counter({"6": 12, "7": 15})
        or {
            row.get("first_a07_detection_delay_hours")
            for row in quick_sensitivity_rows
        }
        != {"3.000", "4.000"}
    ):
        errors.append("quick threshold sensitivity grid metrics changed")
    quick_signal = quick_verdict.get("minimum_viable_signal") or {}
    expected_signal = {
        "candidate_id": "PUB-A07",
        "weak_metadata_trigger_first_observed_lag_minutes": "20.333",
        "physical_rule_measurement_delay_hours": "4.000",
        "numeric_publication_offset_from_row_start_minutes": "62.333",
        "numeric_visibility_bound_status": "upper_bound_only_earlier_slot_incomplete",
        "timing_summary_path": "../wave1_point_day_summary.csv",
        "timing_summary_sha256": "7947c89235725aedf0ba64a93fee5aec9cc988677414daa04b999c48cd400c55",
        "composed_physical_confirmation_lag_minutes": "302.333",
        "reference_event_duration_minutes": 720,
        "reference_event_time_remaining_after_confirmation_minutes": "417.667",
        "composition_status": "cross_event_composition_not_observed_end_to_end",
        "source_signal_status": "technical_poc_only",
        "market_edge_status": "not_established_public_source_and_economic_mapping_absent",
    }
    if any(quick_signal.get(field) != value for field, value in expected_signal.items()):
        errors.append("quick minimum viable signal timing changed")
    quick_timing_source = (
        quick_root / quick_signal.get("timing_summary_path", "")
    ).resolve()
    if not quick_timing_source.is_file() or sha256(quick_timing_source) != quick_signal.get(
        "timing_summary_sha256"
    ):
        errors.append("quick minimum viable signal timing source hash mismatch")
    _, quick_signal_rows = read_csv(quick_root / "minimum_viable_signal_card.csv")
    if len(quick_signal_rows) != 1:
        errors.append("quick feasibility must contain one minimum viable signal card")
    else:
        csv_expected_signal = {
            field: str(value) for field, value in expected_signal.items()
        }
        if any(
            quick_signal_rows[0].get(field) != value
            for field, value in csv_expected_signal.items()
        ):
            errors.append("quick minimum viable signal card changed")
    _, quick_events = read_csv(quick_root / "event_registry.csv")
    if len(quick_events) != 2:
        errors.append("quick feasibility must retain two sanitized event metadata rows")
    if any(row.get("weak_label_only") != "1" for row in quick_events):
        errors.append("quick events must remain weak labels")
    _, quick_hours = read_csv(quick_root / "hourly_proxy_diagnostics.csv")
    if len(quick_hours) != 672:
        errors.append("quick hourly diagnostics must contain 672 numeric point-hours")
    _, quick_points = read_csv(quick_root / "point_proxy_evaluation.csv")
    if len(quick_points) != 5:
        errors.append("quick proxy evaluation must cover five fixed points")
    quick_totals = quick_verdict.get("totals") or {}
    expected_quick_totals = {
        "numeric_measurement_rows": 672,
        "proxy_alert_hours": 6,
        "weak_stop_label_hours": 12,
        "weak_label_true_positive_hours": 6,
        "weak_label_false_positive_hours": 0,
        "weak_label_false_negative_hours": 6,
    }
    if quick_totals != expected_quick_totals:
        errors.append("quick-feasibility totals changed")
    event_diagnostics = [
        row
        for row in quick_points
        if row.get("diagnostic_disposition") == "one_event_separable_diagnostic_only"
    ]
    if len(event_diagnostics) != 1:
        errors.append("quick feasibility must contain exactly one separable-event diagnostic")
    else:
        row = event_diagnostics[0]
        expected_values = {
            "candidate_id": "PUB-A07",
            "weak_label_precision": "1.000000",
            "weak_label_recall": "0.500000",
            "first_detection_delay_hours": "4.000",
            "physical_low_rank_auc": "0.735844",
            "numeric_status_text_conflict_hours": "12",
        }
        if any(row.get(field) != value for field, value in expected_values.items()):
            errors.append("quick A07 diagnostic metrics changed")
    _, quick_followup_rows = read_csv(quick_root / "followup_event_check.csv")
    if len(quick_followup_rows) != 1:
        errors.append("quick follow-up must contain one saved event-start check")
    else:
        row = quick_followup_rows[0]
        if (
            row.get("candidate_id") != "PUB-A07"
            or row.get("proxy_alert") != "0"
            or row.get("interpretation")
            != "second_weak_event_start_hour_not_alerted_transition_only"
            or row.get("weak_label_only") != "1"
            or row.get("confirmed_public_prestart_visibility") != "0"
        ):
            errors.append("unexpected quick follow-up row")

    if all(row.get("current_stage") != "pilot_baseline_only" for row in candidates):
        warnings.append("no pilot mechanisms are active")
    warnings.append("PUB1/PUB2 gates are not yet adjudicated; seven-day test is incomplete")
    summary.update(
        {
            "vintage_id": vintage.get("vintage_id"),
            "status": vintage.get("status"),
            "closed_registry_count": len(coverage_rows),
            "candidate_mechanism_count": len(candidates),
            "discovery_hit_count": total_hits,
            "pilot_point_count": len(pilot_points),
            "pilot_mechanism_count": len(
                {row.get("candidate_id", "") for row in pilot_points}
            ),
            "registered_poll_count": len(poll_registry),
            "completed_wave1_slot_count": len(completed_schedule),
            "missed_wave1_slot_count": sum(
                row.get("status") == "missed" for row in wave_schedule
            ),
            "historical_current_view_run_count": len(history_registry),
            "observed_calendar_day_count": len(
                {row.get("measurement_date", "") for row in poll_registry}
            ),
            "discovery_sample_row_count": len(sample_rows),
            "discovery_specific_name_count": review_counts.get(
                "mechanism_specific_name_evidence", 0
            ),
            "s2_pass_count": 0,
            "s4_pass_count": 0,
            "quick_proxy_verdict": quick_verdict.get("technical_proxy_verdict"),
            "quick_proxy_alert_hours": quick_totals.get("proxy_alert_hours", 0),
            "pre_adjudication_status": pre_adjudication.get("status"),
            "provisional_pubx_count": pre_adjudication.get("provisional_pubx_count"),
            "pub2_count": 0,
        }
    )
    return errors, warnings, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "public_only_v1",
    )
    args = parser.parse_args()
    try:
        errors, warnings, summary = validate(args.root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    for warning in warnings:
        print("WARNING: {}".format(warning), file=sys.stderr)
    for error in errors:
        print("ERROR: {}".format(error), file=sys.stderr)
    if errors:
        return 1
    print(
        "STRUCTURE PASS: public-only v1 controls agree; no PUB1/PUB2 awarded",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
