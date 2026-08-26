#!/usr/bin/env python3
"""Apply the frozen public-name S1 review to the deterministic hit sample.

The decisions use only text already present in the public catalog.  They test
name specificity, not actual production, capacity, point topology or tradeability.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_SAMPLE_SHA256 = "0dd0f36b7965b722f711dc518ab867611d93439d6f8212f7ba06c09c78b2cfa9"
SPECIFIC = "mechanism_specific_name_evidence"
AMBIGUOUS = "ambiguous_name_evidence"
FALSE_POSITIVE = "false_positive_name_evidence"

# Ranks refer to discovery_audit_sample.csv at EXPECTED_SAMPLE_SHA256.  Keeping
# the review separate from sampling prevents later regeneration from silently
# changing which text was adjudicated.
DECISIONS = {
    "A01": {AMBIGUOUS: set(range(1, 11))},
    "A02": {AMBIGUOUS: {1}, FALSE_POSITIVE: set(range(2, 11))},
    "A03": {AMBIGUOUS: {7}, FALSE_POSITIVE: {1, 2, 3, 4, 5, 6, 8, 9, 10}},
    "A04": {SPECIFIC: set(range(3, 11)), AMBIGUOUS: {1}, FALSE_POSITIVE: {2}},
    "A05": {SPECIFIC: set(range(1, 11))},
    "A06": {AMBIGUOUS: {1, 2, 4, 5, 8, 9, 10}, FALSE_POSITIVE: {3, 6, 7}},
    "A07": {SPECIFIC: {3, 5, 7, 9, 10}, AMBIGUOUS: {4, 6, 8}, FALSE_POSITIVE: {1, 2}},
    "A08": {AMBIGUOUS: {1}, FALSE_POSITIVE: {2}},
    "A09": {AMBIGUOUS: {1}, FALSE_POSITIVE: set(range(2, 11))},
    "A10": {FALSE_POSITIVE: set(range(1, 11))},
    "A11": {AMBIGUOUS: {6}, FALSE_POSITIVE: {1, 2, 3, 4, 5, 7, 8, 9, 10}},
    "A12": {AMBIGUOUS: {2, 3, 7, 8}, FALSE_POSITIVE: {1, 4, 5, 6, 9, 10}},
    "A13": {SPECIFIC: {2, 4, 5, 7, 8, 10}, AMBIGUOUS: {1, 3, 6, 9}},
}

REASONS = {
    ("A01", AMBIGUOUS): "Glass melting furnace is named, but float-glass process is not established by the sampled public text.",
    ("A02", AMBIGUOUS): "Soda ash is named only at enterprise level; no core-process monitoring point is identified.",
    ("A02", FALSE_POSITIVE): "Generic lime, calcination or carbonation text appears without public soda-ash context.",
    ("A03", AMBIGUOUS): "A roasting furnace is explicit, but the public text does not identify alumina roasting.",
    ("A03", FALSE_POSITIVE): "Roasting-furnace substring occurs in carbon, steel or other non-alumina context.",
    ("A04", SPECIFIC): "The point explicitly names a sinter, pellet or blast-furnace/cast-house device in the ironmaking chain.",
    ("A04", AMBIGUOUS): "Pellet is named at enterprise level without a specific monitoring point.",
    ("A04", FALSE_POSITIVE): "Sintered shale brick is unrelated to ironmaking sinter.",
    ("A05", SPECIFIC): "The public point explicitly names a coke oven or coke-making operation such as charging, pushing or dry quenching.",
    ("A06", AMBIGUOUS): "Upstream steelmaking equipment is named, but no rebar or bar rolling line is identified.",
    ("A06", FALSE_POSITIVE): "Electric-furnace text is in foundry or machinery context and does not identify a rebar line.",
    ("A07", SPECIFIC): "The point explicitly names PVC workshop monitoring in the sampled public text.",
    ("A07", AMBIGUOUS): "Polymerization is named at a chlor-alkali enterprise, but PVC/main-line identity is not explicit in the sampled row.",
    ("A07", FALSE_POSITIVE): "Polymerization or hydrogen-chloride substring is in a non-PVC public context.",
    ("A08", AMBIGUOUS): "Chlor-alkali is named only at enterprise level; no electrolysis or caustic-soda core point is identified.",
    ("A08", FALSE_POSITIVE): "Evaporation text belongs to a cellulose process, not a chlor-alkali core process.",
    ("A09", AMBIGUOUS): "Sulfur recovery is compatible with several chemical processes; the row does not name ammonia or urea.",
    ("A09", FALSE_POSITIVE): "Reformer or sulfur-recovery text is explicitly in refining, hydrogen or acetate context, not ammonia/urea.",
    ("A10", FALSE_POSITIVE): "Fiber or fiberboard substring is unrelated to corn-starch fiber/product processing.",
    ("A11", AMBIGUOUS): "A generic drying furnace is named with no public soybean-crushing context.",
    ("A11", FALSE_POSITIVE): "Drying text is explicitly in automotive, coating, chemical, battery or other non-soy context.",
    ("A12", AMBIGUOUS): "Reduction or rotary furnace is named, but secondary-lead/feedstock identity is absent.",
    ("A12", FALSE_POSITIVE): "Furnace text is explicitly in aluminum, nut activation or other non-secondary-lead context.",
    ("A13", SPECIFIC): "The point explicitly names a hot-rolling line or furnace.",
    ("A13", AMBIGUOUS): "A converter is upstream steelmaking equipment and does not identify hot-rolled coil production.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_csv", type=Path)
    parser.add_argument("labels_csv", type=Path)
    parser.add_argument("summary_csv", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    sample_hash = sha256(args.sample_csv)
    if sample_hash != EXPECTED_SAMPLE_SHA256:
        raise SystemExit("sample hash changed; freeze and review a new decision map")
    with args.sample_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    labels = []
    for row in rows:
        candidate = row["candidate_id"]
        rank = int(row["sample_rank_within_candidate"])
        matches = [status for status, ranks in DECISIONS[candidate].items() if rank in ranks]
        if len(matches) != 1:
            raise SystemExit(f"{candidate} rank {rank}: expected exactly one decision")
        status = matches[0]
        labels.append(
            {
                "public_study_id": row["public_study_id"],
                "candidate_id": candidate,
                "sample_rank_within_candidate": rank,
                "selection_hash": row["selection_hash"],
                "enterprise_public_id": row["enterprise_public_id"],
                "port_id": row["port_id"],
                "review_status": status,
                "s1_sample_result": "pass_name_specificity" if status == SPECIFIC else "blocked",
                "review_reason": REASONS[(candidate, status)],
                "scope_limit": "public_name_only_no_production_capacity_or_topology_inference",
            }
        )

    summaries = []
    for candidate in sorted(DECISIONS, key=lambda value: int(value[1:])):
        candidate_labels = [row for row in labels if row["candidate_id"] == candidate]
        counts = Counter(row["review_status"] for row in candidate_labels)
        summaries.append(
            {
                "public_study_id": "PUB-{}".format(candidate),
                "candidate_id": candidate,
                "sample_row_count": len(candidate_labels),
                "mechanism_specific_name_count": counts[SPECIFIC],
                "ambiguous_name_count": counts[AMBIGUOUS],
                "false_positive_name_count": counts[FALSE_POSITIVE],
                "s1_sample_disposition": (
                    "specific_rows_exist_but_not_universe_adjudication"
                    if counts[SPECIFIC]
                    else "no_specific_row_in_sample"
                ),
                "inference_limit": "deterministic_sample_distribution_not_full-universe_rate",
            }
        )

    write_csv(args.labels_csv, labels)
    write_csv(args.summary_csv, summaries)
    manifest_path = args.manifest or args.labels_csv.with_name(
        args.labels_csv.stem + "_manifest.json"
    )
    manifest = {
        "schema_version": "public-discovery-name-review-v1",
        "sample_path": str(args.sample_csv),
        "sample_sha256": sample_hash,
        "sample_row_count": len(rows),
        "labels_path": str(args.labels_csv),
        "labels_sha256": sha256(args.labels_csv),
        "summary_path": str(args.summary_csv),
        "summary_sha256": sha256(args.summary_csv),
        "review_basis": "public catalog text only",
        "counts": dict(Counter(row["review_status"] for row in labels)),
        "s1_full_universe_pass_count": 0,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
