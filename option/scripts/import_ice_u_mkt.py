#!/usr/bin/env python3
"""Import ICE commodity-option discovery rows from the saved official CSV.

The snapshot was captured after the v2 cutoff.  Therefore this script records
catalog discovery but deliberately does not claim that an unknown listing date
pre-dates the cutoff.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


VINTAGE_CUTOFF = "2026-08-24T17:05:00+08:00"
ACCESSED_AT = "2026-08-24T17:35:14+08:00"
SNAPSHOT_SHA256 = "6c7d524728087c9bc8cb82230688ebfe741c5c6090632bc5f80962294130d0ef"

# ICE product-guide groups that directly represent physical commodities,
# commodity transport, energy or environmental commodity instruments.
COMMODITY_GROUPS = {
    "Biofuels",
    "Canola",
    "Coal",
    "Cocoa",
    "Coffee",
    "Cotton",
    "Crude Oil and Refined Products",
    "Electricity",
    "Emissions",
    "Frozen Orange Juice",
    "Grains",
    "Liquified Natural Gas",
    "Natural Gas",
    "Natural Gas Liquids",
    "Physical Environmental",
    "Sugar",
    "Wet Freight",
}

PRODUCT_LINK = re.compile(r'^=HYPERLINK\("([^"]+)","([^"]+)"\)$')
OPTION_NAME = re.compile(r"\bOptions?\b", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_ice(path: Path) -> Tuple[List[Dict[str, str]], Counter[str]]:
    if sha256(path) != SNAPSHOT_SHA256:
        raise ValueError("ICE source hash does not match the frozen v2 snapshot")

    rows: List[Dict[str, str]] = []
    groups: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for source in reader:
            match = PRODUCT_LINK.fullmatch(
                source.get("PRODUCT (Click to open in Browser)", "")
            )
            if not match or source.get("GROUP") not in COMMODITY_GROUPS:
                continue
            official_url, name = match.groups()
            if not OPTION_NAME.search(name):
                continue
            group = source["GROUP"]
            groups[group] += 1
            product_code = (
                source.get("SYMBOL CODE")
                or source.get("PHYSICAL")
                or source.get("LOGICAL")
                or "unknown"
            )
            notes = (
                "ICE product_id={}; group={}; MIC={}; clearing_venue={}; "
                "official catalog captured 30m14s after cutoff, so cutoff listing "
                "status remains unproven"
            ).format(
                source.get("PRODUCT ID", ""),
                group,
                source.get("MIC CODE", ""),
                source.get("CLEARING VENUE", ""),
            )
            rows.append(
                {
                    "universe_id": "U-MKT-v2",
                    "vintage_cutoff": VINTAGE_CUTOFF,
                    "venue": "ICE",
                    "product_family": name,
                    "underlying": "unknown; official ICE group={}".format(group),
                    "product_code": product_code,
                    "instrument_type": "options",
                    "listing_status_at_cutoff": "current_catalog_member_cutoff_not_proven",
                    "first_listed_at": "unknown",
                    "official_catalog_url": official_url,
                    "accessed_at": ACCESSED_AT,
                    "snapshot_hash": SNAPSHOT_SHA256,
                    "member_status": "discovered_member_unfrozen",
                    "w0_status": "pending_listing_date_and_universe_freeze",
                    "notes": notes,
                }
            )

    rows.sort(key=lambda row: (row["product_family"].casefold(), row["product_code"]))
    if len(rows) != 281:
        raise ValueError("expected 281 ICE commodity-option products, got {}".format(len(rows)))
    if len({row["product_family"] for row in rows}) != len(rows):
        raise ValueError("ICE product names are not unique")
    return rows, groups


def update_master(master: Path, ice_rows: List[Dict[str, str]], write: bool) -> int:
    with master.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        existing = list(reader)
    if not fieldnames:
        raise ValueError("U-MKT master has no header")

    non_ice = [row for row in existing if row.get("venue") != "ICE"]
    output_rows = non_ice + ice_rows
    keys = [(row["venue"], row["product_family"]) for row in output_rows]
    if len(keys) != len(set(keys)):
        raise ValueError("combined U-MKT member keys are not unique")

    if write:
        with master.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(output_rows)
    print(
        "ICE rows: {}; combined U-MKT rows: {}; mode: {}".format(
            len(ice_rows), len(output_rows), "write" if write else "check"
        )
    )
    return len(output_rows)


def main() -> int:
    option_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=option_root
        / "data"
        / "official_snapshots"
        / "20260824T173514+0800"
        / "ice_product_codes.csv",
    )
    parser.add_argument(
        "--master",
        type=Path,
        default=option_root / "data" / "universe_v2" / "u_mkt_v2.csv",
    )
    parser.add_argument("--write", action="store_true", help="replace existing ICE rows")
    args = parser.parse_args()
    try:
        rows, groups = read_ice(args.source)
        update_master(args.master, rows, args.write)
    except (OSError, ValueError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    print("ICE group counts:")
    for group, count in sorted(groups.items()):
        print("  {}: {}".format(group, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
