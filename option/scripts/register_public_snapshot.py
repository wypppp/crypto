#!/usr/bin/env python3
"""Verify and register one immutable public-only snapshot manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_raw(snapshot: Path, manifest: dict) -> int:
    records = manifest.get("files") or []
    for record in records:
        path = snapshot / record["path"]
        if not path.is_file():
            raise SystemExit("missing raw response: {}".format(path))
        if sha256(path) != record.get("sha256"):
            raise SystemExit("raw response hash mismatch: {}".format(path))
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--role", required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--schedule", type=Path)
    args = parser.parse_args()
    registry = args.registry.resolve()
    snapshot = args.snapshot_dir.resolve()
    root = (args.root or registry.parent).resolve()
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("study_id") != "public-only-v1":
        raise SystemExit("only study_id=public-only-v1 can enter this registry")
    observations = manifest.get("observations") or []
    raw_count = verify_raw(snapshot, manifest)
    if raw_count != len(observations) * 2:
        raise SystemExit("expected two raw responses per point")

    with registry.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    run_id = str(manifest.get("run_id") or snapshot.name)
    if any(row.get("run_id") == run_id for row in rows):
        raise SystemExit("run_id already registered: {}".format(run_id))
    try:
        relative_manifest = manifest_path.relative_to(root)
    except ValueError as exc:
        raise SystemExit("snapshot manifest must be under registry root") from exc
    rows.append(
        {
            "run_id": run_id,
            "measurement_date": manifest.get("measurement_date", ""),
            "study_id": manifest.get("study_id", ""),
            "point_count": len(observations),
            "raw_file_count": raw_count,
            "manifest_path": str(relative_manifest),
            "manifest_sha256": sha256(manifest_path),
            "hash_verified": 1,
            "role": args.role,
        }
    )
    schedule_fields = []
    schedule_rows = []
    if args.schedule:
        with args.schedule.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            schedule_fields = list(reader.fieldnames or [])
            schedule_rows = list(reader)
        matching_slots = [row for row in schedule_rows if row.get("planned_run_id") == run_id]
        if len(matching_slots) != 1:
            raise SystemExit("expected one planned schedule slot for {}".format(run_id))
        slot = matching_slots[0]
        if slot.get("status") != "pending":
            raise SystemExit("planned schedule slot is not pending")
        slot["status"] = "completed"
        slot["actual_run_id"] = run_id
    temporary = registry.with_name(".{}.{}.tmp".format(registry.name, os.getpid()))
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, registry)
    if args.schedule:
        schedule_temporary = args.schedule.with_name(
            ".{}.{}.tmp".format(args.schedule.name, os.getpid())
        )
        with schedule_temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=schedule_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(schedule_rows)
        os.replace(schedule_temporary, args.schedule)
    print("registered {} {}".format(run_id, sha256(manifest_path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
