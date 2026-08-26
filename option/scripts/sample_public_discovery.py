#!/usr/bin/env python3
"""Freeze a deterministic, review-ready sample of public discovery hits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SCOPE_ENTERPRISE = "enterprise_or_industry_name"
SCOPE_POINT = "monitoring_point_or_process_field"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_key(row: dict[str, str]) -> str:
    material = "\x1f".join(
        row.get(field, "")
        for field in (
            "candidate_id",
            "hit_scope",
            "enterprise_public_id",
            "port_id",
            "matched_terms",
            "matched_fields",
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--enterprise-reserve", type=int, default=2)
    args = parser.parse_args()
    if args.sample_size < 1 or args.enterprise_reserve < 0:
        raise SystemExit("sample-size must be positive and enterprise-reserve nonnegative")

    with args.source_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    grouped: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in source_rows:
        row = dict(row)
        row["selection_hash"] = stable_key(row)
        grouped[row["candidate_id"]][row["hit_scope"]].append(row)
    for scopes in grouped.values():
        for rows in scopes.values():
            rows.sort(key=lambda row: row["selection_hash"])

    selected: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    for candidate_id in sorted(grouped, key=lambda value: int(value[1:])):
        enterprise = grouped[candidate_id].get(SCOPE_ENTERPRISE, [])
        points = grouped[candidate_id].get(SCOPE_POINT, [])
        take_enterprise = min(args.enterprise_reserve, len(enterprise), args.sample_size)
        take_points = min(len(points), args.sample_size - take_enterprise)
        remaining = args.sample_size - take_enterprise - take_points
        if remaining:
            take_enterprise += min(remaining, len(enterprise) - take_enterprise)
        chosen = enterprise[:take_enterprise] + points[:take_points]
        chosen.sort(key=lambda row: (row["hit_scope"], row["selection_hash"]))
        for rank, row in enumerate(chosen, start=1):
            selected.append(
                {
                    "public_study_id": "PUB-{}".format(candidate_id),
                    **row,
                    "sample_rank_within_candidate": rank,
                    "review_status": "unreviewed",
                    "review_reason": "",
                    "review_rule": (
                        "Confirm whether the public name identifies the frozen mechanism; "
                        "ambiguous boiler, generic process and unrelated substring hits fail S1."
                    ),
                }
            )
        counts[candidate_id] = {
            "source_rows": len(enterprise) + len(points),
            "sample_rows": len(chosen),
            "enterprise_sample_rows": take_enterprise,
            "point_sample_rows": take_points,
        }

    fields = list(selected[0]) if selected else []
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    manifest_path = args.manifest or args.output_csv.with_name(
        args.output_csv.stem + "_manifest.json"
    )
    manifest = {
        "schema_version": "public-discovery-audit-sample-v1",
        "source_path": str(args.source_csv),
        "source_sha256": sha256(args.source_csv),
        "source_row_count": len(source_rows),
        "output_path": str(args.output_csv),
        "output_sha256": sha256(args.output_csv),
        "sample_row_count": len(selected),
        "selection_method": (
            "Per candidate reserve up to 2 enterprise-name rows, fill to 10 with "
            "point/process rows, then backfill enterprise rows; lowest SHA-256 stable keys."
        ),
        "review_status": "unreviewed",
        "candidate_counts": counts,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
