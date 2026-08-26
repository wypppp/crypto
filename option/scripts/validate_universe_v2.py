#!/usr/bin/env python3
"""Validate the active Round 0 v2 universe worktables.

This validator checks structural invariants only.  A passing result does not
turn discovery rows into a frozen universe or grant W0/W1 status.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple


EXPECTED_UNIVERSES = {
    "U-MKT-v2": "u_mkt_v2.csv",
    "U-ECON-v2": "u_econ_v2.csv",
    "U-OBS-v2": "u_obs_v2.csv",
    "U-PROC-v2": "u_proc_v2.csv",
}

EXPECTED_VENUES = {
    "SHFE",
    "INE",
    "DCE",
    "CZCE",
    "GFEX",
    "SGX",
    "CME Group",
    "ICE",
    "LME",
}

SCHEMAS = {
    "venue_coverage_v2.csv": {
        "universe_id",
        "vintage_cutoff",
        "venue",
        "scope",
        "official_catalog_url",
        "catalog_evidence_as_of",
        "accessed_at",
        "raw_snapshot_hash",
        "discovered_product_families",
        "coverage_status",
        "remaining_gap",
    },
    "u_mkt_v2.csv": {
        "universe_id",
        "vintage_cutoff",
        "venue",
        "product_family",
        "underlying",
        "product_code",
        "instrument_type",
        "listing_status_at_cutoff",
        "first_listed_at",
        "official_catalog_url",
        "accessed_at",
        "snapshot_hash",
        "member_status",
        "w0_status",
        "notes",
    },
    "exclusions_v2.csv": {
        "universe_id",
        "vintage_cutoff",
        "entity_type",
        "venue_or_source",
        "entity_name",
        "product_code",
        "decision",
        "effective_at_cutoff",
        "reason",
        "evidence_url",
        "accessed_at",
        "snapshot_hash",
        "reopen_condition",
    },
}

ALLOWED_COVERAGE = {
    "pending_enumeration",
    "partial_members_enumerated",
    "complete_members_enumerated",
    "frozen",
}

ALLOWED_MEMBER_STATUS = {
    "discovered_member_unfrozen",
    "frozen_member",
}

ALLOWED_LISTING_STATUS = {
    "listed",
    "listed_product_no_current_contract_check",
    "current_catalog_member_cutoff_not_proven",
}

# These venues have an official disclosure whose own as-of date predates the
# cutoff, so individual first-listing dates are not required to prove that a
# product family was already in the catalog at the cutoff.
AS_OF_CATALOG_PROOF_VENUES = {"DCE", "CZCE"}


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def duplicate_values(rows: Sequence[Dict[str, str]], fields: Sequence[str]) -> List[str]:
    values = [tuple(row.get(field, "").strip() for field in fields) for row in rows]
    counts = Counter(values)
    return [" / ".join(value) for value, count in counts.items() if count > 1]


def validate_date_not_after_cutoff(
    value: str, cutoff: datetime, label: str, errors: List[str]
) -> None:
    if value in {"", "unknown"}:
        return
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        errors.append("{} is not an ISO date: {!r}".format(label, value))
        return
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=cutoff.tzinfo)
    if parsed > cutoff:
        errors.append("{}={} is after vintage cutoff".format(label, value))


def validate(root: Path) -> Tuple[List[str], List[str], Dict[str, object]]:
    errors: List[str] = []
    warnings: List[str] = []
    summary: Dict[str, object] = {}

    vintage_path = root / "vintage.json"
    try:
        with vintage_path.open("r", encoding="utf-8") as handle:
            vintage = json.load(handle)
    except (OSError, ValueError) as exc:
        return ["cannot read vintage.json: {}".format(exc)], warnings, summary

    cutoff_text = vintage.get("cutoff", "")
    try:
        cutoff = datetime.fromisoformat(cutoff_text)
    except (TypeError, ValueError):
        return ["vintage.json cutoff is not a valid ISO timestamp"], warnings, summary
    if cutoff.tzinfo is None:
        errors.append("vintage.json cutoff must include a timezone offset")

    if vintage.get("vintage_id") != "v2@{}".format(cutoff_text):
        errors.append("vintage_id does not match cutoff")
    if set(vintage.get("universes", [])) != set(EXPECTED_UNIVERSES):
        errors.append("vintage.json universes do not match the four expected v2 IDs")

    tables: Dict[str, List[Dict[str, str]]] = {}
    required_files = list(EXPECTED_UNIVERSES.values()) + [
        "venue_coverage_v2.csv",
        "exclusions_v2.csv",
    ]
    for name in required_files:
        path = root / name
        if not path.exists():
            errors.append("missing file: {}".format(name))
            continue
        headers, rows = read_csv(path)
        tables[name] = rows
        if name in SCHEMAS:
            missing = SCHEMAS[name] - set(headers)
            if missing:
                errors.append(
                    "{} missing columns: {}".format(name, ", ".join(sorted(missing)))
                )

    for universe_id, name in EXPECTED_UNIVERSES.items():
        for line_number, row in enumerate(tables.get(name, []), start=2):
            if row.get("universe_id") != universe_id:
                errors.append(
                    "{} line {} has universe_id={!r}".format(
                        name, line_number, row.get("universe_id")
                    )
                )
            if row.get("vintage_cutoff") != cutoff_text:
                errors.append("{} line {} has a different cutoff".format(name, line_number))

    coverage_rows = tables.get("venue_coverage_v2.csv", [])
    mkt_rows = tables.get("u_mkt_v2.csv", [])
    exclusion_rows = tables.get("exclusions_v2.csv", [])

    coverage_venues = {row.get("venue", "") for row in coverage_rows}
    if coverage_venues != EXPECTED_VENUES:
        errors.append(
            "venue coverage mismatch; missing={}, extra={}".format(
                sorted(EXPECTED_VENUES - coverage_venues),
                sorted(coverage_venues - EXPECTED_VENUES),
            )
        )
    duplicates = duplicate_values(coverage_rows, ["venue"])
    if duplicates:
        errors.append("duplicate venue coverage rows: {}".format(", ".join(duplicates)))

    mkt_counts = Counter(row.get("venue", "") for row in mkt_rows)
    for line_number, row in enumerate(coverage_rows, start=2):
        if row.get("universe_id") != "U-MKT-v2":
            errors.append("venue coverage line {} has wrong universe_id".format(line_number))
        if row.get("vintage_cutoff") != cutoff_text:
            errors.append("venue coverage line {} has a different cutoff".format(line_number))
        try:
            stated_count = int(row.get("discovered_product_families", ""))
        except ValueError:
            errors.append("venue coverage line {} has a non-integer count".format(line_number))
            continue
        actual_count = mkt_counts[row.get("venue", "")]
        if stated_count != actual_count:
            errors.append(
                "{} coverage count is {}, but u_mkt has {}".format(
                    row.get("venue"), stated_count, actual_count
                )
            )
        status = row.get("coverage_status", "")
        if status not in ALLOWED_COVERAGE:
            errors.append("venue coverage line {} has invalid status".format(line_number))
        if status == "pending_enumeration" and stated_count != 0:
            errors.append(
                "{} is pending enumeration but has a nonzero member count".format(
                    row.get("venue")
                )
            )
        if status != "frozen":
            warnings.append(
                "{} coverage remains {}: {}".format(
                    row.get("venue"), status, row.get("remaining_gap", "")
                )
            )

    duplicates = duplicate_values(mkt_rows, ["venue", "product_family"])
    if duplicates:
        errors.append("duplicate U-MKT members: {}".format(", ".join(duplicates)))
    for line_number, row in enumerate(mkt_rows, start=2):
        if row.get("venue") not in EXPECTED_VENUES:
            errors.append("u_mkt line {} has an unknown venue".format(line_number))
        if row.get("instrument_type") != "options":
            errors.append("u_mkt line {} is not an options row".format(line_number))
        if row.get("member_status") not in ALLOWED_MEMBER_STATUS:
            errors.append("u_mkt line {} has invalid member_status".format(line_number))
        if row.get("member_status") == "frozen_member" and row.get("w0_status") != "W0":
            errors.append("u_mkt line {} freezes a member without W0".format(line_number))
        listing_status = row.get("listing_status_at_cutoff", "")
        if listing_status not in ALLOWED_LISTING_STATUS:
            errors.append("u_mkt line {} has invalid listing status".format(line_number))
        if (
            listing_status == "listed"
            and row.get("first_listed_at") == "unknown"
            and row.get("venue") not in AS_OF_CATALOG_PROOF_VENUES
        ):
            errors.append(
                "u_mkt line {} claims cutoff listing without a listing date or "
                "pre-cutoff as-of catalog".format(line_number)
            )
        if listing_status == "current_catalog_member_cutoff_not_proven":
            if row.get("member_status") != "discovered_member_unfrozen":
                errors.append(
                    "u_mkt line {} has unproven cutoff status but is frozen".format(
                        line_number
                    )
                )
            if row.get("w0_status") == "W0":
                errors.append(
                    "u_mkt line {} grants W0 before cutoff membership is proven".format(
                        line_number
                    )
                )
        validate_date_not_after_cutoff(
            row.get("first_listed_at", ""),
            cutoff,
            "u_mkt line {} first_listed_at".format(line_number),
            errors,
        )

    duplicates = duplicate_values(
        exclusion_rows,
        ["universe_id", "entity_type", "venue_or_source", "entity_name"],
    )
    if duplicates:
        errors.append("duplicate exclusions: {}".format(", ".join(duplicates)))
    for line_number, row in enumerate(exclusion_rows, start=2):
        if row.get("universe_id") != "U-MKT-v2":
            errors.append("exclusions line {} has wrong universe_id".format(line_number))
        if row.get("vintage_cutoff") != cutoff_text:
            errors.append("exclusions line {} has a different cutoff".format(line_number))
        if row.get("effective_at_cutoff") not in {"0", "1"}:
            errors.append(
                "exclusions line {} effective_at_cutoff must be 0 or 1".format(
                    line_number
                )
            )

    empty_universes = [
        universe_id
        for universe_id, name in EXPECTED_UNIVERSES.items()
        if not tables.get(name, [])
    ]
    for universe_id in empty_universes:
        warnings.append("{} has no member rows yet".format(universe_id))

    frozen_venues = sum(row.get("coverage_status") == "frozen" for row in coverage_rows)
    listing_status_counts = Counter(
        row.get("listing_status_at_cutoff", "") for row in mkt_rows
    )
    summary.update(
        {
            "vintage_id": vintage.get("vintage_id"),
            "status": vintage.get("status"),
            "venue_count": len(coverage_rows),
            "frozen_venue_count": frozen_venues,
            "u_mkt_member_count": len(mkt_rows),
            "u_mkt_by_venue": dict(sorted(mkt_counts.items())),
            "u_mkt_by_listing_status": dict(sorted(listing_status_counts.items())),
            "exclusion_count": len(exclusion_rows),
            "empty_universes": empty_universes,
        }
    )
    if vintage.get("status") == "frozen" and (warnings or errors):
        errors.append("vintage cannot be frozen while validation gaps remain")
    return errors, warnings, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "universe_v2",
        help="directory containing the v2 worktables",
    )
    args = parser.parse_args()
    errors, warnings, summary = validate(args.root)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    for warning in warnings:
        print("WARNING: {}".format(warning), file=sys.stderr)
    for error in errors:
        print("ERROR: {}".format(error), file=sys.stderr)
    if errors:
        return 1
    print(
        "STRUCTURE PASS: {} warning(s); universe is not frozen".format(len(warnings)),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
